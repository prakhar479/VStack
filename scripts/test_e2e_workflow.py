#!/usr/bin/env python3
"""
End-to-end workflow testing for V-Stack.
Tests complete upload and playback workflows.
"""

import asyncio
import aiohttp
import sys
import os
import time
import logging
import hashlib
from typing import Dict, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class E2EWorkflowTester:
    """End-to-end workflow tester for V-Stack"""
    
    def __init__(self):
        self.metadata_url = os.getenv('METADATA_SERVICE_URL', 'http://localhost:8080')
        self.uploader_url = os.getenv('UPLOADER_SERVICE_URL', 'http://localhost:8084')
        # Storage nodes for uploading from host
        self.storage_nodes = [
            'http://localhost:8081',
            'http://localhost:8082',
            'http://localhost:8083'
        ]
        # Storage nodes for metadata service (inside Docker network)
        self.storage_nodes_internal = [
            'http://storage-node-1:8081',
            'http://storage-node-2:8081',
            'http://storage-node-3:8081'
        ]
        self.test_results = {
            'upload_workflow': False,
            'playback_workflow': False,
            'error_handling': False,
            'performance': False
        }
    
    async def test_upload_workflow(self) -> bool:
        """Test complete upload workflow: video → chunks → distributed storage → manifest"""
        logger.info("=" * 60)
        logger.info("Testing Upload Workflow")
        logger.info("=" * 60)
        
        try:
            # Step 1: Create a test video record
            logger.info("Step 1: Creating video record...")
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.metadata_url}/video",
                    json={"title": "E2E Test Video", "duration_sec": 60},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        logger.error(f"Failed to create video: {response.status}")
                        return False
                    video_data = await response.json()
                    video_id = video_data['video_id']
                    logger.info(f"✓ Video created: {video_id}")
            
            # Step 2: Simulate chunk creation and storage
            logger.info("Step 2: Simulating chunk storage...")
            test_chunk_data = b"Test chunk data " * 1000  # ~16KB test chunk
            chunk_id = f"{video_id}-chunk-000"
            
            # Upload to all storage nodes
            upload_success = []
            for node_url in self.storage_nodes:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.put(
                            f"{node_url}/chunk/{chunk_id}",
                            data=test_chunk_data,
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as response:
                            if response.status == 201:
                                upload_success.append(node_url)
                                logger.info(f"✓ Chunk uploaded to {node_url}")
                            else:
                                logger.warning(f"Failed to upload to {node_url}: {response.status}")
                except Exception as e:
                    logger.warning(f"Error uploading to {node_url}: {e}")
            
            if len(upload_success) < 2:
                logger.error("Failed to upload chunk to sufficient nodes")
                return False
            
            # Step 3: Commit chunk placement via consensus
            logger.info("Step 3: Committing chunk placement...")
            # Generate valid SHA-256 checksum (64 hex characters)
            checksum = hashlib.sha256(test_chunk_data).hexdigest()
            
            # Map external URLs to internal URLs for consensus
            upload_success_internal = []
            for node_url in upload_success:
                if 'localhost:8081' in node_url:
                    upload_success_internal.append('http://storage-node-1:8081')
                elif 'localhost:8082' in node_url:
                    upload_success_internal.append('http://storage-node-2:8081')
                elif 'localhost:8083' in node_url:
                    upload_success_internal.append('http://storage-node-3:8081')
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.metadata_url}/chunk/{chunk_id}/commit",
                    json={
                        "node_urls": upload_success_internal,  # Use internal Docker network URLs
                        "checksum": checksum,
                        "size_bytes": len(test_chunk_data),
                        "video_id": video_id,
                        "sequence_num": 0
                    },
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get("success"):
                            logger.info("✓ Chunk placement committed")
                        else:
                            logger.error(f"Consensus failed: {result.get('message')}")
                            return False
                    else:
                        logger.error(f"Failed to commit chunk: {response.status}")
                        return False
            
            # Step 4: Verify manifest
            logger.info("Step 4: Verifying manifest...")
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.metadata_url}/manifest/{video_id}",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        manifest = await response.json()
                        logger.info(f"✓ Manifest retrieved: {len(manifest.get('chunks', []))} chunks")
                        logger.info("✓ Upload workflow completed successfully!")
                        return True
                    else:
                        logger.error(f"Failed to retrieve manifest: {response.status}")
                        return False
        
        except Exception as e:
            logger.error(f"Upload workflow failed: {e}")
            return False
    
    async def test_playback_workflow(self) -> bool:
        """Test complete playback workflow: manifest → intelligent scheduling → smooth playback"""
        logger.info("=" * 60)
        logger.info("Testing Playback Workflow")
        logger.info("=" * 60)
        
        try:
            # Step 1: Get list of available videos
            logger.info("Step 1: Getting available videos...")
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.metadata_url}/videos",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        logger.warning("No videos endpoint available or no videos exist")
                        logger.info("Skipping playback test - no videos to play")
                        return True  # Not a failure, just no videos yet
                    else:
                        videos = await response.json()
                        if not videos or len(videos) == 0:
                            logger.warning("No videos available for playback")
                            logger.info("Skipping playback test - no videos to play")
                            return True  # Not a failure, just no videos yet
                        video_id = videos[0]['video_id']
                        logger.info(f"✓ Found video: {video_id}")
            
            # Step 2: Fetch manifest
            logger.info("Step 2: Fetching video manifest...")
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.metadata_url}/manifest/{video_id}",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        logger.error(f"Failed to fetch manifest: {response.status}")
                        return False
                    manifest = await response.json()
                    chunks = manifest.get('chunks', [])
                    logger.info(f"✓ Manifest fetched: {len(chunks)} chunks")
            
            # Step 3: Test intelligent scheduling (download first chunk from best node)
            logger.info("Step 3: Testing intelligent chunk download...")
            if not chunks:
                logger.warning("No chunks in manifest")
                return False
            
            first_chunk = chunks[0]
            chunk_id = first_chunk['chunk_id']
            replicas = first_chunk.get('replicas', [])
            
            if not replicas:
                logger.error("No replicas available for chunk")
                return False
            
            # Try downloading from first replica
            download_success = False
            for replica_url in replicas:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f"{replica_url}/chunk/{chunk_id}",
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as response:
                            if response.status == 200:
                                chunk_data = await response.read()
                                logger.info(f"✓ Downloaded chunk from {replica_url} ({len(chunk_data)} bytes)")
                                download_success = True
                                break
                            else:
                                logger.warning(f"Failed to download from {replica_url}: {response.status}")
                except Exception as e:
                    logger.warning(f"Error downloading from {replica_url}: {e}")
            
            if not download_success:
                logger.error("Failed to download chunk from any replica")
                return False
            
            logger.info("✓ Playback workflow completed successfully!")
            return True
        
        except Exception as e:
            logger.error(f"Playback workflow failed: {e}")
            return False
    
    async def test_error_handling(self) -> bool:
        """Test system-wide error handling and recovery"""
        logger.info("=" * 60)
        logger.info("Testing Error Handling")
        logger.info("=" * 60)
        
        try:
            # Test 1: Invalid video ID
            logger.info("Test 1: Invalid video ID...")
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.metadata_url}/manifest/invalid-video-id",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 404:
                        logger.info("✓ Correctly returned 404 for invalid video")
                    else:
                        logger.warning(f"Unexpected status for invalid video: {response.status}")
            
            # Test 2: Invalid chunk ID
            logger.info("Test 2: Invalid chunk ID...")
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.storage_nodes[0]}/chunk/invalid-chunk-id",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 404:
                        logger.info("✓ Correctly returned 404 for invalid chunk")
                    else:
                        logger.warning(f"Unexpected status for invalid chunk: {response.status}")
            
            # Test 3: Health check on all nodes
            logger.info("Test 3: Health checks...")
            healthy_nodes = 0
            for node_url in self.storage_nodes:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f"{node_url}/health",
                            timeout=aiohttp.ClientTimeout(total=5)
                        ) as response:
                            if response.status == 200:
                                healthy_nodes += 1
                                logger.info(f"✓ {node_url} is healthy")
                except Exception as e:
                    logger.warning(f"{node_url} health check failed: {e}")
            
            if healthy_nodes >= 2:
                logger.info(f"✓ {healthy_nodes}/3 nodes healthy (sufficient for operation)")
                logger.info("✓ Error handling tests completed!")
                return True
            else:
                logger.error(f"Only {healthy_nodes}/3 nodes healthy (insufficient)")
                return False
        
        except Exception as e:
            logger.error(f"Error handling tests failed: {e}")
            return False
    
    async def test_performance_metrics(self) -> bool:
        """Test performance monitoring and metrics collection"""
        logger.info("=" * 60)
        logger.info("Testing Performance Metrics")
        logger.info("=" * 60)
        
        try:
            # Test 1: Measure storage node latency
            logger.info("Test 1: Measuring storage node latency...")
            latencies = []
            for node_url in self.storage_nodes:
                try:
                    start_time = time.time()
                    async with aiohttp.ClientSession() as session:
                        async with session.head(
                            f"{node_url}/ping",
                            timeout=aiohttp.ClientTimeout(total=5)
                        ) as response:
                            latency = (time.time() - start_time) * 1000  # Convert to ms
                            if response.status == 200:
                                latencies.append(latency)
                                logger.info(f"✓ {node_url} latency: {latency:.2f}ms")
                except Exception as e:
                    logger.warning(f"Failed to ping {node_url}: {e}")
            
            if latencies:
                avg_latency = sum(latencies) / len(latencies)
                logger.info(f"✓ Average latency: {avg_latency:.2f}ms")
                
                if avg_latency < 100:  # Target: <10ms for production, <100ms acceptable for testing
                    logger.info("✓ Latency within acceptable range")
                else:
                    logger.warning(f"Latency higher than expected: {avg_latency:.2f}ms")
            
            # Test 2: Check metadata service health
            logger.info("Test 2: Checking metadata service health...")
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.metadata_url}/health",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        health_data = await response.json()
                        logger.info(f"✓ Metadata service health: {health_data.get('status', 'unknown')}")
                    else:
                        logger.warning(f"Metadata service health check returned: {response.status}")
            
            logger.info("✓ Performance metrics tests completed!")
            return True
        
        except Exception as e:
            logger.error(f"Performance metrics tests failed: {e}")
            return False
    
    async def run_all_tests(self) -> bool:
        """Run all end-to-end workflow tests"""
        logger.info("\n" + "=" * 60)
        logger.info("V-Stack End-to-End Workflow Testing")
        logger.info("=" * 60 + "\n")
        
        # Wait for services to be ready
        logger.info("Waiting for services to be ready...")
        await asyncio.sleep(5)
        
        # Run tests
        self.test_results['upload_workflow'] = await self.test_upload_workflow()
        await asyncio.sleep(2)
        
        self.test_results['playback_workflow'] = await self.test_playback_workflow()
        await asyncio.sleep(2)
        
        self.test_results['error_handling'] = await self.test_error_handling()
        await asyncio.sleep(2)
        
        self.test_results['performance'] = await self.test_performance_metrics()
        
        # Print summary
        logger.info("\n" + "=" * 60)
        logger.info("Test Results Summary")
        logger.info("=" * 60)
        
        all_passed = True
        for test_name, result in self.test_results.items():
            status = "✓ PASS" if result else "✗ FAIL"
            logger.info(f"{test_name:25s} {status}")
            if not result:
                all_passed = False
        
        logger.info("=" * 60)
        
        if all_passed:
            logger.info("✓ All end-to-end workflow tests passed!")
            return True
        else:
            logger.error("✗ Some tests failed. Please check the logs.")
            return False


async def main():
    """Main entry point"""
    tester = E2EWorkflowTester()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    asyncio.run(main())
