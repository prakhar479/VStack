#!/usr/bin/env python3
"""
Demo Web Server - Serves the demo interface and proxies API calls
"""

import asyncio
import logging
import os
import json
import aiohttp
from aiohttp import web, ClientSession
import aiofiles
from dotenv import load_dotenv

# Import benchmark and chaos modules (will be refactored to support real system)
# Note: These imports assume the files are in the same directory or python path
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
# We will import these dynamically or assume they exist. 
# For now, we'll import them, but we need to make sure the files exist and have the classes.
# Since I haven't refactored them yet, this might fail if I run it immediately.
# But I will refactor them next.
from benchmark import PerformanceBenchmark
from chaos_test import ChaosEngineer

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Config:
    """Configuration for the Demo Server."""
    def __init__(self):
        self.host = os.getenv('DEMO_HOST', '0.0.0.0')
        self.port = int(os.getenv('DEMO_PORT', 8085))
        
        # Service URLs
        self.metadata_url = os.getenv('METADATA_SERVICE_URL', 'http://localhost:8080')
        self.uploader_url = os.getenv('UPLOADER_SERVICE_URL', 'http://localhost:8084')
        self.client_url = os.getenv('CLIENT_DASHBOARD_URL', 'http://localhost:8086')
        
        # Storage Nodes (dynamic discovery would be better, but config is a good start)
        self.storage_nodes = [
            os.getenv('STORAGE_NODE_1_URL', 'http://localhost:8081'),
            os.getenv('STORAGE_NODE_2_URL', 'http://localhost:8082'),
            os.getenv('STORAGE_NODE_3_URL', 'http://localhost:8083'),
        ]

    def to_dict(self):
        return {
            'metadata_url': self.metadata_url,
            'uploader_url': self.uploader_url,
            'client_url': self.client_url,
            'storage_nodes': self.storage_nodes
        }


