#!/usr/bin/env python3
"""
Simple integration tests for V-Stack Metadata Service
"""

import asyncio
import pytest
import tempfile
import os
import json
from datetime import datetime, timedelta

# Import the application components
from database import DatabaseManager
from consensus import ChunkPaxos
from health_monitor import HealthMonitor
from models import ConsensusPhase

@pytest.mark.asyncio
async def test_database_operations():
    """Test basic database operations"""
    print("Testing database operations...")
    
    # Create temporary database
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        db_path = tmp.name
    
    try:
        db = DatabaseManager(db_path)
        await db.initialize()
        
        # Test video creation
        video_id = "test-video-123"
        success = await db.create_video(video_id, "Test Video", 600)
        assert success, "Video creation failed"
        
        # Test video retrieval
        video = await db.get_video(video_id)
        assert video is not None, "Video retrieval failed"
        assert video["video_id"] == video_id
        
        # Test node registration
        success = await db.register_storage_node("http://node1:8080", "node-1")
        assert success, "Node registration failed"
        
        # Test healthy nodes
        nodes = await db.get_healthy_nodes()
        assert len(nodes) == 1, "Should have 1 healthy node"
        
        print("✓ Database operations test passed")
        
    finally:
        os.unlink(db_path)

@pytest.mark.asyncio
async def test_consensus_state_management():
    """Test consensus protocol state management"""
    print("Testing consensus state management...")
    
    # Create temporary database
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        db_path = tmp.name
    
    try:
        db = DatabaseManager(db_path)
        await db.initialize()
        
        consensus = ChunkPaxos(db)
        
        # Test consensus state creation
        chunk_id = "test-chunk-001"
        
        # Initially no state
        state = await consensus.get_consensus_state(chunk_id)
        assert state is None, "Should have no initial state"
        
        # Create consensus state
        await consensus._update_consensus_state(chunk_id, 1, None, ConsensusPhase.PREPARE)
        
        # Verify state
        state = await consensus.get_consensus_state(chunk_id)
        assert state is not None, "State should exist"
        assert state.chunk_id == chunk_id
        assert state.promised_ballot == 1
        assert state.phase == ConsensusPhase.PREPARE
        
        print("✓ Consensus state management test passed")
        
    finally:
        os.unlink(db_path)

@pytest.mark.asyncio
async def test_health_monitoring():
    """Test health monitoring functionality"""
    print("Testing health monitoring...")
    
    # Create temporary database
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        db_path = tmp.name
    
    try:
        db = DatabaseManager(db_path)
        await db.initialize()
        
        monitor = HealthMonitor(db, heartbeat_timeout_sec=30)
        
        # Register test nodes
        await db.register_storage_node("http://node1:8080", "node-1")
        await db.register_storage_node("http://node2:8080", "node-2")
        
        # Test health summary
        summary = await monitor.get_node_health_summary()
        assert summary["healthy"] == 2, "Should have 2 healthy nodes"
        
        # Test node details
        details = await monitor.get_node_details()
        assert len(details) == 2, "Should have 2 nodes in details"
        
        # Test heartbeat update
        success = await db.update_node_heartbeat("node-1", 50.0, 100)
        assert success, "Heartbeat update should succeed"
        
        print("✓ Health monitoring test passed")
        
    finally:
        os.unlink(db_path)

@pytest.mark.asyncio
async def test_video_manifest():
    """Test video manifest generation"""
    print("Testing video manifest generation...")
    
    # Create temporary database
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        db_path = tmp.name
    
    try:
        db = DatabaseManager(db_path)
        await db.initialize()
        
        # Create video
        video_id = "test-video-manifest"
        await db.create_video(video_id, "Manifest Test", 300)
        
        # Add chunks and replicas
        chunk_ids = ["chunk-001", "chunk-002"]
        node_urls = ["http://node1:8080", "http://node2:8080"]
        
        conn = await db.get_connection()
        # Add chunks
        for i, chunk_id in enumerate(chunk_ids):
            await conn.execute("""
                INSERT INTO chunks (chunk_id, video_id, sequence_num, size_bytes, checksum)
                VALUES (?, ?, ?, 2097152, ?)
            """, (chunk_id, video_id, i, f"checksum-{i}"))
            
            # Add replicas
            for node_url in node_urls:
                await conn.execute("""
                    INSERT INTO chunk_replicas (chunk_id, node_url, status)
                    VALUES (?, ?, 'active')
                """, (chunk_id, node_url))
        
        await conn.commit()
        
        # Test manifest retrieval
        manifest = await db.get_video_manifest(video_id)
        assert manifest is not None, "Manifest should exist"
        assert len(manifest["chunks"]) == 2, "Should have 2 chunks"
        
        for chunk in manifest["chunks"]:
            assert len(chunk["replicas"]) == 2, "Each chunk should have 2 replicas"
        
        print("✓ Video manifest test passed")
        
    finally:
        os.unlink(db_path)

@pytest.mark.asyncio
async def test_node_failure_simulation():
    """Test node failure detection"""
    print("Testing node failure simulation...")
    
    # Create temporary database
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        db_path = tmp.name
    
    try:
        db = DatabaseManager(db_path)
        await db.initialize()
        
        monitor = HealthMonitor(db, heartbeat_timeout_sec=1)  # Very short timeout for testing
        
        # Register nodes
        await db.register_storage_node("http://node1:8080", "node-1")
        await db.register_storage_node("http://node2:8080", "node-2")
        
        # Initial state - all healthy
        summary = await monitor.get_node_health_summary()
        assert summary["healthy"] == 2, "Should have 2 healthy nodes initially"
        
        # Simulate old heartbeat for node-1
        old_time = datetime.now() - timedelta(seconds=120)
        conn = await db.get_connection()
        await conn.execute("""
            UPDATE storage_nodes 
            SET last_heartbeat = ?
            WHERE node_id = 'node-1'
        """, (old_time.isoformat(),))
        await conn.commit()
        
        # Mark unhealthy nodes
        await monitor._mark_unhealthy_nodes()
        
        # Check results
        summary = await monitor.get_node_health_summary()
        assert summary["healthy"] == 1, "Should have 1 healthy node after failure"
        assert summary["down"] == 1, "Should have 1 down node"
        
        print("✓ Node failure simulation test passed")
        
    finally:
        os.unlink(db_path)

async def run_all_tests():
    """Run all tests"""
    print("Starting V-Stack Metadata Service Integration Tests")
    print("=" * 60)
    
    try:
        await test_database_operations()
        await test_consensus_state_management()
        await test_health_monitoring()
        await test_video_manifest()
        await test_node_failure_simulation()
        
        print("=" * 60)
        print("✓ All tests passed successfully!")
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)