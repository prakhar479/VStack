#!/usr/bin/env python3
"""
Uploader Service - Video upload and chunking service for V-Stack
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import os
import sys
import logging
import uuid
import asyncio
import aiofiles
import httpx
from typing import Dict, Optional
from datetime import datetime

# Add parent directory to path for shared config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from video_processor import VideoProcessor
from upload_coordinator import UploadCoordinator

try:
    from config import UploaderServiceConfig, validate_config
    config = UploaderServiceConfig.from_env()
    if not validate_config(config):
        logger.error("Configuration validation failed!")
        sys.exit(1)
except ImportError:
    # Fallback configuration
    logging.basicConfig(level=logging.INFO)
    config = None

logger = logging.getLogger(__name__)

app = FastAPI(title="V-Stack Uploader Service", version="1.0.0")

# Global instances
video_processor: Optional[VideoProcessor] = None
upload_coordinator: Optional[UploadCoordinator] = None

# Upload session tracking
upload_sessions: Dict[str, dict] = {}

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global video_processor, upload_coordinator
    
    metadata_service_url = os.getenv("METADATA_SERVICE_URL", "http://metadata-service:8080")
    temp_dir = os.getenv("TEMP_DIR", "/tmp/uploads")
    
    # Create temp directory
    os.makedirs(temp_dir, exist_ok=True)
    
    # Verify FFmpeg is available
    try:
        import subprocess
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        if result.returncode == 0:
            logger.info("FFmpeg is available")
        else:
            logger.error("FFmpeg check failed")
    except Exception as e:
        logger.error(f"FFmpeg not found or not working: {e}")
        logger.warning("Video processing may fail without FFmpeg")
    
    video_processor = VideoProcessor(temp_dir)
    upload_coordinator = UploadCoordinator(metadata_service_url)
    
    logger.info(f"Uploader Service initialized with metadata service at {metadata_service_url}")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global upload_coordinator
    
    if upload_coordinator:
        await upload_coordinator.close()
        logger.info("Upload coordinator closed")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "uploader-service",
        "active_uploads": len(upload_sessions)
    }

@app.post("/upload")
async def upload_video(
    video: UploadFile = File(...),
    title: str = Form(...)
):
    """
    Upload video endpoint - accepts video files and processes them into chunks
    Requirements: 1.1, 1.2
    """
    logger.info(f"Received upload request for: {title} (filename: {video.filename})")
    
    # Generate unique video ID and upload session
    video_id = str(uuid.uuid4())
    upload_session_id = str(uuid.uuid4())
    
    # Basic validation
    if not video.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    if not video.filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv')):
        raise HTTPException(
            status_code=400,
            detail="Unsupported video format. Supported formats: mp4, avi, mov, mkv, webm, flv"
        )
    
    # Initialize upload session tracking
    upload_sessions[upload_session_id] = {
        "video_id": video_id,
        "title": title,
        "filename": video.filename,
        "status": "uploading",
        "progress": 0,
        "started_at": datetime.utcnow().isoformat(),
        "error": None
    }
    
    try:
        # Save uploaded file temporarily
        temp_video_path = os.path.join(video_processor.temp_dir, f"{video_id}_input{os.path.splitext(video.filename)[1]}")
        
        logger.info(f"Saving uploaded file to {temp_video_path}")
        async with aiofiles.open(temp_video_path, 'wb') as f:
            content = await video.read()
            await f.write(content)
        
        file_size_mb = len(content) / (1024 * 1024)
        logger.info(f"Saved video file: {file_size_mb:.2f} MB")
        
        # Update session status
        upload_sessions[upload_session_id]["status"] = "processing"
        upload_sessions[upload_session_id]["progress"] = 10
        
        # Process video in background
        asyncio.create_task(
            process_and_upload_video(
                video_id=video_id,
                upload_session_id=upload_session_id,
                temp_video_path=temp_video_path,
                title=title
            )
        )
        
        return {
            "video_id": video_id,
            "upload_session_id": upload_session_id,
            "title": title,
            "status": "processing",
            "message": "Video upload received and processing started",
            "status_url": f"/upload/status/{upload_session_id}"
        }
        
    except Exception as e:
        logger.error(f"Upload failed for {title}: {e}")
        upload_sessions[upload_session_id]["status"] = "failed"
        upload_sessions[upload_session_id]["error"] = str(e)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/upload/status/{upload_session_id}")
async def get_upload_status(upload_session_id: str):
    """
    Get upload progress and status
    Requirements: 1.2
    """
    if upload_session_id not in upload_sessions:
        raise HTTPException(status_code=404, detail="Upload session not found")
    
    return upload_sessions[upload_session_id]

async def process_and_upload_video(
    video_id: str,
    upload_session_id: str,
    temp_video_path: str,
    title: str
):
    """
    Background task to process and upload video chunks
    Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 10.4
    """
    try:
        # Step 1: Extract video metadata and chunk the video
        logger.info(f"Processing video {video_id}: {title}")
        upload_sessions[upload_session_id]["status"] = "chunking"
        upload_sessions[upload_session_id]["progress"] = 20
        
        chunks, video_metadata = await video_processor.process_video(video_id, temp_video_path)
        
        logger.info(f"Video processed: {len(chunks)} chunks created, duration: {video_metadata['duration_sec']}s")
        upload_sessions[upload_session_id]["progress"] = 40
        upload_sessions[upload_session_id]["total_chunks"] = len(chunks)
        
        # Step 2: Register video with metadata service
        logger.info(f"Registering video {video_id} with metadata service")
        upload_sessions[upload_session_id]["status"] = "registering"
        
        await upload_coordinator.register_video(
            video_id=video_id,
            title=title,
            duration_sec=video_metadata["duration_sec"]
        )
        
        upload_sessions[upload_session_id]["progress"] = 50
        
        # Step 3: Upload chunks to storage nodes
        logger.info(f"Uploading {len(chunks)} chunks for video {video_id}")
        upload_sessions[upload_session_id]["status"] = "uploading_chunks"
        
        await upload_coordinator.upload_chunks(
            video_id=video_id,
            chunks=chunks,
            progress_callback=lambda p: update_upload_progress(upload_session_id, 50 + int(p * 0.4))
        )
        
        upload_sessions[upload_session_id]["progress"] = 90
        
        # Step 4: Finalize video and create manifest
        logger.info(f"Finalizing video {video_id}")
        upload_sessions[upload_session_id]["status"] = "finalizing"
        
        manifest = await upload_coordinator.finalize_video(video_id, chunks)
        
        # Step 5: Cleanup temporary files
        logger.info(f"Cleaning up temporary files for video {video_id}")
        await video_processor.cleanup(video_id)
        
        # Mark upload as complete
        upload_sessions[upload_session_id]["status"] = "completed"
        upload_sessions[upload_session_id]["progress"] = 100
        upload_sessions[upload_session_id]["completed_at"] = datetime.utcnow().isoformat()
        upload_sessions[upload_session_id]["manifest_url"] = f"/manifest/{video_id}"
        
        logger.info(f"Video {video_id} upload completed successfully")
        
    except Exception as e:
        logger.error(f"Failed to process video {video_id}: {e}", exc_info=True)
        upload_sessions[upload_session_id]["status"] = "failed"
        upload_sessions[upload_session_id]["error"] = str(e)
        
        # Cleanup on failure
        try:
            await video_processor.cleanup(video_id)
            await upload_coordinator.cleanup_failed_upload(video_id)
        except Exception as cleanup_error:
            logger.error(f"Cleanup failed for {video_id}: {cleanup_error}")

def update_upload_progress(upload_session_id: str, progress: int):
    """Update upload progress for a session"""
    if upload_session_id in upload_sessions:
        upload_sessions[upload_session_id]["progress"] = min(progress, 100)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8082))
    uvicorn.run(app, host="0.0.0.0", port=port)