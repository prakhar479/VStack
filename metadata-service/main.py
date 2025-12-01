#!/usr/bin/env python3
"""
Metadata Service - Coordination layer for V-Stack distributed video storage
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn
import os
import sys
import uuid
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List

# Add parent directory to path for shared config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import DatabaseManager
from consensus import ChunkPaxos
from health_monitor import HealthMonitor
from redundancy_manager import RedundancyManager, RedundancyPolicy
from models import (
    CreateVideoRequest, CreateVideoResponse, VideoManifest, StorageNode,
    HeartbeatRequest, ChunkCommitRequest, ChunkCommitResponse, HealthResponse,
    StorageOverheadStats, RedundancyMode
)

try:
    from config import MetadataServiceConfig, validate_config
except ImportError:
    # Fallback if config module not available
    MetadataServiceConfig = None
    validate_config = None

# Load and validate configuration
if MetadataServiceConfig:
    config = MetadataServiceConfig.from_env()
    if validate_config and not validate_config(config):
        logger.error("Configuration validation failed!")
        sys.exit(1)
else:
    # Fallback configuration
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

# Global instances
db_manager = None
consensus = None
health_monitor = None
redundancy_manager = None
redundancy_policy = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global db_manager, consensus, health_monitor, redundancy_manager, redundancy_policy
    
    # STARTUP
    logger.info("Starting V-Stack Metadata Service...")
    try:
        # Initialize database
        db_manager = DatabaseManager(db_path=os.getenv("DB_PATH", "./data/metadata.db"))
        await db_manager.initialize()
        logger.info("Database initialized")
        
        # Initialize consensus protocol
        consensus = ChunkPaxos(db_manager)
        await consensus.initialize()
        logger.info("Consensus protocol initialized")
        
        # Initialize redundancy manager
        popularity_threshold = int(os.getenv("POPULARITY_THRESHOLD", "1000"))
        redundancy_manager = RedundancyManager(popularity_threshold=popularity_threshold)
        redundancy_policy = RedundancyPolicy(redundancy_manager)
        logger.info("Redundancy manager initialized")
        
        # Initialize and start health monitoring
        health_monitor = HealthMonitor(db_manager, heartbeat_timeout_sec=os.getenv("HEARTBEAT_TIMEOUT_SEC", 100), probe_interval_sec=os.getenv("PROBE_INTERVAL_SEC", 30))
        await health_monitor.start_monitoring()
        logger.info("Health monitor started")
        
        logger.info("Metadata Service startup complete")
    except Exception as e:
        logger.error(f"Failed to start Metadata Service: {e}")
        raise
    
    yield  # REQUIRED - separates startup from shutdown
    
    # SHUTDOWN
    logger.info("Shutting down Metadata Service...")
    try:
        if health_monitor:
            await health_monitor.stop_monitoring()
            logger.info("Health monitor stopped")
        
        if consensus:
            await consensus.close()
            logger.info("Consensus protocol closed")
        
        if db_manager:
            await db_manager.close()
            logger.info("Database closed")
        
        logger.info("Metadata Service shutdown complete")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

app = FastAPI(
    title="V-Stack Metadata Service", 
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Enhanced health check endpoint"""
    try:
        health_summary = await health_monitor.get_node_health_summary()
        
        # Test database connectivity
        test_video = await db_manager.get_video("test")
        db_status = "healthy"
        
        total_nodes = sum(health_summary.values())
        healthy_nodes = health_summary.get("healthy", 0)
        
        return HealthResponse(
            status="healthy",
            service="metadata-service",
            healthy_nodes=healthy_nodes,
            total_nodes=total_nodes,
            database_status=db_status
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "V-Stack Metadata Service", "version": "1.0.0"}

@app.post("/video", response_model=CreateVideoResponse)
async def create_video(request: CreateVideoRequest):
    """Create a new video record"""
    video_id = str(uuid.uuid4())
    
    success = await db_manager.create_video(
        video_id=video_id,
        title=request.title,
        duration_sec=request.duration_sec
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create video record")
    
    upload_url = f"/upload/{video_id}"
    
    return CreateVideoResponse(
        video_id=video_id,
        upload_url=upload_url
    )

@app.patch("/video/{video_id}/status", response_model=dict)
async def update_video_status(video_id: str, status_update: dict) -> dict:
    """Update video status.
    
    Valid status values: 'uploading', 'processing', 'ready', 'failed'
    """
    try:
        # Validate status
        valid_statuses = {"uploading", "active", "deleted"}
        new_status = status_update.get("status")
        
        if not new_status or new_status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            )
        
        # Update status in database
        success = await db_manager.update_video_status(video_id, new_status)
        if not success:
            raise HTTPException(status_code=404, detail="Video not found")
        
        return {
            "status": "success",
            "message": f"Video status updated to {new_status}",
            "video_id": video_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update video status: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to update video status"
        )

