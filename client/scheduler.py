#!/usr/bin/env python3
"""
Chunk Scheduler - Intelligently selects optimal storage nodes for chunk downloads
"""

import asyncio
import aiohttp
import time
import logging
import random
from typing import List, Dict, Optional, Set
from collections import defaultdict
from dotenv import load_dotenv

from config import config

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChunkScheduler:
    """
    Intelligent chunk scheduler that selects optimal storage nodes based on performance scores.
    Supports parallel downloads with automatic failover.
    """
    
    def __init__(self, network_monitor):
        """
        Initialize chunk scheduler.
        
        Args:
            network_monitor: NetworkMonitor instance for node performance data
        """
        self.network_monitor = network_monitor
        self.max_concurrent_downloads = config.MAX_CONCURRENT_DOWNLOADS
        
        # Track active downloads to avoid overloading nodes
        self.active_downloads = {}  # chunk_id -> node_url
        self.node_load = defaultdict(int)  # node_url -> active download count
        
        # Download history for analytics
        self.download_history = defaultdict(list)  # node_url -> list of timestamps
        self.chunk_sources = {}  # chunk_id -> node_url (for visualization)
        
        # Semaphore to limit concurrent downloads
        self.download_semaphore = asyncio.Semaphore(self.max_concurrent_downloads)
        
        # Statistics
        self.total_downloads = 0
        self.failed_downloads = 0
        self.failover_count = 0
        self.session = None

    def set_session(self, session: aiohttp.ClientSession):
        """Set the shared aiohttp session."""
        self.session = session
        
    def select_best_node(self, chunk_id: str, available_replicas: List[str]) -> Optional[str]:
        """
        Select optimal node for downloading a chunk based on performance scores.
        
        Args:
            chunk_id: ID of the chunk to download
            available_replicas: List of node URLs that have this chunk
            
        Returns:
            Selected node URL or None if no suitable node found
        """
        if not available_replicas:
            logger.warning(f"No available replicas for chunk {chunk_id}")
            return None
            
        # Filter out unhealthy nodes
        healthy_replicas = [
            node for node in available_replicas 
            if self.network_monitor.is_node_healthy(node)
        ]
        
        if not healthy_replicas:
            logger.warning(f"No healthy replicas for chunk {chunk_id}, using all replicas")
            healthy_replicas = available_replicas
            
        # Calculate scores for all healthy replicas
        node_scores = {}
        for node_url in healthy_replicas:
            score = self.network_monitor.get_node_score(node_url)
            
            # Apply load balancing penalty - reduce score for busy nodes
            load_penalty = 1.0 / (1.0 + self.node_load[node_url] * 0.2)
            adjusted_score = score * load_penalty
            
            node_scores[node_url] = adjusted_score
            
        # Select node with highest adjusted score
        best_node = max(node_scores.keys(), key=lambda n: node_scores[n])
        
        logger.debug(f"Selected {best_node} for chunk {chunk_id} (score: {node_scores[best_node]:.2f})")
        
        return best_node
        
    async def download_chunk(
        self, 
        chunk_id: str, 
        available_replicas: List[str],
        retry_count: int = None
    ) -> Optional[bytes]:
        """
        Download a chunk with automatic failover and retry logic.
        
        Args:
            chunk_id: ID of the chunk to download
            available_replicas: List of node URLs that have this chunk
            retry_count: Number of retry attempts per replica
            
        Returns:
            Chunk data as bytes or None if all attempts failed
        """
        if retry_count is None:
            retry_count = config.MAX_RETRIES

        async with self.download_semaphore:
            # Try each replica in order of preference
            attempted_nodes = set()
            
            # We want to try replicas until we succeed or run out of options
            # But we also want to respect the retry count per replica
            
            # Strategy:
            # 1. Select best node
            # 2. Try to download
            # 3. If fail, retry same node 'retry_count' times
            # 4. If all retries fail, mark node as attempted and go to 1
            
            while len(attempted_nodes) < len(available_replicas):
                # Select best available node that hasn't been tried yet
                remaining_replicas = [n for n in available_replicas if n not in attempted_nodes]
                
                if not remaining_replicas:
                    break
                    
                node_url = self.select_best_node(chunk_id, remaining_replicas)
                
                if not node_url:
                    break
                    
                attempted_nodes.add(node_url)
                
                # Try downloading from this node with retries
                for attempt in range(retry_count):
                    try:
                        chunk_data = await self._download_from_node(chunk_id, node_url)
                        
                        # Success!
                        self._record_successful_download(chunk_id, node_url, len(chunk_data))
                        return chunk_data
                        
                    except Exception as e:
                        logger.debug(f"Download attempt {attempt + 1}/{retry_count} failed for {chunk_id} from {node_url}: {e}")
                        
                        if attempt < retry_count - 1:
                            # Exponential backoff before retry
                            await asyncio.sleep(0.5 * (2 ** attempt))
                            
                # All retries failed for this node, try next replica
                logger.warning(f"All retries failed for {chunk_id} from {node_url}, trying failover")
                self.failover_count += 1
                
            # All replicas failed
            self.failed_downloads += 1
            logger.error(f"Failed to download chunk {chunk_id} from all replicas")
            return None
            
    async def _download_from_node(self, chunk_id: str, node_url: str) -> bytes:
        """
        Download chunk data from a specific node.
        
        Args:
            chunk_id: ID of the chunk to download
            node_url: URL of the storage node
            
        Returns:
            Chunk data as bytes
            
        Raises:
            Exception if download fails
        """
        # Mark node as busy
        self.active_downloads[chunk_id] = node_url
        self.node_load[node_url] += 1
        
        try:
            start_time = time.time()
            
            # Use shared session if available
            if not self.session:
                raise Exception("No session available for download")

            async with self.session.get(f"{node_url}/chunk/{chunk_id}", timeout=config.DOWNLOAD_TIMEOUT) as response:
                if response.status != 200:
                    raise Exception(f"HTTP {response.status}")
                    
                chunk_data = await response.read()
                
                # Calculate bandwidth
                download_time = time.time() - start_time
                if download_time > 0:
                    bandwidth_mbps = (len(chunk_data) * 8) / (download_time * 1_000_000)
                    self.network_monitor.update_bandwidth(node_url, bandwidth_mbps)
                    
                return chunk_data
                    
        finally:
            # Mark node as available
            if chunk_id in self.active_downloads:
                del self.active_downloads[chunk_id]
            self.node_load[node_url] = max(0, self.node_load[node_url] - 1)
            
    def _record_successful_download(self, chunk_id: str, node_url: str, size_bytes: int):
        """Record successful download for analytics."""
        self.total_downloads += 1
        self.download_history[node_url].append(time.time())
        self.chunk_sources[chunk_id] = node_url
        
        logger.debug(f"Successfully downloaded chunk {chunk_id} from {node_url} ({size_bytes} bytes)")
        
    async def download_chunks_parallel(
        self, 
        chunks_to_download: List[Dict]
    ) -> Dict[str, Optional[bytes]]:
        """
        Download multiple chunks in parallel with intelligent scheduling.
        Uses a worker pool to prevent task explosion.
        
        Args:
            chunks_to_download: List of dicts with 'chunk_id' and 'replicas' keys
            
        Returns:
            Dictionary mapping chunk_id to chunk data (or None if failed)
        """
        results = {}
        queue = asyncio.Queue()
        
        # Populate queue
        for chunk_info in chunks_to_download:
            queue.put_nowait(chunk_info)
            
        async def worker():
            while True:
                try:
                    chunk_info = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                    
                chunk_id = chunk_info['chunk_id']
                replicas = chunk_info['replicas']
                
                try:
                    chunk_data = await self.download_chunk(chunk_id, replicas)
                    results[chunk_id] = chunk_data
                except Exception as e:
                    logger.error(f"Error downloading chunk {chunk_id}: {e}")
                    results[chunk_id] = None
                finally:
                    queue.task_done()
        
        # Create worker tasks
        # Limit workers to max_concurrent_downloads
        num_workers = min(len(chunks_to_download), self.max_concurrent_downloads)
        workers = [asyncio.create_task(worker()) for _ in range(num_workers)]
        
        # Wait for all workers to complete
        await asyncio.gather(*workers)
        
        return results
        
    def get_chunk_source(self, chunk_id: str) -> Optional[str]:
        """
        Get the node URL that a chunk was downloaded from.
        Useful for visualization.
        
        Args:
            chunk_id: ID of the chunk
            
        Returns:
            Node URL or None if chunk hasn't been downloaded
        """
        return self.chunk_sources.get(chunk_id)
        
    def get_statistics(self) -> Dict:
        """
        Get scheduler statistics.
        
        Returns:
            Dictionary with scheduler statistics
        """
        return {
            'total_downloads': self.total_downloads,
            'failed_downloads': self.failed_downloads,
            'failover_count': self.failover_count,
            'success_rate': (self.total_downloads - self.failed_downloads) / max(1, self.total_downloads),
            'active_downloads': len(self.active_downloads),
            'node_load': dict(self.node_load),
            'downloads_per_node': {
                node: len(timestamps) 
                for node, timestamps in self.download_history.items()
            }
        }
        
    def get_load_distribution(self) -> Dict[str, int]:
        """
        Get current load distribution across nodes.
        
        Returns:
            Dictionary mapping node URLs to number of downloads served
        """
        return {
            node: len(timestamps)
            for node, timestamps in self.download_history.items()
        }
