#!/usr/bin/env python3
"""
Dashboard Server - Provides API endpoints and serves the dashboard UI
"""

import asyncio
import aiohttp
import json
import logging
import time
import os
from aiohttp import web
from typing import Dict, Optional

from config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Collects and aggregates metrics from the SmartClient.
    """
    
    def __init__(self, client):
        self.client = client
        self.history = []
        self.max_history = 3600  # 1 hour of history at 1s interval
        
    async def collect_metrics(self):
        """Collect current metrics snapshot."""
        if not self.client:
            return
            
        try:
            status = self.client.get_status()
            
            snapshot = {
                'timestamp': time.time(),
                'buffer_level': status['buffer']['buffer_level_sec'],
                'buffer_health': status['buffer']['buffer_health_percent'],
                'download_rate': self._calculate_download_rate(status),
                'active_downloads': status['scheduler_stats']['active_downloads'],
                'node_scores': status['node_scores']
            }
            
            self.history.append(snapshot)
            
            # Prune history
            if len(self.history) > self.max_history:
                self.history = self.history[-self.max_history:]
                
        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")
            
    def _calculate_download_rate(self, status: Dict) -> float:
        """Calculate aggregate download rate across all nodes."""
        total_rate = 0.0
        for node_stats in status.get('network_stats', []):
            if node_stats and 'bandwidth_mbps' in node_stats:
                # Use current bandwidth if available, otherwise 0
                current = node_stats['bandwidth_mbps'].get('current')
                if current:
                    total_rate += current
        return total_rate
        
    def get_history(self) -> list:
        """Get metrics history."""
        return self.history


class DashboardServer:
    """
    Web server for the client dashboard.
    """
    
    def __init__(self, client, port: int = None):
        self.client = client
        self.port = port or config.DASHBOARD_PORT
        self.app = web.Application()
        self.runner = None
        self.site = None
        self.metrics_collector = MetricsCollector(client)
        self.collect_task = None
        
        # Cache dashboard HTML and validate
        self.dashboard_html = None
        self.dashboard_path = os.path.join(os.path.dirname(__file__), 'dashboard.html')
        
        # Validate dashboard file exists
        if not os.path.exists(self.dashboard_path):
            logger.warning(f"Dashboard HTML not found at {self.dashboard_path}")
            logger.warning("Dashboard UI will not be available, only API endpoints")
        
        self._setup_routes()
        
    def _setup_routes(self):
        """Setup API routes."""
        self.app.router.add_get('/', self.handle_index)
        self.app.router.add_get('/health', self.handle_health)
        self.app.router.add_get('/api/status', self.handle_status)
        self.app.router.add_get('/api/history', self.handle_history)
        self.app.router.add_get('/api/stream/{video_id}', self.handle_stream)
        self.app.router.add_post('/api/control', self.handle_control)
            
    async def start(self):
        """Start the dashboard server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, '0.0.0.0', self.port)
        await self.site.start()
        
        # Start metrics collection
        self.collect_task = asyncio.create_task(self._collection_loop())
        
        logger.info(f"Dashboard server started on http://localhost:{self.port}")
        
    async def stop(self):
        """Stop the dashboard server."""
        if self.collect_task:
            self.collect_task.cancel()
            try:
                await self.collect_task
            except asyncio.CancelledError:
                pass
                
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
            
        logger.info("Dashboard server stopped")
        
    async def _collection_loop(self):
        """Background task to collect metrics."""
        while True:
            try:
                await self.metrics_collector.collect_metrics()
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in metrics collection: {e}")
                await asyncio.sleep(1.0)
                
    async def handle_index(self, request):
        """Serve the dashboard HTML."""
        try:
            # Load and cache HTML if not already loaded
            if self.dashboard_html is None:
                if os.path.exists(self.dashboard_path):
                    with open(self.dashboard_path, 'r') as f:
                        self.dashboard_html = f.read()
                else:
                    return web.Response(text="Dashboard HTML not found", status=404)
            
            return web.Response(text=self.dashboard_html, content_type='text/html')
        except Exception as e:
            logger.error(f"Error serving dashboard: {e}")
            return web.Response(text="Internal Server Error", status=500)
            
    async def handle_status(self, request):
        """Return current client status."""
        if not self.client:
            return web.json_response({'error': 'Client not initialized'}, status=503)
            
        try:
            status = self.client.get_status()
            return web.json_response(status)
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return web.json_response({'error': str(e)}, status=500)
            
    async def handle_history(self, request):
        """Return metrics history."""
        try:
            history = self.metrics_collector.get_history()
            return web.json_response({'history': history})
        except Exception as e:
            logger.error(f"Error getting history: {e}")
            return web.json_response({'error': str(e)}, status=500)
            
    async def handle_health(self, request):
        """Health check endpoint for k8s/docker."""
        if not self.client:
            return web.json_response({'status': 'unhealthy', 'reason': 'Client not initialized'}, status=503)
        
        # Check if client is ready
        try:
            status = self.client.get_status()
            is_healthy = status.get('is_initialized', False)
            
            if is_healthy:
                return web.json_response({'status': 'healthy'}, status=200)
            else:
                return web.json_response({'status': 'unhealthy', 'reason': 'Client not ready'}, status=503)
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return web.json_response({'status': 'unhealthy', 'error': str(e)}, status=503)
    
    async def handle_control(self, request):
        """Handle control commands (play, stop, etc.)."""
        if not self.client:
            return web.json_response({'error': 'Client not initialized'}, status=503)
            
        try:
            # Validate JSON
            try:
                data = await request.json()
            except json.JSONDecodeError:
                return web.json_response({'error': 'Invalid JSON'}, status=400)
            
            # Validate command field
            command = data.get('command')
            if not command or not isinstance(command, str):
                return web.json_response({'error': 'Missing or invalid command field'}, status=400)
            
            if command == 'play':
                video_id = data.get('video_id')
                if not video_id or not isinstance(video_id, str):
                    return web.json_response({'error': 'Missing or invalid video_id'}, status=400)
                
                # Validate video_id format (optional but recommended)
                if not video_id.strip():
                    return web.json_response({'error': 'video_id cannot be empty'}, status=400)
                    
                # Note: Actual playback implementation needs refactoring (see Priority 2)
                return web.json_response({
                    'status': 'acknowledged',
                    'note': 'Playback API not yet implemented - use main.py directly'
                })
                
            elif command == 'stop':
                await self.client.stop()
                return web.json_response({'status': 'stopped'})
                
            else:
                return web.json_response({
                    'error': f'Unknown command: {command}',
                    'valid_commands': ['play', 'stop']
                }, status=400)
                
        except Exception as e:
            logger.error(f"Error handling control command: {e}", exc_info=True)
            return web.json_response({'error': 'Internal server error'}, status=500)

    async def handle_stream(self, request):
        """
        Stream video chunks to the client.
        """
        video_id = request.match_info['video_id']
        if not self.client:
            return web.Response(status=503, text="Client not initialized")
            
        logger.info(f"Starting stream for video {video_id}")
        
        # Start streaming mode in client
        success = await self.client.start_stream(video_id)
        if not success:
            return web.Response(status=404, text="Video not found or failed to start")
            
        # Create streaming response
        response = web.StreamResponse(
            status=200,
            reason='OK',
            headers={
                'Content-Type': 'video/mp4',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive'
            }
        )
        
        # Prepare response
        await response.prepare(request)
        
        try:
            while True:
                # Get next chunk
                chunk_data = await self.client.get_stream_chunk()
                
                if chunk_data is None:
                    # End of stream
                    break
                    
                # Write chunk to stream
                await response.write(chunk_data)
                
                # Yield to event loop
                await asyncio.sleep(0)
                
        except asyncio.CancelledError:
            logger.info("Stream cancelled by client")
        except Exception as e:
            logger.error(f"Error during streaming: {e}")
        finally:
            # Stop client when stream ends or disconnects
            await self.client.stop()
            
        return response
