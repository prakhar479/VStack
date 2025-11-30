#!/usr/bin/env python3
"""
Client Service - Main entry point for the client-side service.
Exposes the SmartClient functionality via HTTP API.
"""

import asyncio
import logging
import os
import sys
from aiohttp import web

from config import config
from main import SmartClient
from dashboard_server import DashboardServer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ClientService:
    """
    Main service that runs the SmartClient and DashboardServer.
    """
    
    def __init__(self):
        self.client = SmartClient()
        self.dashboard = DashboardServer(self.client, port=config.CLIENT_SERVICE_PORT)
        
    async def start(self):
        """Start the service."""
        # Initialize client
        if not await self.client.initialize():
            logger.error("Failed to initialize SmartClient")
            return
            
        logger.info("SmartClient initialized")
        
        # Start dashboard/API server
        await self.dashboard.start()
        
        # Keep running
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
            
    async def stop(self):
        """Stop the service."""
        await self.dashboard.stop()
        await self.client.stop()


async def main():
    """Main entry point."""
    service = ClientService()
    
    try:
        await service.start()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Service error: {e}")
    finally:
        await service.stop()


if __name__ == "__main__":
    asyncio.run(main())
