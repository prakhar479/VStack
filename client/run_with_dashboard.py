#!/usr/bin/env python3
"""
Run Smart Client with Dashboard - Integrated script to run client and dashboard together
"""

import asyncio
import logging
import sys
import signal

from main import SmartClient
from dashboard_server import DashboardServer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IntegratedClient:
    """Runs smart client and dashboard server together."""
    
    def __init__(self, metadata_service_url: str = "http://localhost:8080", dashboard_port: int = 8888):
        """
        Initialize integrated client.
        
        Args:
            metadata_service_url: URL of the metadata service
            dashboard_port: Port for dashboard server
        """
        self.client = SmartClient(metadata_service_url)
        self.dashboard = DashboardServer(self.client, port=dashboard_port)
        self.running = False
        
    async def start(self, video_id: str):
        """
        Start both client and dashboard.
        
        Args:
            video_id: ID of the video to play
        """
        logger.info("Starting V-Stack Smart Client with Dashboard")
        
        # Initialize client
        if not await self.client.initialize():
            logger.error("Failed to initialize Smart Client")
            return False
            
        # Start dashboard server
        await self.dashboard.start()
        
        # Start video playback
        self.running = True
        playback_task = asyncio.create_task(self.client.play_video(video_id))
        
        # Print status periodically
        status_task = asyncio.create_task(self._status_loop())
        
        try:
            await asyncio.gather(playback_task, status_task)
        except asyncio.CancelledError:
            logger.info("Shutting down...")
            
        return True
        
    async def _status_loop(self):
        """Print status updates periodically."""
        while self.running and self.client.playing:
            await asyncio.sleep(10.0)
            
            status = self.client.get_status()
            
            logger.info("="*60)
            logger.info("STATUS UPDATE")
            logger.info(f"Buffer: {status['buffer']['buffer_level_sec']:.1f}s / {status['buffer']['target_buffer_sec']}s")
            logger.info(f"Chunks Played: {status['buffer_stats']['total_chunks_played']}")
            logger.info(f"Rebuffering Events: {status['buffer_stats']['rebuffering_events']}")
            logger.info(f"Downloads: {status['scheduler_stats']['total_downloads']} (Success: {status['scheduler_stats']['success_rate']*100:.1f}%)")
            logger.info("="*60)
            
    async def stop(self):
        """Stop client and dashboard."""
        logger.info("Stopping client...")
        self.running = False
        await self.client.stop()
        
        if self.dashboard.collection_task:
            self.dashboard.collection_task.cancel()
            
        logger.info("Stopped")


async def main():
    """Main entry point."""
    # Get video ID from command line or use default
    video_id = sys.argv[1] if len(sys.argv) > 1 else "test-video-001"
    
    # Get metadata service URL from environment or use default
    import os
    metadata_url = os.getenv('METADATA_SERVICE_URL', 'http://localhost:8080')
    dashboard_port = int(os.getenv('DASHBOARD_PORT', '8888'))
    
    # Create integrated client
    integrated = IntegratedClient(metadata_url, dashboard_port)
    
    # Setup signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        logger.info("Received interrupt signal")
        asyncio.create_task(integrated.stop())
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Start client and dashboard
        success = await integrated.start(video_id)
        
        if success:
            # Print final statistics
            logger.info("\n" + "="*60)
            logger.info("PLAYBACK COMPLETE - FINAL STATISTICS")
            logger.info("="*60)
            integrated.client.print_status()
            
            # Print dashboard URL
            logger.info(f"\nDashboard available at: http://localhost:{dashboard_port}")
            logger.info("Press Ctrl+C to exit")
            
            # Keep dashboard running
            await asyncio.Event().wait()
            
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        await integrated.stop()
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await integrated.stop()


if __name__ == "__main__":
    asyncio.run(main())
