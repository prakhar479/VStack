#!/usr/bin/env python3
"""
Smart Client - Intelligent video streaming client for V-Stack
"""

import asyncio
import aiohttp
import time
import logging
import json
import sys
import os
from typing import List, Dict, Optional

# Add parent directory to path for shared config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from network_monitor import NetworkMonitor
from scheduler import ChunkScheduler
from buffer_manager import BufferManager

try:
    from config import SmartClientConfig, validate_config
    config = SmartClientConfig.from_env()
    if not validate_config(config):
        logger.error("Configuration validation failed!")
        sys.exit(1)
except ImportError:
    # Fallback configuration
    logging.basicConfig(level=logging.INFO)
    config = None

logger = logging.getLogger(__name__)


class SmartClient:
    """
    Smart client with network monitoring, intelligent scheduling, and buffer management.
    Implements the core novelty of adaptive chunk scheduling based on real-time network conditions.
    """
    
    def __init__(self, metadata_service_url: str = "http://localhost:8080"):
        self.metadata_url = metadata_service_url
        self.video_id = None
        self.manifest = None
        
        # Core components
        self.network_monitor = NetworkMonitor(ping_interval=3.0, history_size=10)
        self.scheduler = ChunkScheduler(self.network_monitor, max_concurrent_downloads=4)
        self.buffer_manager = BufferManager(
            target_buffer_sec=30,
            low_water_mark_sec=15,
            chunk_duration_sec=10,
            start_playback_sec=10
        )
        
        # Playback state
        self.playing = False
        self.playback_task = None
        self.download_task = None
        
        # Statistics
        self.startup_latency = None
        self.playback_start_time = None
        
    async def initialize(self):
        """Initialize client and test connection to metadata service."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.metadata_url}/health") as response:
                    if response.status == 200:
                        logger.info("Connected to metadata service")
                        return True
        except Exception as e:
            logger.error(f"Failed to connect to metadata service: {e}")
            return False
            
    async def fetch_manifest(self, video_id: str) -> Optional[Dict]:
        """
        Fetch video manifest from metadata service.
        
        Args:
            video_id: ID of the video to play
            
        Returns:
            Video manifest dictionary or None if failed
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.metadata_url}/manifest/{video_id}") as response:
                    if response.status == 200:
                        manifest = await response.json()
                        logger.info(f"Fetched manifest for video {video_id}: {manifest.get('total_chunks', 0)} chunks")
                        return manifest
                    else:
                        logger.error(f"Failed to fetch manifest: HTTP {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Error fetching manifest: {e}")
            return None
            
    def get_all_storage_nodes(self) -> List[str]:
        """Extract all unique storage node URLs from manifest."""
        if not self.manifest:
            return []
            
        nodes = set()
        for chunk in self.manifest.get('chunks', []):
            for replica in chunk.get('replicas', []):
                nodes.add(replica)
                
        return list(nodes)
        
    async def play_video(self, video_id: str):
        """
        Main video playback method.
        Orchestrates network monitoring, chunk downloading, and playback.
        
        Args:
            video_id: ID of the video to play
        """
        init_start_time = time.time()
        
        # Fetch manifest
        self.video_id = video_id
        self.manifest = await self.fetch_manifest(video_id)
        
        if not self.manifest:
            logger.error("Cannot play video without manifest")
            return
            
        # Start network monitoring
        storage_nodes = self.get_all_storage_nodes()
        if not storage_nodes:
            logger.error("No storage nodes found in manifest")
            return
            
        logger.info(f"Starting network monitoring for {len(storage_nodes)} nodes")
        await self.network_monitor.start_monitoring(storage_nodes)
        
        # Wait a moment for initial network measurements
        await asyncio.sleep(1.0)
        
        # Start background tasks
        self.playing = True
        self.download_task = asyncio.create_task(self._download_loop())
        self.playback_task = asyncio.create_task(self._playback_loop())
        
        # Wait for initial buffer to fill
        logger.info("Buffering initial chunks...")
        while not self.buffer_manager.can_start_playback() and self.playing:
            await asyncio.sleep(0.1)
            
        self.startup_latency = time.time() - init_start_time
        self.playback_start_time = time.time()
        logger.info(f"Playback ready! Startup latency: {self.startup_latency:.2f}s")
        
        # Wait for playback to complete
        try:
            await asyncio.gather(self.download_task, self.playback_task)
        except asyncio.CancelledError:
            logger.info("Playback cancelled")
            
    async def _download_loop(self):
        """Background task that downloads chunks to maintain buffer."""
        logger.info("Download loop started")
        
        while self.playing:
            try:
                # Check if buffer needs refilling
                if self.buffer_manager.needs_more_chunks():
                    # Determine how many chunks to download
                    buffer_deficit = (
                        self.buffer_manager.target_buffer_sec - 
                        self.buffer_manager.get_buffer_level_seconds()
                    ) / self.buffer_manager.chunk_duration_sec
                    
                    chunks_to_download = max(1, int(buffer_deficit) + 2)
                    
                    # Get next chunk sequences to download
                    next_sequences = self.buffer_manager.get_next_chunk_sequences(chunks_to_download)
                    
                    # Build download list
                    download_list = []
                    for seq_num in next_sequences:
                        # Find chunk in manifest
                        chunk_info = self._get_chunk_info(seq_num)
                        if chunk_info:
                            download_list.append(chunk_info)
                            
                    if download_list:
                        logger.debug(f"Downloading {len(download_list)} chunks")
                        
                        # Download chunks in parallel
                        results = await self.scheduler.download_chunks_parallel(download_list)
                        
                        # Add downloaded chunks to buffer
                        for chunk_id, chunk_data in results.items():
                            if chunk_data:
                                # Extract sequence number from chunk_id
                                seq_num = self._extract_sequence_number(chunk_id)
                                if seq_num is not None:
                                    self.buffer_manager.add_chunk(chunk_id, seq_num, chunk_data)
                                    
                # Sleep briefly before checking again
                await asyncio.sleep(0.5)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in download loop: {e}")
                await asyncio.sleep(1.0)
                
        logger.info("Download loop stopped")
        
    async def _playback_loop(self):
        """Background task that simulates video playback."""
        logger.info("Playback loop started")
        
        while self.playing:
            try:
                # Wait until buffer has content
                if not self.buffer_manager.can_start_playback():
                    await asyncio.sleep(0.1)
                    continue
                    
                # Get next chunk for playback
                chunk = self.buffer_manager.get_next_chunk_for_playback()
                
                if chunk:
                    # Simulate playing the chunk (10 seconds)
                    logger.info(f"Playing chunk {chunk.chunk_id} (seq {chunk.sequence_num})")
                    
                    # Record buffer level for analytics
                    self.buffer_manager.record_buffer_level()
                    
                    # Sleep for chunk duration (simulating playback)
                    await asyncio.sleep(self.buffer_manager.chunk_duration_sec)
                    
                    # Check if this was the last chunk
                    if chunk.sequence_num >= self.manifest.get('total_chunks', 0) - 1:
                        logger.info("Reached end of video")
                        self.playing = False
                        break
                else:
                    # Buffer underrun - wait for more chunks
                    logger.warning("Buffer underrun, waiting for chunks...")
                    await asyncio.sleep(0.5)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in playback loop: {e}")
                await asyncio.sleep(1.0)
                
        logger.info("Playback loop stopped")
        
    def _get_chunk_info(self, sequence_num: int) -> Optional[Dict]:
        """Get chunk information from manifest by sequence number."""
        if not self.manifest:
            return None
            
        for chunk in self.manifest.get('chunks', []):
            if chunk.get('sequence_num') == sequence_num:
                return {
                    'chunk_id': chunk['chunk_id'],
                    'replicas': chunk.get('replicas', [])
                }
                
        return None
        
    def _extract_sequence_number(self, chunk_id: str) -> Optional[int]:
        """Extract sequence number from chunk ID."""
        # Assuming chunk_id format: "video_id-chunk-XXX"
        try:
            parts = chunk_id.split('-chunk-')
            if len(parts) == 2:
                return int(parts[1])
        except:
            pass
            
        # Try to find in manifest
        if self.manifest:
            for chunk in self.manifest.get('chunks', []):
                if chunk['chunk_id'] == chunk_id:
                    return chunk.get('sequence_num')
                    
        return None
        
    async def stop(self):
        """Stop playback and cleanup."""
        logger.info("Stopping playback...")
        self.playing = False
        
        # Cancel tasks
        if self.download_task:
            self.download_task.cancel()
        if self.playback_task:
            self.playback_task.cancel()
            
        # Stop monitoring
        await self.network_monitor.stop_monitoring()
        
        logger.info("Playback stopped")
        
    def get_status(self) -> Dict:
        """Get comprehensive client status for dashboard."""
        status = {
            'video_id': self.video_id,
            'playing': self.playing,
            'startup_latency': self.startup_latency,
            'buffer': self.buffer_manager.get_buffer_status(),
            'buffer_stats': self.buffer_manager.get_statistics(),
            'scheduler_stats': self.scheduler.get_statistics(),
            'network_stats': self.network_monitor.get_all_stats(),
            'node_scores': self.network_monitor.get_all_node_scores(),
        }
        
        if self.playback_start_time:
            status['playback_duration'] = time.time() - self.playback_start_time
            
        return status
        
    def print_status(self):
        """Print current status to console (simple dashboard)."""
        status = self.get_status()
        
        print("\n" + "="*60)
        print("V-STACK SMART CLIENT STATUS")
        print("="*60)
        
        if status['video_id']:
            print(f"Video ID: {status['video_id']}")
            
        if status['startup_latency']:
            print(f"Startup Latency: {status['startup_latency']:.2f}s")
            
        print(f"\nBuffer Status: {status['buffer']['state'].upper()}")
        print(f"  Level: {status['buffer']['buffer_level_sec']:.1f}s / {status['buffer']['target_buffer_sec']}s")
        print(f"  Health: {status['buffer']['buffer_health_percent']:.0f}%")
        print(f"  Position: Chunk {status['buffer']['current_position']}")
        
        print(f"\nPlayback Statistics:")
        print(f"  Chunks Played: {status['buffer_stats']['total_chunks_played']}")
        print(f"  Rebuffering Events: {status['buffer_stats']['rebuffering_events']}")
        
        print(f"\nDownload Statistics:")
        print(f"  Total Downloads: {status['scheduler_stats']['total_downloads']}")
        print(f"  Success Rate: {status['scheduler_stats']['success_rate']*100:.1f}%")
        print(f"  Failovers: {status['scheduler_stats']['failover_count']}")
        
        print(f"\nStorage Node Scores:")
        for node_url, score in status['node_scores'].items():
            print(f"  {node_url}: {score:.2f}")
            
        print("="*60 + "\n")


async def main():
    """Main entry point for smart client."""
    import sys
    
    client = SmartClient()
    
    if not await client.initialize():
        logger.error("Failed to initialize Smart Client")
        return
        
    logger.info("Smart Client initialized successfully")
    
    # Get video ID from command line or use default
    video_id = sys.argv[1] if len(sys.argv) > 1 else "test-video-001"
    
    try:
        # Start playback
        playback_task = asyncio.create_task(client.play_video(video_id))
        
        # Print status periodically
        while client.playing:
            await asyncio.sleep(5.0)
            client.print_status()
            
        await playback_task
        
        # Print final statistics
        print("\n" + "="*60)
        print("PLAYBACK COMPLETE - FINAL STATISTICS")
        print("="*60)
        client.print_status()
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        await client.stop()
    except Exception as e:
        logger.error(f"Error during playback: {e}")
        await client.stop()


if __name__ == "__main__":
    asyncio.run(main())