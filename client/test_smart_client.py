#!/usr/bin/env python3
"""
Comprehensive tests for Smart Client components
"""

import asyncio
import pytest
import time
from unittest.mock import Mock, AsyncMock, patch
from collections import deque

from network_monitor import NetworkMonitor
from scheduler import ChunkScheduler
from buffer_manager import BufferManager
from config import config

# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


class TestNetworkMonitor:
    """Tests for NetworkMonitor class."""
    
    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test network monitor initialization."""
        with patch('config.config.PING_INTERVAL', 3.0), \
             patch('config.config.HISTORY_SIZE', 10):
            monitor = NetworkMonitor()
            
            assert monitor.ping_interval == 3.0
            assert monitor.history_size == 10
            assert not monitor.monitoring
            assert len(monitor.node_urls) == 0
        
    @pytest.mark.asyncio
    async def test_start_stop_monitoring(self):
        """Test starting and stopping network monitoring."""
        monitor = NetworkMonitor()
        nodes = ['http://node1:8080', 'http://node2:8080']
        
        try:
            # Start monitoring
            session = AsyncMock()
            await monitor.start_monitoring(nodes, session)
            assert monitor.monitoring
            assert monitor.node_urls == nodes
            assert monitor.session == session
            
            # Give it a moment to run
            await asyncio.sleep(0.5)
        finally:
            # Always stop monitoring to cleanup
            await monitor.stop_monitoring()
            assert not monitor.monitoring
            assert monitor.session is None
        
    @pytest.mark.asyncio
    async def test_node_scoring_formula(self):
        """Test node scoring formula: (bandwidth × reliability) / (1 + latency × 0.1)."""
        monitor = NetworkMonitor()
        node_url = 'http://test-node:8080'
        
        # Add test measurements
        monitor.latencies[node_url].extend([20.0, 20.0, 20.0])  # 20ms average
        monitor.bandwidths[node_url].extend([50.0, 50.0, 50.0])  # 50 Mbps average
        monitor.success_rates[node_url].extend([1.0, 1.0, 1.0])  # 100% success
        
        score = monitor.get_node_score(node_url)
        
        # Expected: (50 × 1.0) / (1 + 20 × 0.1) = 50 / 3 = 16.67
        expected_score = (50.0 * 1.0) / (1 + 20.0 * 0.1)
        assert abs(score - expected_score) < 0.01
        
    @pytest.mark.asyncio
    async def test_node_health_check(self):
        """Test node health checking."""
        monitor = NetworkMonitor()
        node_url = 'http://test-node:8080'
        
        # Node with no data should be unhealthy
        assert not monitor.is_node_healthy(node_url)
        
        # Add recent successful measurements
        monitor.latencies[node_url].append(20.0)
        monitor.success_rates[node_url].extend([1.0, 1.0, 1.0])
        monitor.last_update[node_url] = time.time()
        
        assert monitor.is_node_healthy(node_url)
        
        # Node with old data should be unhealthy
        monitor.last_update[node_url] = time.time() - 60  # 60 seconds ago
        assert not monitor.is_node_healthy(node_url, timeout_sec=30)
        
    @pytest.mark.asyncio
    async def test_bandwidth_update(self):
        """Test bandwidth measurement updates."""
        monitor = NetworkMonitor()
        node_url = 'http://test-node:8080'
        
        # Update bandwidth
        monitor.update_bandwidth(node_url, 45.5)
        monitor.update_bandwidth(node_url, 48.2)
        monitor.update_bandwidth(node_url, 46.8)
        
        assert len(monitor.bandwidths[node_url]) == 3
        assert monitor.bandwidths[node_url][-1] == 46.8
        
    @pytest.mark.asyncio
    async def test_get_healthy_nodes(self):
        """Test getting list of healthy nodes."""
        monitor = NetworkMonitor()
        
        # Add healthy node
        node1 = 'http://node1:8080'
        monitor.latencies[node1].append(20.0)
        monitor.success_rates[node1].extend([1.0, 1.0])
        monitor.last_update[node1] = time.time()
        
        # Add unhealthy node (old data)
        node2 = 'http://node2:8080'
        monitor.latencies[node2].append(20.0)
        monitor.success_rates[node2].extend([1.0, 1.0])
        monitor.last_update[node2] = time.time() - 60
        
        monitor.node_urls = [node1, node2]
        
        healthy = monitor.get_healthy_nodes()
        assert node1 in healthy
        assert node2 not in healthy


class TestChunkScheduler:
    """Tests for ChunkScheduler class."""
    
    def test_initialization(self):
        """Test chunk scheduler initialization."""
        monitor = NetworkMonitor()
        with patch('config.config.MAX_CONCURRENT_DOWNLOADS', 4):
            scheduler = ChunkScheduler(monitor)
            
            assert scheduler.max_concurrent_downloads == 4
            assert scheduler.total_downloads == 0
            assert scheduler.failed_downloads == 0
        
    def test_select_best_node(self):
        """Test node selection based on performance scores."""
        monitor = NetworkMonitor()
        scheduler = ChunkScheduler(monitor)
        
        # Setup nodes with different scores
        node1 = 'http://node1:8080'
        node2 = 'http://node2:8080'
        node3 = 'http://node3:8080'
        
        # Node 1: High score
        monitor.latencies[node1].extend([15.0] * 3)
        monitor.bandwidths[node1].extend([50.0] * 3)
        monitor.success_rates[node1].extend([1.0] * 3)
        monitor.last_update[node1] = time.time()
        
        # Node 2: Medium score
        monitor.latencies[node2].extend([25.0] * 3)
        monitor.bandwidths[node2].extend([45.0] * 3)
        monitor.success_rates[node2].extend([1.0] * 3)
        monitor.last_update[node2] = time.time()
        
        # Node 3: Low score
        monitor.latencies[node3].extend([35.0] * 3)
        monitor.bandwidths[node3].extend([40.0] * 3)
        monitor.success_rates[node3].extend([0.8] * 3)
        monitor.last_update[node3] = time.time()
        
        # Select best node
        best = scheduler.select_best_node('chunk-001', [node1, node2, node3])
        
        # Should select node1 (highest score)
        assert best == node1
        
    def test_load_balancing(self):
        """Test that scheduler avoids overloading nodes."""
        monitor = NetworkMonitor()
        scheduler = ChunkScheduler(monitor)
        
        node1 = 'http://node1:8080'
        node2 = 'http://node2:8080'
        
        # Both nodes have same performance
        for node in [node1, node2]:
            monitor.latencies[node].extend([20.0] * 3)
            monitor.bandwidths[node].extend([50.0] * 3)
            monitor.success_rates[node].extend([1.0] * 3)
            monitor.last_update[node] = time.time()
        
        # Simulate node1 being busy
        scheduler.node_load[node1] = 3
        scheduler.node_load[node2] = 0
        
        # Should prefer node2 due to lower load
        best = scheduler.select_best_node('chunk-001', [node1, node2])
        assert best == node2
        
    @pytest.mark.asyncio
    async def test_download_statistics(self):
        """Test download statistics tracking."""
        monitor = NetworkMonitor()
        scheduler = ChunkScheduler(monitor)
        
        # Record successful download
        scheduler._record_successful_download('chunk-001', 'http://node1:8080', 2097152)
        
        assert scheduler.total_downloads == 1
        assert scheduler.chunk_sources['chunk-001'] == 'http://node1:8080'
        
        stats = scheduler.get_statistics()
        assert stats['total_downloads'] == 1
        assert stats['success_rate'] == 1.0


class TestBufferManager:
    """Tests for BufferManager class."""
    
    def test_initialization(self):
        """Test buffer manager initialization."""
        with patch('config.config.TARGET_BUFFER_SEC', 30), \
             patch('config.config.LOW_WATER_MARK_SEC', 15), \
             patch('config.config.CHUNK_DURATION_SEC', 10):
            buffer = BufferManager()
            
            assert buffer.target_buffer_sec == 30
            assert buffer.low_water_mark_sec == 15
            assert buffer.chunk_duration_sec == 10
            assert buffer.current_position == 0
            assert not buffer.playback_started
        
    def test_buffer_level_calculation(self):
        """Test buffer level calculation in seconds."""
        with patch('config.config.CHUNK_DURATION_SEC', 10):
            buffer = BufferManager()
            
            # Empty buffer
            assert buffer.get_buffer_level_seconds() == 0
            
            # Add 3 chunks
            buffer.add_chunk('chunk-0', 0, b'data0')
            buffer.add_chunk('chunk-1', 1, b'data1')
            buffer.add_chunk('chunk-2', 2, b'data2')
            
            # Should be 30 seconds (3 chunks × 10 seconds)
            assert buffer.get_buffer_level_seconds() == 30
        
    def test_needs_more_chunks(self):
        """Test low water mark detection."""
        with patch('config.config.TARGET_BUFFER_SEC', 30), \
             patch('config.config.LOW_WATER_MARK_SEC', 15), \
             patch('config.config.CHUNK_DURATION_SEC', 10):
            buffer = BufferManager()
            
            # Empty buffer needs chunks
            assert buffer.needs_more_chunks()
            
            # Add 2 chunks (20 seconds) - above low water mark
            buffer.add_chunk('chunk-0', 0, b'data0')
            buffer.add_chunk('chunk-1', 1, b'data1')
            
            assert not buffer.needs_more_chunks()
            
            # Add only 1 chunk (10 seconds) - below low water mark
            buffer.buffer.clear()
            buffer.add_chunk('chunk-0', 0, b'data0')
            
            assert buffer.needs_more_chunks()
        
    def test_can_start_playback(self):
        """Test playback start condition."""
        with patch('config.config.START_PLAYBACK_SEC', 10), \
             patch('config.config.CHUNK_DURATION_SEC', 10):
            buffer = BufferManager()
            
            # Not enough buffer
            assert not buffer.can_start_playback()
            
            # Add 1 chunk (10 seconds) - exactly enough
            buffer.add_chunk('chunk-0', 0, b'data0')
            assert buffer.can_start_playback()
        
    def test_add_chunk_in_order(self):
        """Test adding chunks in sequential order."""
        buffer = BufferManager()
        
        # Add chunks in order
        assert buffer.add_chunk('chunk-0', 0, b'data0')
        assert buffer.add_chunk('chunk-1', 1, b'data1')
        assert buffer.add_chunk('chunk-2', 2, b'data2')
        
        assert buffer.get_buffer_level_chunks() == 3
        
    def test_add_chunk_out_of_order(self):
        """Test adding chunks out of order."""
        buffer = BufferManager()
        
        # Add chunks out of order
        assert buffer.add_chunk('chunk-2', 2, b'data2')
        assert buffer.add_chunk('chunk-0', 0, b'data0')
        assert buffer.add_chunk('chunk-1', 1, b'data1')
        
        # Should still have 3 chunks
        assert buffer.get_buffer_level_chunks() == 3
        
        # Chunks should be sorted by sequence number
        sequences = [chunk.sequence_num for chunk in buffer.buffer]
        assert sequences == [0, 1, 2]
        
    def test_reject_duplicate_chunk(self):
        """Test that duplicate chunks are rejected."""
        buffer = BufferManager()
        
        # Add chunk
        assert buffer.add_chunk('chunk-0', 0, b'data0')
        
        # Try to add same chunk again
        assert not buffer.add_chunk('chunk-0', 0, b'data0-duplicate')
        
        # Should still have only 1 chunk
        assert buffer.get_buffer_level_chunks() == 1
        
    def test_reject_old_chunk(self):
        """Test that old chunks (already played) are rejected."""
        buffer = BufferManager()
        buffer.current_position = 5  # Already played chunks 0-4
        
        # Try to add old chunk
        assert not buffer.add_chunk('chunk-3', 3, b'data3')
        
        # Should have 0 chunks
        assert buffer.get_buffer_level_chunks() == 0
        
    def test_get_next_chunk_for_playback(self):
        """Test getting next chunk for playback."""
        buffer = BufferManager()
        
        # Add chunks
        buffer.add_chunk('chunk-0', 0, b'data0')
        buffer.add_chunk('chunk-1', 1, b'data1')
        buffer.add_chunk('chunk-2', 2, b'data2')
        
        # Get chunks in order
        chunk0 = buffer.get_next_chunk_for_playback()
        assert chunk0 is not None
        assert chunk0.sequence_num == 0
        assert buffer.current_position == 1
        
        chunk1 = buffer.get_next_chunk_for_playback()
        assert chunk1.sequence_num == 1
        assert buffer.current_position == 2
        
        # Buffer should have 1 chunk left
        assert buffer.get_buffer_level_chunks() == 1
        
    def test_playback_started_flag(self):
        """Test that playback_started flag is set correctly."""
        buffer = BufferManager()
        
        assert not buffer.playback_started
        
        # Add and play a chunk
        buffer.add_chunk('chunk-0', 0, b'data0')
        buffer.get_next_chunk_for_playback()
        
        assert buffer.playback_started
        
    def test_rebuffering_detection(self):
        """Test rebuffering event detection."""
        buffer = BufferManager()
        
        # Start playback
        buffer.add_chunk('chunk-0', 0, b'data0')
        buffer.get_next_chunk_for_playback()
        
        assert buffer.rebuffering_events == 0
        
        # Try to get chunk from empty buffer (rebuffering)
        chunk = buffer.get_next_chunk_for_playback()
        assert chunk is None
        assert buffer.rebuffering_events == 1
        
    def test_get_next_chunk_sequences(self):
        """Test getting next chunk sequences to download."""
        buffer = BufferManager()
        
        # Empty buffer, starting from position 0
        sequences = buffer.get_next_chunk_sequences(5)
        assert sequences == [0, 1, 2, 3, 4]
        
        # Add some chunks
        buffer.add_chunk('chunk-0', 0, b'data0')
        buffer.add_chunk('chunk-1', 1, b'data1')
        
        # Should get sequences after buffered chunks
        sequences = buffer.get_next_chunk_sequences(3)
        assert sequences == [2, 3, 4]
        
    def test_buffer_statistics(self):
        """Test buffer statistics collection."""
        buffer = BufferManager()
        
        # Add and play chunks
        buffer.add_chunk('chunk-0', 0, b'data0')
        buffer.add_chunk('chunk-1', 1, b'data1')
        buffer.get_next_chunk_for_playback()
        
        stats = buffer.get_statistics()
        
        assert stats['total_chunks_buffered'] == 2
        assert stats['total_chunks_played'] == 1
        assert stats['playback_started'] is True
        
    def test_buffer_status(self):
        """Test buffer status reporting."""
        with patch('config.config.TARGET_BUFFER_SEC', 30), \
             patch('config.config.LOW_WATER_MARK_SEC', 15), \
             patch('config.config.CHUNK_DURATION_SEC', 10):
            buffer = BufferManager()
            
            # Empty buffer
            status = buffer.get_buffer_status()
            assert status['state'] == 'empty'
            assert status['buffer_level_sec'] == 0
            
            # Add chunks to reach healthy state
            buffer.add_chunk('chunk-0', 0, b'data0')
            buffer.add_chunk('chunk-1', 1, b'data1')
            
            status = buffer.get_buffer_status()
            assert status['state'] == 'healthy'
            assert status['buffer_level_sec'] == 20
        
    def test_buffer_reset(self):
        """Test buffer reset functionality."""
        buffer = BufferManager()
        
        # Add chunks and play
        buffer.add_chunk('chunk-0', 0, b'data0')
        buffer.get_next_chunk_for_playback()
        
        # Reset
        buffer.reset()
        
        assert buffer.get_buffer_level_chunks() == 0
        assert buffer.current_position == 0
        assert not buffer.playback_started
        assert buffer.total_chunks_buffered == 0
        assert buffer.total_chunks_played == 0


# Run tests
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
