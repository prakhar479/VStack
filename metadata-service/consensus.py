#!/usr/bin/env python3
"""
ChunkPaxos consensus protocol implementation for V-Stack
"""

import asyncio
import httpx
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import json
import random

from database import DatabaseManager
from models import ConsensusPhase, ConsensusState

logger = logging.getLogger(__name__)

class ChunkPaxosError(Exception):
    """Base exception for ChunkPaxos protocol errors"""
    pass

class QuorumNotReachedException(ChunkPaxosError):
    """Raised when quorum cannot be reached"""
    pass

class BallotConflictException(ChunkPaxosError):
    """Raised when ballot number conflicts occur"""
    pass

class ChunkPaxos:
    """
    Simplified consensus protocol for chunk placement coordination.
    
    ChunkPaxos exploits the fact that writing different chunks doesn't conflict,
    allowing multiple instances to run in parallel. This is a key simplification
    over full Paxos.
    """
    
    def __init__(self, db_manager: DatabaseManager, timeout_sec: float = 10.0):
        self.db = db_manager
        self.timeout = timeout_sec
        self.ballot_counter = 0
    
    def _generate_ballot_number(self) -> int:
        """Generate unique ballot number"""
        self.ballot_counter += 1
        # Include timestamp to ensure uniqueness across restarts
        timestamp = int(datetime.now().timestamp() * 1000)
        return (timestamp << 16) | (self.ballot_counter & 0xFFFF)
    
    async def propose_chunk_placement(self, chunk_id: str, node_urls: List[str], 
                                    checksum: str, size_bytes: int, video_id: str, 
                                    sequence_num: int, redundancy_mode: str = "replication",
                                    fragments_metadata: Optional[List[Dict]] = None) -> Tuple[bool, List[str]]:
        """
        Propose chunk placement using simplified quorum-based consensus.
        
        Returns:
            Tuple of (success, committed_nodes)
        """
        if len(node_urls) < 1:
            raise ValueError("At least one node required for consensus")
        
        quorum_size = len(node_urls) // 2 + 1
        ballot_number = self._generate_ballot_number()
        
        logger.info(f"Starting consensus for chunk {chunk_id} with ballot {ballot_number}")
        
        # Retry logic with exponential backoff
        max_retries = 3
        base_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                # Phase 1: Prepare - Check if nodes can accept this chunk
                prepare_responses = await self._prepare_phase(chunk_id, node_urls, ballot_number)
                
                if len(prepare_responses) < quorum_size:
                    logger.warning(f"Prepare phase failed for {chunk_id}: only {len(prepare_responses)}/{quorum_size} responses")
                    
                    # If not enough nodes, try with a new ballot number
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.info(f"Retrying consensus for {chunk_id} in {delay}s (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(delay)
                        ballot_number = self._generate_ballot_number()
                        continue
                    else:
                        raise QuorumNotReachedException(f"Prepare phase: {len(prepare_responses)}/{quorum_size}")
                
                # Phase 2: Accept - Request nodes to store the chunk
                accept_responses = await self._accept_phase(chunk_id, prepare_responses, 
                                                         ballot_number, checksum, size_bytes)
                
                if len(accept_responses) < quorum_size:
                    logger.warning(f"Accept phase failed for {chunk_id}: only {len(accept_responses)}/{quorum_size} responses")
                    
                    # If not enough accepts, try with a new ballot number
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.info(f"Retrying consensus for {chunk_id} in {delay}s (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(delay)
                        ballot_number = self._generate_ballot_number()
                        continue
                    else:
                        raise QuorumNotReachedException(f"Accept phase: {len(accept_responses)}/{quorum_size}")
                
                # Phase 3: Commit - Update metadata database
                await self._commit_phase(chunk_id, accept_responses, ballot_number, 
                                       checksum, size_bytes, video_id, sequence_num,
                                       redundancy_mode, fragments_metadata)
                
                logger.info(f"Consensus successful for {chunk_id} on nodes: {accept_responses}")
                return True, accept_responses
                
            except (QuorumNotReachedException, BallotConflictException) as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    logger.info(f"Consensus attempt {attempt + 1} failed for {chunk_id}: {e}. Retrying in {delay}s")
                    await asyncio.sleep(delay)
                    ballot_number = self._generate_ballot_number()
                    continue
                else:
                    logger.error(f"Consensus failed for {chunk_id} after {max_retries} attempts: {e}")
                    await self._cleanup_failed_consensus(chunk_id, ballot_number)
                    return False, []
            except Exception as e:
                logger.error(f"Consensus failed for {chunk_id}: {e}")
                await self._cleanup_failed_consensus(chunk_id, ballot_number)
                return False, []
        
        return False, []
    
    async def _prepare_phase(self, chunk_id: str, node_urls: List[str], 
                           ballot_number: int) -> List[str]:
        """
        Phase 1: Send prepare requests to all nodes.
        Nodes respond if they can accept this ballot number.
        """
        logger.debug(f"Prepare phase for {chunk_id} with ballot {ballot_number}")
        
        # Update consensus state
        await self._update_consensus_state(chunk_id, ballot_number, None, ConsensusPhase.PREPARE)
        
        # Send prepare requests to all nodes
        prepare_tasks = [
            self._send_prepare_request(node_url, chunk_id, ballot_number)
            for node_url in node_urls
        ]
        
        results = await asyncio.gather(*prepare_tasks, return_exceptions=True)
        
        # Collect successful responses
        successful_nodes = []
        for i, result in enumerate(results):
            if isinstance(result, bool) and result:
                successful_nodes.append(node_urls[i])
            elif isinstance(result, Exception):
                logger.debug(f"Prepare failed for {node_urls[i]}: {result}")
        
        return successful_nodes
    
    async def _send_prepare_request(self, node_url: str, chunk_id: str, 
                                  ballot_number: int) -> bool:
        """Send prepare request to a single node"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.head(
                    f"{node_url}/chunk/{chunk_id}",
                    headers={"X-Ballot-Number": str(ballot_number)}
                )
                
                # Node accepts if chunk doesn't exist or ballot is higher
                if response.status_code == 404:  # Chunk doesn't exist - good
                    return True
                elif response.status_code == 200:  # Chunk exists - check ballot
                    existing_ballot = int(response.headers.get("X-Ballot-Number", "0"))
                    if ballot_number > existing_ballot:
                        return True
                    elif ballot_number < existing_ballot:
                        # Higher ballot number exists - conflict
                        raise BallotConflictException(f"Higher ballot {existing_ballot} exists on {node_url}")
                    else:
                        # Same ballot number - this is unusual but acceptable
                        return True
                elif response.status_code == 409:  # Conflict - node is busy with another consensus
                    logger.debug(f"Node {node_url} busy with another consensus for {chunk_id}")
                    return False
                else:
                    return False
                    
        except BallotConflictException:
            raise  # Re-raise ballot conflicts
        except Exception as e:
            logger.debug(f"Prepare request failed for {node_url}: {e}")
            return False
    
    async def _accept_phase(self, chunk_id: str, prepared_nodes: List[str],
                          ballot_number: int, checksum: str, size_bytes: int) -> List[str]:
        """
        Phase 2: Send accept requests to prepared nodes.
        Nodes store the chunk if they still accept this ballot.
        """
        logger.debug(f"Accept phase for {chunk_id} with {len(prepared_nodes)} nodes")
        
        # Update consensus state
        node_list_json = json.dumps(prepared_nodes)
        await self._update_consensus_state(chunk_id, ballot_number, node_list_json, ConsensusPhase.ACCEPT)
        
        # Send accept requests
        accept_tasks = [
            self._send_accept_request(node_url, chunk_id, ballot_number, checksum, size_bytes)
            for node_url in prepared_nodes
        ]
        
        results = await asyncio.gather(*accept_tasks, return_exceptions=True)
        
        # Collect successful responses
        accepted_nodes = []
        for i, result in enumerate(results):
            if isinstance(result, bool) and result:
                accepted_nodes.append(prepared_nodes[i])
            elif isinstance(result, Exception):
                logger.debug(f"Accept failed for {prepared_nodes[i]}: {result}")
        
        return accepted_nodes
    
    async def _send_accept_request(self, node_url: str, chunk_id: str,
                                 ballot_number: int, checksum: str, size_bytes: int) -> bool:
        """Send accept request to a single node"""
        try:
            # First verify the chunk exists and has correct checksum
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.head(f"{node_url}/chunk/{chunk_id}")
                
                if response.status_code == 200:
                    # Verify checksum matches
                    node_checksum = response.headers.get("ETag", "").strip('"')
                    if node_checksum == checksum:
                        return True
                    else:
                        logger.warning(f"Checksum mismatch for {chunk_id} on {node_url}")
                        return False
                else:
                    logger.warning(f"Chunk {chunk_id} not found on {node_url}")
                    return False
                    
        except Exception as e:
            logger.debug(f"Accept request failed for {node_url}: {e}")
            return False
    
    async def _commit_phase(self, chunk_id: str, accepted_nodes: List[str], 
                          ballot_number: int, checksum: str, size_bytes: int,
                          video_id: str, sequence_num: int, redundancy_mode: str = "replication",
                          fragments_metadata: Optional[List[Dict]] = None):
        """
        Phase 3: Commit the consensus result to metadata database.
        """
        logger.debug(f"Commit phase for {chunk_id} with {len(accepted_nodes)} nodes")
        
        try:
            conn = await self.db.get_connection()
            
            # Insert chunk metadata into chunks table
            await conn.execute("""
                INSERT OR REPLACE INTO chunks 
                (chunk_id, video_id, sequence_num, size_bytes, checksum, redundancy_mode, created_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (chunk_id, video_id, sequence_num, size_bytes, checksum, redundancy_mode))
            
            # Insert chunk replicas or fragments
            if redundancy_mode == "erasure_coding" and fragments_metadata:
                # Store fragment metadata
                for frag in fragments_metadata:
                    await conn.execute("""
                        INSERT OR REPLACE INTO chunk_fragments 
                        (fragment_id, chunk_id, fragment_index, node_url, size_bytes, checksum, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP)
                    """, (frag['fragment_id'], frag['chunk_id'], frag['fragment_index'],
                          frag['node_url'], frag['size_bytes'], frag['checksum']))
            else:
                # Store replicas
                for node_url in accepted_nodes:
                    await conn.execute("""
                        INSERT OR REPLACE INTO chunk_replicas 
                        (chunk_id, node_url, status, ballot_number, created_at)
                        VALUES (?, ?, 'active', ?, CURRENT_TIMESTAMP)
                    """, (chunk_id, node_url, ballot_number))
            
            # Update video total_chunks count
            await conn.execute("""
                UPDATE videos 
                SET total_chunks = (
                    SELECT COUNT(DISTINCT chunk_id) 
                    FROM chunks 
                    WHERE video_id = ?
                )
                WHERE video_id = ?
            """, (video_id, video_id))
            
            await conn.commit()
            
            # Update consensus state to committed
            await self._update_consensus_state(chunk_id, ballot_number, 
                                             json.dumps(accepted_nodes), ConsensusPhase.COMMITTED)
            
        except Exception as e:
            logger.error(f"Commit phase failed for {chunk_id}: {e}")
            raise
    
    async def _update_consensus_state(self, chunk_id: str, ballot_number: int,
                                    accepted_value: Optional[str], phase: ConsensusPhase):
        """Update consensus state in database"""
        try:
            conn = await self.db.get_connection()
            await conn.execute("""
                INSERT OR REPLACE INTO consensus_state 
                (chunk_id, promised_ballot, accepted_ballot, accepted_value, phase)
                VALUES (?, ?, ?, ?, ?)
            """, (chunk_id, ballot_number, ballot_number, accepted_value, phase.value))
            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to update consensus state for {chunk_id}: {e}")
    
    async def _cleanup_failed_consensus(self, chunk_id: str, ballot_number: int):
        """Clean up after failed consensus attempt"""
        try:
            conn = await self.db.get_connection()
            
            # Remove any partial replica entries
            await conn.execute("""
                DELETE FROM chunk_replicas 
                WHERE chunk_id = ? AND ballot_number = ?
            """, (chunk_id, ballot_number))
            
            # Reset consensus state
            await conn.execute("""
                UPDATE consensus_state 
                SET phase = 'none', accepted_value = NULL
                WHERE chunk_id = ?
            """, (chunk_id,))
            
            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to cleanup consensus for {chunk_id}: {e}")
    
    async def get_consensus_state(self, chunk_id: str) -> Optional[ConsensusState]:
        """Get current consensus state for a chunk"""
        try:
            conn = await self.db.get_connection()
            cursor = await conn.execute("""
                SELECT chunk_id, promised_ballot, accepted_ballot, accepted_value, phase
                FROM consensus_state WHERE chunk_id = ?
            """, (chunk_id,))
            row = await cursor.fetchone()
            await cursor.close()
            
            if row:
                return ConsensusState(
                    chunk_id=row[0],
                    promised_ballot=row[1],
                    accepted_ballot=row[2],
                    accepted_value=row[3],
                    phase=ConsensusPhase(row[4])
                )
            return None
        except Exception as e:
            logger.error(f"Failed to get consensus state for {chunk_id}: {e}")
            return None