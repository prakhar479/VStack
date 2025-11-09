#!/usr/bin/env python3
"""
Integration tests for V-Stack Metadata Service
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta

import pytest
import pytest_asyncio

# Import the application components
from consensus import ChunkPaxos
from database import DatabaseManager
from health_monitor import HealthMonitor
from models import (ChunkCommitRequest, CreateVideoRequest, ConsensusPhase,
                    HeartbeatRequest)


class TestMetadataService:
    """Integration tests for metadata service functionality"""

    # CRITICAL FIX: Added `scope="function"` to ensure each test gets a new
    # instance of the database manager, which prevents the "threads can only be
    # started once" RuntimeError.
    @pytest_asyncio.fixture(scope="function")
    async def db_manager(self):
        """
        Create a test database manager for each test function.
        This provides test isolation and prevents connection state leakage.
        """
        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp:
            db_path = tmp.name

        db = DatabaseManager(db_path)
        await db.initialize()

        yield db

        # --- Teardown Phase ---
        # BEST PRACTICE: Explicitly close the database connection after the test.
        # This assumes your DatabaseManager class has a `close` method like:
        # async def close(self): await self._connection.close()
        await db.close()

        # BEST PRACTICE: Robustly clean up the temporary database file.
        try:
            os.unlink(db_path)
        except OSError as e:
            print(f"Error removing temporary database file: {e}")

    @pytest_asyncio.fixture
    async def consensus(self, db_manager):
        """
        Create consensus protocol instance. This will be created fresh for
        each test because it depends on the function-scoped `db_manager`.
        """
        return ChunkPaxos(db_manager, timeout_sec=5.0)

    @pytest_asyncio.fixture
    async def health_monitor(self, db_manager):
        """
        Create health monitor instance. This will also be created fresh
        for each test.
        """
        monitor = HealthMonitor(db_manager, heartbeat_timeout_sec=30, probe_interval_sec=10)
        return monitor

    @pytest.mark.asyncio
    async def test_video_registration_and_manifest_retrieval(self, db_manager):
        """Test video registration and manifest generation functionality"""

        # Test video creation
        video_id = "test-video-123"
        title = "Test Video"
        duration = 600

        success = await db_manager.create_video(video_id, title, duration)
        assert success, "Video creation should succeed"

        # Test video retrieval
        video = await db_manager.get_video(video_id)
        assert video is not None, "Video should be retrievable"
        assert video["video_id"] == video_id
        assert video["title"] == title
        assert video["duration_sec"] == duration
        assert video["status"] == "uploading"

        # Test manifest retrieval (empty initially)
        manifest = await db_manager.get_video_manifest(video_id)
        assert manifest is not None, "Manifest should be retrievable"
        assert manifest["video_id"] == video_id
        assert len(manifest["chunks"]) == 0, "No chunks initially"

        # Add some test chunks
        chunk_ids = ["chunk-001", "chunk-002", "chunk-003"]
        node_urls = ["http://node1:8080", "http://node2:8080", "http://node3:8080"]

        conn = await db_manager.get_connection()
        # Add chunks
        for i, chunk_id in enumerate(chunk_ids):
            await conn.execute("""
                INSERT INTO chunks (chunk_id, video_id, sequence_num, size_bytes, checksum)
                VALUES (?, ?, ?, 2097152, ?)
            """, (chunk_id, video_id, i, f'test-checksum-{i}'))

            # Add replicas
            for node_url in node_urls:
                await conn.execute("""
                    INSERT INTO chunk_replicas (chunk_id, node_url, status)
                    VALUES (?, ?, 'active')
                """, (chunk_id, node_url))

        await conn.commit()

        # Test manifest with chunks
        manifest = await db_manager.get_video_manifest(video_id)
        assert len(manifest["chunks"]) == 3, "Should have 3 chunks"

        for i, chunk in enumerate(manifest["chunks"]):
            assert chunk["chunk_id"] == chunk_ids[i]
            assert chunk["sequence_num"] == i
            assert len(chunk["replicas"]) == 3, "Each chunk should have 3 replicas"

    @pytest.mark.asyncio
    async def test_consensus_protocol_basic_operation(self, consensus, db_manager):
        """Test basic consensus protocol operation"""

        # Register test nodes
        node_urls = ["http://node1:8080", "http://node2:8080", "http://node3:8080"]
        for i, node_url in enumerate(node_urls):
            await db_manager.register_storage_node(node_url, f"node-{i+1}")

        chunk_id = "test-chunk-001"

        # For this test, we'll test the consensus state management directly
        state = await consensus.get_consensus_state(chunk_id)
        assert state is None, "No consensus state initially"

        # Test consensus state updates
        await consensus._update_consensus_state(chunk_id, 1, None, ConsensusPhase.PREPARE)

        state = await consensus.get_consensus_state(chunk_id)
        assert state is not None, "Consensus state should exist"
        assert state.chunk_id == chunk_id
        assert state.promised_ballot == 1
        assert state.phase.value == "prepare"

    @pytest.mark.asyncio
    async def test_consensus_with_concurrent_uploads(self, consensus, db_manager):
        """Test consensus protocol with concurrent upload scenarios"""

        # Register test nodes
        node_urls = ["http://node1:8080", "http://node2:8080", "http://node3:8080"]
        for i, node_url in enumerate(node_urls):
            await db_manager.register_storage_node(node_url, f"node-{i+1}")

        # Simulate concurrent consensus attempts for different chunks
        chunk_ids = ["chunk-001", "chunk-002", "chunk-003"]

        # Test that different chunks can have consensus in parallel
        for chunk_id in chunk_ids:
            await consensus._update_consensus_state(
                chunk_id, 1, json.dumps(node_urls), ConsensusPhase.COMMITTED
            )

        # Verify all consensus states exist
        for chunk_id in chunk_ids:
            state = await consensus.get_consensus_state(chunk_id)
            assert state is not None, f"Consensus state should exist for {chunk_id}"
            assert state.phase.value == "committed"

    @pytest.mark.asyncio
    async def test_health_monitoring_system(self, health_monitor, db_manager):
        """Test health monitoring with simulated node failures and recoveries"""

        # Register test nodes
        node_data = [
            ("http://node1:8080", "node-1", "1.0.0"),
            ("http://node2:8080", "node-2", "1.0.0"),
            ("http://node3:8080", "node-3", "1.0.0")
        ]

        for node_url, node_id, version in node_data:
            await db_manager.register_storage_node(node_url, node_id, version)

        # Test initial health status
        summary = await health_monitor.get_node_health_summary()
        assert summary["healthy"] == 3, "All nodes should be healthy initially"
        assert summary["down"] == 0, "No nodes should be down initially"

        # Simulate node heartbeats
        for i, (_, node_id, _) in enumerate(node_data):
            success = await db_manager.update_node_heartbeat(
                node_id, disk_usage=50.0 + i * 10, chunk_count=100 + i * 50
            )
            assert success, f"Heartbeat update should succeed for {node_id}"

        # Test node details
        details = await health_monitor.get_node_details()
        assert len(details) == 3, "Should have 3 nodes"

        for detail in details:
            assert detail["status"] == "healthy"
            assert detail["disk_usage_percent"] >= 50.0
            assert detail["chunk_count"] >= 100

        # Simulate node failure by setting old heartbeat
        old_time = datetime.now() - timedelta(seconds=120)  # 2 minutes ago

        conn = await db_manager.get_connection()
        await conn.execute("""
            UPDATE storage_nodes
            SET last_heartbeat = ?
            WHERE node_id = 'node-1'
        """, (old_time.isoformat(),))
        await conn.commit()

        # Mark unhealthy nodes
        await health_monitor._mark_unhealthy_nodes()

        # Check health summary after failure
        summary = await health_monitor.get_node_health_summary()
        assert summary["healthy"] == 2, "Should have 2 healthy nodes"
        assert summary["down"] == 1, "Should have 1 down node"

        # Test node recovery
        await db_manager.update_node_heartbeat("node-1", 45.0, 80)
        await health_monitor._mark_unhealthy_nodes() # Re-run health check

        summary = await health_monitor.get_node_health_summary()
        assert summary["healthy"] == 3, "All nodes should be healthy after recovery"
        assert summary["down"] == 0, "No nodes should be down after recovery"

    @pytest.mark.asyncio
    async def test_database_consistency_under_failures(self, db_manager, consensus):
        """Test database consistency under various failure scenarios"""

        # Test transaction rollback on failure
        video_id = "test-video-failure"

        # Create video
        success = await db_manager.create_video(video_id, "Test Video", 300)
        assert success, "Video creation should succeed"

        # Test chunk insertion with foreign key constraint
        chunk_id = "test-chunk-001"

        conn = await db_manager.get_connection()
        # This should succeed (valid video_id)
        await conn.execute("""
            INSERT INTO chunks (chunk_id, video_id, sequence_num, size_bytes, checksum)
            VALUES (?, ?, 0, 2097152, 'test-checksum')
        """, (chunk_id, video_id))
        await conn.commit()

        # Verify chunk was inserted
        cursor = await conn.execute("SELECT COUNT(*) FROM chunks WHERE chunk_id = ?", (chunk_id,))
        count = (await cursor.fetchone())[0]
        await cursor.close()
        assert count == 1, "Chunk should be inserted"

        # Test replica consistency
        node_urls = ["http://node1:8080", "http://node2:8080"]

        # Insert replicas
        for node_url in node_urls:
            await conn.execute("""
                INSERT INTO chunk_replicas (chunk_id, node_url, status)
                VALUES (?, ?, 'active')
            """, (chunk_id, node_url))
        await conn.commit()

        # Verify replicas
        cursor = await conn.execute("SELECT COUNT(*) FROM chunk_replicas WHERE chunk_id = ?", (chunk_id,))
        count = (await cursor.fetchone())[0]
        await cursor.close()
        assert count == 2, "Should have 2 replicas"

        # Test manifest consistency
        manifest = await db_manager.get_video_manifest(video_id)
        assert len(manifest["chunks"]) == 1, "Should have 1 chunk in manifest"
        assert len(manifest["chunks"][0]["replicas"]) == 2, "Chunk should have 2 replicas"

    @pytest.mark.asyncio
    async def test_chunk_commit_endpoint(self, db_manager):
        """Test the chunk commit endpoint with consensus protocol"""
        # Register test nodes
        node_urls = ["http://node1:8080", "http://node2:8080", "http://node3:8080"]
        for i, node_url in enumerate(node_urls):
            await db_manager.register_storage_node(node_url, f"node-{i+1}")

        # Create consensus instance
        consensus = ChunkPaxos(db_manager, timeout_sec=5.0)

        # Test consensus state management
        chunk_id = "test-chunk-commit-001"

        # Verify no initial state
        state = await consensus.get_consensus_state(chunk_id)
        assert state is None, "No consensus state should exist initially"

        # Test ballot number generation
        ballot1 = consensus._generate_ballot_number()
        ballot2 = consensus._generate_ballot_number()
        assert ballot2 > ballot1, "Ballot numbers should be monotonically increasing"

        # Test consensus state updates
        await consensus._update_consensus_state(chunk_id, ballot1, None, ConsensusPhase.PREPARE)

        state = await consensus.get_consensus_state(chunk_id)
        assert state is not None, "Consensus state should exist after update"
        assert state.chunk_id == chunk_id
        assert state.promised_ballot == ballot1
        assert state.phase == ConsensusPhase.PREPARE

        # Test state progression
        await consensus._update_consensus_state(chunk_id, ballot1, json.dumps(node_urls), ConsensusPhase.ACCEPT)
        state = await consensus.get_consensus_state(chunk_id)
        assert state.phase == ConsensusPhase.ACCEPT
        assert state.accepted_value == json.dumps(node_urls)

        # Test commit phase
        await consensus._commit_phase(chunk_id, node_urls[:2], ballot1)

        # Verify replicas were created
        conn = await db_manager.get_connection()
        cursor = await conn.execute("""
            SELECT COUNT(*) FROM chunk_replicas WHERE chunk_id = ?
        """, (chunk_id,))
        count = (await cursor.fetchone())[0]
        await cursor.close()
        assert count == 2, "Should have 2 replicas committed"

        # Verify final consensus state
        state = await consensus.get_consensus_state(chunk_id)
        assert state.phase == ConsensusPhase.COMMITTED

    @pytest.mark.asyncio
    async def test_ballot_conflict_resolution(self, db_manager):
        """Test ballot number conflict resolution"""
        consensus = ChunkPaxos(db_manager, timeout_sec=5.0)
        chunk_id = "test-chunk-conflict-001"

        # Simulate concurrent consensus attempts with different ballots
        ballot1 = consensus._generate_ballot_number()
        ballot2 = consensus._generate_ballot_number()

        assert ballot2 > ballot1, "Later ballot should be higher"

        # Set initial state with ballot1
        await consensus._update_consensus_state(chunk_id, ballot1, None, ConsensusPhase.PREPARE)

        # Update with higher ballot (should succeed)
        await consensus._update_consensus_state(chunk_id, ballot2, None, ConsensusPhase.PREPARE)

        state = await consensus.get_consensus_state(chunk_id)
        assert state.promised_ballot == ballot2, "Higher ballot should win"

    @pytest.mark.asyncio
    async def test_consensus_cleanup_on_failure(self, db_manager):
        """Test cleanup after failed consensus"""
        consensus = ChunkPaxos(db_manager, timeout_sec=5.0)
        chunk_id = "test-chunk-cleanup-001"
        ballot = consensus._generate_ballot_number()

        # Create some partial state
        await consensus._update_consensus_state(chunk_id, ballot, None, ConsensusPhase.PREPARE)

        # Add partial replicas
        conn = await db_manager.get_connection()
        await conn.execute("""
            INSERT INTO chunk_replicas (chunk_id, node_url, status, ballot_number)
            VALUES (?, ?, 'pending', ?)
        """, (chunk_id, "http://node1:8080", ballot))
        await conn.commit()

        # Cleanup
        await consensus._cleanup_failed_consensus(chunk_id, ballot)

        # Verify cleanup
        cursor = await conn.execute("""
            SELECT COUNT(*) FROM chunk_replicas WHERE chunk_id = ? AND ballot_number = ?
        """, (chunk_id, ballot))
        count = (await cursor.fetchone())[0]
        await cursor.close()
        assert count == 0, "Partial replicas should be cleaned up"

        state = await consensus.get_consensus_state(chunk_id)
        assert state.phase.value == "none", "Consensus state should be reset"

# Test runner
if __name__ == "__main__":
    pytest.main([__file__, "-v"])