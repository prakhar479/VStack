#!/usr/bin/env python3
"""
Video Processor - FFmpeg integration for video chunking
Requirements: 1.1, 1.2, 10.1
"""

import os
import asyncio
import hashlib
import glob
import logging
import json
from typing import List, Dict, Tuple
import ffmpeg

logger = logging.getLogger(__name__)

class VideoChunk:
    """Represents a video chunk with metadata"""
    def __init__(self, chunk_id: str, video_id: str, sequence_num: int, 
                 data: bytes, size_bytes: int, checksum: str):
        self.chunk_id = chunk_id
        self.video_id = video_id
        self.sequence_num = sequence_num
        self.data = data
        self.size_bytes = size_bytes
        self.checksum = checksum

class VideoProcessor:
    """Handles video processing and chunking using FFmpeg"""
    
    def __init__(self, temp_dir: str, chunk_duration_sec: int = 10, 
                 target_chunk_size_bytes: int = 2 * 1024 * 1024):
        self.temp_dir = temp_dir
        self.chunk_duration_sec = chunk_duration_sec
        self.target_chunk_size_bytes = target_chunk_size_bytes
        
    async def process_video(self, video_id: str, video_path: str) -> Tuple[List[VideoChunk], Dict]:
        """
        Process video into chunks using FFmpeg
        Requirements: 1.1, 1.2, 10.1
        
        Returns:
            Tuple of (chunks list, video metadata dict)
        """
        logger.info(f"Starting video processing for {video_id}")
        
        # Step 1: Extract video metadata
        metadata = await self._extract_metadata(video_path)
        logger.info(f"Video metadata: duration={metadata['duration_sec']}s, "
                   f"resolution={metadata.get('width')}x{metadata.get('height')}, "
                   f"format={metadata.get('format')}")
        
        # Step 2: Split video into chunks
        chunk_files = await self._split_video_into_chunks(video_id, video_path)
        logger.info(f"Created {len(chunk_files)} chunk files")
        
        # Step 3: Read chunks and compute checksums
        chunks = await self._process_chunk_files(video_id, chunk_files)
        logger.info(f"Processed {len(chunks)} chunks with checksums")
        
        return chunks, metadata
    
    async def _extract_metadata(self, video_path: str) -> Dict:
        """
        Extract video metadata using FFmpeg probe
        Requirements: 1.2
        """
        try:
            probe = await asyncio.to_thread(
                ffmpeg.probe, video_path
            )
            
            video_stream = next(
                (stream for stream in probe['streams'] if stream['codec_type'] == 'video'),
                None
            )
            
            if not video_stream:
                raise ValueError("No video stream found in file")
            
            # Extract duration
            duration_sec = float(probe['format'].get('duration', 0))
            
            metadata = {
                'duration_sec': int(duration_sec),
                'format': probe['format'].get('format_name', 'unknown'),
                'size_bytes': int(probe['format'].get('size', 0)),
                'bitrate': int(probe['format'].get('bit_rate', 0)),
                'width': int(video_stream.get('width', 0)),
                'height': int(video_stream.get('height', 0)),
                'codec': video_stream.get('codec_name', 'unknown'),
                'fps': self._parse_fps(video_stream.get('r_frame_rate', '0/1'))
            }
            
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to extract metadata: {e}")
            raise ValueError(f"Failed to extract video metadata: {str(e)}")
    
    def _parse_fps(self, fps_str: str) -> float:
        """Parse FPS from FFmpeg format (e.g., '30/1')"""
        try:
            if '/' in fps_str:
                num, den = fps_str.split('/')
                return float(num) / float(den)
            return float(fps_str)
        except:
            return 0.0
    
    async def _split_video_into_chunks(self, video_id: str, video_path: str) -> List[str]:
        """
        Split video into 10-second chunks using FFmpeg
        Requirements: 1.1, 1.2
        
        Uses FFmpeg segment muxer to split video into chunks of approximately
        10 seconds each, targeting 2MB per chunk as specified in requirements.
        """
        output_pattern = os.path.join(self.temp_dir, f"{video_id}_chunk_%03d.mp4")
        
        try:
            # Use FFmpeg to segment the video
            # -c copy: Copy streams without re-encoding (fast)
            # -f segment: Use segment muxer
            # -segment_time: Duration of each segment in seconds
            # -reset_timestamps: Reset timestamps for each segment
            # -map 0: Include all streams from input
            
            logger.info(f"Splitting video with FFmpeg: {self.chunk_duration_sec}s segments")
            
            await asyncio.to_thread(
                lambda: (
                    ffmpeg
                    .input(video_path)
                    .output(
                        output_pattern,
                        format='segment',
                        segment_time=self.chunk_duration_sec,
                        reset_timestamps=1,
                        c='copy',
                        map='0'
                    )
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True)
                )
            )
            
            # Find all generated chunk files
            chunk_files = sorted(glob.glob(os.path.join(self.temp_dir, f"{video_id}_chunk_*.mp4")))
            
            if not chunk_files:
                raise ValueError("No chunk files were created by FFmpeg")
            
            logger.info(f"FFmpeg created {len(chunk_files)} chunk files")
            
            return chunk_files
            
        except ffmpeg.Error as e:
            stderr = e.stderr.decode() if e.stderr else "No error output"
            logger.error(f"FFmpeg error: {stderr}")
            raise ValueError(f"FFmpeg failed to split video: {stderr}")
        except Exception as e:
            logger.error(f"Failed to split video: {e}")
            raise
    
    async def _process_chunk_files(self, video_id: str, chunk_files: List[str]) -> List[VideoChunk]:
        """
        Read chunk files and compute SHA-256 checksums
        Requirements: 1.2, 10.1
        """
        chunks = []
        
        for i, chunk_file in enumerate(chunk_files):
            try:
                # Read chunk data
                async with asyncio.Lock():
                    with open(chunk_file, 'rb') as f:
                        chunk_data = f.read()
                
                # Compute SHA-256 checksum for integrity
                checksum = hashlib.sha256(chunk_data).hexdigest()
                
                # Create chunk object
                chunk_id = f"{video_id}-chunk-{i:03d}"
                chunk = VideoChunk(
                    chunk_id=chunk_id,
                    video_id=video_id,
                    sequence_num=i,
                    data=chunk_data,
                    size_bytes=len(chunk_data),
                    checksum=checksum
                )
                
                chunks.append(chunk)
                
                logger.debug(f"Processed chunk {i}: {len(chunk_data)} bytes, checksum: {checksum[:16]}...")
                
            except Exception as e:
                logger.error(f"Failed to process chunk file {chunk_file}: {e}")
                raise
        
        return chunks
    
    async def cleanup(self, video_id: str):
        """
        Cleanup temporary files for a video
        Requirements: 1.2, 10.4
        """
        try:
            # Find all files related to this video
            patterns = [
                os.path.join(self.temp_dir, f"{video_id}_input*"),
                os.path.join(self.temp_dir, f"{video_id}_chunk_*.mp4")
            ]
            
            files_deleted = 0
            for pattern in patterns:
                files = glob.glob(pattern)
                for file_path in files:
                    try:
                        os.unlink(file_path)
                        files_deleted += 1
                        logger.debug(f"Deleted temporary file: {file_path}")
                    except Exception as e:
                        logger.warning(f"Failed to delete {file_path}: {e}")
            
            logger.info(f"Cleanup completed for {video_id}: {files_deleted} files deleted")
            
        except Exception as e:
            logger.error(f"Cleanup failed for {video_id}: {e}")
            # Don't raise - cleanup is best effort
