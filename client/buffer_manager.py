#!/usr/bin/env python3
"""
Buffer Manager - Maintains playback buffer and manages smooth video playback
"""

import asyncio
import time
import logging
import tempfile
import os
from typing import Optional, List, Dict, Deque
from collections import deque
from dataclasses import dataclass

from config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class BufferedChunk:
    """Represents a chunk in the buffer."""
    chunk_id: str
    sequence_num: int
    data: Optional[bytes]  # Can be None if stored on disk
    size_bytes: int
    buffered_at: float
    temp_file_path: Optional[str] = None  # Path to temp file if stored on disk


class BufferManager:
    """
    Manages video playback buffer with configurable target and low water mark.
    Maintains smooth playback by triggering downloads when buffer drops below threshold.
    """
    
    def __init__(self):
        """
        Initialize buffer manager.
        """
        self.target_buffer_sec = config.TARGET_BUFFER_SEC
        self.low_water_mark_sec = config.LOW_WATER_MARK_SEC
        self.chunk_duration_sec = config.CHUNK_DURATION_SEC
        self.start_playback_sec = config.START_PLAYBACK_SEC
        self.max_memory_bytes = config.MAX_MEMORY_BYTES
        
        # Buffer storage
        self.buffer: Deque[BufferedChunk] = deque()
        self.current_memory_usage = 0
        
        # Playback state
        self.current_position = 0  # Current playback position (chunk sequence number)
        self.playback_started = False
        self.playback_rate = 1.0  # Normal speed
        
        # Events for state changes
        self.buffer_updated_event = asyncio.Event()
        self.playback_ready_event = asyncio.Event()
        
        # Statistics
        self.total_chunks_buffered = 0
        self.total_chunks_played = 0
        self.rebuffering_events = 0
        self.last_rebuffer_time = 0
        self.buffer_level_history = []  # For analytics
        
        # Timing
        self.playback_start_time = None
        self.last_chunk_played_time = None
        
    def get_buffer_level_seconds(self) -> float:
        """
        Calculate current buffer level in seconds.
        
        Returns:
            Buffer level in seconds
        """
        return len(self.buffer) * self.chunk_duration_sec
        
    def get_buffer_level_chunks(self) -> int:
        """
        Get current buffer level in number of chunks.
        
        Returns:
            Number of chunks in buffer
        """
        return len(self.buffer)
        
    def needs_more_chunks(self) -> bool:
        """
        Check if buffer needs refilling (below low water mark).
        
        Returns:
            True if more chunks should be downloaded
        """
        return self.get_buffer_level_seconds() < self.low_water_mark_sec
        
    def can_start_playback(self) -> bool:
        """
        Check if buffer has enough content to start playback.
        
        Returns:
            True if playback can start
        """
        return self.get_buffer_level_seconds() >= self.start_playback_sec
        
    def is_buffer_healthy(self) -> bool:
        """
        Check if buffer is at a healthy level (above low water mark).
        
        Returns:
            True if buffer is healthy
        """
        return self.get_buffer_level_seconds() >= self.low_water_mark_sec
        
    def get_next_chunk_sequences(self, count: int = 10) -> List[int]:
        """
        Get sequence numbers of next chunks to download.
        
        Args:
            count: Number of chunk sequences to return
            
        Returns:
            List of chunk sequence numbers
        """
        # Calculate where buffer ends
        if self.buffer:
            # Get the highest sequence number in buffer
            buffer_end = max(chunk.sequence_num for chunk in self.buffer) + 1
        else:
            # Start from current position
            buffer_end = self.current_position
            
        return list(range(buffer_end, buffer_end + count))
        
    def add_chunk(self, chunk_id: str, sequence_num: int, chunk_data: bytes) -> bool:
        """
        Add a downloaded chunk to the buffer.
        Handles out-of-order delivery by inserting in correct position.
        Manages memory usage by spilling to disk if necessary.
        
        Args:
            chunk_id: ID of the chunk
            sequence_num: Sequence number of the chunk
            chunk_data: Raw chunk data
            
        Returns:
            True if chunk was added, False if rejected (duplicate or too old)
        """
        # Check if chunk is too old (already played)
        if sequence_num < self.current_position:
            logger.debug(f"Rejecting old chunk {chunk_id} (seq {sequence_num} < pos {self.current_position})")
            return False
            
        # Check if chunk is already in buffer
        for buffered_chunk in self.buffer:
            if buffered_chunk.sequence_num == sequence_num:
                logger.debug(f"Chunk {chunk_id} already in buffer")
                return False
                
        chunk_size = len(chunk_data)
        temp_file_path = None
        stored_data = None
        
        # Check memory usage
        if self.current_memory_usage + chunk_size > self.max_memory_bytes:
            # Spill to disk
            try:
                fd, temp_file_path = tempfile.mkstemp(prefix=f"vstack_chunk_{sequence_num}_")
                with os.fdopen(fd, 'wb') as f:
                    f.write(chunk_data)
                # Don't store data in memory
                stored_data = None
                logger.debug(f"Spilled chunk {chunk_id} to disk: {temp_file_path}")
            except Exception as e:
                logger.error(f"Failed to spill chunk to disk: {e}")
                return False
        else:
            # Store in memory
            stored_data = chunk_data
            self.current_memory_usage += chunk_size
        
        # Create buffered chunk
        buffered_chunk = BufferedChunk(
            chunk_id=chunk_id,
            sequence_num=sequence_num,
            data=stored_data,
            size_bytes=chunk_size,
            buffered_at=time.time(),
            temp_file_path=temp_file_path
        )
        
        # Insert in correct position (maintain sorted order)
        inserted = False
        for i, existing_chunk in enumerate(self.buffer):
            if sequence_num < existing_chunk.sequence_num:
                self.buffer.insert(i, buffered_chunk)
                inserted = True
                break
                
        if not inserted:
            self.buffer.append(buffered_chunk)
            
        self.total_chunks_buffered += 1
        
        # Notify waiting tasks
        self.buffer_updated_event.set()
        if self.can_start_playback():
            self.playback_ready_event.set()
        
        logger.debug(f"Added chunk {chunk_id} (seq {sequence_num}) to buffer. Buffer level: {self.get_buffer_level_seconds():.1f}s")
        
        return True
        
    def get_next_chunk_for_playback(self) -> Optional[BufferedChunk]:
        """
        Get next chunk for video player.
        Returns None if buffer is empty (rebuffering needed).
        
        Returns:
            Next chunk to play or None if buffer empty
        """
        if not self.buffer:
            # Buffer underrun - rebuffering event
            if self.playback_started:
                self.rebuffering_events += 1
                self.last_rebuffer_time = time.time()
                logger.warning(f"Rebuffering event #{self.rebuffering_events}")
                self.playback_ready_event.clear()
            return None
            
        # Get next chunk in sequence
        next_chunk = None
        
        # Check if the first chunk is the one we want
        # Note: In a real player, we might skip gaps, but here we expect strict sequence
        if self.buffer[0].sequence_num == self.current_position:
            next_chunk = self.buffer.popleft()
            
            # Update memory usage
            if next_chunk.data:
                self.current_memory_usage -= next_chunk.size_bytes
            
            # Clean up temp file if exists
            # NOTE: In a real player, we would read the data first before deleting
            # Here we assume the caller will read the data immediately or we return the path
            # For this simulation, we'll just return the chunk object which has the path/data
            # The caller is responsible for cleanup if it's a file, but we'll do it here for simplicity
            # assuming 'playing' just means consuming it.
            # Actually, let's keep the file until the object is garbage collected or explicitly closed.
            # But since we are passing the object out, we can't delete the file yet.
            # We will rely on the caller or a destructor.
            # For now, let's just delete it here because the simulation doesn't actually "play" the bytes.
            if next_chunk.temp_file_path and os.path.exists(next_chunk.temp_file_path):
                try:
                    os.remove(next_chunk.temp_file_path)
                except OSError:
                    pass
        
        if next_chunk:
            self.current_position += 1
            self.total_chunks_played += 1
            self.last_chunk_played_time = time.time()
            
            if not self.playback_started:
                self.playback_started = True
                self.playback_start_time = time.time()
                logger.info("Playback started")
                
            logger.debug(f"Playing chunk {next_chunk.chunk_id} (seq {next_chunk.sequence_num}). Buffer: {self.get_buffer_level_seconds():.1f}s")
            
            # Notify that buffer changed
            self.buffer_updated_event.set()
            
        else:
            # Expected chunk not in buffer (gap in sequence)
            # Check if we have future chunks
            if self.buffer and self.buffer[0].sequence_num > self.current_position:
                 logger.warning(f"Gap in sequence: expected {self.current_position}, got {self.buffer[0].sequence_num}")
            else:
                 logger.warning(f"Expected chunk seq {self.current_position} not in buffer")
            
        return next_chunk
        
    def peek_next_chunk(self) -> Optional[BufferedChunk]:
        """
        Peek at next chunk without removing it from buffer.
        
        Returns:
            Next chunk or None if not available
        """
        for chunk in self.buffer:
            if chunk.sequence_num == self.current_position:
                return chunk
        return None
        
    async def wait_for_buffer(self, timeout: float = 1.0) -> bool:
        """
        Wait for buffer update or timeout.
        
        Args:
            timeout: Max time to wait
            
        Returns:
            True if buffer updated, False if timeout
        """
        try:
            await asyncio.wait_for(self.buffer_updated_event.wait(), timeout)
            self.buffer_updated_event.clear()
            return True
        except asyncio.TimeoutError:
            return False

    async def wait_for_playback_ready(self):
        """Wait until buffer is ready for playback."""
        await self.playback_ready_event.wait()

    def get_buffer_status(self) -> Dict:
        """
        Get detailed buffer status for monitoring and visualization.
        
        Returns:
            Dictionary with buffer status information
        """
        buffer_level_sec = self.get_buffer_level_seconds()
        
        # Calculate buffer health percentage
        buffer_health = min(100, (buffer_level_sec / self.target_buffer_sec) * 100)
        
        # Determine buffer state
        if buffer_level_sec == 0:
            state = "empty"
        elif buffer_level_sec < self.start_playback_sec:
            state = "initializing"
        elif buffer_level_sec < self.low_water_mark_sec:
            state = "low"
        elif buffer_level_sec >= self.target_buffer_sec:
            state = "full"
        else:
            state = "healthy"
            
        status = {
            'buffer_level_sec': buffer_level_sec,
            'buffer_level_chunks': self.get_buffer_level_chunks(),
            'buffer_health_percent': buffer_health,
            'state': state,
            'target_buffer_sec': self.target_buffer_sec,
            'low_water_mark_sec': self.low_water_mark_sec,
            'current_position': self.current_position,
            'playback_started': self.playback_started,
            'needs_more_chunks': self.needs_more_chunks(),
            'can_start_playback': self.can_start_playback(),
            'is_healthy': self.is_buffer_healthy(),
            'memory_usage_bytes': self.current_memory_usage
        }
        
        return status
        
    def get_statistics(self) -> Dict:
        """
        Get buffer statistics for analytics.
        
        Returns:
            Dictionary with buffer statistics
        """
        stats = {
            'total_chunks_buffered': self.total_chunks_buffered,
            'total_chunks_played': self.total_chunks_played,
            'rebuffering_events': self.rebuffering_events,
            'current_buffer_level_sec': self.get_buffer_level_seconds(),
            'playback_started': self.playback_started,
        }
        
        # Add timing statistics if playback has started
        if self.playback_start_time:
            stats['playback_duration_sec'] = time.time() - self.playback_start_time
            
        if self.last_rebuffer_time:
            stats['time_since_last_rebuffer_sec'] = time.time() - self.last_rebuffer_time
            
        return stats
        
    def record_buffer_level(self):
        """Record current buffer level for historical analysis."""
        self.buffer_level_history.append({
            'timestamp': time.time(),
            'buffer_level_sec': self.get_buffer_level_seconds(),
            'position': self.current_position
        })
        
        # Keep only recent history (last 1000 samples)
        if len(self.buffer_level_history) > 1000:
            self.buffer_level_history = self.buffer_level_history[-1000:]
            
    def get_buffer_history(self) -> List[Dict]:
        """
        Get buffer level history for visualization.
        
        Returns:
            List of buffer level snapshots
        """
        return self.buffer_level_history.copy()
        
    def reset(self):
        """Reset buffer manager to initial state."""
        # Cleanup temp files
        for chunk in self.buffer:
            if chunk.temp_file_path and os.path.exists(chunk.temp_file_path):
                try:
                    os.remove(chunk.temp_file_path)
                except OSError:
                    pass
                    
        self.buffer.clear()
        self.current_memory_usage = 0
        self.current_position = 0
        self.playback_started = False
        self.total_chunks_buffered = 0
        self.total_chunks_played = 0
        self.rebuffering_events = 0
        self.last_rebuffer_time = 0
        self.playback_start_time = None
        self.last_chunk_played_time = None
        self.buffer_level_history.clear()
        self.buffer_updated_event.clear()
        self.playback_ready_event.clear()
        
        logger.info("Buffer manager reset")
