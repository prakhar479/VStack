#!/usr/bin/env python3
"""
Client Service - Web server for smart client dashboard and API
"""

import asyncio
import logging
import os
import sys
from aiohttp import web

# Add parent directory to path for shared config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config import SmartClientConfig, validate_config
    config = SmartClientConfig.from_env()
    if not validate_config(config):
        logging.error("Configuration validation failed!")
        sys.exit(1)
except ImportError:
    # Fallback configuration
    logging.basicConfig(level=logging.INFO)
    config = None

logger = logging.getLogger(__name__)

from main import SmartClient
from dashboard_server import DashboardServer


class ClientService:
    """Client service with web dashboard and API"""
    
    def __init__(self, port=8083):
        self.port = port
        self.app = web.Application()
        self.smart_client = None
        self.dashboard_server = None
        self.setup_routes()
    
    def setup_routes(self):
        """Setup HTTP routes"""
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_get('/api/status', self.get_status)
        self.app.router.add_get('/', self.serve_dashboard)
    
    async def health_check(self, request):
        """Health check endpoint"""
        health = {
            'status': 'healthy',
            'service': 'smart-client',
            'port': self.port
        }
        return web.json_response(health)
    
    async def get_status(self, request):
        """Get client status"""
        if self.smart_client:
            try:
                status = self.smart_client.get_status()
                return web.json_response(status)
            except Exception as e:
                logger.error(f"Error getting status: {e}")
                return web.json_response({'error': str(e)}, status=500)
        else:
            return web.json_response({'status': 'not_initialized'})
    
    async def serve_dashboard(self, request):
        """Serve dashboard HTML"""
        dashboard_path = os.path.join(os.path.dirname(__file__), 'dashboard.html')
        
        try:
            with open(dashboard_path, 'r') as f:
                html_content = f.read()
            return web.Response(text=html_content, content_type='text/html')
        except FileNotFoundError:
            return web.Response(
                text='<h1>Smart Client Dashboard</h1><p>Dashboard coming soon...</p>',
                content_type='text/html'
            )
    
    async def start(self):
        """Start the service"""
        logger.info(f"Starting Smart Client Service on port {self.port}...")
        
        # Initialize smart client (but don't start playback)
        metadata_url = os.getenv('METADATA_SERVICE_URL', 'http://metadata-service:8080')
        self.smart_client = SmartClient(metadata_url)
        
        # Start web server
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()
        
        logger.info(f"Smart Client Service started at http://0.0.0.0:{self.port}")
        logger.info(f"Health check: http://localhost:{self.port}/health")
        logger.info(f"Dashboard: http://localhost:{self.port}/")
        
        # Keep running
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass


async def main():
    """Main entry point"""
    port = int(os.getenv('PORT', '8083'))
    service = ClientService(port=port)
    await service.start()


if __name__ == "__main__":
    asyncio.run(main())
