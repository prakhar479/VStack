#!/usr/bin/env python3
"""
Database models and schema for V-Stack Metadata Service
"""

import sqlite3
import aiosqlite
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
import json
import logging

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path: str = "./data/metadata.db"):
        self.db_path = db_path
        self._connection = None
    
    async def initialize(self):
        """Initialize database and create tables"""
        if self._connection is None:
            self._connection = await aiosqlite.connect(self.db_path)
        await self._create_tables()
        logger.info(f"Database initialized at {self.db_path}")
    
    async def close(self):
        """Close database connection"""
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
            logger.info("Database connection closed")
    
    async def get_connection(self):
        """Get database connection"""
        if self._connection is None:
            await self.initialize()
        return self._connection
    
    async def _create_tables(self):
        """Create all required tables"""
        conn = await self.get_connection()
        
        # Videos table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                video_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                duration_sec INTEGER NOT NULL,
                total_chunks INTEGER NOT NULL,
                chunk_size_bytes INTEGER DEFAULT 2097152,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'active'
            )
        """)
        
        # Chunks table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                video_id TEXT NOT NULL,
                sequence_num INTEGER NOT NULL,
                size_bytes INTEGER NOT NULL,
                checksum TEXT NOT NULL,
                redundancy_mode TEXT DEFAULT 'replication',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (video_id) REFERENCES videos(video_id),
                UNIQUE(video_id, sequence_num)
            )
        """)
        
        # Chunk replicas table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chunk_replicas (
                chunk_id TEXT NOT NULL,
                node_url TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                ballot_number INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chunk_id, node_url),
                FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id)
            )
        """)
        
        # Storage nodes table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS storage_nodes (
                node_url TEXT PRIMARY KEY,
                node_id TEXT UNIQUE NOT NULL,
                last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                disk_usage_percent REAL DEFAULT 0.0,
                chunk_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'healthy',
                version TEXT
            )
        """)
        
        # Consensus state table (for ChunkPaxos)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS consensus_state (
                chunk_id TEXT PRIMARY KEY,
                promised_ballot INTEGER DEFAULT 0,
                accepted_ballot INTEGER DEFAULT 0,
                accepted_value TEXT,
                phase TEXT DEFAULT 'none'
            )
        """)
        
        # Chunk fragments table (for erasure coding)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chunk_fragments (
                fragment_id TEXT PRIMARY KEY,
                chunk_id TEXT NOT NULL,
                fragment_index INTEGER NOT NULL,
                node_url TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                checksum TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id),
                UNIQUE(chunk_id, fragment_index)
            )
        """)
        
        # Video statistics table (for popularity tracking)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS video_stats (
                video_id TEXT PRIMARY KEY,
                view_count INTEGER DEFAULT 0,
                last_viewed TIMESTAMP,
                total_bytes_served INTEGER DEFAULT 0,
                FOREIGN KEY (video_id) REFERENCES videos(video_id)
            )
        """)
        
        # Create indexes for performance
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_video_id ON chunks(video_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_chunk_replicas_chunk_id ON chunk_replicas(chunk_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_chunk_fragments_chunk_id ON chunk_fragments(chunk_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_video_stats_video_id ON video_stats(video_id)")
        
        await conn.commit()
    
    async def create_video(self, video_id: str, title: str, duration_sec: int) -> bool:
        """Create a new video record"""
        try:
            conn = await self.get_connection()
            await conn.execute("""
                INSERT INTO videos (video_id, title, duration_sec, total_chunks, status)
                VALUES (?, ?, ?, 0, 'uploading')
            """, (video_id, title, duration_sec))
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to create video {video_id}: {e}")
            return False
    
    async def get_video(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Get video by ID"""
        try:
            conn = await self.get_connection()
            cursor = await conn.execute("""
                SELECT video_id, title, duration_sec, total_chunks, 
                       chunk_size_bytes, created_at, status
                FROM videos WHERE video_id = ?
            """, (video_id,))
            row = await cursor.fetchone()
            await cursor.close()
            
            if row:
                return {
                    "video_id": row[0],
                    "title": row[1],
                    "duration_sec": row[2],
                    "total_chunks": row[3],
                    "chunk_size_bytes": row[4],
                    "created_at": row[5],
                    "status": row[6]
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get video {video_id}: {e}")
            return None
    
    async def get_video_manifest(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Get complete video manifest with chunk locations"""
        try:
            conn = await self.get_connection()
            
            # Get video info
            video = await self.get_video(video_id)
            if not video:
                return None
            
            # Get chunks with replicas
            cursor = await conn.execute("""
                SELECT c.chunk_id, c.sequence_num, c.size_bytes, c.checksum,
                       c.redundancy_mode,
                       GROUP_CONCAT(cr.node_url, '|') as replicas
                FROM chunks c
                LEFT JOIN chunk_replicas cr 
                    ON c.chunk_id = cr.chunk_id 
                    AND cr.status = 'active'
                WHERE c.video_id = ?
                GROUP BY c.chunk_id, c.sequence_num, c.size_bytes, c.checksum, c.redundancy_mode
                ORDER BY c.sequence_num
            """, (video_id,))
            
            chunks = []
            async for row in cursor:
                replicas = row[5].split('|') if row[5] else []
                chunk_dict = {
                    "chunk_id": row[0],
                    "sequence_num": row[1],
                    "size_bytes": row[2],
                    "checksum": row[3],
                    "redundancy_mode": row[4],
                    "replicas": replicas
                }
                
                # If erasure coded, fetch fragments
                if row[4] == "erasure_coding":
                    fragments = await self.get_chunk_fragments(row[0])
                    if fragments:
                        chunk_dict["fragments"] = fragments
                
                chunks.append(chunk_dict)
            await cursor.close()
            
            return {
                **video,
                "chunks": chunks
            }
        except Exception as e:
            logger.error(f"Failed to get manifest for video {video_id}: {e}")
            return None
    
    async def register_storage_node(self, node_url: str, node_id: str, version: str = "1.0.0") -> bool:
        """Register a new storage node"""
        try:
            conn = await self.get_connection()
            await conn.execute("""
                INSERT OR REPLACE INTO storage_nodes 
                (node_url, node_id, last_heartbeat, status, version)
                VALUES (?, ?, CURRENT_TIMESTAMP, 'healthy', ?)
            """, (node_url, node_id, version))
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to register node {node_url}: {e}")
            return False
    
    async def update_node_heartbeat(self, node_id: str, disk_usage: float, chunk_count: int) -> bool:
        """Update node heartbeat and stats"""
        try:
            conn = await self.get_connection()
            cursor = await conn.execute("""
                UPDATE storage_nodes 
                SET last_heartbeat = CURRENT_TIMESTAMP,
                    disk_usage_percent = ?,
                    chunk_count = ?,
                    status = 'healthy'
                WHERE node_id = ?
            """, (disk_usage, chunk_count, node_id))
            await conn.commit()
            
            # Check if update actually modified a row
            if cursor.rowcount == 0:
                logger.warning(f"Heartbeat update failed: node {node_id} not found")
                return False
            return True
        except Exception as e:
            logger.error(f"Failed to update heartbeat for node {node_id}: {e}")
            return False
    
    async def get_healthy_nodes(self) -> List[Dict[str, Any]]:
        """Get list of healthy storage nodes"""
        try:
            conn = await self.get_connection()
            cursor = await conn.execute("""
                SELECT node_url, node_id, last_heartbeat, disk_usage_percent, 
                       chunk_count, status, version
                FROM storage_nodes 
                WHERE status = 'healthy' 
                AND datetime(last_heartbeat) > datetime('now', '-60 seconds')
                ORDER BY disk_usage_percent ASC
            """)
            
            nodes = []
            async for row in cursor:
                nodes.append({
                    "node_url": row[0],
                    "node_id": row[1],
                    "last_heartbeat": row[2],
                    "disk_usage_percent": row[3],
                    "chunk_count": row[4],
                    "status": row[5],
                    "version": row[6]
                })
            await cursor.close()
            return nodes
        except Exception as e:
            logger.error(f"Failed to get healthy nodes: {e}")
            return []
    
    async def mark_unhealthy_nodes(self):
        """Mark nodes as unhealthy if they haven't sent heartbeat in 60 seconds"""
        try:
            conn = await self.get_connection()
            await conn.execute("""
                UPDATE storage_nodes 
                SET status = 'down'
                WHERE datetime(last_heartbeat) < datetime('now', '-60 seconds')
                AND status != 'down'
            """)
            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to mark unhealthy nodes: {e}")
    
    async def list_videos(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """List all videos"""
        try:
            conn = await self.get_connection()
            cursor = await conn.execute("""
                SELECT video_id, title, duration_sec, total_chunks, 
                       chunk_size_bytes, created_at, status
                FROM videos 
                WHERE status != 'deleted'
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
            
            videos = []
            async for row in cursor:
                videos.append({
                    "video_id": row[0],
                    "title": row[1],
                    "duration_sec": row[2],
                    "total_chunks": row[3],
                    "chunk_size_bytes": row[4],
                    "created_at": row[5],
                    "status": row[6]
                })
            await cursor.close()
            return videos
        except Exception as e:
            logger.error(f"Failed to list videos: {e}")
            return []
    

    async def store_chunk_fragments(self, chunk_id: str, fragments_metadata: List[Dict[str, Any]]) -> bool:
        """Store fragment metadata for erasure-coded chunk"""
        try:
            conn = await self.get_connection()
            
            for frag in fragments_metadata:
                await conn.execute("""
                    INSERT INTO chunk_fragments 
                    (fragment_id, chunk_id, fragment_index, node_url, size_bytes, checksum, status)
                    VALUES (?, ?, ?, ?, ?, ?, 'active')
                """, (
                    frag['fragment_id'],
                    frag['chunk_id'],
                    frag['fragment_index'],
                    frag['node_url'],
                    frag['size_bytes'],
                    frag['checksum']
                ))
            
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to store fragments for chunk {chunk_id}: {e}")
            return False
    
    async def get_chunk_fragments(self, chunk_id: str) -> List[Dict[str, Any]]:
        """Get all fragments for a chunk"""
        try:
            conn = await self.get_connection()
            cursor = await conn.execute("""
                SELECT fragment_id, chunk_id, fragment_index, node_url, 
                       size_bytes, checksum, status, created_at
                FROM chunk_fragments
                WHERE chunk_id = ? AND status = 'active'
                ORDER BY fragment_index
            """, (chunk_id,))
            
            fragments = []
            async for row in cursor:
                fragments.append({
                    "fragment_id": row[0],
                    "chunk_id": row[1],
                    "fragment_index": row[2],
                    "node_url": row[3],
                    "size_bytes": row[4],
                    "checksum": row[5],
                    "status": row[6],
                    "created_at": row[7]
                })
            await cursor.close()
            return fragments
        except Exception as e:
            logger.error(f"Failed to get fragments for chunk {chunk_id}: {e}")
            return []
    
    async def update_video_stats(self, video_id: str, increment_views: bool = True) -> bool:
        """Update video statistics for popularity tracking"""
        try:
            conn = await self.get_connection()
            
            if increment_views:
                await conn.execute("""
                    INSERT INTO video_stats (video_id, view_count, last_viewed)
                    VALUES (?, 1, CURRENT_TIMESTAMP)
                    ON CONFLICT(video_id) DO UPDATE SET
                        view_count = view_count + 1,
                        last_viewed = CURRENT_TIMESTAMP
                """, (video_id,))
            
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update stats for video {video_id}: {e}")
            return False
    
    async def get_video_popularity(self, video_id: str) -> int:
        """Get view count for a video"""
        try:
            conn = await self.get_connection()
            cursor = await conn.execute("""
                SELECT view_count FROM video_stats WHERE video_id = ?
            """, (video_id,))
            row = await cursor.fetchone()
            await cursor.close()
            
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"Failed to get popularity for video {video_id}: {e}")
            return 0
    
    async def get_storage_overhead_stats(self) -> Dict[str, Any]:
        """Calculate storage overhead statistics"""
        try:
            conn = await self.get_connection()
            
            # Count chunks by redundancy mode
            cursor = await conn.execute("""
                SELECT redundancy_mode, COUNT(*) as count, SUM(size_bytes) as total_bytes
                FROM chunks
                GROUP BY redundancy_mode
            """)
            
            stats = {
                "replication": {"count": 0, "total_bytes": 0},
                "erasure_coding": {"count": 0, "total_bytes": 0}
            }
            
            async for row in cursor:
                mode = row[0]
                count = row[1]
                total_bytes = row[2] or 0
                
                if mode in stats:
                    stats[mode] = {"count": count, "total_bytes": total_bytes}
            
            await cursor.close()
            
            # Calculate total storage (not overhead)
            replication_total_storage = stats["replication"]["total_bytes"] * 3  # 3 full copies
            erasure_total_storage = stats["erasure_coding"]["total_bytes"] * (5/3)  # 5 fragments
            
            # Calculate actual overhead (extra storage beyond original)
            replication_overhead = stats["replication"]["total_bytes"] * 2  # 2 extra copies
            erasure_overhead = stats["erasure_coding"]["total_bytes"] * (2/3)  # 2/3 extra
            
            total_logical = stats["replication"]["total_bytes"] + stats["erasure_coding"]["total_bytes"]
            total_physical = replication_total_storage + erasure_total_storage
            
            savings = 0.0
            if total_logical > 0:
                # Compare to full replication baseline
                baseline = total_logical * 3
                savings = (baseline - total_physical) / baseline
            
            return {
                "replication_chunks": stats["replication"]["count"],
                "erasure_coded_chunks": stats["erasure_coding"]["count"],
                "total_logical_bytes": total_logical,
                "total_physical_bytes": total_physical,
                "storage_savings_percent": savings * 100,
                "replication_overhead_bytes": replication_overhead,
                "erasure_overhead_bytes": erasure_overhead
            }
        except Exception as e:
            logger.error(f"Failed to get storage overhead stats: {e}")
            return {}
