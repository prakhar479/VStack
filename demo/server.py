#!/usr/bin/env python3
"""
Demo Web Server - Serves the demo interface and proxies API calls
"""

import asyncio
import logging
import os
import aiohttp
from aiohttp import web, ClientSession
import aiofiles

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DemoServer:
    """Demo web server with API proxy."""
    
    def __init__(self, host='0.0.0.0', port=8085):
        self.host = host
        self.port = port
        self.app = web.Application()
        
        # Service URLs from environment
        self.metadata_url = os.getenv('METADATA_SERVICE_URL', 'http://metadata-service:8080')
        self.uploader_url = os.getenv('UPLOADER_SERVICE_URL', 'http://uploader-service:8084')
        self.client_url = os.getenv('CLIENT_DASHBOARD_URL', 'http://smart-client:8086')
        
        self.setup_routes()
        
    def setup_routes(self):
        """Setup HTTP routes."""
        # Serve static files
        self.app.router.add_get('/', self.serve_index)
        self.app.router.add_get('/consensus', self.serve_consensus)
        self.app.router.add_get('/storage-efficiency', self.serve_storage_efficiency)
        
        # API proxy endpoints
        self.app.router.add_get('/api/health', self.get_system_health)
        self.app.router.add_get('/api/videos', self.list_videos)
        self.app.router.add_get('/api/stats', self.get_stats)
        self.app.router.add_post('/api/upload', self.upload_video)
        
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
            
    async def get_system_health(self, request):
        """Get health status of all services."""
        health_status = {}
        
        async with ClientSession() as session:
            # Check metadata service
            try:
                async with session.get(f'{self.metadata_url}/health', timeout=5) as resp:
                    if resp.status == 200:
                        health_status['metadata'] = await resp.json()
                    else:
                        health_status['metadata'] = {'status': 'unhealthy', 'code': resp.status}
            except Exception as e:
                health_status['metadata'] = {'status': 'error', 'error': str(e)}
                
            # Check uploader service
            try:
                async with session.get(f'{self.uploader_url}/health', timeout=5) as resp:
                    if resp.status == 200:
                        health_status['uploader'] = await resp.json()
                    else:
                        health_status['uploader'] = {'status': 'unhealthy', 'code': resp.status}
            except Exception as e:
                health_status['uploader'] = {'status': 'error', 'error': str(e)}
                
            # Check storage nodes
            storage_nodes = []
            for port in [8081, 8082, 8083]:
                node_url = f'http://storage-node-{port-8080}:8081'
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
                async with session.get(f'{self.metadata_url}/videos') as resp:
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
                async with session.get(f'{self.metadata_url}/stats') as resp:
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
            
    async def upload_video(self, request):
        """Proxy video upload to uploader service."""
        try:
            # This is a simplified proxy - in production you'd stream the upload
            reader = await request.multipart()
            
            async with ClientSession() as session:
                data = aiohttp.FormData()
                
                async for field in reader:
                    if field.name == 'video':
                        data.add_field('video', 
                                     await field.read(),
                                     filename=field.filename,
                                     content_type=field.content_type)
                    elif field.name == 'title':
                        data.add_field('title', await field.text())
                        
                async with session.post(f'{self.uploader_url}/upload', data=data) as resp:
                    result = await resp.json()
                    return web.json_response(result, status=resp.status)
                    
        except Exception as e:
            logger.error(f'Error uploading video: {e}')
            return web.json_response({'error': str(e)}, status=500)
            
    async def start(self):
        """Start the demo server."""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        
        logger.info(f"Demo server started at http://{self.host}:{self.port}")
        logger.info(f"Metadata Service: {self.metadata_url}")
        logger.info(f"Uploader Service: {self.uploader_url}")
        logger.info(f"Client Dashboard: {self.client_url}")
        
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