@app.get("/videos")
async def list_videos(limit: int = 100, offset: int = 0):
    """List all videos"""
    # Validate pagination parameters
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="Limit must be between 1 and 1000")
    if offset < 0:
        raise HTTPException(status_code=400, detail="Offset must be non-negative")
        
    videos = await db_manager.list_videos(limit, offset)
    return videos

def _translate_internal_to_external_urls(replicas: List[str]) -> List[str]:
    """Translate internal Docker network URLs to external localhost URLs for clients"""
    external_replicas = []
    for url in replicas:
        # Map internal Docker network names to external localhost ports
        # Note: All storage nodes use port 8081 internally, but are exposed on different external ports
        if 'storage-node-1:8081' in url:
            external_replicas.append(url.replace('storage-node-1:8081', 'localhost:8081'))
        elif 'storage-node-2:8081' in url:
            external_replicas.append(url.replace('storage-node-2:8081', 'localhost:8082'))
        elif 'storage-node-3:8081' in url:
            external_replicas.append(url.replace('storage-node-3:8081', 'localhost:8083'))
        else:
            # Keep URL as-is if it doesn't match known patterns
            external_replicas.append(url)
    return external_replicas

@app.get("/manifest/{video_id}", response_model=VideoManifest)
async def get_video_manifest(video_id: str):
    """Get video manifest with chunk locations"""
    manifest = await db_manager.get_video_manifest(video_id)
    
    if not manifest:
        raise HTTPException(status_code=404, detail="Video not found")
    
    try:
        # Translate internal Docker network URLs to external URLs for clients
        for chunk in manifest.get('chunks', []):
            if chunk.get('replicas'):
                chunk['replicas'] = _translate_internal_to_external_urls(chunk['replicas'])
            else:
                logger.warning(f"Chunk {chunk.get('chunk_id')} has no replicas")
                chunk['replicas'] = []
    except Exception as e:
        logger.error(f"Error translating URLs in manifest: {e}")
        raise HTTPException(status_code=500, detail="Failed to process manifest")
    
    return VideoManifest(**manifest)

@app.get("/nodes/healthy", response_model=List[StorageNode])
async def get_healthy_nodes():
    """Get list of healthy storage nodes"""
    nodes = await db_manager.get_healthy_nodes()
    return [StorageNode(**node) for node in nodes]

@app.post("/chunk/{chunk_id}/commit", response_model=ChunkCommitResponse)
async def commit_chunk_placement(chunk_id: str, request: ChunkCommitRequest):
    """Commit chunk placement using ChunkPaxos consensus"""
    try:
        success, committed_nodes = await consensus.propose_chunk_placement(
            chunk_id=chunk_id,
            node_urls=request.node_urls,
            checksum=request.checksum,
            size_bytes=request.size_bytes,
            video_id=request.video_id,
            sequence_num=request.sequence_num,
            redundancy_mode=request.redundancy_mode.value,
            fragments_metadata=request.fragments_metadata
        )
        
        if success:
            return ChunkCommitResponse(
                success=True,
                committed_nodes=committed_nodes,
                message=f"Chunk {chunk_id} committed to {len(committed_nodes)} nodes"
            )
        else:
            return ChunkCommitResponse(
                success=False,
                committed_nodes=[],
                message=f"Failed to reach consensus for chunk {chunk_id}"
            )
            
    except Exception as e:
        logger.error(f"Chunk commit failed for {chunk_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/nodes/{node_id}/heartbeat")
