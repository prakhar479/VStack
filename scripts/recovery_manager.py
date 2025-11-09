#!/usr/bin/env python3
"""
Recovery manager for V-Stack system.
Handles automatic recovery from failures and provides manual recovery tools.
"""

import asyncio
import aiohttp
import sys
import os
import logging
from typing import Dict, List, Optional
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RecoveryManager:
    """Manages system recovery and failure handling"""
    
    def __init__(self):
        self.metadata_url = os.getenv('METADATA_SERVICE_URL', 'http://localhost:8080')
        self.storage_nodes = [
            {'name': 'storage-node-1', 'url': 'http://localhost:8081'},
            {'name': 'storage-node-2', 'url': 'http://localhost:8082'},
            {'name': 'storage-node-3', 'url': 'http://localhost:8083'}
        ]
        self.recovery_actions = []
    
    async def check_service_health(self, url: str, service_name: str) -> bool:
        """Check if a service is healthy"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{url}/health",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    return response.status == 200
        except Exception as e:
            logger.debug(f"{service_name} health check failed: {e}")
            return False
    
    async def detect_failures(self) -> Dict[str, List[str]]:
        """Detect failed services"""
        failures = {
            'metadata_service': [],
            'storage_nodes': []
        }
        
        # Check metadata service
        if not await self.check_service_health(self.metadata_url, 'metadata-service'):
            failures['metadata_service'].append('metadata-service')
            logger.warning("⚠ Metadata service is down")
        
        # Check storage nodes
        for node in self.storage_nodes:
            if not await self.check_service_health(node['url'], node['name']):
                failures['storage_nodes'].append(node['name'])
                logger.warning(f"⚠ {node['name']} is down")
        
        return failures
    
    async def attempt_metadata_recovery(self) -> bool:
        """Attempt to recover metadata service"""
        logger.info("Attempting metadata service recovery...")
        
        # Wait and retry
        for attempt in range(3):
            logger.info(f"Recovery attempt {attempt + 1}/3...")
            await asyncio.sleep(5)
            
            if await self.check_service_health(self.metadata_url, 'metadata-service'):
                logger.info("✓ Metadata service recovered")
                self.recovery_actions.append({
                    'timestamp': datetime.now().isoformat(),
                    'service': 'metadata-service',
                    'action': 'automatic_recovery',
                    'success': True
                })
                return True
        
        logger.error("✗ Failed to recover metadata service")
        self.recovery_actions.append({
            'timestamp': datetime.now().isoformat(),
            'service': 'metadata-service',
            'action': 'automatic_recovery',
            'success': False
        })
        return False
    
    async def attempt_storage_node_recovery(self, node_name: str) -> bool:
        """Attempt to recover a storage node"""
        logger.info(f"Attempting {node_name} recovery...")
        
        node = next((n for n in self.storage_nodes if n['name'] == node_name), None)
        if not node:
            logger.error(f"Unknown node: {node_name}")
            return False
        
        # Wait and retry
        for attempt in range(3):
            logger.info(f"Recovery attempt {attempt + 1}/3...")
            await asyncio.sleep(5)
            
            if await self.check_service_health(node['url'], node_name):
                logger.info(f"✓ {node_name} recovered")
                
                # Re-register with metadata service
                await self.reregister_node(node)
                
                self.recovery_actions.append({
                    'timestamp': datetime.now().isoformat(),
                    'service': node_name,
                    'action': 'automatic_recovery',
                    'success': True
                })
                return True
        
        logger.error(f"✗ Failed to recover {node_name}")
        self.recovery_actions.append({
            'timestamp': datetime.now().isoformat(),
            'service': node_name,
            'action': 'automatic_recovery',
            'success': False
        })
        return False
    
    async def reregister_node(self, node: Dict) -> bool:
        """Re-register a recovered node with metadata service"""
        try:
            logger.info(f"Re-registering {node['name']} with metadata service...")
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.metadata_url}/nodes/{node['name']}/heartbeat",
                    json={
                        "node_url": node['url'],
                        "status": "healthy",
                        "disk_usage": 0.0,
                        "chunk_count": 0
                    },
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        logger.info(f"✓ {node['name']} re-registered successfully")
                        return True
                    else:
                        logger.warning(f"Failed to re-register {node['name']}: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Error re-registering {node['name']}: {e}")
            return False
    
    async def check_quorum(self) -> bool:
        """Check if system has quorum (majority of nodes available)"""
        healthy_count = 0
        for node in self.storage_nodes:
            if await self.check_service_health(node['url'], node['name']):
                healthy_count += 1
        
        has_quorum = healthy_count >= 2
        logger.info(f"Quorum check: {healthy_count}/3 nodes healthy - {'✓ QUORUM' if has_quorum else '✗ NO QUORUM'}")
        return has_quorum
    
    async def perform_recovery(self) -> bool:
        """Perform automatic recovery for detected failures"""
        logger.info("=" * 60)
        logger.info("V-Stack Recovery Manager")
        logger.info("=" * 60)
        
        # Detect failures
        logger.info("\nDetecting failures...")
        failures = await self.detect_failures()
        
        total_failures = len(failures['metadata_service']) + len(failures['storage_nodes'])
        
        if total_failures == 0:
            logger.info("✓ No failures detected. System is healthy.")
            return True
        
        logger.warning(f"\n⚠ Detected {total_failures} failure(s)")
        
        # Attempt recovery
        recovery_success = True
        
        # Recover metadata service first (critical)
        if failures['metadata_service']:
            if not await self.attempt_metadata_recovery():
                logger.error("✗ Critical: Metadata service recovery failed")
                recovery_success = False
        
        # Recover storage nodes
        for node_name in failures['storage_nodes']:
            if not await self.attempt_storage_node_recovery(node_name):
                logger.warning(f"⚠ {node_name} recovery failed")
                # Don't mark as complete failure if we still have quorum
        
        # Check final system state
        logger.info("\nChecking final system state...")
        has_quorum = await self.check_quorum()
        
        if not has_quorum:
            logger.error("✗ System does not have quorum. Manual intervention required.")
            recovery_success = False
        
        # Print recovery summary
        logger.info("\n" + "=" * 60)
        logger.info("Recovery Summary")
        logger.info("=" * 60)
        
        for action in self.recovery_actions:
            status = "✓" if action['success'] else "✗"
            logger.info(f"{status} {action['service']:20s} - {action['action']}")
        
        logger.info("=" * 60)
        
        if recovery_success and has_quorum:
            logger.info("✓ System recovery completed successfully")
            return True
        else:
            logger.error("✗ System recovery incomplete. Manual intervention may be required.")
            return False
    
    async def continuous_monitoring(self, interval: int = 30):
        """Continuously monitor and recover from failures"""
        logger.info(f"Starting continuous recovery monitoring (interval: {interval}s)")
        logger.info("Press Ctrl+C to stop")
        
        try:
            while True:
                await self.perform_recovery()
                await asyncio.sleep(interval)
        
        except KeyboardInterrupt:
            logger.info("\nRecovery monitoring stopped by user")


async def main():
    """Main entry point"""
    manager = RecoveryManager()
    
    if len(sys.argv) > 1 and sys.argv[1] == '--continuous':
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        await manager.continuous_monitoring(interval)
    else:
        success = await manager.perform_recovery()
        sys.exit(0 if success else 1)


if __name__ == '__main__':
    asyncio.run(main())
