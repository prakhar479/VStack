#!/usr/bin/env python3
"""
Run Smart Client with Dashboard - Integrated script to run client and dashboard together
"""

import asyncio
import logging
import sys
import signal
import argparse

from main import SmartClient
from dashboard_server import DashboardServer
from config import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IntegratedClient:
    """Runs smart client and dashboard server together."""
    
    def __init__(self, metadata_service_url: str = None, dashboard_port: int = None):
        """
        Initialize integrated client.
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
            
            try:
                status = self.client.get_status()
                
                logger.info("="*60)
                logger.info("STATUS UPDATE")
                logger.info(f"Buffer: {status['buffer']['buffer_level_sec']:.1f}s / {status['buffer']['target_buffer_sec']}s")
                logger.info(f"Chunks Played: {status['buffer_stats']['total_chunks_played']}")
                logger.info(f"Rebuffering Events: {status['buffer_stats']['rebuffering_events']}")
                logger.info(f"Downloads: {status['scheduler_stats']['total_downloads']} (Success: {status['scheduler_stats']['success_rate']*100:.1f}%)")
                logger.info("="*60)
            except Exception as e:
                logger.error(f"Error in status loop: {e}")
            
    async def stop(self):
        """Stop client and dashboard."""
        logger.info("Stopping client...")
        self.running = False
        await self.client.stop()
        await self.dashboard.stop()
        logger.info("Stopped")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="V-Stack Smart Client with Dashboard")
    parser.add_argument("video_id", nargs="?", default="test-video-001", help="ID of the video to play")
    parser.add_argument("--metadata-url", help="URL of the metadata service")
    parser.add_argument("--port", type=int, help="Port for dashboard server")
    args = parser.parse_args()
    
    # Create integrated client
    integrated = IntegratedClient(
        metadata_service_url=args.metadata_url,
        dashboard_port=args.port
    )
    
    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    
    def signal_handler():
        logger.info("Received interrupt signal")
        asyncio.create_task(integrated.stop())
        
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    try:
        # Start client and dashboard
        success = await integrated.start(args.video_id)
        
        if success:
            # Print final statistics
            logger.info("\n" + "="*60)
            logger.info("PLAYBACK COMPLETE - FINAL STATISTICS")
            logger.info("="*60)
            integrated.client.print_status()
            
            # Print dashboard URL
            port = args.port or config.DASHBOARD_PORT
            logger.info(f"\nDashboard available at: http://localhost:{port}")
            logger.info("Press Ctrl+C to exit")
            
            # Keep dashboard running
            await asyncio.Event().wait()
            
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
    finally:
        await integrated.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
