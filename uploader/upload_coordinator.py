#!/usr/bin/env python3
"""
Upload Coordinator - Manages parallel chunk uploads and consensus
Requirements: 1.3, 1.4, 1.5, 8.2, 10.4
"""

import asyncio
import httpx
import random
import logging
from typing import List, Dict, Callable, Optional
from video_processor import VideoChunk

logger = logging.getLogger(__name__)

class UploadCoordinator:
    """Coordinates parallel chunk uploads to storage nodes"""
    
    def __init__(self, metadata_service_url: str, 
                 replicas_per_chunk: int = 3,
                 max_concurrent_uploads: int = 5,
                 max_retries: int = 3):
        self.metadata_service_url = metadata_service_url
        self.replicas_per_chunk = replicas_per_chunk
        self.max_concurrent_uploads = max_concurrent_uploads
        self.max_retries = max_retries
        self.http_client = None
        
    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self.http_client is None:
            self.http_client = httpx.AsyncClient(timeout=30.0)
        return self.http_client
    
    async def register_video(self, video_id: str, title: str, duration_sec: int):
        """
        Register video with metadata service
        Requirements: 1.4
        """
        client = await self._get_http_client()
        
        try:
            response = await client.post(
                f"{self.metadata_service_url}/video",
                json={
                    "title": title,
                    "duration_sec": duration_sec
                }
            )
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Video registered: {video_id} -> {result.get('video_id')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to register video {video_id}: {e}")
            raise ValueError(f"Failed to register video with metadata service: {str(e)}")
    
    async def get_healthy_nodes(self) -> List[str]:
        """
        Get list of healthy storage nodes from metadata service
        Requirements: 1.3
        """
        client = await self._get_http_client()
        
        try:
            response = await client.get(f"{self.metadata_service_url}/nodes/healthy")
            response.raise_for_status()
            
            nodes = response.json()
            node_urls = [node['node_url'] for node in nodes]
            
            logger.info(f"Retrieved {len(node_urls)} healthy storage nodes")
            return node_urls
            
        except Exception as e:
            logger.error(f"Failed to get healthy nodes: {e}")
            raise ValueError(f"Failed to get healthy storage nodes: {str(e)}")
    
    async def upload_chunks(self, video_id: str, chunks: List[VideoChunk],
                           progress_callback: Optional[Callable[[float], None]] = None):
        """
        Upload all chunks in parallel with retry logic
        Requirements: 1.3, 1.4, 8.2
        """
        # Get healthy storage nodes
        storage_nodes = await self.get_healthy_nodes()
        
        if len(storage_nodes) < self.replicas_per_chunk:
            raise ValueError(
                f"Insufficient storage nodes: need {self.replicas_per_chunk}, "
                f"have {len(storage_nodes)}"
            )
        
        logger.info(f"Starting upload of {len(chunks)} chunks to {len(storage_nodes)} nodes")
        
        # Create semaphore to limit concurrent uploads
        semaphore = asyncio.Semaphore(self.max_concurrent_uploads)
        
        # Track progress
        completed_chunks = 0
        total_chunks = len(chunks)
        
        async def upload_single_chunk_with_progress(chunk: VideoChunk):
            nonlocal completed_chunks
            
            async with semaphore:
                result = await self._upload_single_chunk(chunk, storage_nodes)
                completed_chunks += 1
                
                if progress_callback:
                    progress = completed_chunks / total_chunks
                    progress_callback(progress)
                
                return result
        
        # Upload all chunks in parallel
        upload_tasks = [
            upload_single_chunk_with_progress(chunk)
            for chunk in chunks
        ]
        
        results = await asyncio.gather(*upload_tasks, return_exceptions=True)
        
        # Check for failures
        failed_chunks = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed_chunks.append((chunks[i].chunk_id, str(result)))
        
        if failed_chunks:
            error_msg = f"Failed to upload {len(failed_chunks)} chunks: {failed_chunks[:3]}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info(f"Successfully uploaded all {len(chunks)} chunks")
    
    async def _upload_single_chunk(self, chunk: VideoChunk, storage_nodes: List[str]) -> Dict:
        """
        Upload a single chunk to multiple storage nodes with consensus
        Requirements: 1.3, 1.4, 8.2
        """
        # Select random nodes for this chunk (requirement: 3 nodes per chunk)
        target_nodes = random.sample(
            storage_nodes,
            min(self.replicas_per_chunk, len(storage_nodes))
        )
        
        logger.debug(f"Uploading chunk {chunk.chunk_id} to {len(target_nodes)} nodes")
        
        # Retry logic for failed uploads
        for attempt in range(self.max_retries):
            try:
                # Upload to all target nodes in parallel
                upload_tasks = [
                    self._upload_chunk_to_node(chunk, node_url)
                    for node_url in target_nodes
                ]
                
                results = await asyncio.gather(*upload_tasks, return_exceptions=True)
                
                # Check which uploads succeeded
                successful_nodes = []
                for i, result in enumerate(results):
                    if not isinstance(result, Exception):
                        successful_nodes.append(target_nodes[i])
                    else:
                        logger.warning(f"Upload to {target_nodes[i]} failed: {result}")
                
                # Require at least 2 successful uploads (quorum)
                min_replicas = min(2, self.replicas_per_chunk)
                if len(successful_nodes) >= min_replicas:
                    # Commit chunk placement via consensus
                    await self._commit_chunk_placement(chunk, successful_nodes)
                    
                    logger.debug(f"Chunk {chunk.chunk_id} uploaded to {len(successful_nodes)} nodes")
                    return {
                        "chunk_id": chunk.chunk_id,
                        "nodes": successful_nodes,
                        "replicas": len(successful_nodes)
                    }
                else:
                    if attempt < self.max_retries - 1:
                        logger.warning(
                            f"Insufficient replicas for {chunk.chunk_id} "
                            f"({len(successful_nodes)}/{min_replicas}), retrying..."
                        )
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    else:
                        raise ValueError(
                            f"Failed to upload chunk {chunk.chunk_id} to sufficient nodes: "
                            f"only {len(successful_nodes)}/{min_replicas} succeeded"
                        )
                        
            except Exception as e:
                if attempt < self.max_retries - 1:
                    logger.warning(f"Upload attempt {attempt + 1} failed for {chunk.chunk_id}: {e}")
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
        
        raise ValueError(f"Failed to upload chunk {chunk.chunk_id} after {self.max_retries} attempts")
    
    async def _upload_chunk_to_node(self, chunk: VideoChunk, node_url: str):
        """
        Upload chunk data to a single storage node
        Requirements: 1.3
        """
        client = await self._get_http_client()
        
        try:
            response = await client.put(
                f"{node_url}/chunk/{chunk.chunk_id}",
                content=chunk.data,
                headers={
                    "Content-Type": "application/octet-stream",
                    "X-Chunk-Size": str(chunk.size_bytes),
                    "X-Checksum": chunk.checksum
                }
            )
            
            if response.status_code not in [200, 201]:
                raise ValueError(f"Upload failed with status {response.status_code}")
            
            logger.debug(f"Uploaded {chunk.chunk_id} to {node_url}")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to upload {chunk.chunk_id} to {node_url}: {e}")
            raise
    
    async def _commit_chunk_placement(self, chunk: VideoChunk, node_urls: List[str]):
        """
        Commit chunk placement using consensus protocol
        Requirements: 1.4, 8.2
        """
        client = await self._get_http_client()
        
        try:
            response = await client.post(
                f"{self.metadata_service_url}/chunk/{chunk.chunk_id}/commit",
                json={
                    "node_urls": node_urls,
                    "checksum": chunk.checksum,
                    "size_bytes": chunk.size_bytes,
                    "video_id": chunk.video_id,
                    "sequence_num": chunk.sequence_num,
                    "redundancy_mode": "replication",  # Default to replication mode
                    "fragments_metadata": None  # No fragments for replication mode
                }
            )
            response.raise_for_status()
            
            result = response.json()
            if not result.get("success"):
                raise ValueError(f"Consensus failed: {result.get('message')}")
            
            logger.debug(f"Committed chunk {chunk.chunk_id} placement via consensus")
            
        except Exception as e:
            logger.error(f"Failed to commit chunk placement for {chunk.chunk_id}: {e}")
            raise
    
    async def finalize_video(self, video_id: str, chunks: List[VideoChunk]) -> Dict:
        """
        Finalize video upload and verify all chunks are stored
        Requirements: 1.4, 1.5, 10.4
        """
        client = await self._get_http_client()
        
        try:
            # Get video manifest to verify all chunks are registered
            response = await client.get(f"{self.metadata_service_url}/manifest/{video_id}")
            response.raise_for_status()
            
            manifest = response.json()
            
            # Verify chunk count matches
            if manifest["total_chunks"] != len(chunks):
                logger.warning(
                    f"Chunk count mismatch for {video_id}: "
                    f"expected {len(chunks)}, got {manifest['total_chunks']}"
                )
            
            # Verify all chunks have replicas
            for chunk_info in manifest["chunks"]:
                if not chunk_info.get("replicas"):
                    raise ValueError(f"Chunk {chunk_info['chunk_id']} has no replicas")
            
            logger.info(f"Video {video_id} finalized: {len(chunks)} chunks verified")
            return manifest
            
        except Exception as e:
            logger.error(f"Failed to finalize video {video_id}: {e}")
            raise ValueError(f"Failed to finalize video: {str(e)}")
    
    async def cleanup_failed_upload(self, video_id: str):
        """
        Cleanup partial uploads on failure
        Requirements: 1.5, 10.4
        """
        try:
            # In a production system, we would:
            # 1. Mark video as deleted in metadata service
            # 2. Send cleanup requests to storage nodes
            # 3. Remove partial chunk records
            
            logger.info(f"Cleaning up failed upload for video {video_id}")
            
            # For MVP, we just log the cleanup
            # Storage nodes will handle orphaned chunks via garbage collection
            
        except Exception as e:
            logger.error(f"Cleanup failed for {video_id}: {e}")
    
    async def close(self):
        """Close HTTP client"""
        if self.http_client:
            await self.http_client.aclose()
