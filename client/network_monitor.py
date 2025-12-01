#!/usr/bin/env python3
"""
Network Monitor - Continuously measures latency, bandwidth, and reliability to storage nodes
"""

import asyncio
import aiohttp
import time
import statistics
import logging
from typing import List, Dict, Optional
from collections import defaultdict, deque

from config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NetworkMonitor:
    """
    Monitors network performance to all storage nodes.
    Tracks latency, bandwidth, and success rates using exponentially weighted moving averages.
    """
    
    def __init__(self):
        """
        Initialize network monitor.
        """
        self.ping_interval = config.PING_INTERVAL
        self.history_size = config.HISTORY_SIZE
        
        # Store recent measurements for each node
        self.latencies = defaultdict(lambda: deque(maxlen=self.history_size))
        self.bandwidths = defaultdict(lambda: deque(maxlen=self.history_size))
        self.success_rates = defaultdict(lambda: deque(maxlen=20))  # More samples for reliability
        
        # Track last update time for each node
        self.last_update = defaultdict(float)
        
        # Monitoring state
        self.monitoring = False
        self.node_urls = []
        self.monitor_task = None
        self.session = None
        self.emulator = None
        
    def set_emulator(self, emulator):
        """
        Set network emulator for simulation.
        
        Args:
            emulator: NetworkEmulator instance
        """
        self.emulator = emulator
        logger.info("Network emulator attached to monitor")
        
    async def start_monitoring(self, node_urls: List[str], session: aiohttp.ClientSession):
        """
        Start background network monitoring for given nodes.
        
        Args:
            node_urls: List of storage node URLs to monitor
            session: Shared aiohttp ClientSession
        """
        if self.monitoring:
            logger.warning("Monitoring already started")
            return
            
        self.node_urls = node_urls
        self.session = session
        self.monitoring = True
        
        logger.info(f"Starting network monitoring for {len(node_urls)} nodes")
        
        # Start background monitoring task
        self.monitor_task = asyncio.create_task(self._monitoring_loop())
        
    async def stop_monitoring(self):
        """Stop background network monitoring."""
        if not self.monitoring:
            return
            
        self.monitoring = False
        self.session = None
        
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
                
        logger.info("Network monitoring stopped")
        
    async def _monitoring_loop(self):
        """Background task that pings nodes every ping_interval seconds."""
        while self.monitoring:
            try:
                # Ping all nodes in parallel
                tasks = [self._ping_node(node_url) for node_url in self.node_urls]
                await asyncio.gather(*tasks, return_exceptions=True)
                
                # Wait for next cycle
                await asyncio.sleep(self.ping_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(self.ping_interval)
                
    async def _ping_node(self, node_url: str):
        """
        Measure latency to a single node using HEAD /ping endpoint.
        
        Args:
            node_url: URL of the storage node
        """
        start_time = time.time()
        
        try:
            # Apply emulation if active
            if self.emulator:
                if self.emulator.should_fail(node_url):
                    raise Exception("Simulated node failure")
                if self.emulator.should_drop_packet(node_url):
                    raise asyncio.TimeoutError("Simulated packet loss")
                await self.emulator.apply_network_delay(node_url)
        
            # Use shared session if available
            if not self.session:
                logger.warning("No session available for ping")
                return

            async with self.session.head(f"{node_url}/ping", timeout=config.PING_TIMEOUT) as response:
                # Calculate latency in milliseconds
                latency = (time.time() - start_time) * 1000
                
                # Record successful ping
                self.latencies[node_url].append(latency)
                self.success_rates[node_url].append(1.0)
                self.last_update[node_url] = time.time()
                
                # Extract bandwidth info from headers if available
                # For now, we'll estimate bandwidth based on successful responses
                # In a real implementation, this would be measured during chunk downloads
                if not self.bandwidths[node_url]:
                    # Initialize with a default estimate
                    self.bandwidths[node_url].append(50.0)  # 50 Mbps default
                
                logger.debug(f"Ping {node_url}: {latency:.2f}ms")
                    
        except asyncio.TimeoutError:
            self.success_rates[node_url].append(0.0)
            logger.debug(f"Ping timeout for {node_url}")
            
        except Exception as e:
            self.success_rates[node_url].append(0.0)
            logger.debug(f"Ping failed for {node_url}: {e}")
            
    def update_bandwidth(self, node_url: str, bandwidth_mbps: float):
        """
        Update bandwidth measurement for a node.
        This is called after actual chunk downloads to record real bandwidth.
        
        Args:
            node_url: URL of the storage node
            bandwidth_mbps: Measured bandwidth in Mbps
        """
        self.bandwidths[node_url].append(bandwidth_mbps)
        logger.debug(f"Updated bandwidth for {node_url}: {bandwidth_mbps:.2f} Mbps")
        
    def get_node_score(self, node_url: str) -> float:
        """
        Calculate node performance score using the exact formula from requirements:
        Formula: (bandwidth × reliability) / (1 + latency × 0.1)
        
        Args:
            node_url: URL of the storage node
            
        Returns:
            Performance score (higher is better)
        """
        # Check if we have any measurements
        if not self.latencies[node_url]:
            return 0.0
            
        try:
            # Calculate average latency (ms)
            avg_latency = statistics.mean(self.latencies[node_url])
            
            # Calculate average bandwidth (Mbps)
            if self.bandwidths[node_url]:
                avg_bandwidth = statistics.mean(self.bandwidths[node_url])
            else:
                avg_bandwidth = 50.0  # Default estimate
                
            # Calculate success rate (reliability)
            if self.success_rates[node_url]:
                success_rate = statistics.mean(self.success_rates[node_url])
            else:
                success_rate = 0.0
                
            # Apply exact scoring formula from requirements
            score = (avg_bandwidth * success_rate) / (1 + avg_latency * 0.1)
            
            return score
        except statistics.StatisticsError:
            return 0.0
        
    def get_all_node_scores(self) -> Dict[str, float]:
        """
        Get performance scores for all monitored nodes.
        
        Returns:
            Dictionary mapping node URLs to their scores
        """
        return {node_url: self.get_node_score(node_url) for node_url in self.node_urls}
        
    def get_node_stats(self, node_url: str) -> Optional[Dict]:
        """
        Get detailed statistics for a specific node.
        
        Args:
            node_url: URL of the storage node
            
        Returns:
            Dictionary with node statistics or None if no data
        """
        if not self.latencies[node_url]:
            return None
            
        try:
            stats = {
                'node_url': node_url,
                'latency_ms': {
                    'current': self.latencies[node_url][-1] if self.latencies[node_url] else None,
                    'average': statistics.mean(self.latencies[node_url]) if self.latencies[node_url] else None,
                    'min': min(self.latencies[node_url]) if self.latencies[node_url] else None,
                    'max': max(self.latencies[node_url]) if self.latencies[node_url] else None,
                },
                'bandwidth_mbps': {
                    'current': self.bandwidths[node_url][-1] if self.bandwidths[node_url] else None,
                    'average': statistics.mean(self.bandwidths[node_url]) if self.bandwidths[node_url] else None,
                },
                'success_rate': statistics.mean(self.success_rates[node_url]) if self.success_rates[node_url] else 0.0,
                'score': self.get_node_score(node_url),
                'last_update': self.last_update.get(node_url, 0),
                'measurements_count': len(self.latencies[node_url])
            }
            
            return stats
        except statistics.StatisticsError:
            return None
        
    def get_all_stats(self) -> List[Dict]:
        """
        Get detailed statistics for all monitored nodes.
        
        Returns:
            List of dictionaries with node statistics
        """
        return [self.get_node_stats(node_url) for node_url in self.node_urls 
                if self.get_node_stats(node_url) is not None]
        
    def is_node_healthy(self, node_url: str, timeout_sec: float = None) -> bool:
        """
        Check if a node is considered healthy based on recent measurements.
        
        Args:
            node_url: URL of the storage node
            timeout_sec: Seconds since last successful ping to consider node down
            
        Returns:
            True if node is healthy, False otherwise
        """
        if timeout_sec is None:
            timeout_sec = config.NODE_HEALTH_TIMEOUT

        # Check if we have recent data
        last_seen = self.last_update.get(node_url, 0)
        
        # If never seen, check if we've been monitoring long enough to expect a ping
        if last_seen == 0:
            # If we just started, give it a chance
            if not self.monitoring:
                return False # Not monitoring, so unknown/unhealthy
            # If we've been monitoring longer than ping interval + buffer, and no ping, then unhealthy
            # But here we don't track start time easily. 
            # Simplification: if no data, assume unhealthy unless we have no nodes at all
            return False

        if time.time() - last_seen > timeout_sec:
            return False
            
        # Check success rate
        if self.success_rates[node_url]:
            try:
                recent_success_rate = statistics.mean(list(self.success_rates[node_url])[-5:])
                return recent_success_rate > 0.5  # At least 50% success rate
            except statistics.StatisticsError:
                return False
            
        return False
        
    def get_healthy_nodes(self) -> List[str]:
        """
        Get list of currently healthy nodes.
        
        Returns:
            List of node URLs that are considered healthy
        """
        return [node_url for node_url in self.node_urls if self.is_node_healthy(node_url)]