class DemoServer:
    """Demo web server with API proxy."""
    
    def __init__(self):
        self.config = Config()
        self.app = web.Application()
        self.setup_routes()
        self.benchmark_running = False
        self.chaos_running = False
        
    def setup_routes(self):
        """Setup HTTP routes."""
        # Serve static files
        self.app.router.add_get('/', self.serve_index)
        self.app.router.add_get('/consensus.html', self.serve_consensus)
        self.app.router.add_get('/storage_efficiency.html', self.serve_storage_efficiency)
        
        
        # API proxy endpoints
        self.app.router.add_get('/api/health', self.get_system_health)
        self.app.router.add_get('/api/videos', self.list_videos)
        self.app.router.add_get('/api/stats', self.get_stats)
        self.app.router.add_get('/api/storage/overhead', self.get_storage_overhead)
        self.app.router.add_post('/api/upload', self.upload_video)
        
        # New API endpoints
        self.app.router.add_get('/api/config', self.get_config)
        self.app.router.add_post('/api/benchmark/run', self.run_benchmark)
        self.app.router.add_post('/api/chaos/run', self.run_chaos)
        
        # Client Dashboard Proxy
        self.app.router.add_get('/client', self.serve_client_dashboard)
        self.app.router.add_get('/client/', self.serve_client_dashboard)
        self.app.router.add_get('/client/api/{path:.+}', self.proxy_client_api)
        
    async def serve_index(self, request):
        """Serve the main demo page."""
        html_path = os.path.join(os.path.dirname(__file__), 'index.html')
        try:
            async with aiofiles.open(html_path, 'r') as f:
                content = await f.read()
            return web.Response(text=content, content_type='text/html')
        except FileNotFoundError:
            return web.Response(text='Demo page not found', status=404)
            
    async def serve_consensus(self, request):
        """Serve consensus visualization page."""
        html_path = os.path.join(os.path.dirname(__file__), 'consensus_visualization.html')
        try:
            async with aiofiles.open(html_path, 'r') as f:
                content = await f.read()
            return web.Response(text=content, content_type='text/html')
        except FileNotFoundError:
            return web.Response(text='Consensus visualization not found', status=404)
            
    async def serve_storage_efficiency(self, request):
        """Serve storage efficiency dashboard."""
        html_path = os.path.join(os.path.dirname(__file__), 'storage_efficiency_dashboard.html')
        try:
            async with aiofiles.open(html_path, 'r') as f:
                content = await f.read()
            return web.Response(text=content, content_type='text/html')
        except FileNotFoundError:
            return web.Response(text='Storage efficiency dashboard not found', status=404)

    async def get_config(self, request):
        """Get system configuration."""
        return web.json_response(self.config.to_dict())
            
    async def get_system_health(self, request):
        """Get health status of all services."""
        health_status = {}
        
        async with ClientSession() as session:
            # Check metadata service
            try:
                async with session.get(f'{self.config.metadata_url}/health', timeout=5) as resp:
                    if resp.status == 200:
                        health_status['metadata'] = await resp.json()
                    else:
                        health_status['metadata'] = {'status': 'unhealthy', 'code': resp.status}
            except Exception as e:
                health_status['metadata'] = {'status': 'error', 'error': str(e)}
                
            # Check uploader service
            try:
                async with session.get(f'{self.config.uploader_url}/health', timeout=5) as resp:
                    if resp.status == 200:
                        health_status['uploader'] = await resp.json()
                    else:
                        health_status['uploader'] = {'status': 'unhealthy', 'code': resp.status}
            except Exception as e:
                health_status['uploader'] = {'status': 'error', 'error': str(e)}
                
            # Check storage nodes
            storage_nodes = []
            for node_url in self.config.storage_nodes:
                try:
                    async with session.get(f'{node_url}/health', timeout=5) as resp:
                        if resp.status == 200:
                            node_health = await resp.json()
                            node_health['url'] = node_url
                            storage_nodes.append(node_health)
                except Exception as e:
                    storage_nodes.append({
                        'url': node_url,
                        'status': 'error',
                        'error': str(e)
                    })
                    
            health_status['storage_nodes'] = storage_nodes
            
        return web.json_response(health_status)
        
    async def list_videos(self, request):
        """List all videos from metadata service."""
        try:
            async with ClientSession() as session:
                async with session.get(f'{self.config.metadata_url}/videos') as resp:
                    if resp.status == 200:
                        videos = await resp.json()
                        return web.json_response(videos)
                    else:
                        return web.json_response(
                            {'error': f'Failed to fetch videos: {resp.status}'},
                            status=resp.status
                        )
        except Exception as e:
            logger.error(f'Error listing videos: {e}')
            return web.json_response({'error': str(e)}, status=500)
            
    async def get_stats(self, request):
        """Get system statistics."""
        try:
            async with ClientSession() as session:
                async with session.get(f'{self.config.metadata_url}/stats') as resp:
                    if resp.status == 200:
                        stats = await resp.json()
                        return web.json_response(stats)
                    else:
                        return web.json_response(
                            {'error': f'Failed to fetch stats: {resp.status}'},
                            status=resp.status
                        )
        except Exception as e:
            logger.error(f'Error getting stats: {e}')
            return web.json_response({'error': str(e)}, status=500)

    async def get_storage_overhead(self, request):
        """Get storage overhead statistics."""
        try:
            async with ClientSession() as session:
                async with session.get(f'{self.config.metadata_url}/storage/overhead') as resp:
                    if resp.status == 200:
                        stats = await resp.json()
                        return web.json_response(stats)
                    else:
                        return web.json_response(
                            {'error': f'Failed to fetch storage stats: {resp.status}'},
                            status=resp.status
                        )
        except Exception as e:
            logger.error(f'Error getting storage stats: {e}')
            return web.json_response({'error': str(e)}, status=500)
            
    async def upload_video(self, request):
        """Proxy video upload to uploader service using streaming."""
        try:
            reader = await request.multipart()
            
            # We need to collect the fields and stream the video
            video_field = None
            title = "Untitled"
            
            # Read fields
            async for field in reader:
                if field.name == 'title':
                    title = await field.text()
                elif field.name == 'video':
                    video_field = field
                    # Don't break - we need to keep the field for streaming
                    filename = field.filename or 'video.mp4'
                    content_type = field.headers.get('Content-Type', 'video/mp4')
                    break
            
            if not video_field:
                return web.json_response({'error': 'No video file found'}, status=400)

            # Stream to uploader service using FormData
            async with ClientSession() as session:
                # Create a new FormData with proper multipart encoding
                data = aiohttp.FormData()
                data.add_field('title', title)
                data.add_field('video', 
                              video_field,  # Stream the field directly
                              filename=filename,
                              content_type=content_type)
                
                # Post with streaming
                async with session.post(f'{self.config.uploader_url}/upload', data=data) as resp:
                    if resp.content_type == 'application/json':
                        result = await resp.json()
                    else:
                        text = await resp.text()
                        result = {'error': f'Unexpected response: {text}'}
                    
                    return web.json_response(result, status=resp.status)
                    
        except Exception as e:
            logger.error(f'Error uploading video: {e}', exc_info=True)
            return web.json_response({'error': str(e)}, status=500)

    async def run_benchmark(self, request):
        """Run the benchmark suite."""
        if self.benchmark_running:
            return web.json_response({'error': 'Benchmark already running'}, status=409)
            
        self.benchmark_running = True
        try:
            # Initialize benchmark with real system config
            benchmark = PerformanceBenchmark(
                metadata_url=self.config.metadata_url,
                storage_nodes=self.config.storage_nodes
            )
            report = await benchmark.run_all_benchmarks()
            return web.json_response(report)
        except Exception as e:
            logger.error(f"Benchmark failed: {e}", exc_info=True)
            return web.json_response({'error': str(e)}, status=500)
        finally:
            self.benchmark_running = False

    async def run_chaos(self, request):
        """Run the chaos/resilience test."""
        if self.chaos_running:
            return web.json_response({'error': 'Chaos test already running'}, status=409)
            
        self.chaos_running = True
        try:
            # Parse duration from request
            data = await request.json()
            duration = data.get('duration', 60)
            
            chaos = ChaosEngineer(self.config.storage_nodes)
            report = await chaos.run_chaos_test(duration_sec=duration)
            return web.json_response(report)
        except Exception as e:
            logger.error(f"Chaos test failed: {e}", exc_info=True)
            return web.json_response({'error': str(e)}, status=500)
        finally:
            self.chaos_running = False
            
    async def serve_client_dashboard(self, request):
        """Proxy the client dashboard HTML."""
        try:
            # Ensure trailing slash for relative links to work
            if not request.path.endswith('/'):
                return web.HTTPFound('/client/')
                
            async with ClientSession() as session:
                async with session.get(f'{self.config.client_url}/') as resp:
                    if resp.status == 200:
                        content = await resp.text()
                        return web.Response(text=content, content_type='text/html')
                    else:
                        return web.Response(text='Client dashboard not found', status=resp.status)
        except Exception as e:
            logger.error(f'Error serving client dashboard: {e}')
            return web.Response(text=f'Error connecting to client: {str(e)}', status=500)

    async def proxy_client_api(self, request):
        """Proxy client API calls."""
        path = request.match_info['path']
        try:
            async with ClientSession() as session:
                async with session.get(f'{self.config.client_url}/api/{path}') as resp:
                    content = await resp.read()
                    return web.Response(body=content, status=resp.status, content_type=resp.content_type)
        except Exception as e:
            logger.error(f'Error proxying client API: {e}')
            return web.json_response({'error': str(e)}, status=500)
            
    async def start(self):
        """Start the demo server."""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.config.host, self.config.port)
        await site.start()
        
        logger.info(f"Demo server started at http://{self.config.host}:{self.config.port}")
        logger.info(f"Metadata Service: {self.config.metadata_url}")
        logger.info(f"Uploader Service: {self.config.uploader_url}")
        logger.info(f"Client Dashboard: {self.config.client_url}")
        
    async def run(self):
        """Run the demo server indefinitely."""
        await self.start()
        
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass


async def main():
    """Main entry point."""
    server = DemoServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
