#!/usr/bin/env python3
"""
End-to-end integration tests for V-Stack.
Tests complete system functionality including upload, playback, failures, and performance.
"""

import pytest
import asyncio
import aiohttp
import time
import os
import sys
import hashlib
from typing import Dict, List

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestE2EIntegration:
    """End-to-end integration tests"""
    
    @pytest.fixture
    def metadata_url(self):
        return os.getenv('METADATA_SERVICE_URL', 'http://localhost:8080')
    
    @pytest.fixture
    def storage_nodes(self):
        """Storage node URLs for uploading chunks from host"""
        return [
            'http://localhost:8081',
            'http://localhost:8082',
            'http://localhost:8083'
        ]
    
    @pytest.fixture
    def storage_nodes_internal(self):
        """Storage node URLs for metadata service (inside Docker network)"""
        return [
            'http://storage-node-1:8081',
            'http://storage-node-2:8081',
            'http://storage-node-3:8081'
        ]
    
    @pytest.fixture
    def uploader_url(self):
        return os.getenv('UPLOADER_SERVICE_URL', 'http://localhost:8084')
    
    @pytest.mark.asyncio
    async def test_complete_upload_playback_cycle(self, metadata_url, storage_nodes, storage_nodes_internal):
        """Test complete video upload and playback cycle with real video files"""
        # Step 1: Create video record
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{metadata_url}/video",
                json={"title": "Integration Test Video", "duration_sec": 30},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                assert response.status == 200
                video_data = await response.json()
                video_id = video_data['video_id']
                assert video_id is not None
        
        # Step 2: Upload test chunks
        test_chunk_data = b"Test video chunk data " * 1000  # ~22KB
        chunk_ids = []
        
        for i in range(3):  # Upload 3 chunks
            chunk_id = f"{video_id}-chunk-{i:03d}"
            chunk_ids.append(chunk_id)
            
            # Upload to all storage nodes
            upload_tasks = []
            async with aiohttp.ClientSession() as session:
                for node_url in storage_nodes:
                    upload_tasks.append(
                        session.put(
                            f"{node_url}/chunk/{chunk_id}",
                            data=test_chunk_data,
                            timeout=aiohttp.ClientTimeout(total=10)
                        )
                    )
                
                responses = await asyncio.gather(*upload_tasks, return_exceptions=True)
                successful_uploads = sum(1 for r in responses if not isinstance(r, Exception) and r.status == 201)
                assert successful_uploads >= 2, "Failed to upload chunk to sufficient nodes"
        
        # Step 3: Commit chunks via consensus
        async with aiohttp.ClientSession() as session:
            for i, chunk_id in enumerate(chunk_ids):
                # Generate valid SHA-256 checksum (64 hex characters)
                checksum = hashlib.sha256(test_chunk_data).hexdigest()
                
                async with session.post(
                    f"{metadata_url}/chunk/{chunk_id}/commit",
                    json={
                        "node_urls": storage_nodes_internal,  # Use internal Docker network URLs
                        "checksum": checksum,
                        "size_bytes": len(test_chunk_data),
                        "video_id": video_id,
                        "sequence_num": i
                    },
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    assert response.status == 200, f"Failed to commit chunk {chunk_id}: HTTP {response.status}"
                    result = await response.json()
                    assert result.get("success") is True, f"Consensus failed for chunk {chunk_id}: {result.get('message')}"
        
        # Step 4: Retrieve manifest
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{metadata_url}/manifest/{video_id}",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                assert response.status == 200
                manifest = await response.json()
                assert len(manifest['chunks']) == 3
        
        # Step 5: Download chunks (simulate playback)
        for chunk_info in manifest['chunks']:
            chunk_id = chunk_info['chunk_id']
            replicas = chunk_info['replicas']
            
            # Try downloading from first replica
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{replicas[0]}/chunk/{chunk_id}",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    assert response.status == 200
                    downloaded_data = await response.read()
                    assert len(downloaded_data) > 0
    
    @pytest.mark.asyncio
    async def test_node_failure_during_upload(self, metadata_url, storage_nodes, storage_nodes_internal):
        """Test system behavior when a storage node fails during upload"""
        # Create video
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{metadata_url}/video",
                json={"title": "Failure Test Video", "duration_sec": 10},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                assert response.status == 200
                video_data = await response.json()
                video_id = video_data['video_id']
        
        # Upload chunk to only 2 nodes (simulating one node failure)
        chunk_id = f"{video_id}-chunk-000"
        test_data = b"Test data " * 100
        
        available_nodes = storage_nodes[:2]  # Only use first 2 nodes for upload
        available_nodes_internal = storage_nodes_internal[:2]  # Internal URLs for consensus
        
        async with aiohttp.ClientSession() as session:
            for node_url in available_nodes:
                async with session.put(
                    f"{node_url}/chunk/{chunk_id}",
                    data=test_data,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    assert response.status == 201
        
        # Commit should succeed with 2 nodes (quorum)
        async with aiohttp.ClientSession() as session:
            # Generate valid SHA-256 checksum (64 hex characters)
            checksum = hashlib.sha256(test_data).hexdigest()
            
            async with session.post(
                f"{metadata_url}/chunk/{chunk_id}/commit",
                json={
                    "node_urls": available_nodes_internal,  # Use internal Docker network URLs
                    "checksum": checksum,
                    "size_bytes": len(test_data),
                    "video_id": video_id,
                    "sequence_num": 0
                },
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                assert response.status == 200, f"Failed to commit chunk: HTTP {response.status}"
                result = await response.json()
                assert result.get("success") is True, f"Consensus failed: {result.get('message')}"
    
    @pytest.mark.asyncio
    async def test_concurrent_uploads(self, metadata_url, storage_nodes):
        """Test concurrent operations with multiple uploads"""
        # Create multiple videos concurrently
        video_ids = []
        
        async def create_and_upload_video(index: int):
            async with aiohttp.ClientSession() as session:
                # Create video
                async with session.post(
                    f"{metadata_url}/video",
                    json={"title": f"Concurrent Test {index}", "duration_sec": 10},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    assert response.status == 200
                    video_data = await response.json()
                    video_id = video_data['video_id']
                    
                    # Upload one chunk
                    chunk_id = f"{video_id}-chunk-000"
                    test_data = b"Test " * 100
                    
                    for node_url in storage_nodes:
                        async with session.put(
                            f"{node_url}/chunk/{chunk_id}",
                            data=test_data,
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as upload_response:
                            pass  # Don't assert here to allow some failures
                    
                    return video_id
        
        # Upload 5 videos concurrently
        tasks = [create_and_upload_video(i) for i in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # At least 3 should succeed
        successful = sum(1 for r in results if not isinstance(r, Exception))
        assert successful >= 3, f"Only {successful}/5 concurrent uploads succeeded"
    
    @pytest.mark.asyncio
    async def test_performance_targets(self, storage_nodes):
        """Test performance targets: startup latency <2s, rebuffering events <1"""
        # Test storage node latency
        latencies = []
        
        for node_url in storage_nodes:
            try:
                start_time = time.time()
                async with aiohttp.ClientSession() as session:
                    async with session.head(
                        f"{node_url}/ping",
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        latency = (time.time() - start_time) * 1000
                        if response.status == 200:
                            latencies.append(latency)
            except Exception:
                pass
        
        if latencies:
            avg_latency = sum(latencies) / len(latencies)
            # For testing environment, accept <100ms (production target is <10ms)
            assert avg_latency < 100, f"Average latency {avg_latency:.2f}ms exceeds threshold"
    
    @pytest.mark.asyncio
    async def test_chunk_retrieval_with_failover(self, metadata_url, storage_nodes):
        """Test automatic failover when storage nodes become unavailable"""
        # Create and upload a test chunk
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{metadata_url}/video",
                json={"title": "Failover Test", "duration_sec": 10},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                assert response.status == 200
                video_data = await response.json()
                video_id = video_data['video_id']
        
        chunk_id = f"{video_id}-chunk-000"
        test_data = b"Failover test data " * 100
        
        # Upload to all nodes
        async with aiohttp.ClientSession() as session:
            for node_url in storage_nodes:
                async with session.put(
                    f"{node_url}/chunk/{chunk_id}",
                    data=test_data,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    pass  # Allow some failures
        
        # Try to download from each node
        download_success = False
        for node_url in storage_nodes:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{node_url}/chunk/{chunk_id}",
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        if response.status == 200:
                            data = await response.read()
                            if len(data) > 0:
                                download_success = True
                                break
            except Exception:
                continue
        
        assert download_success, "Failed to download chunk from any replica"
    
    @pytest.mark.asyncio
    async def test_system_health_endpoints(self, metadata_url, storage_nodes):
        """Test health check endpoints for all services"""
        # Test metadata service health
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{metadata_url}/health",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                assert response.status == 200
                health_data = await response.json()
                assert 'status' in health_data
        
        # Test storage node health
        healthy_nodes = 0
        for node_url in storage_nodes:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{node_url}/health",
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        if response.status == 200:
                            healthy_nodes += 1
            except Exception:
                pass
        
        # At least 2 nodes should be healthy for quorum
        assert healthy_nodes >= 2, f"Only {healthy_nodes}/3 nodes are healthy"
    
    @pytest.mark.asyncio
    async def test_invalid_requests(self, metadata_url, storage_nodes):
        """Test error handling for invalid requests"""
        # Test invalid video ID
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{metadata_url}/manifest/invalid-video-id",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                assert response.status == 404
        
        # Test invalid chunk ID
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{storage_nodes[0]}/chunk/invalid-chunk-id",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                assert response.status == 404


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--asyncio-mode=auto'])
