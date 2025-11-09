#!/usr/bin/env python3
"""
Buffer Manager - Maintains playback buffer and manages smooth video playback
"""

import asyncio
import time
import logging
from typing import Optional, List, Dict, Deque
from collections import deque
from dataclasses import dataclass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class BufferedChunk:
    """Represents a chunk in the buffer."""
    chunk_id: str
    sequence_num: int
    data: bytes
    size_bytes: int
    buffered_at: float


class BufferManager:
    """
    Manages video playback buffer with configurable target and low water mark.
    Maintains smooth playback by triggering downloads when buffer drops below threshold.
    """
    
    def __init__(
        self, 
        target_buffer_sec: int = 30,
        low_water_mark_sec: int = 15,
        chunk_duration_sec: int = 10,
        start_playback_sec: int = 10
    ):
        """
        Initialize buffer manager.
        
        Args:
            target_buffer_sec: Target buffer size in seconds (default: 30)
            low_water_mark_sec: Threshold to trigger more downloads (default: 15)
            chunk_duration_sec: Duration of each chunk in seconds (default: 10)
            start_playback_sec: Buffer size needed to start playback (default: 10)
        """
        self.target_buffer_sec = target_buffer_sec
        self.low_water_mark_sec = low_water_mark_sec
        self.chunk_duration_sec = chunk_duration_sec
        self.start_playback_sec = start_playback_sec
        
        # Buffer storage
        self.buffer: Deque[BufferedChunk] = deque()
        
        # Playback state
        self.current_position = 0  # Current playback position (chunk sequence number)
        self.playback_started = False
        self.playback_rate = 1.0  # Normal speed
        
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
                
        # Create buffered chunk
        buffered_chunk = BufferedChunk(
            chunk_id=chunk_id,
            sequence_num=sequence_num,
            data=chunk_data,
            size_bytes=len(chunk_data),
            buffered_at=time.time()
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
            return None
            
        # Get next chunk in sequence
        next_chunk = None
        for i, chunk in enumerate(self.buffer):
            if chunk.sequence_num == self.current_position:
                next_chunk = self.buffer[i]
                del self.buffer[i]
                break
                
        if next_chunk:
            self.current_position += 1
            self.total_chunks_played += 1
            self.last_chunk_played_time = time.time()
            
            if not self.playback_started:
                self.playback_started = True
                self.playback_start_time = time.time()
                logger.info("Playback started")
                
            logger.debug(f"Playing chunk {next_chunk.chunk_id} (seq {next_chunk.sequence_num}). Buffer: {self.get_buffer_level_seconds():.1f}s")
            
        else:
            # Expected chunk not in buffer (gap in sequence)
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
        self.buffer.clear()
        self.current_position = 0
        self.playback_started = False
        self.total_chunks_buffered = 0
        self.total_chunks_played = 0
        self.rebuffering_events = 0
        self.last_rebuffer_time = 0
        self.playback_start_time = None
        self.last_chunk_played_time = None
        self.buffer_level_history.clear()
        
        logger.info("Buffer manager reset")