async def update_node_heartbeat(node_id: str, request: HeartbeatRequest):
    """Update storage node heartbeat and health status"""
    success = await db_manager.update_node_heartbeat(
        node_id=node_id,
        disk_usage=request.disk_usage_percent,
        chunk_count=request.chunk_count
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update heartbeat")
    
    return {"status": "ok", "message": f"Heartbeat updated for node {node_id}"}

class NodeRegistration(BaseModel):
    node_url: str
    node_id: str
    version: str = "1.0.0"

@app.post("/nodes/register")
async def register_storage_node(node_data: NodeRegistration):
    """Register a new storage node"""
    # Validate URL format
    if not node_data.node_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid node_url: must start with http:// or https://")
        
    success = await db_manager.register_storage_node(
        node_url=node_data.node_url,
        node_id=node_data.node_id,
        version=node_data.version
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to register storage node")
    
    return {"status": "registered", "node_id": node_data.node_id, "node_url": node_data.node_url}

@app.get("/nodes/all")
async def get_all_nodes():
    """Get detailed information about all storage nodes"""
    nodes = await health_monitor.get_node_details()
    return {"nodes": nodes}

@app.get("/nodes/health-summary")
async def get_health_summary():
    """Get summary of node health status"""
    summary = await health_monitor.get_node_health_summary()
    return summary

# Additional endpoints for debugging and monitoring
@app.get("/consensus/{chunk_id}")
async def get_consensus_state(chunk_id: str):
    """Get consensus state for a chunk (debugging)"""
    state = await consensus.get_consensus_state(chunk_id)
    if not state:
        raise HTTPException(status_code=404, detail="Consensus state not found")
    return state

@app.get("/stats")
async def get_service_stats():
    """Get service statistics"""
    try:
        healthy_nodes = await db_manager.get_healthy_nodes()
        
        # Get total videos and chunks
        async with await db_manager.get_connection() as db:
            async with db.execute("SELECT COUNT(*) FROM videos") as cursor:
                total_videos = (await cursor.fetchone())[0]
            
            async with db.execute("SELECT COUNT(*) FROM chunks") as cursor:
                total_chunks = (await cursor.fetchone())[0]
            
            async with db.execute("SELECT COUNT(*) FROM chunk_replicas WHERE status='active'") as cursor:
                total_replicas = (await cursor.fetchone())[0]
        
        return {
            "total_videos": total_videos,
            "total_chunks": total_chunks,
            "total_replicas": total_replicas,
            "healthy_nodes": len(healthy_nodes),
            "service_version": "1.0.0"
        }
    except Exception as e:
        logger.error(f"Stats query failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get stats")

@app.get("/storage/overhead")
async def get_storage_overhead():
    """Get storage overhead statistics showing erasure coding savings"""
    try:
        stats = await db_manager.get_storage_overhead_stats()
        return stats
    except Exception as e:
        logger.error(f"Storage overhead query failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get storage overhead stats")

@app.get("/video/{video_id}/popularity")
async def get_video_popularity(video_id: str):
    """Get video popularity (view count)"""
    try:
        view_count = await db_manager.get_video_popularity(video_id)
        return {"video_id": video_id, "view_count": view_count}
    except Exception as e:
        logger.error(f"Failed to get popularity for {video_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get video popularity")

@app.post("/video/{video_id}/view")
async def increment_video_view(video_id: str):
    """Increment video view count"""
    try:
        success = await db_manager.update_video_stats(video_id, increment_views=True)
        if success:
            return {"status": "ok", "message": f"View count incremented for {video_id}"}
        else:
            raise HTTPException(status_code=500, detail="Failed to update view count")
    except Exception as e:
        logger.error(f"Failed to increment view for {video_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to increment view count")

@app.get("/chunk/{chunk_id}/fragments")
async def get_chunk_fragments(chunk_id: str):
    """Get fragment information for erasure-coded chunk"""
    try:
        fragments = await db_manager.get_chunk_fragments(chunk_id)
        return {"chunk_id": chunk_id, "fragments": fragments}
    except Exception as e:
        logger.error(f"Failed to get fragments for {chunk_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get chunk fragments")

@app.get("/redundancy/recommend/{video_id}")
async def recommend_redundancy_mode(video_id: str):
    """Recommend redundancy mode for a video based on popularity"""
    try:
        view_count = await db_manager.get_video_popularity(video_id)
        mode, config = redundancy_manager.determine_redundancy_mode(video_id, view_count)
        
        return {
            "video_id": video_id,
            "view_count": view_count,
            "recommended_mode": mode.value,
            "config": config
        }
    except Exception as e:
        logger.error(f"Failed to recommend redundancy for {video_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to recommend redundancy mode")

@app.post("/redundancy/override/{video_id}")
async def set_redundancy_override(video_id: str, mode: str):
    """Set manual redundancy mode override for a video"""
    try:
        from redundancy_manager import RedundancyMode as RMode
        redundancy_mode = RMode(mode)
        redundancy_manager.set_manual_override(video_id, redundancy_mode)
        
        return {
            "status": "ok",
            "video_id": video_id,
            "override_mode": mode,
            "message": f"Manual override set to {mode}"
        }
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {mode}. Use 'replication' or 'erasure_coding'")
    except Exception as e:
        logger.error(f"Failed to set override for {video_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to set redundancy override")

@app.delete("/redundancy/override/{video_id}")
async def clear_redundancy_override(video_id: str):
    """Clear manual redundancy mode override for a video"""
    try:
        redundancy_manager.clear_manual_override(video_id)
        return {
            "status": "ok",
            "video_id": video_id,
            "message": "Manual override cleared"
        }
    except Exception as e:
        logger.error(f"Failed to clear override for {video_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear redundancy override")

@app.get("/redundancy/efficiency")
async def get_redundancy_efficiency():
    """Get storage efficiency metrics for redundancy modes"""
    try:
        efficiency = redundancy_manager.get_storage_efficiency()
        comparison = redundancy_manager.get_mode_comparison()
        
        return {
            "efficiency": efficiency,
            "mode_comparison": comparison
        }
    except Exception as e:
        logger.error(f"Failed to get efficiency metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get efficiency metrics")

@app.get("/redundancy/config")
async def get_redundancy_config():
    """Get current redundancy manager configuration"""
    return {
        "popularity_threshold": redundancy_manager.popularity_threshold,
        "replication_factor": redundancy_manager.replication_factor,
        "erasure_data_shards": redundancy_manager.erasure_data_shards,
        "erasure_parity_shards": redundancy_manager.erasure_parity_shards,
        "erasure_total_shards": redundancy_manager.erasure_total_shards
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)