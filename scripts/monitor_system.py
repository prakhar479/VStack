#!/usr/bin/env python3
"""
System monitoring script for V-Stack.
Collects and displays real-time metrics from all services.
"""

import asyncio
import aiohttp
import sys
import os
import time
import logging
from typing import Dict, List
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SystemMonitor:
    """Real-time system monitoring for V-Stack"""
    
    def __init__(self):
        self.metadata_url = os.getenv('METADATA_SERVICE_URL', 'http://localhost:8080')
        self.storage_nodes = [
            {'name': 'storage-node-1', 'url': 'http://localhost:8081'},
            {'name': 'storage-node-2', 'url': 'http://localhost:8082'},
            {'name': 'storage-node-3', 'url': 'http://localhost:8083'}
        ]
        self.uploader_url = os.getenv('UPLOADER_SERVICE_URL', 'http://localhost:8084')
        self.client_url = os.getenv('CLIENT_DASHBOARD_URL', 'http://localhost:8086')
        
        self.metrics_history = []
    
    async def collect_metadata_metrics(self) -> Dict:
        """Collect metrics from metadata service"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.metadata_url}/health",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            'status': 'healthy',
                            'data': data
                        }
                    else:
                        return {'status': 'unhealthy', 'error': f'Status {response.status}'}
        except Exception as e:
            return {'status': 'error', 'error': str(e)}
    
    async def collect_storage_node_metrics(self, node: Dict) -> Dict:
        """Collect metrics from a storage node"""
        try:
            # Get health data
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{node['url']}/health",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        health_data = await response.json()
                        
                        # Measure latency
                        start_time = time.time()
                        async with session.head(
                            f"{node['url']}/ping",
                            timeout=aiohttp.ClientTimeout(total=5)
                        ) as ping_response:
                            latency = (time.time() - start_time) * 1000
                        
                        return {
                            'name': node['name'],
                            'status': 'healthy',
                            'latency_ms': round(latency, 2),
                            'disk_usage': health_data.get('disk_usage', 0),
                            'chunk_count': health_data.get('chunk_count', 0)
                        }
                    else:
                        return {
                            'name': node['name'],
                            'status': 'unhealthy',
                            'error': f'Status {response.status}'
                        }
        except Exception as e:
            return {
                'name': node['name'],
                'status': 'error',
                'error': str(e)
            }
    
    async def collect_all_metrics(self) -> Dict:
        """Collect metrics from all services"""
        timestamp = datetime.now().isoformat()
        
        # Collect metadata service metrics
        metadata_metrics = await self.collect_metadata_metrics()
        
        # Collect storage node metrics in parallel
        storage_tasks = [
            self.collect_storage_node_metrics(node)
            for node in self.storage_nodes
        ]
        storage_metrics = await asyncio.gather(*storage_tasks)
        
        metrics = {
            'timestamp': timestamp,
            'metadata_service': metadata_metrics,
            'storage_nodes': storage_metrics
        }
        
        return metrics
    
    def display_metrics(self, metrics: Dict):
        """Display metrics in a readable format"""
        print("\n" + "=" * 80)
        print(f"V-Stack System Metrics - {metrics['timestamp']}")
        print("=" * 80)
        
        # Metadata Service
        print("\n📊 Metadata Service:")
        metadata = metrics['metadata_service']
        if metadata['status'] == 'healthy':
            data = metadata.get('data', {})
            print(f"  Status: ✓ Healthy")
            print(f"  Database: {data.get('database', 'unknown')}")
            print(f"  Uptime: {data.get('uptime_seconds', 0):.0f}s")
        else:
            print(f"  Status: ✗ {metadata['status'].upper()}")
            if 'error' in metadata:
                print(f"  Error: {metadata['error']}")
        
        # Storage Nodes
        print("\n💾 Storage Nodes:")
        healthy_nodes = 0
        total_chunks = 0
        avg_latency = 0
        latency_count = 0
        
        for node in metrics['storage_nodes']:
            status_icon = "✓" if node['status'] == 'healthy' else "✗"
            print(f"  {status_icon} {node['name']:20s}", end="")
            
            if node['status'] == 'healthy':
                healthy_nodes += 1
                total_chunks += node.get('chunk_count', 0)
                latency = node.get('latency_ms', 0)
                avg_latency += latency
                latency_count += 1
                
                print(f" Latency: {latency:6.2f}ms | ", end="")
                print(f"Chunks: {node.get('chunk_count', 0):5d} | ", end="")
                print(f"Disk: {node.get('disk_usage', 0):5.1f}%")
            else:
                print(f" Status: {node['status']}")
                if 'error' in node:
                    print(f"    Error: {node['error']}")
        
        # Summary
        print("\n📈 Summary:")
        print(f"  Healthy Nodes: {healthy_nodes}/3")
        print(f"  Total Chunks: {total_chunks}")
        if latency_count > 0:
            print(f"  Average Latency: {avg_latency/latency_count:.2f}ms")
        
        # System Status
        print("\n🔍 System Status:", end=" ")
        if healthy_nodes >= 2:
            print("✓ OPERATIONAL (Quorum available)")
        elif healthy_nodes >= 1:
            print("⚠ DEGRADED (Limited redundancy)")
        else:
            print("✗ CRITICAL (No storage nodes available)")
        
        print("=" * 80)
    
    async def monitor_continuous(self, interval: int = 10):
        """Continuously monitor system and display metrics"""
        logger.info(f"Starting continuous monitoring (interval: {interval}s)")
        logger.info("Press Ctrl+C to stop")
        
        try:
            while True:
                metrics = await self.collect_all_metrics()
                self.metrics_history.append(metrics)
                
                # Keep only last 100 metrics
                if len(self.metrics_history) > 100:
                    self.metrics_history.pop(0)
                
                self.display_metrics(metrics)
                
                await asyncio.sleep(interval)
        
        except KeyboardInterrupt:
            logger.info("\nMonitoring stopped by user")
    
    async def monitor_once(self):
        """Collect and display metrics once"""
        metrics = await self.collect_all_metrics()
        self.display_metrics(metrics)


async def main():
    """Main entry point"""
    monitor = SystemMonitor()
    
    # Check if continuous monitoring is requested
    if len(sys.argv) > 1 and sys.argv[1] == '--continuous':
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        await monitor.monitor_continuous(interval)
    else:
        await monitor.monitor_once()


if __name__ == '__main__':
    asyncio.run(main())
