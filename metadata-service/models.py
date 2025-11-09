#!/usr/bin/env python3
"""
Pydantic models for V-Stack Metadata Service
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

class VideoStatus(str, Enum):
    UPLOADING = "uploading"
    ACTIVE = "active"
    DELETED = "deleted"

class NodeStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"

class ReplicaStatus(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"
    FAILED = "failed"

class ConsensusPhase(str, Enum):
    NONE = "none"
    PREPARE = "prepare"
    ACCEPT = "accept"
    COMMITTED = "committed"

# Request/Response Models
class CreateVideoRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    duration_sec: int = Field(..., gt=0)

class CreateVideoResponse(BaseModel):
    video_id: str
    upload_url: str

class VideoInfo(BaseModel):
    video_id: str
    title: str
    duration_sec: int
    total_chunks: int
    chunk_size_bytes: int = 2097152
    created_at: str
    status: VideoStatus

class RedundancyMode(str, Enum):
    REPLICATION = "replication"
    ERASURE_CODING = "erasure_coding"

class ChunkInfo(BaseModel):
    chunk_id: str
    sequence_num: int
    size_bytes: int
    checksum: str
    replicas: List[str]
    redundancy_mode: RedundancyMode = RedundancyMode.REPLICATION
    fragments: Optional[List[Dict[str, Any]]] = None

class VideoManifest(BaseModel):
    video_id: str
    title: str
    duration_sec: int
    total_chunks: int
    chunk_duration_sec: int = 10
    chunk_size_bytes: int = 2097152
    created_at: str
    status: VideoStatus
    chunks: List[ChunkInfo]

class StorageNode(BaseModel):
    node_url: str
    node_id: str
    last_heartbeat: str
    disk_usage_percent: float
    chunk_count: int
    status: NodeStatus
    version: Optional[str] = "1.0.0"

class HeartbeatRequest(BaseModel):
    disk_usage_percent: float = Field(..., ge=0.0, le=100.0)
    chunk_count: int = Field(..., ge=0)
    version: Optional[str] = "1.0.0"

class ChunkCommitRequest(BaseModel):
    node_urls: List[str] = Field(..., min_length=1)
    checksum: str = Field(..., min_length=64, max_length=64)  # SHA-256 hex
    size_bytes: int = Field(..., gt=0)
    video_id: str = Field(..., min_length=1)
    sequence_num: int = Field(..., ge=0)
    redundancy_mode: RedundancyMode = RedundancyMode.REPLICATION
    fragments_metadata: Optional[List[Dict[str, Any]]] = None

class ChunkCommitResponse(BaseModel):
    success: bool
    committed_nodes: List[str]
    message: str

class HealthResponse(BaseModel):
    status: str
    service: str
    healthy_nodes: int
    total_nodes: int
    database_status: str

# Internal Models
class ConsensusState(BaseModel):
    chunk_id: str
    promised_ballot: int = 0
    accepted_ballot: int = 0
    accepted_value: Optional[str] = None
    phase: ConsensusPhase = ConsensusPhase.NONE

class ChunkReplica(BaseModel):
    chunk_id: str
    node_url: str
    status: ReplicaStatus = ReplicaStatus.ACTIVE
    ballot_number: int = 0
    created_at: str

class FragmentInfo(BaseModel):
    fragment_id: str
    chunk_id: str
    fragment_index: int
    node_url: str
    size_bytes: int
    checksum: str
    status: str = "active"

class StorageOverheadStats(BaseModel):
    replication_chunks: int
    erasure_coded_chunks: int
    total_logical_bytes: int
    total_physical_bytes: int
    storage_savings_percent: float
    replication_overhead_bytes: int
    erasure_overhead_bytes: int