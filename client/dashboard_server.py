#!/usr/bin/env python3
"""
Dashboard Server - Serves the web dashboard and provides real-time status API
"""

import asyncio
import json
import logging
import time
from aiohttp import web
import os
from typing import Dict, List
from collections import deque

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects and aggregates metrics for dashboard visualization."""
    
    def __init__(self, history_size: int = 100):
        """
        Initialize metrics collector.
        
        Args:
            history_size: Number of historical data points to keep
        """
        self.history_size = history_size
        
        # Historical metrics
        self.buffer_history = deque(maxlen=history_size)
        self.throughput_history = deque(maxlen=history_size)
        self.node_score_history = {}
        self.download_time_history = deque(maxlen=history_size)
        
        # Aggregated statistics
        self.total_data_transferred = 0  # bytes
        self.session_start_time = time.time()
        
    def record_buffer_level(self, buffer_level_sec: float, timestamp: float = None):
        """Record buffer level measurement."""
        if timestamp is None:
            timestamp = time.time()
            
        self.buffer_history.append({
            'timestamp': timestamp,
            'level': buffer_level_sec
        })
        
    def record_throughput(self, throughput_mbps: float, timestamp: float = None):
        """Record throughput measurement."""
        if timestamp is None:
            timestamp = time.time()
            
        self.throughput_history.append({
            'timestamp': timestamp,
            'throughput': throughput_mbps
        })
        
    def record_node_score(self, node_url: str, score: float, timestamp: float = None):
        """Record node performance score."""
        if timestamp is None:
            timestamp = time.time()
            
        if node_url not in self.node_score_history:
            self.node_score_history[node_url] = deque(maxlen=self.history_size)
            
        self.node_score_history[node_url].append({
            'timestamp': timestamp,
            'score': score
        })
        
    def record_download(self, chunk_size_bytes: int, download_time_sec: float):
        """Record chunk download."""
        self.total_data_transferred += chunk_size_bytes
        self.download_time_history.append(download_time_sec)
        
    def get_average_throughput(self) -> float:
        """Calculate average throughput from history."""
        if not self.throughput_history:
            return 0.0
            
        return sum(h['throughput'] for h in self.throughput_history) / len(self.throughput_history)
        
    def get_average_buffer_level(self) -> float:
        """Calculate average buffer level from history."""
        if not self.buffer_history:
            return 0.0
            
        return sum(h['level'] for h in self.buffer_history) / len(self.buffer_history)
        
    def get_average_download_time(self) -> float:
        """Calculate average chunk download time in milliseconds."""
        if not self.download_time_history:
            return 0.0
            
        return (sum(self.download_time_history) / len(self.download_time_history)) * 1000
        
    def get_session_uptime(self) -> float:
        """Get session uptime in seconds."""
        return time.time() - self.session_start_time
        
    def get_metrics_summary(self) -> Dict:
        """Get summary of all collected metrics."""
        return {
            'avg_throughput_mbps': self.get_average_throughput(),
            'avg_buffer_level_sec': self.get_average_buffer_level(),
            'avg_download_time_ms': self.get_average_download_time(),
            'total_data_transferred_mb': self.total_data_transferred / (1024 * 1024),
            'session_uptime_sec': self.get_session_uptime(),
            'buffer_history': list(self.buffer_history),
            'throughput_history': list(self.throughput_history),
            'node_score_history': {
                node: list(history) 
                for node, history in self.node_score_history.items()
            }
        }


class DashboardServer:
    """HTTP server for the web dashboard."""
    
    def __init__(self, smart_client, host='0.0.0.0', port=8888):
        """
        Initialize dashboard server.
        
        Args:
            smart_client: SmartClient instance to monitor
            host: Host to bind to
            port: Port to listen on
        """
        self.smart_client = smart_client
        self.host = host
        self.port = port
        self.app = web.Application()
        self.metrics_collector = MetricsCollector()
        self.setup_routes()
        
        # Start background metrics collection
        self.collection_task = None
        
    def setup_routes(self):
        """Setup HTTP routes."""
        self.app.router.add_get('/', self.serve_dashboard)
        self.app.router.add_get('/api/status', self.get_status)
        self.app.router.add_get('/api/stats', self.get_stats)
        self.app.router.add_get('/api/metrics', self.get_metrics)
        self.app.router.add_get('/api/performance', self.get_performance_summary)
        
    async def serve_dashboard(self, request):
        """Serve the dashboard HTML page."""
        dashboard_path = os.path.join(os.path.dirname(__file__), 'dashboard.html')
        
        try:
            with open(dashboard_path, 'r') as f:
                html_content = f.read()
            return web.Response(text=html_content, content_type='text/html')
        except FileNotFoundError:
            return web.Response(text='Dashboard not found', status=404)
            
    async def get_status(self, request):
        """Get current client status as JSON."""
        try:
            status = self.smart_client.get_status()
            return web.json_response(status)
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return web.json_response({'error': str(e)}, status=500)
            
    async def get_stats(self, request):
        """Get detailed statistics as JSON."""
        try:
            status = self.smart_client.get_status()
            
            # Extract detailed stats
            stats = {
                'buffer': status.get('buffer', {}),
                'buffer_stats': status.get('buffer_stats', {}),
                'scheduler_stats': status.get('scheduler_stats', {}),
                'network_stats': status.get('network_stats', []),
                'node_scores': status.get('node_scores', {}),
                'buffer_history': self.smart_client.buffer_manager.get_buffer_history()
            }
            
            return web.json_response(stats)
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return web.json_response({'error': str(e)}, status=500)
            
    async def get_metrics(self, request):
        """Get collected metrics history."""
        try:
            metrics = self.metrics_collector.get_metrics_summary()
            return web.json_response(metrics)
        except Exception as e:
            logger.error(f"Error getting metrics: {e}")
            return web.json_response({'error': str(e)}, status=500)
            
    async def get_performance_summary(self, request):
        """Get performance summary comparing against targets."""
        try:
            status = self.smart_client.get_status()
            
            # Performance targets from requirements
            targets = {
                'startup_latency_sec': 2.0,
                'max_rebuffering_events': 1,
                'min_avg_buffer_sec': 20.0,
                'min_avg_throughput_mbps': 40.0
            }
            
            # Actual performance
            actual = {
                'startup_latency_sec': status.get('startup_latency', 0),
                'rebuffering_events': status.get('buffer_stats', {}).get('rebuffering_events', 0),
                'avg_buffer_sec': self.metrics_collector.get_average_buffer_level(),
                'avg_throughput_mbps': self.metrics_collector.get_average_throughput()
            }
            
            # Calculate if targets are met
            targets_met = {
                'startup_latency': actual['startup_latency_sec'] < targets['startup_latency_sec'],
                'rebuffering': actual['rebuffering_events'] <= targets['max_rebuffering_events'],
                'buffer_level': actual['avg_buffer_sec'] > targets['min_avg_buffer_sec'],
                'throughput': actual['avg_throughput_mbps'] > targets['min_avg_throughput_mbps']
            }
            
            summary = {
                'targets': targets,
                'actual': actual,
                'targets_met': targets_met,
                'overall_score': sum(targets_met.values()) / len(targets_met) * 100
            }
            
            return web.json_response(summary)
        except Exception as e:
            logger.error(f"Error getting performance summary: {e}")
            return web.json_response({'error': str(e)}, status=500)
            
    async def _collect_metrics_loop(self):
        """Background task to collect metrics periodically."""
        while True:
            try:
                status = self.smart_client.get_status()
                
                # Record buffer level
                buffer_level = status.get('buffer', {}).get('buffer_level_sec', 0)
                self.metrics_collector.record_buffer_level(buffer_level)
                
                # Calculate and record throughput
                network_stats = status.get('network_stats', [])
                if network_stats:
                    avg_bandwidth = sum(
                        node.get('bandwidth_mbps', {}).get('average', 0) 
                        for node in network_stats
                    ) / len(network_stats)
                    self.metrics_collector.record_throughput(avg_bandwidth)
                
                # Record node scores
                node_scores = status.get('node_scores', {})
                for node_url, score in node_scores.items():
                    self.metrics_collector.record_node_score(node_url, score)
                
                await asyncio.sleep(2.0)  # Collect every 2 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in metrics collection loop: {e}")
                await asyncio.sleep(2.0)
            
    async def start(self):
        """Start the dashboard server."""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        
        # Start metrics collection
        self.collection_task = asyncio.create_task(self._collect_metrics_loop())
        
        logger.info(f"Dashboard server started at http://{self.host}:{self.port}")
        logger.info(f"Open http://localhost:{self.port} in your browser to view the dashboard")
        
    async def run(self):
        """Run the dashboard server indefinitely."""
        await self.start()
        
        # Keep running
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            if self.collection_task:
                self.collection_task.cancel()
                try:
                    await self.collection_task
                except asyncio.CancelledError:
                    pass


async def main():
    """Main entry point for standalone dashboard server."""
    from main import SmartClient
    
    # Create a mock client for testing
    client = SmartClient()
    
    # Start dashboard server
    server = DashboardServer(client, port=8888)
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
