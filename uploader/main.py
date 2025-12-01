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
from typing import Dict, Optional, Any
from datetime import datetime, UTC
from dotenv import load_dotenv
from contextlib import asynccontextmanager

load_dotenv()

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

class SessionManager:
    """Manages upload sessions"""
    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}
    
    def create_session(self, video_id: str, title: str, filename: str) -> str:
        """Create a new upload session"""
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = {
            "video_id": video_id,
            "title": title,
            "filename": filename,
            "status": "uploading",
            "progress": 0,
            "started_at": datetime.now(UTC).isoformat(),
            "error": None
        }
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session details"""
        return self._sessions.get(session_id)
    
    def update_status(self, session_id: str, status: str, progress: Optional[int] = None, error: Optional[str] = None):
        """Update session status"""
        if session_id in self._sessions:
            self._sessions[session_id]["status"] = status
            if progress is not None:
                self._sessions[session_id]["progress"] = min(progress, 100)
            if error:
                self._sessions[session_id]["error"] = error
            
            if status == "completed":
                self._sessions[session_id]["completed_at"] = datetime.now(UTC).isoformat()
    
    def update_progress(self, session_id: str, progress: int):
        """Update session progress"""
        if session_id in self._sessions:
            self._sessions[session_id]["progress"] = min(progress, 100)
            
    def add_metadata(self, session_id: str, key: str, value: Any):
        """Add arbitrary metadata to session"""
        if session_id in self._sessions:
            self._sessions[session_id][key] = value
            
    def get_active_count(self) -> int:
        """Get number of active sessions"""
        return len(self._sessions)
        
    def update_video_id(self, session_id: str, video_id: str) -> None:
        """
        Update the video_id for a session
        
        Args:
            session_id: The ID of the session to update
            video_id: The new video_id to set
            
        Raises:
            KeyError: If the session_id is not found
        """
        if session_id in self._sessions:
            self._sessions[session_id]["video_id"] = video_id
            logger.debug(f"Updated video_id for session {session_id} to {video_id}")
        else:
            logger.warning(f"Attempted to update video_id for non-existent session: {session_id}")
            raise KeyError(f"Session {session_id} not found")

# Global instances
video_processor: Optional[VideoProcessor] = None
upload_coordinator: Optional[UploadCoordinator] = None
session_manager: SessionManager = SessionManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup and cleanup on shutdown"""
    global video_processor, upload_coordinator
    
    # STARTUP
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
    
    yield
    
    # SHUTDOWN
    if upload_coordinator:
        await upload_coordinator.close()
        logger.info("Upload coordinator closed")

app = FastAPI(
    title="V-Stack Uploader Service", 
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "uploader-service",
        "active_uploads": session_manager.get_active_count()
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
    
    # Generate unique video ID
    video_id = str(uuid.uuid4())
    
    # Basic validation
    if not video.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    if not video.filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv')):
        raise HTTPException(
            status_code=400,
            detail="Unsupported video format. Supported formats: mp4, avi, mov, mkv, webm, flv"
        )
    
    # Create session
    upload_session_id = session_manager.create_session(video_id, title, video.filename)
    
    try:
        # Save uploaded file temporarily
        temp_video_path = os.path.join(video_processor.temp_dir, f"{video_id}_input{os.path.splitext(video.filename)[1]}")
        
        logger.info(f"Saving uploaded file to {temp_video_path}")
        
        # Stream file to disk to avoid OOM
        file_size = 0
        async with aiofiles.open(temp_video_path, 'wb') as f:
            while True:
                chunk = await video.read(1024 * 1024)  # Read in 1MB chunks
                if not chunk:
                    break
                await f.write(chunk)
                file_size += len(chunk)
        
        file_size_mb = file_size / (1024 * 1024)
        logger.info(f"Saved video file: {file_size_mb:.2f} MB")
        
        # Update session status
        session_manager.update_status(upload_session_id, "processing", progress=10)
        
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
        session_manager.update_status(upload_session_id, "deleted", error=str(e))
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/upload/status/{upload_session_id}")
async def get_upload_status(upload_session_id: str):
    """
    Get upload progress and status
    Requirements: 1.2
    """
    session = session_manager.get_session(upload_session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Upload session not found")
    
    return session

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
        session_manager.update_status(upload_session_id, "chunking", progress=20)
        
        chunks, video_metadata = await video_processor.process_video(video_id, temp_video_path)
        
        logger.info(f"Video processed: {len(chunks)} chunks created, duration: {video_metadata['duration_sec']}s")
        session_manager.update_status(upload_session_id, "chunking", progress=40)
        session_manager.add_metadata(upload_session_id, "total_chunks", len(chunks))
        
        # Step 2: Register video with metadata service
        logger.info(f"Registering video {video_id} with metadata service")
        session_manager.update_status(upload_session_id, "registering")
        
        # Register video and get the server-assigned video_id
        registration_result = await upload_coordinator.register_video(
            video_id=video_id,
            title=title,
            duration_sec=video_metadata["duration_sec"]
        )
        
        # Update the video_id with the server-assigned ID for all subsequent operations
        server_video_id = registration_result['video_id']
        logger.info(f"Using server-assigned video_id: {server_video_id}")
        
        # Update the session with the new video_id
        session_manager.update_video_id(upload_session_id, server_video_id)
        
        # Update chunk video_ids to use the server-assigned ID
        for chunk in chunks:
            chunk.video_id = server_video_id
        
        session_manager.update_progress(upload_session_id, 50)
        
        # Step 3: Upload chunks to storage nodes
        logger.info(f"Uploading {len(chunks)} chunks for video {server_video_id}")
        session_manager.update_status(upload_session_id, "uploading_chunks")
        
        await upload_coordinator.upload_chunks(
            video_id=server_video_id,
            chunks=chunks,
            progress_callback=lambda p: session_manager.update_progress(upload_session_id, 50 + int(p * 0.4))
        )
        
        session_manager.update_progress(upload_session_id, 90)
        
        # Step 4: Finalize video and create manifest
        logger.info(f"Finalizing video {server_video_id}")
        session_manager.update_status(upload_session_id, "finalizing")
        
        manifest = await upload_coordinator.finalize_video(server_video_id, chunks)
        
        # Step 5: Cleanup temporary files
        logger.info(f"Cleaning up temporary files for video {server_video_id}")
        # Cleanup using the original video_id for the temp files, but use server_video_id for metadata
        await video_processor.cleanup(video_id)  # Uses original ID for temp file cleanup
        
        # Mark upload as complete
        session_manager.update_status(upload_session_id, "active", progress=100)
        session_manager.add_metadata(upload_session_id, "manifest_url", f"/manifest/{server_video_id}")
        
        logger.info(f"Video {server_video_id} upload completed successfully")
        
    except Exception as e:
        logger.error(f"Failed to process video {video_id}: {e}", exc_info=True)
        session_manager.update_status(upload_session_id, "deleted", error=str(e))
        
        # Cleanup on failure
        try:
            await video_processor.cleanup(video_id)
            await upload_coordinator.cleanup_failed_upload(video_id)
        except Exception as cleanup_error:
            logger.error(f"Cleanup failed for {video_id}: {cleanup_error}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8082))
    uvicorn.run(app, host="0.0.0.0", port=port)