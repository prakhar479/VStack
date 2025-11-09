#!/usr/bin/env python3
"""
Health monitoring system for V-Stack storage nodes
"""

import asyncio
import httpx
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json

from database import DatabaseManager
from models import NodeStatus

logger = logging.getLogger(__name__)

class HealthMonitor:
    """
    Monitors storage node health through heartbeats and active probing.
    Automatically discovers new nodes and marks unhealthy nodes as down.
    """
    
    def __init__(self, db_manager: DatabaseManager, 
                 heartbeat_timeout_sec: int = 60,
                 probe_interval_sec: int = 30):
        self.db = db_manager
        self.heartbeat_timeout = heartbeat_timeout_sec
        self.probe_interval = probe_interval_sec
        self.monitoring = False
        self.monitor_task = None
    
    async def start_monitoring(self):
        """Start background health monitoring"""
        if self.monitoring:
            return
        
        self.monitoring = True
        self.monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Health monitoring started")
    
    async def stop_monitoring(self):
        """Stop background health monitoring"""
        self.monitoring = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Health monitoring stopped")
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.monitoring:
            try:
                # Mark nodes as unhealthy if no recent heartbeat
                await self._mark_unhealthy_nodes()
                
                # Probe all known nodes for health
                await self._probe_all_nodes()
                
                # Sleep until next check
                await asyncio.sleep(self.probe_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitoring error: {e}")
                await asyncio.sleep(self.probe_interval)
    
    async def _mark_unhealthy_nodes(self):
        """Mark nodes as unhealthy if they haven't sent heartbeat recently"""
        try:
            cutoff_time = datetime.now() - timedelta(seconds=self.heartbeat_timeout)
            
            conn = await self.db.get_connection()
            
            # Get nodes that haven't sent heartbeat recently
            cursor = await conn.execute("""
                SELECT node_id, node_url, status 
                FROM storage_nodes 
                WHERE datetime(last_heartbeat) < datetime(?)
                AND status != 'down'
            """, (cutoff_time.isoformat(),))
            stale_nodes = await cursor.fetchall()
            await cursor.close()
            
            # Mark them as down
            for node_id, node_url, current_status in stale_nodes:
                await conn.execute("""
                    UPDATE storage_nodes 
                    SET status = 'down'
                    WHERE node_id = ?
                """, (node_id,))
                
                logger.warning(f"Marked node {node_id} ({node_url}) as down - no heartbeat")
            
            await conn.commit()
            
            if stale_nodes:
                logger.info(f"Marked {len(stale_nodes)} nodes as unhealthy")
            
            return len(stale_nodes)
        except Exception as e:
            logger.error(f"Failed to mark unhealthy nodes: {e}")
            return 0
    
    async def _probe_all_nodes(self):
        """Actively probe all known nodes for health"""
        try:
            # Get all registered nodes
            conn = await self.db.get_connection()
            cursor = await conn.execute("""
                SELECT node_id, node_url, status 
                FROM storage_nodes
            """)
            nodes = await cursor.fetchall()
            await cursor.close()
            
            # Probe each node
            probe_tasks = [
                self._probe_single_node(node_id, node_url, current_status)
                for node_id, node_url, current_status in nodes
            ]
            
            if probe_tasks:
                await asyncio.gather(*probe_tasks, return_exceptions=True)
                
        except Exception as e:
            logger.error(f"Failed to probe nodes: {e}")
    
    async def _probe_single_node(self, node_id: str, node_url: str, current_status: str):
        """Probe a single node for health"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{node_url}/health")
                
                if response.status_code == 200:
                    # Node is responding - update status if needed
                    if current_status == 'down':
                        await self._mark_node_recovered(node_id, node_url)
                    
                    # Extract health info if available
                    try:
                        health_data = response.json()
                        disk_usage = health_data.get('disk_usage', 0.0)
                        chunk_count = health_data.get('chunk_count', 0)
                        
                        # Update stats without changing heartbeat timestamp
                        await self._update_node_stats(node_id, disk_usage, chunk_count)
                        
                    except (json.JSONDecodeError, KeyError):
                        # Health endpoint doesn't return expected format
                        pass
                        
                else:
                    # Node not responding properly
                    if current_status != 'down':
                        logger.warning(f"Node {node_id} health check failed: HTTP {response.status_code}")
                        
        except Exception as e:
            # Node is unreachable
            if current_status != 'down':
                logger.debug(f"Node {node_id} probe failed: {e}")
    
    async def _mark_node_recovered(self, node_id: str, node_url: str):
        """Mark a previously down node as recovered"""
        try:
            conn = await self.db.get_connection()
            await conn.execute("""
                UPDATE storage_nodes 
                SET status = 'healthy', last_heartbeat = CURRENT_TIMESTAMP
                WHERE node_id = ?
            """, (node_id,))
            await conn.commit()
                
            logger.info(f"Node {node_id} ({node_url}) recovered and marked as healthy")
            
        except Exception as e:
            logger.error(f"Failed to mark node {node_id} as recovered: {e}")
    
    async def _update_node_stats(self, node_id: str, disk_usage: float, chunk_count: int):
        """Update node statistics without changing heartbeat timestamp"""
        try:
            conn = await self.db.get_connection()
            await conn.execute("""
                UPDATE storage_nodes 
                SET disk_usage_percent = ?, chunk_count = ?
                WHERE node_id = ?
            """, (disk_usage, chunk_count, node_id))
            await conn.commit()
                
        except Exception as e:
            logger.error(f"Failed to update stats for node {node_id}: {e}")
    
    async def register_node_if_new(self, node_url: str, node_id: str, version: str = "1.0.0") -> bool:
        """Register a node if it's not already known (auto-discovery)"""
        try:
            conn = await self.db.get_connection()
            
            # Check if node already exists
            cursor = await conn.execute("""
                SELECT node_id FROM storage_nodes WHERE node_id = ? OR node_url = ?
            """, (node_id, node_url))
            existing = await cursor.fetchone()
            await cursor.close()
            
            if not existing:
                # New node - register it
                await conn.execute("""
                    INSERT INTO storage_nodes 
                    (node_url, node_id, last_heartbeat, status, version)
                    VALUES (?, ?, CURRENT_TIMESTAMP, 'healthy', ?)
                """, (node_url, node_id, version))
                await conn.commit()
                
                logger.info(f"Auto-discovered and registered new node: {node_id} ({node_url})")
                return True
            else:
                return False
                    
        except Exception as e:
            logger.error(f"Failed to register node {node_id}: {e}")
            return False
    
    async def get_node_health_summary(self) -> Dict[str, int]:
        """Get summary of node health status"""
        try:
            conn = await self.db.get_connection()
            cursor = await conn.execute("""
                SELECT status, COUNT(*) as count
                FROM storage_nodes
                GROUP BY status
            """)
            results = await cursor.fetchall()
            await cursor.close()
            
            summary = {"healthy": 0, "degraded": 0, "down": 0}
            for status, count in results:
                summary[status] = count
            
            return summary
        except Exception as e:
            logger.error(f"Failed to get health summary: {e}")
            return {"healthy": 0, "degraded": 0, "down": 0}
    
    async def get_node_details(self) -> List[Dict[str, any]]:
        """Get detailed information about all nodes"""
        try:
            conn = await self.db.get_connection()
            cursor = await conn.execute("""
                SELECT node_url, node_id, last_heartbeat, disk_usage_percent,
                       chunk_count, status, version
                FROM storage_nodes
                ORDER BY status, last_heartbeat DESC
            """)
            results = await cursor.fetchall()
            await cursor.close()
            
            nodes = []
            for row in results:
                nodes.append({
                    "node_url": row[0],
                    "node_id": row[1],
                    "last_heartbeat": row[2],
                    "disk_usage_percent": row[3],
                    "chunk_count": row[4],
                    "status": row[5],
                    "version": row[6]
                })
            return nodes
        except Exception as e:
            logger.error(f"Failed to get node details: {e}")
            return []