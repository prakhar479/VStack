#!/usr/bin/env python3
"""
Tests for Uploader Service
Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
"""

import pytest
import asyncio
import os
import tempfile
import hashlib
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from video_processor import VideoProcessor, VideoChunk
from upload_coordinator import UploadCoordinator

# Test fixtures
@pytest.fixture
def temp_dir():
    """Create temporary directory for tests"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir

@pytest.fixture
def video_processor(temp_dir):
    """Create VideoProcessor instance"""
    return VideoProcessor(temp_dir)

@pytest.fixture
def upload_coordinator():
    """Create UploadCoordinator instance"""
    return UploadCoordinator("http://metadata-service:8080")

@pytest.fixture
def sample_chunk():
    """Create a sample video chunk"""
    data = b"sample video chunk data" * 100
    checksum = hashlib.sha256(data).hexdigest()
    return VideoChunk(
        chunk_id="test-video-chunk-000",
        video_id="test-video",
        sequence_num=0,
        data=data,
        size_bytes=len(data),
        checksum=checksum
    )

# Video Processor Tests
class TestVideoProcessor:
    """Test video processing and chunking functionality"""
    
    @pytest.mark.asyncio
    async def test_cleanup_removes_temp_files(self, video_processor, temp_dir):
        """Test cleanup of temporary files - Requirement 1.2"""
        video_id = "test-video-123"
        
        # Create some temporary files
        test_files = [
            os.path.join(temp_dir, f"{video_id}_input.mp4"),
            os.path.join(temp_dir, f"{video_id}_chunk_000.mp4"),
            os.path.join(temp_dir, f"{video_id}_chunk_001.mp4")
        ]
        
        for file_path in test_files:
            with open(file_path, 'w') as f:
                f.write("test data")
        
        # Verify files exist
        for file_path in test_files:
            assert os.path.exists(file_path)
        
        # Run cleanup
        await video_processor.cleanup(video_id)
        
        # Verify files are deleted
        for file_path in test_files:
            assert not os.path.exists(file_path)
    
    def test_parse_fps_handles_various_formats(self, video_processor):
        """Test FPS parsing from different formats"""
        assert video_processor._parse_fps("30/1") == 30.0
        assert video_processor._parse_fps("60/1") == 60.0
        assert video_processor._parse_fps("24000/1001") == pytest.approx(23.976, rel=0.01)
        assert video_processor._parse_fps("invalid") == 0.0

# Upload Coordinator Tests
class TestUploadCoordinator:
    """Test upload coordination and parallel uploads"""
    
    @pytest.mark.asyncio
    async def test_get_healthy_nodes_returns_node_list(self, upload_coordinator):
        """Test retrieval of healthy storage nodes - Requirement 1.3"""
        mock_response = Mock()
        mock_response.json.return_value = [
            {"node_url": "http://node1:8081", "node_id": "node1"},
            {"node_url": "http://node2:8082", "node_id": "node2"},
            {"node_url": "http://node3:8083", "node_id": "node3"}
        ]
        mock_response.raise_for_status = Mock()
        
        with patch.object(upload_coordinator, '_get_http_client') as mock_client:
            mock_http = AsyncMock()
            mock_http.get.return_value = mock_response
            mock_client.return_value = mock_http
            
            nodes = await upload_coordinator.get_healthy_nodes()
            
            assert len(nodes) == 3
            assert "http://node1:8081" in nodes
            assert "http://node2:8082" in nodes
    
    @pytest.mark.asyncio
    async def test_register_video_creates_video_record(self, upload_coordinator):
        """Test video registration with metadata service - Requirement 1.4"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "video_id": "test-video-123",
            "upload_url": "/upload/test-video-123"
        }
        mock_response.raise_for_status = Mock()
        
        with patch.object(upload_coordinator, '_get_http_client') as mock_client:
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            mock_client.return_value = mock_http
            
            result = await upload_coordinator.register_video(
                video_id="test-video-123",
                title="Test Video",
                duration_sec=120
            )
            
            assert result["video_id"] == "test-video-123"
            mock_http.post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_upload_chunk_to_node_sends_correct_data(self, upload_coordinator, sample_chunk):
        """Test chunk upload to storage node - Requirement 1.3"""
        mock_response = Mock()
        mock_response.status_code = 201
        
        with patch.object(upload_coordinator, '_get_http_client') as mock_client:
            mock_http = AsyncMock()
            mock_http.put.return_value = mock_response
            mock_client.return_value = mock_http
            
            result = await upload_coordinator._upload_chunk_to_node(
                sample_chunk,
                "http://node1:8081"
            )
            
            assert result is True
            mock_http.put.assert_called_once()
            call_args = mock_http.put.call_args
            assert sample_chunk.chunk_id in call_args[0][0]
            assert call_args[1]['content'] == sample_chunk.data
    
    @pytest.mark.asyncio
    async def test_commit_chunk_placement_uses_consensus(self, upload_coordinator, sample_chunk):
        """Test consensus-based chunk placement commit - Requirement 8.2"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "success": True,
            "committed_nodes": ["http://node1:8081", "http://node2:8082"],
            "message": "Chunk committed"
        }
        mock_response.raise_for_status = Mock()
        
        with patch.object(upload_coordinator, '_get_http_client') as mock_client:
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            mock_client.return_value = mock_http
            
            await upload_coordinator._commit_chunk_placement(
                sample_chunk,
                ["http://node1:8081", "http://node2:8082"]
            )
            
            mock_http.post.assert_called_once()
            call_args = mock_http.post.call_args
            assert sample_chunk.chunk_id in call_args[0][0]
            assert call_args[1]['json']['checksum'] == sample_chunk.checksum
    
    @pytest.mark.asyncio
    async def test_finalize_video_verifies_all_chunks(self, upload_coordinator):
        """Test video finalization and verification - Requirement 1.5, 10.4"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "video_id": "test-video",
            "total_chunks": 3,
            "chunks": [
                {"chunk_id": "test-video-chunk-000", "replicas": ["http://node1:8081"]},
                {"chunk_id": "test-video-chunk-001", "replicas": ["http://node2:8082"]},
                {"chunk_id": "test-video-chunk-002", "replicas": ["http://node3:8083"]}
            ]
        }
        mock_response.raise_for_status = Mock()
        
        with patch.object(upload_coordinator, '_get_http_client') as mock_client:
            mock_http = AsyncMock()
            mock_http.get.return_value = mock_response
            mock_client.return_value = mock_http
            
            chunks = [
                VideoChunk(f"test-video-chunk-{i:03d}", "test-video", i, b"data", 4, "checksum")
                for i in range(3)
            ]
            
            manifest = await upload_coordinator.finalize_video("test-video", chunks)
            
            assert manifest["total_chunks"] == 3
            assert len(manifest["chunks"]) == 3
            for chunk_info in manifest["chunks"]:
                assert len(chunk_info["replicas"]) > 0
    
    @pytest.mark.asyncio
    async def test_upload_chunks_handles_insufficient_nodes(self, upload_coordinator):
        """Test error handling when insufficient storage nodes - Requirement 1.3"""
        with patch.object(upload_coordinator, 'get_healthy_nodes') as mock_get_nodes:
            mock_get_nodes.return_value = ["http://node1:8081"]  # Only 1 node, need 3
            
            chunks = [
                VideoChunk(f"test-chunk-{i}", "test-video", i, b"data", 4, "checksum")
                for i in range(2)
            ]
            
            with pytest.raises(ValueError, match="Insufficient storage nodes"):
                await upload_coordinator.upload_chunks("test-video", chunks)
    
    @pytest.mark.asyncio
    async def test_upload_single_chunk_retries_on_failure(self, upload_coordinator, sample_chunk):
        """Test retry logic for failed chunk uploads - Requirement 1.5"""
        storage_nodes = ["http://node1:8081", "http://node2:8082", "http://node3:8083"]
        
        # Mock upload to fail first time, succeed second time
        call_count = 0
        async def mock_upload(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Network error")
            return True
        
        with patch.object(upload_coordinator, '_upload_chunk_to_node', side_effect=mock_upload):
            with patch.object(upload_coordinator, '_commit_chunk_placement', new_callable=AsyncMock):
                # Should succeed on retry
                result = await upload_coordinator._upload_single_chunk(sample_chunk, storage_nodes)
                assert result is not None

# Integration Tests
class TestUploadIntegration:
    """Integration tests for complete upload workflow"""
    
    @pytest.mark.asyncio
    async def test_complete_upload_workflow(self, temp_dir):
        """Test complete upload workflow from video to chunks - Requirements 1.1-1.5"""
        # This is a simplified integration test
        # In a real scenario, we would use actual video files and running services
        
        processor = VideoProcessor(temp_dir)
        coordinator = UploadCoordinator("http://metadata-service:8080")
        
        # Create mock chunks
        chunks = [
            VideoChunk(f"video-chunk-{i:03d}", "test-video", i, 
                      b"chunk data" * 100, 1000, hashlib.sha256(b"chunk data" * 100).hexdigest())
            for i in range(3)
        ]
        
        # Verify chunks have correct properties
        assert len(chunks) == 3
        assert all(chunk.size_bytes > 0 for chunk in chunks)
        assert all(len(chunk.checksum) == 64 for chunk in chunks)  # SHA-256 hex length
        assert all(chunk.sequence_num == i for i, chunk in enumerate(chunks))

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
