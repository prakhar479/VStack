#!/usr/bin/env python3
"""
Consensus Demo Server - Serves the interactive ChunkPaxos visualization
"""

import asyncio
import logging
from aiohttp import web
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConsensusDemoServer:
    """HTTP server for consensus visualization."""
    
    def __init__(self, host='0.0.0.0', port=8889):
        """
        Initialize consensus demo server.
        
        Args:
            host: Host to bind to
            port: Port to listen on
        """
        self.host = host
        self.port = port
        self.app = web.Application()
        self.setup_routes()
        
    def setup_routes(self):
        """Setup HTTP routes."""
        self.app.router.add_get('/', self.serve_visualization)
        self.app.router.add_get('/api/scenarios', self.get_scenarios)
        
    async def serve_visualization(self, request):
        """Serve the consensus visualization HTML page."""
        viz_path = os.path.join(os.path.dirname(__file__), 'consensus_visualization.html')
        
        try:
            with open(viz_path, 'r') as f:
                html_content = f.read()
            return web.Response(text=html_content, content_type='text/html')
        except FileNotFoundError:
            return web.Response(text='Visualization not found', status=404)
            
    async def get_scenarios(self, request):
        """Get available consensus scenarios."""
        scenarios = {
            'normal': {
                'name': 'Normal Operation',
                'description': 'Standard consensus with all nodes healthy',
                'steps': 5
            },
            'conflict': {
                'name': 'Concurrent Uploaders',
                'description': 'Two uploaders competing with ballot numbers',
                'steps': 6
            },
            'failure': {
                'name': 'Node Failure',
                'description': 'Consensus with one node down (quorum still works)',
                'steps': 5
            }
        }
        
        return web.json_response(scenarios)
        
    async def start(self):
        """Start the demo server."""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        
        logger.info("="*60)
        logger.info("ChunkPaxos Consensus Visualization Server Started")
        logger.info("="*60)
        logger.info(f"Server running at: http://{self.host}:{self.port}")
        logger.info(f"Open http://localhost:{self.port} in your browser")
        logger.info("")
        logger.info("Available scenarios:")
        logger.info("  1. Normal Operation - Standard consensus flow")
        logger.info("  2. Concurrent Uploaders - Conflict resolution with ballot numbers")
        logger.info("  3. Node Failure - Consensus with minority node failure")
        logger.info("="*60)
        
    async def run(self):
        """Run the demo server indefinitely."""
        await self.start()
        
        # Keep running
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass


async def main():
    """Main entry point for consensus demo server."""
    import sys
    
    # Get port from command line or use default
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8889
    
    # Create and start server
    server = ConsensusDemoServer(port=port)
    
    try:
        await server.run()
    except KeyboardInterrupt:
        logger.info("\nServer stopped by user")


if __name__ == "__main__":
    asyncio.run(main())
