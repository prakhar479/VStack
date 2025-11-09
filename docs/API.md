# V-Stack API Documentation

Complete API reference for all V-Stack services.

## Table of Contents

- [Metadata Service API](#metadata-service-api)
- [Storage Node API](#storage-node-api)
- [Uploader Service API](#uploader-service-api)
- [Smart Client API](#smart-client-api)

---

## Metadata Service API

**Base URL:** `http://localhost:8080`

### Health and Status

#### GET /health
Get service health status.

**Response:**
```json
{
  "status": "healthy",
  "service": "metadata-service",
  "healthy_nodes": 3,
  "total_nodes": 3,
  "database_status": "healthy"
}
```

#### GET /
Root endpoint with service information.

**Response:**
```json
{
  "message": "V-Stack Metadata Service",
  "version": "1.0.0"
}
```

#### GET /stats
Get service statistics.

**Response:**
```json
{
  "total_videos": 42,
  "total_chunks": 2520,
  "total_replicas": 7560,
  "healthy_nodes": 3,
  "service_version": "1.0.0"
}
```

### Video Management

#### POST /video
Create a new video record.

**Request Body:**
```json
{
  "title": "My Video",
  "duration_sec": 600
}
```

**Response:**
```json
{
  "video_id": "550e8400-e29b-41d4-a716-446655440000",
  "upload_url": "/upload/550e8400-e29b-41d4-a716-446655440000"
}
```

#### GET /videos
List all videos with pagination.

**Query Parameters:**
- `limit` (optional): Maximum number of videos to return (default: 100)
- `offset` (optional): Number of videos to skip (default: 0)

**Response:**
```json
[
  {
    "video_id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "My Video",
    "duration_sec": 600,
    "total_chunks": 60,
    "status": "active",
    "created_at": "2024-11-06T10:30:00Z"
  }
]
```

#### GET /manifest/{video_id}
Get video manifest with chunk locations.

**Response:**
```json
{
  "video_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "My Video",
  "duration_sec": 600,
  "total_chunks": 60,
  "chunk_duration_sec": 10,
  "chunk_size_bytes": 2097152,
  "created_at": "2024-11-06T10:30:00Z",
  "status": "active",
  "chunks": [
    {
      "chunk_id": "550e8400-...-chunk-000",
      "sequence_num": 0,
      "size_bytes": 2097152,
      "checksum": "sha256:a1b2c3d4...",
      "redundancy_mode": "replication",
      "replicas": [
        "http://localhost:8081",
        "http://localhost:8082",
        "http://localhost:8083"
      ]
    }
  ]
}
```

#### GET /video/{video_id}/popularity
Get video popularity (view count).

**Response:**
```json
{
  "video_id": "550e8400-e29b-41d4-a716-446655440000",
  "view_count": 1250
}
```

#### POST /video/{video_id}/view
Increment video view count.

**Response:**
```json
{
  "status": "ok",
  "message": "View count incremented for 550e8400-e29b-41d4-a716-446655440000"
}
```

### Chunk Management

#### POST /chunk/{chunk_id}/commit
Commit chunk placement using ChunkPaxos consensus.

**Request Body:**
```json
{
  "node_urls": [
    "http://storage-node-1:8081",
    "http://storage-node-2:8081",
    "http://storage-node-3:8081"
  ],
  "checksum": "sha256:a1b2c3d4e5f6...",
  "size_bytes": 2097152,
  "video_id": "550e8400-e29b-41d4-a716-446655440000",
  "sequence_num": 0,
  "redundancy_mode": "replication",
  "fragments_metadata": null
}
```

**Response:**
```json
{
  "success": true,
  "committed_nodes": [
    "http://storage-node-1:8081",
    "http://storage-node-2:8081",
    "http://storage-node-3:8081"
  ],
  "message": "Chunk chunk-000 committed to 3 nodes"
}
```

#### GET /chunk/{chunk_id}/fragments
Get fragment information for erasure-coded chunk.

**Response:**
```json
{
  "chunk_id": "550e8400-...-chunk-000",
  "fragments": [
    {
      "fragment_id": "550e8400-...-chunk-000-frag-0",
      "fragment_index": 0,
      "node_url": "http://storage-node-1:8081",
      "size_bytes": 419430,
      "checksum": "sha256:...",
      "status": "active"
    }
  ]
}
```

#### GET /consensus/{chunk_id}
Get consensus state for a chunk (debugging).

**Response:**
```json
{
  "chunk_id": "550e8400-...-chunk-000",
  "promised_ballot": 1,
  "accepted_ballot": 1,
  "accepted_value": "[\"http://storage-node-1:8081\", ...]",
  "phase": "committed"
}
```

### Storage Node Management

#### GET /nodes/healthy
Get list of healthy storage nodes.

**Response:**
```json
[
  {
    "node_url": "http://storage-node-1:8081",
    "node_id": "storage-node-1",
    "last_heartbeat": "2024-11-06T10:35:00Z",
    "disk_usage_percent": 45.2,
    "chunk_count": 1250,
    "status": "healthy",
    "version": "1.0.0"
  }
]
```

#### GET /nodes/all
Get detailed information about all storage nodes.

**Response:**
```json
{
  "nodes": [
    {
      "node_url": "http://storage-node-1:8081",
      "node_id": "storage-node-1",
      "status": "healthy",
      "last_heartbeat": "2024-11-06T10:35:00Z",
      "disk_usage_percent": 45.2,
      "chunk_count": 1250
    }
  ]
}
```

#### GET /nodes/health-summary
Get summary of node health status.

**Response:**
```json
{
  "healthy": 3,
  "degraded": 0,
  "down": 0
}
```

#### POST /nodes/register
Register a new storage node.

**Query Parameters:**
- `node_url`: URL of the storage node
- `node_id`: Unique identifier for the node
- `version` (optional): Node version (default: "1.0.0")

**Response:**
```json
{
  "status": "registered",
  "node_id": "storage-node-1",
  "node_url": "http://storage-node-1:8081"
}
```

#### POST /nodes/{node_id}/heartbeat
Update storage node heartbeat and health status.

**Request Body:**
```json
{
  "disk_usage_percent": 45.2,
  "chunk_count": 1250
}
```

**Response:**
```json
{
  "status": "ok",
  "message": "Heartbeat updated for node storage-node-1"
}
```

### Redundancy Management

#### GET /redundancy/recommend/{video_id}
Recommend redundancy mode for a video based on popularity.

**Response:**
```json
{
  "video_id": "550e8400-e29b-41d4-a716-446655440000",
  "view_count": 500,
  "recommended_mode": "erasure_coding",
  "config": {
    "mode": "erasure_coding",
    "data_shards": 3,
    "parity_shards": 2,
    "total_shards": 5,
    "min_shards_for_recovery": 3
  }
}
```

#### POST /redundancy/override/{video_id}
Set manual redundancy mode override for a video.

**Query Parameters:**
- `mode`: Redundancy mode ("replication" or "erasure_coding")

**Response:**
```json
{
  "status": "ok",
  "video_id": "550e8400-e29b-41d4-a716-446655440000",
  "override_mode": "replication",
  "message": "Manual override set to replication"
}
```

#### DELETE /redundancy/override/{video_id}
Clear manual redundancy mode override for a video.

**Response:**
```json
{
  "status": "ok",
  "video_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Manual override cleared"
}
```

#### GET /redundancy/efficiency
Get storage efficiency metrics for redundancy modes.

**Response:**
```json
{
  "efficiency": {
    "replication_overhead_factor": 3.0,
    "erasure_coding_overhead_factor": 1.67,
    "storage_savings_percent": 44.4
  },
  "mode_comparison": {
    "replication": {
      "storage_per_chunk_mb": 6.0,
      "nodes_required": 3,
      "failures_tolerated": 2
    },
    "erasure_coding": {
      "storage_per_chunk_mb": 3.33,
      "nodes_required": 5,
      "failures_tolerated": 2
    }
  }
}
```

#### GET /redundancy/config
Get current redundancy manager configuration.

**Response:**
```json
{
  "popularity_threshold": 1000,
  "replication_factor": 3,
  "erasure_data_shards": 3,
  "erasure_parity_shards": 2,
  "erasure_total_shards": 5
}
```

#### GET /storage/overhead
Get storage overhead statistics showing erasure coding savings.

**Response:**
```json
{
  "replication_chunks": 2500,
  "erasure_coded_chunks": 47500,
  "total_logical_bytes": 104857600000,
  "total_physical_bytes": 186413875200,
  "storage_savings_percent": 42.2,
  "replication_overhead_bytes": 15728640000,
  "erasure_overhead_bytes": 170685235200
}
```

---

## Storage Node API

**Base URLs:**
- Node 1: `http://localhost:8081`
- Node 2: `http://localhost:8082`
- Node 3: `http://localhost:8083`

### Chunk Operations

#### PUT /chunk/{chunk_id}
Store a video chunk.

**Request:**
- Method: PUT
- Content-Type: application/octet-stream
- Body: Raw chunk data (up to 2MB)

**Response:**
- Status: 201 Created (new chunk) or 200 OK (existing chunk)
- Headers:
  - `Location`: /chunk/{chunk_id}
  - `ETag`: SHA-256 checksum
  - `X-Chunk-Size`: Size in bytes

**Error Responses:**
- 400 Bad Request: Invalid chunk_id or empty data
- 413 Request Entity Too Large: Chunk exceeds 2MB limit
- 507 Insufficient Storage: Disk full or usage >95%
- 500 Internal Server Error: Storage error

#### GET /chunk/{chunk_id}
Retrieve a video chunk.

**Response:**
- Status: 200 OK
- Content-Type: application/octet-stream
- Headers:
  - `Content-Length`: Chunk size
  - `ETag`: SHA-256 checksum
  - `X-Chunk-Size`: Size in bytes
  - `X-Superblock-ID`: Superblock file ID
- Body: Raw chunk data

**Error Responses:**
- 404 Not Found: Chunk doesn't exist
- 500 Internal Server Error: Read error or corruption detected

**Performance:**
- Target latency: <10ms for chunk retrieval
- Logged if exceeds 10ms

#### HEAD /chunk/{chunk_id}
Check if chunk exists (same headers as GET, no body).

**Response:**
- Status: 200 OK or 404 Not Found
- Headers: Same as GET endpoint

### Health and Monitoring

#### HEAD /ping
Latency measurement endpoint (optimized for speed).

**Response:**
- Status: 200 OK
- Headers:
  - `X-Node-ID`: Node identifier
  - `X-Disk-Usage-Percent`: Current disk usage
  - `X-Chunk-Count`: Number of stored chunks
  - `X-Response-Time`: Response time in milliseconds
  - `Cache-Control`: no-cache

**Purpose:**
- Used by smart client for network monitoring
- Measures latency every 3 seconds
- Updates node performance scores

#### GET /health
Comprehensive health check.

**Response:**
```json
{
  "status": "healthy",
  "disk_usage": 45.2,
  "chunk_count": 1250,
  "uptime": 86400,
  "node_id": "storage-node-1"
}
```

**Status Values:**
- `healthy`: Disk usage <85%
- `warning`: Disk usage 85-95%
- `critical`: Disk usage >95% (returns 503 status)

---

## Uploader Service API

**Base URL:** `http://localhost:8084`

### Health

#### GET /health
Get service health status.

**Response:**
```json
{
  "status": "healthy",
  "service": "uploader-service",
  "active_uploads": 2
}
```

### Video Upload

#### POST /upload
Upload a video file for processing and storage.

**Request:**
- Method: POST
- Content-Type: multipart/form-data
- Form Fields:
  - `video`: Video file (mp4, avi, mov, mkv, webm, flv)
  - `title`: Video title (string)

**Response:**
```json
{
  "video_id": "550e8400-e29b-41d4-a716-446655440000",
  "upload_session_id": "660f9511-f39c-52e5-b827-557766551111",
  "title": "My Video",
  "status": "processing",
  "message": "Video upload received and processing started",
  "status_url": "/upload/status/660f9511-f39c-52e5-b827-557766551111"
}
```

**Error Responses:**
- 400 Bad Request: Invalid file format or missing fields
- 500 Internal Server Error: Upload processing failed

**Supported Formats:**
- MP4, AVI, MOV, MKV, WebM, FLV

**Processing Steps:**
1. Save uploaded file temporarily
2. Split video into 2MB chunks (10 seconds each) using FFmpeg
3. Register video with metadata service
4. Upload chunks to storage nodes (3 replicas each)
5. Commit chunk placement via consensus
6. Create video manifest
7. Cleanup temporary files

#### GET /upload/status/{upload_session_id}
Get upload progress and status.

**Response:**
```json
{
  "video_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "My Video",
  "filename": "video.mp4",
  "status": "uploading_chunks",
  "progress": 65,
  "started_at": "2024-11-06T10:30:00Z",
  "total_chunks": 60,
  "error": null
}
```

**Status Values:**
- `uploading`: Receiving file from client
- `processing`: Saving file temporarily
- `chunking`: Splitting video with FFmpeg
- `registering`: Creating video record
- `uploading_chunks`: Distributing chunks to storage nodes
- `finalizing`: Creating manifest
- `completed`: Upload successful
- `failed`: Upload failed (check `error` field)

**Progress Values:**
- 0-10: Uploading file
- 10-20: Processing file
- 20-40: Chunking video
- 40-50: Registering video
- 50-90: Uploading chunks
- 90-100: Finalizing

---

## Smart Client API

The Smart Client is primarily a library/application, but when run with the dashboard server, it exposes these endpoints:

**Base URL:** `http://localhost:8888` (when using dashboard)

### Dashboard Endpoints

#### GET /
Serve dashboard HTML interface.

#### GET /api/status
Get current client status.

**Response:**
```json
{
  "video_id": "550e8400-e29b-41d4-a716-446655440000",
  "playing": true,
  "startup_latency": 1.85,
  "playback_duration": 45.2,
  "buffer": {
    "state": "healthy",
    "buffer_level_sec": 28.5,
    "target_buffer_sec": 30,
    "buffer_health_percent": 95.0,
    "current_position": 4
  },
  "buffer_stats": {
    "total_chunks_played": 4,
    "rebuffering_events": 0,
    "average_buffer_level": 26.8
  },
  "scheduler_stats": {
    "total_downloads": 7,
    "success_rate": 1.0,
    "failover_count": 0
  },
  "network_stats": {
    "http://localhost:8081": {
      "latency_ms": 18.5,
      "bandwidth_mbps": 48.2,
      "success_rate": 1.0
    }
  },
  "node_scores": {
    "http://localhost:8081": 16.8,
    "http://localhost:8082": 15.2,
    "http://localhost:8083": 14.9
  }
}
```

#### GET /api/stats
Get detailed statistics.

**Response:**
```json
{
  "session": {
    "video_id": "550e8400-e29b-41d4-a716-446655440000",
    "startup_latency": 1.85,
    "playback_duration": 45.2,
    "total_chunks_played": 4
  },
  "buffer": {
    "current_level_sec": 28.5,
    "target_sec": 30,
    "health_percent": 95.0,
    "rebuffering_events": 0
  },
  "downloads": {
    "total": 7,
    "successful": 7,
    "failed": 0,
    "success_rate": 1.0,
    "failovers": 0
  },
  "nodes": {
    "http://localhost:8081": {
      "score": 16.8,
      "downloads": 3,
      "latency_ms": 18.5,
      "bandwidth_mbps": 48.2,
      "success_rate": 1.0
    }
  }
}
```

#### GET /api/metrics
Get historical metrics for charting.

**Response:**
```json
{
  "buffer_history": [
    {"timestamp": 1699270800, "level": 10.0},
    {"timestamp": 1699270802, "level": 15.5},
    {"timestamp": 1699270804, "level": 20.2}
  ],
  "throughput_history": [
    {"timestamp": 1699270800, "mbps": 42.5},
    {"timestamp": 1699270802, "mbps": 45.8}
  ],
  "node_score_history": {
    "http://localhost:8081": [
      {"timestamp": 1699270800, "score": 16.2},
      {"timestamp": 1699270803, "score": 16.8}
    ]
  }
}
```

#### GET /api/performance
Get performance summary.

**Response:**
```json
{
  "startup_latency_sec": 1.85,
  "average_throughput_mbps": 44.2,
  "rebuffering_events": 0,
  "average_buffer_level_sec": 26.8,
  "playback_duration_sec": 45.2,
  "chunks_played": 4,
  "download_success_rate": 1.0
}
```

---

## Error Handling

### Standard Error Response Format

All services return errors in this format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

### Common HTTP Status Codes

- **200 OK**: Request successful
- **201 Created**: Resource created successfully
- **204 No Content**: Successful deletion
- **400 Bad Request**: Invalid request parameters
- **404 Not Found**: Resource not found
- **409 Conflict**: Consensus conflict
- **413 Request Entity Too Large**: Chunk too large
- **500 Internal Server Error**: Server error
- **503 Service Unavailable**: Service unhealthy
- **507 Insufficient Storage**: Disk full

### Retry Logic

Clients should implement exponential backoff for:
- 500 Internal Server Error
- 503 Service Unavailable
- Network timeouts

Example retry strategy:
```python
max_retries = 3
base_delay = 1.0

for attempt in range(max_retries):
    try:
        response = await make_request()
        break
    except Exception:
        if attempt < max_retries - 1:
            delay = base_delay * (2 ** attempt)
            await asyncio.sleep(delay)
```

---

## Rate Limiting

Currently, V-Stack does not implement rate limiting. For production deployments, consider:

- Request rate limits per client IP
- Upload size limits per user
- Concurrent connection limits
- Bandwidth throttling for fairness

---

## Authentication

The current implementation does not include authentication. For production:

- Add API key authentication
- Implement JWT tokens for session management
- Use OAuth2 for user authentication
- Add role-based access control (RBAC)

---

## Versioning

API version is included in service responses but not in URLs. Future versions may use:

- URL versioning: `/v1/video`, `/v2/video`
- Header versioning: `Accept: application/vnd.vstack.v1+json`
- Query parameter versioning: `/video?api_version=1`

---

## WebSocket Support

Future enhancement: Real-time updates via WebSocket for:

- Upload progress streaming
- Playback status updates
- Node health changes
- System alerts

---

## Examples

### Complete Upload and Playback Flow

```python
import aiohttp
import asyncio

async def upload_and_play():
    # 1. Upload video
    async with aiohttp.ClientSession() as session:
        data = aiohttp.FormData()
        data.add_field('video', open('video.mp4', 'rb'))
        data.add_field('title', 'My Video')
        
        async with session.post('http://localhost:8084/upload', data=data) as resp:
            result = await resp.json()
            video_id = result['video_id']
            session_id = result['upload_session_id']
    
    # 2. Poll upload status
    while True:
        async with session.get(f'http://localhost:8084/upload/status/{session_id}') as resp:
            status = await resp.json()
            if status['status'] == 'completed':
                break
            elif status['status'] == 'failed':
                raise Exception(status['error'])
            await asyncio.sleep(2)
    
    # 3. Get manifest
    async with session.get(f'http://localhost:8080/manifest/{video_id}') as resp:
        manifest = await resp.json()
    
    # 4. Play video with smart client
    from client.main import SmartClient
    client = SmartClient()
    await client.play_video(video_id)

asyncio.run(upload_and_play())
```

### Monitor Node Health

```python
import aiohttp

async def monitor_nodes():
    async with aiohttp.ClientSession() as session:
        # Get all nodes
        async with session.get('http://localhost:8080/nodes/all') as resp:
            data = await resp.json()
            nodes = data['nodes']
        
        # Check each node
        for node in nodes:
            async with session.get(f"{node['node_url']}/health") as resp:
                health = await resp.json()
                print(f"{node['node_id']}: {health['status']} "
                      f"(disk: {health['disk_usage']:.1f}%, "
                      f"chunks: {health['chunk_count']})")

asyncio.run(monitor_nodes())
```

---

## See Also

- [Architecture Documentation](../ARCHITECTURE.md)
- [Quick Start Guide](../QUICKSTART.md)
- [Adaptive Redundancy](adaptive-redundancy.md)
- [Demo Tools](../demo/README.md)
