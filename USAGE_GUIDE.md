# V-Stack Usage Guide

Complete guide for using the V-Stack distributed video storage system.

## Table of Contents

1. [Installation](#installation)
2. [Basic Usage](#basic-usage)
3. [Demo Interface](#demo-interface)
4. [Command Line Tools](#command-line-tools)
5. [API Reference](#api-reference)
6. [Advanced Features](#advanced-features)
7. [Monitoring & Debugging](#monitoring--debugging)
8. [Performance Tuning](#performance-tuning)
9. [Troubleshooting](#troubleshooting)

---

## Installation

### System Requirements

- **Operating System:** Linux, macOS, or Windows with WSL2
- **Docker:** Version 20.10 or higher
- **Docker Compose:** Version 2.0 or higher
- **RAM:** Minimum 4GB, recommended 8GB
- **Disk Space:** Minimum 10GB free
- **Network:** Ports 8080-8086 must be available

### Installation Steps

#### Method 1: Using Docker Compose (Recommended)

```bash
# 1. Clone the repository
git clone <repository-url>
cd VStack

# 2. Verify Docker is running
docker --version
docker-compose --version

# 3. Build and start services
docker-compose up -d

# 4. Wait for services to be healthy (30-60 seconds)
watch docker-compose ps

# 5. Verify all services are running
curl http://localhost:8085/api/health
```

#### Method 2: Using Native Docker Commands

```bash
# 1. Clone the repository
git clone <repository-url>
cd VStack

# 2. Verify Docker is running
docker --version

# 3. Create Docker network
docker network create vstack-network

# 4. Create persistent volumes
docker volume create vstack-metadata-data
docker volume create vstack-storage-node-1-data
docker volume create vstack-storage-node-2-data
docker volume create vstack-storage-node-3-data
docker volume create vstack-upload-temp

# 5. Build all images
docker build -t vstack-metadata -f metadata-service/Dockerfile .
docker build -t vstack-storage-node -f storage-node/Dockerfile .
docker build -t vstack-uploader -f uploader/Dockerfile .
docker build -t vstack-client -f client/Dockerfile .
docker build -t vstack-demo -f demo/Dockerfile .

# 6. Start Metadata Service (must start first)
docker run -d --name vstack-metadata-service \
  --network vstack-network \
  --network-alias metadata-service \
  -p 8080:8080 \
  -v vstack-metadata-data:/data \
  -e PORT=8080 \
  -e DATABASE_URL=/data/metadata.db \
  -e LOG_LEVEL=INFO \
  -e HEARTBEAT_INTERVAL=10 \
  -e NODE_TIMEOUT=30 \
  -e POPULARITY_THRESHOLD=1000 \
  -e STORAGE_NODES=http://storage-node-1:8081,http://storage-node-2:8081,http://storage-node-3:8081 \
  vstack-metadata

# Wait for metadata service to be ready
sleep 10

# 7. Start Storage Nodes
docker run -d --name vstack-storage-node-1 \
  --network vstack-network \
  --network-alias storage-node-1 \
  -p 8081:8081 \
  -v vstack-storage-node-1-data:/data \
  -e PORT=8081 \
  -e NODE_ID=storage-node-1 \
  -e NODE_URL=http://storage-node-1:8081 \
  -e DATA_DIR=/data \
  -e METADATA_SERVICE_URL=http://metadata-service:8080 \
  -e MAX_SUPERBLOCK_SIZE=1073741824 \
  vstack-storage-node

docker run -d --name vstack-storage-node-2 \
  --network vstack-network \
  --network-alias storage-node-2 \
  -p 8082:8081 \
  -v vstack-storage-node-2-data:/data \
  -e PORT=8081 \
  -e NODE_ID=storage-node-2 \
  -e NODE_URL=http://storage-node-2:8081 \
  -e DATA_DIR=/data \
  -e METADATA_SERVICE_URL=http://metadata-service:8080 \
  -e MAX_SUPERBLOCK_SIZE=1073741824 \
  vstack-storage-node

docker run -d --name vstack-storage-node-3 \
  --network vstack-network \
  --network-alias storage-node-3 \
  -p 8083:8081 \
  -v vstack-storage-node-3-data:/data \
  -e PORT=8081 \
  -e NODE_ID=storage-node-3 \
  -e NODE_URL=http://storage-node-3:8081 \
  -e DATA_DIR=/data \
  -e METADATA_SERVICE_URL=http://metadata-service:8080 \
  -e MAX_SUPERBLOCK_SIZE=1073741824 \
  vstack-storage-node

# Wait for storage nodes to be ready
sleep 10

# 8. Start Uploader Service
docker run -d --name vstack-uploader-service \
  --network vstack-network \
  --network-alias uploader-service \
  -p 8084:8084 \
  -v vstack-upload-temp:/tmp/uploads \
  -e PORT=8084 \
  -e METADATA_SERVICE_URL=http://metadata-service:8080 \
  -e STORAGE_NODES=http://storage-node-1:8081,http://storage-node-2:8081,http://storage-node-3:8081 \
  -e CHUNK_SIZE=2097152 \
  -e CHUNK_DURATION=10 \
  -e MAX_CONCURRENT_UPLOADS=5 \
  -e TEMP_DIR=/tmp/uploads \
  vstack-uploader

# 9. Start Smart Client
docker run -d --name vstack-smart-client \
  --network vstack-network \
  --network-alias smart-client \
  -p 8086:8086 \
  -e PORT=8086 \
  -e METADATA_SERVICE_URL=http://metadata-service:8080 \
  -e STORAGE_NODES=http://storage-node-1:8081,http://storage-node-2:8081,http://storage-node-3:8081 \
  -e MONITORING_INTERVAL=3 \
  -e TARGET_BUFFER_SEC=30 \
  -e LOW_WATER_MARK_SEC=15 \
  -e MAX_CONCURRENT_DOWNLOADS=4 \
  vstack-client

# 10. Start Demo Interface
docker run -d --name vstack-demo \
  --network vstack-network \
  --network-alias demo \
  -p 8085:8085 \
  -e PORT=8085 \
  -e METADATA_SERVICE_URL=http://metadata-service:8080 \
  -e UPLOADER_SERVICE_URL=http://uploader-service:8084 \
  -e CLIENT_DASHBOARD_URL=http://smart-client:8086 \
  vstack-demo

# 11. Wait for all services to be ready
sleep 20

# 12. Verify all services are running
curl http://localhost:8085/api/health
```

### Expected Output

All services should show status as `Up (healthy)`:

```
NAME                        STATUS
vstack-metadata-service     Up (healthy)
vstack-storage-node-1       Up (healthy)
vstack-storage-node-2       Up (healthy)
vstack-storage-node-3       Up (healthy)
vstack-uploader-service     Up (healthy)
vstack-smart-client         Up (healthy)
vstack-demo                 Up (healthy)
```

---

## Basic Usage

### Upload a Video

#### Method 1: Using Demo Interface (Recommended)

1. Open http://localhost:8085 in your browser
2. Click "Select Video" button
3. Choose a video file
4. Enter a title when prompted
5. Wait for upload to complete

#### Method 2: Using cURL

```bash
curl -X POST http://localhost:8084/upload \
  -F "video=@/path/to/video.mp4" \
  -F "title=My Video"
```

**Response:**
```json
{
  "video_id": "550e8400-e29b-41d4-a716-446655440000",
  "upload_session_id": "abc123...",
  "title": "My Video",
  "status": "processing",
  "status_url": "/upload/status/abc123..."
}
```

#### Method 3: Using Python

```python
import requests

with open('video.mp4', 'rb') as f:
    files = {'video': f}
    data = {'title': 'My Video'}
    response = requests.post('http://localhost:8084/upload', 
                           files=files, data=data)
    print(response.json())
```

### Check Upload Status

```bash
curl http://localhost:8084/upload/status/<upload_session_id>
```

**Response:**
```json
{
  "video_id": "550e8400-...",
  "title": "My Video",
  "status": "completed",
  "progress": 100,
  "total_chunks": 60,
  "manifest_url": "/manifest/550e8400-..."
}
```

### List All Videos

```bash
curl http://localhost:8080/videos
```

### Get Video Manifest

```bash
curl http://localhost:8080/manifest/<video_id>
```

**Response:**
```json
{
  "video_id": "550e8400-...",
  "title": "My Video",
  "duration_sec": 600,
  "total_chunks": 60,
  "chunk_duration_sec": 10,
  "chunks": [
    {
      "chunk_id": "550e8400-...-chunk-000",
      "sequence_num": 0,
      "size_bytes": 2097152,
      "checksum": "sha256:a1b2c3...",
      "replicas": [
        "http://localhost:8081",
        "http://localhost:8082",
        "http://localhost:8083"
      ]
    }
  ]
}
```

### Play a Video

```bash
# Using smart client
python client/main.py <video_id>

# With real-time dashboard
python client/run_with_dashboard.py <video_id>
# Then open http://localhost:8888
```

---

## Demo Interface

### Accessing the Demo

Open your browser to: **http://localhost:8085**

### Features

#### 1. Video Upload
- Drag and drop or click to select video files
- Supported formats: MP4, AVI, MOV, MKV, WebM, FLV
- Real-time upload progress tracking
- Automatic video chunking and distribution

#### 2. System Health Dashboard
- **Auto-updates every 3 seconds**
- Storage node status (healthy/degraded/down)
- System statistics (videos, chunks, replicas)
- Service availability monitoring

#### 3. Storage Node Status
Each node displays:
- Node ID and URL
- Health status
- Chunk count
- Disk usage

#### 4. Additional Visualizations
- **Consensus Visualization:** http://localhost:8085/consensus
- **Storage Efficiency:** http://localhost:8085/storage-efficiency

---

## Command Line Tools

### Smart Client

Play videos with intelligent chunk scheduling:

```bash
# Basic playback
python client/main.py <video_id>

# With dashboard
python client/run_with_dashboard.py <video_id>
```

**Output:**
```
V-STACK SMART CLIENT STATUS
============================================================
Video ID: 550e8400-...
Startup Latency: 1.85s

Buffer Status: HEALTHY
  Level: 26.8s / 30s
  Health: 89%
  Position: Chunk 5

Playback Statistics:
  Chunks Played: 5
  Rebuffering Events: 0

Download Statistics:
  Total Downloads: 8
  Success Rate: 100.0%
  Failovers: 0

Storage Node Scores:
  http://localhost:8081: 16.8
  http://localhost:8082: 14.2
  http://localhost:8083: 12.5
============================================================
```

### Performance Benchmarks

Run comprehensive performance tests:

```bash
python demo/benchmark.py
```

**Tests:**
- Startup latency
- Rebuffering events
- Average buffer level
- Storage node latency
- Concurrent requests
- Throughput
- Load distribution
- Failover time

### Network Emulation

Simulate various network conditions:

```bash
python demo/network_emulator.py
```

**Scenarios:**
- Normal operation
- High latency
- Low bandwidth
- Packet loss
- Node failures
- Recovery

### Smart vs Naive Comparison

Compare smart client vs naive round-robin:

```bash
python demo/smart_vs_naive_demo.py
```

### Chaos Testing

Random failure injection:

```bash
python demo/chaos_test.py
```

---

## API Reference

### Demo Service APIs

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Demo HTML page |
| `/consensus` | GET | Consensus visualization |
| `/storage-efficiency` | GET | Storage efficiency dashboard |
| `/api/health` | GET | System health status |
| `/api/videos` | GET | List all videos |
| `/api/stats` | GET | System statistics |
| `/api/upload` | POST | Upload video (proxy) |

### Metadata Service APIs

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health |
| `/video` | POST | Create video record |
| `/videos` | GET | List videos (limit, offset) |
| `/manifest/{video_id}` | GET | Get video manifest |
| `/nodes/healthy` | GET | List healthy storage nodes |
| `/nodes/all` | GET | List all storage nodes |
| `/chunk/{chunk_id}/commit` | POST | Commit chunk placement |
| `/stats` | GET | System statistics |
| `/storage/overhead` | GET | Storage overhead stats |
| `/video/{video_id}/popularity` | GET | Get video view count |
| `/video/{video_id}/view` | POST | Increment view count |

### Storage Node APIs

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Node health status |
| `/ping` | HEAD | Latency measurement |
| `/chunk/{chunk_id}` | PUT | Store chunk (2MB max) |
| `/chunk/{chunk_id}` | GET | Retrieve chunk |
| `/chunk/{chunk_id}` | HEAD | Check chunk exists |

### Uploader Service APIs

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health |
| `/upload` | POST | Upload video file |
| `/upload/status/{session_id}` | GET | Check upload progress |

---

## Advanced Features

### Adaptive Redundancy

The system automatically selects between replication and erasure coding:

#### Check Redundancy Mode

```bash
curl http://localhost:8080/redundancy/recommend/<video_id>
```

**Response:**
```json
{
  "video_id": "550e8400-...",
  "view_count": 500,
  "recommended_mode": "erasure_coding",
  "config": {
    "data_shards": 3,
    "parity_shards": 2,
    "total_shards": 5
  }
}
```

#### Manual Override

```bash
# Force replication mode
curl -X POST http://localhost:8080/redundancy/override/<video_id>?mode=replication

# Force erasure coding mode
curl -X POST http://localhost:8080/redundancy/override/<video_id>?mode=erasure_coding

# Clear override (use automatic)
curl -X DELETE http://localhost:8080/redundancy/override/<video_id>
```

#### Storage Efficiency

```bash
curl http://localhost:8080/redundancy/efficiency
```

**Response:**
```json
{
  "efficiency": {
    "storage_savings_percent": 40.2,
    "total_logical_bytes": 10737418240,
    "total_physical_bytes": 6442450944
  },
  "mode_comparison": {
    "replication": {
      "overhead_factor": 3.0,
      "storage_efficiency": 33.3
    },
    "erasure_coding": {
      "overhead_factor": 1.67,
      "storage_efficiency": 60.0
    }
  }
}
```

### Network Monitoring

The smart client continuously monitors network performance:

```python
from client.network_monitor import NetworkMonitor

monitor = NetworkMonitor(ping_interval=3.0)
await monitor.start_monitoring([
    'http://localhost:8081',
    'http://localhost:8082',
    'http://localhost:8083'
])

# Get node scores
scores = monitor.get_all_node_scores()
print(scores)
# {'http://localhost:8081': 16.8, ...}

# Get detailed stats
stats = monitor.get_node_stats('http://localhost:8081')
print(stats)
```

### Consensus Protocol

ChunkPaxos ensures consistent chunk placement:

```bash
# Get consensus state for a chunk
curl http://localhost:8080/consensus/<chunk_id>
```

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

---

## Monitoring & Debugging

### View Logs

**Using Docker Compose:**
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f metadata-service
docker-compose logs -f storage-node-1
docker-compose logs -f uploader-service
docker-compose logs -f demo

# Last 100 lines
docker-compose logs --tail=100 metadata-service

# Since specific time
docker-compose logs --since 2024-11-22T10:00:00 metadata-service
```

**Using Native Docker:**
```bash
# View logs for specific service
docker logs -f vstack-metadata-service
docker logs -f vstack-storage-node-1
docker logs -f vstack-uploader-service
docker logs -f vstack-demo

# Last 100 lines
docker logs --tail=100 vstack-metadata-service

# Since specific time
docker logs --since 2024-11-22T10:00:00 vstack-metadata-service

# View all container logs
for container in vstack-metadata-service vstack-storage-node-1 \
  vstack-storage-node-2 vstack-storage-node-3 vstack-uploader-service \
  vstack-smart-client vstack-demo; do
  echo "=== $container ==="
  docker logs --tail=20 $container
done
```

### Check Service Health

```bash
# Quick health check script
for port in 8080 8081 8082 8083 8084 8086 8085; do
  echo "Port $port:"
  curl -s http://localhost:$port/health | jq .
done
```

### Monitor Resource Usage

```bash
# Real-time resource monitoring (all containers)
docker stats

# Specific service
docker stats vstack-metadata-service

# All V-Stack services
docker stats vstack-metadata-service vstack-storage-node-1 \
  vstack-storage-node-2 vstack-storage-node-3 vstack-uploader-service \
  vstack-smart-client vstack-demo
```

### Access Service Shell

**Using Docker Compose:**
```bash
# Metadata service
docker-compose exec metadata-service /bin/bash

# Storage node
docker-compose exec storage-node-1 /bin/sh

# Uploader service
docker-compose exec uploader-service /bin/bash
```

**Using Native Docker:**
```bash
# Metadata service
docker exec -it vstack-metadata-service /bin/bash

# Storage node
docker exec -it vstack-storage-node-1 /bin/sh

# Uploader service
docker exec -it vstack-uploader-service /bin/bash

# Demo service
docker exec -it vstack-demo /bin/bash
```

### Database Inspection

**Using Docker Compose:**
```bash
# Access metadata database
docker-compose exec metadata-service sqlite3 /data/metadata.db

# List tables
.tables

# Query videos
SELECT * FROM videos;

# Query chunks
SELECT * FROM chunks LIMIT 10;

# Query storage nodes
SELECT * FROM storage_nodes;
```

**Using Native Docker:**
```bash
# Access metadata database
docker exec -it vstack-metadata-service sqlite3 /data/metadata.db

# Or run queries directly
docker exec vstack-metadata-service sqlite3 /data/metadata.db "SELECT * FROM videos;"
docker exec vstack-metadata-service sqlite3 /data/metadata.db "SELECT * FROM chunks LIMIT 10;"
docker exec vstack-metadata-service sqlite3 /data/metadata.db "SELECT * FROM storage_nodes;"
```

---

## Performance Tuning

### Configuration Parameters

#### Metadata Service
```yaml
environment:
  - HEARTBEAT_INTERVAL=10      # Node heartbeat interval (seconds)
  - NODE_TIMEOUT=30            # Node timeout (seconds)
  - POPULARITY_THRESHOLD=1000  # Views threshold for redundancy mode
```

#### Storage Nodes
```yaml
environment:
  - MAX_SUPERBLOCK_SIZE=1073741824  # 1GB superblock size
```

#### Uploader Service
```yaml
environment:
  - CHUNK_SIZE=2097152              # 2MB chunk size
  - CHUNK_DURATION=10               # 10 seconds per chunk
  - MAX_CONCURRENT_UPLOADS=5        # Parallel upload limit
```

#### Smart Client
```yaml
environment:
  - MONITORING_INTERVAL=3           # Network monitoring interval (seconds)
  - TARGET_BUFFER_SEC=30            # Target buffer size (seconds)
  - LOW_WATER_MARK_SEC=15           # Buffer refill threshold (seconds)
  - MAX_CONCURRENT_DOWNLOADS=4      # Parallel download limit
```

### Scaling

#### Add More Storage Nodes

1. Edit `docker-compose.yml`:

```yaml
storage-node-4:
  build:
    context: .
    dockerfile: storage-node/Dockerfile
  container_name: vstack-storage-node-4
  ports:
    - "8084:8081"
  environment:
    - PORT=8081
    - NODE_ID=storage-node-4
    - NODE_URL=http://storage-node-4:8081
    - DATA_DIR=/data
    - METADATA_SERVICE_URL=http://metadata-service:8080
  volumes:
    - storage_node_4_data:/data
  networks:
    - vstack-network
```

2. Update STORAGE_NODES environment variable in metadata and uploader services

3. Restart services:
```bash
docker-compose up -d
```

---

## Troubleshooting

### Common Issues

#### 1. Services Not Starting

**Symptom:** Services show unhealthy or restarting status

**Solutions:**

**Using Docker Compose:**
```bash
# Check logs
docker-compose logs <service-name>

# Common causes:
# - Port already in use
sudo lsof -i :8080-8086

# - Insufficient memory
docker stats

# - Database initialization failed
docker-compose logs metadata-service | grep -i error

# Rebuild and restart
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d
```

**Using Native Docker:**
```bash
# Check logs
docker logs vstack-<service-name>

# Check if ports are in use
sudo lsof -i :8080-8086

# Check resource usage
docker stats

# Check specific service errors
docker logs vstack-metadata-service | grep -i error

# Restart specific service
docker restart vstack-<service-name>

# Complete rebuild
# Stop and remove all containers
docker stop vstack-demo vstack-smart-client vstack-uploader-service \
  vstack-storage-node-1 vstack-storage-node-2 vstack-storage-node-3 \
  vstack-metadata-service

docker rm vstack-demo vstack-smart-client vstack-uploader-service \
  vstack-storage-node-1 vstack-storage-node-2 vstack-storage-node-3 \
  vstack-metadata-service

# Remove volumes for clean slate
docker volume rm vstack-metadata-data vstack-storage-node-1-data \
  vstack-storage-node-2-data vstack-storage-node-3-data vstack-upload-temp

# Rebuild images
docker build --no-cache -t vstack-metadata -f metadata-service/Dockerfile .
docker build --no-cache -t vstack-storage-node -f storage-node/Dockerfile .
docker build --no-cache -t vstack-uploader -f uploader/Dockerfile .
docker build --no-cache -t vstack-client -f client/Dockerfile .
docker build --no-cache -t vstack-demo -f demo/Dockerfile .

# Restart services (follow installation steps above)
```

#### 2. Demo Page Not Loading

**Symptom:** Browser shows "Connection refused"

**Solutions:**

**Using Docker Compose:**
```bash
# Check demo service
docker-compose logs demo

# Verify port is available
netstat -an | grep 8085

# Restart demo service
docker-compose restart demo

# Check health
curl http://localhost:8085/api/health
```

**Using Native Docker:**
```bash
# Check demo service logs
docker logs vstack-demo

# Verify port is available
netstat -an | grep 8085

# Check if container is running
docker ps | grep vstack-demo

# Restart demo service
docker restart vstack-demo

# Check health
curl http://localhost:8085/api/health

# If still not working, recreate container
docker stop vstack-demo
docker rm vstack-demo
docker run -d --name vstack-demo \
  --network vstack-network \
  --network-alias demo \
  -p 8085:8085 \
  -e PORT=8085 \
  -e METADATA_SERVICE_URL=http://metadata-service:8080 \
  -e UPLOADER_SERVICE_URL=http://uploader-service:8084 \
  vstack-demo
```

#### 3. Upload Fails

**Symptom:** Upload returns error or hangs

**Solutions:**
```bash
# Check uploader logs
docker-compose logs uploader-service

# Verify FFmpeg
docker-compose exec uploader-service ffmpeg -version

# Check storage nodes
curl http://localhost:8081/health
curl http://localhost:8082/health
curl http://localhost:8083/health

# Check metadata service
curl http://localhost:8080/nodes/healthy

# Verify file format is supported
# Supported: MP4, AVI, MOV, MKV, WebM, FLV
```

#### 4. Playback Issues

**Symptom:** Client cannot download chunks

**Solutions:**
```bash
# Check manifest exists
curl http://localhost:8080/manifest/<video_id>

# Verify chunks are stored
curl -I http://localhost:8081/chunk/<chunk_id>

# Check network connectivity
docker-compose exec smart-client curl http://storage-node-1:8081/health

# Check client logs
python client/main.py <video_id> 2>&1 | tee client.log
```

#### 5. Dashboard Not Updating

**Symptom:** Node status shows "unknown" or doesn't refresh

**Solutions:**
```bash
# Check browser console (F12)
# Look for JavaScript errors

# Verify API connectivity
curl http://localhost:8085/api/health

# Check metadata service
curl http://localhost:8080/stats

# Restart demo service
docker-compose restart demo
```

### Getting Help

1. **Check Logs:** Always start with `docker-compose logs <service-name>`
2. **Verify Health:** Use health endpoints to check service status
3. **Check Documentation:** Review ARCHITECTURE.md for design details
4. **Test APIs:** Use curl to test individual endpoints
5. **Clean Slate:** Try `docker-compose down -v && docker-compose up -d`

---

## Best Practices

### Development

1. **Use Volume Mounts:** Services mount local directories for live code updates
2. **Check Logs Regularly:** Monitor logs during development
3. **Test Incrementally:** Test each component before integration
4. **Use Health Checks:** Always verify services are healthy

### Production

1. **Use PostgreSQL:** Replace SQLite with PostgreSQL for metadata
2. **Add Load Balancer:** Use Nginx for load balancing
3. **Enable SSL/TLS:** Secure all communications
4. **Monitor Resources:** Set up Prometheus + Grafana
5. **Backup Data:** Regular backups of metadata and chunks
6. **Scale Horizontally:** Add more storage nodes as needed

### Security

1. **Authentication:** Add API authentication
2. **Authorization:** Implement role-based access control
3. **Rate Limiting:** Prevent abuse
4. **Input Validation:** Validate all user inputs
5. **Network Isolation:** Use Docker networks properly

---

## Appendix

### Port Reference

| Service | Port | Protocol | Purpose |
|---------|------|----------|---------|
| Metadata Service | 8080 | HTTP | Coordination and consensus |
| Storage Node 1 | 8081 | HTTP | Chunk storage |
| Storage Node 2 | 8082 | HTTP | Chunk storage |
| Storage Node 3 | 8083 | HTTP | Chunk storage |
| Uploader Service | 8084 | HTTP | Video upload and processing |
| Demo Interface | 8085 | HTTP | Web interface |
| Smart Client | 8086 | HTTP | Dashboard (optional) |

### File Locations

| Component | Location |
|-----------|----------|
| Metadata Database | `/data/metadata.db` (in container) |
| Storage Node Data | `/data/data/superblock_*.dat` (in container) |
| Upload Temp Files | `/tmp/uploads` (in container) |
| Logs | `docker-compose logs` |

### Environment Variables

See `docker-compose.yml` for complete list of environment variables and their default values.

---

## Native Docker Commands Reference

### Quick Command Comparison

| Task | Docker Compose | Native Docker |
|------|----------------|---------------|
| Start all | `docker-compose up -d` | See installation steps above |
| Stop all | `docker-compose down` | `docker stop vstack-*` |
| View logs | `docker-compose logs -f` | `docker logs -f vstack-*` |
| Restart service | `docker-compose restart <service>` | `docker restart vstack-<service>` |
| Shell access | `docker-compose exec <service> bash` | `docker exec -it vstack-<service> bash` |
| Remove all | `docker-compose down -v` | See cleanup script below |

### Complete Cleanup Script

```bash
#!/bin/bash
# cleanup.sh - Complete V-Stack cleanup

echo "Stopping all V-Stack containers..."
docker stop vstack-demo vstack-smart-client vstack-uploader-service \
  vstack-storage-node-1 vstack-storage-node-2 vstack-storage-node-3 \
  vstack-metadata-service 2>/dev/null

echo "Removing all V-Stack containers..."
docker rm vstack-demo vstack-smart-client vstack-uploader-service \
  vstack-storage-node-1 vstack-storage-node-2 vstack-storage-node-3 \
  vstack-metadata-service 2>/dev/null

echo "Removing volumes..."
docker volume rm vstack-metadata-data vstack-storage-node-1-data \
  vstack-storage-node-2-data vstack-storage-node-3-data \
  vstack-upload-temp 2>/dev/null

echo "Removing network..."
docker network rm vstack-network 2>/dev/null

echo "Removing images (optional)..."
docker rmi vstack-metadata vstack-storage-node vstack-uploader \
  vstack-client vstack-demo 2>/dev/null

echo "Cleanup complete!"
```

### Restart Individual Services

```bash
# Restart metadata service
docker restart vstack-metadata-service

# Restart storage node
docker restart vstack-storage-node-1

# Restart uploader
docker restart vstack-uploader-service

# Restart demo
docker restart vstack-demo

# Restart all services
docker restart vstack-metadata-service vstack-storage-node-1 \
  vstack-storage-node-2 vstack-storage-node-3 vstack-uploader-service \
  vstack-smart-client vstack-demo
```

### Update Single Service

```bash
# Example: Update demo service

# 1. Stop and remove container
docker stop vstack-demo
docker rm vstack-demo

# 2. Rebuild image
docker build -t vstack-demo -f demo/Dockerfile .

# 3. Start new container
docker run -d --name vstack-demo \
  --network vstack-network \
  --network-alias demo \
  -p 8085:8085 \
  -e PORT=8085 \
  -e METADATA_SERVICE_URL=http://metadata-service:8080 \
  -e UPLOADER_SERVICE_URL=http://uploader-service:8084 \
  vstack-demo

# 4. Verify
curl http://localhost:8085/api/health
```

### Backup and Restore

#### Backup Data

```bash
# Backup metadata database
docker cp vstack-metadata-service:/data/metadata.db ./backup/metadata.db

# Backup storage node data
docker cp vstack-storage-node-1:/data ./backup/storage-node-1-data
docker cp vstack-storage-node-2:/data ./backup/storage-node-2-data
docker cp vstack-storage-node-3:/data ./backup/storage-node-3-data

# Or backup volumes
docker run --rm -v vstack-metadata-data:/data -v $(pwd)/backup:/backup \
  alpine tar czf /backup/metadata-data.tar.gz -C /data .

docker run --rm -v vstack-storage-node-1-data:/data -v $(pwd)/backup:/backup \
  alpine tar czf /backup/storage-node-1-data.tar.gz -C /data .
```

#### Restore Data

```bash
# Restore metadata database
docker cp ./backup/metadata.db vstack-metadata-service:/data/metadata.db
docker restart vstack-metadata-service

# Restore from volume backup
docker run --rm -v vstack-metadata-data:/data -v $(pwd)/backup:/backup \
  alpine tar xzf /backup/metadata-data.tar.gz -C /data

docker run --rm -v vstack-storage-node-1-data:/data -v $(pwd)/backup:/backup \
  alpine tar xzf /backup/storage-node-1-data.tar.gz -C /data
```

### Health Check Script

```bash
#!/bin/bash
# health-check.sh - Check all V-Stack services

services=(
  "vstack-metadata-service:8080"
  "vstack-storage-node-1:8081"
  "vstack-storage-node-2:8082"
  "vstack-storage-node-3:8083"
  "vstack-uploader-service:8084"
  "vstack-smart-client:8086"
  "vstack-demo:8085"
)

echo "V-Stack Health Check"
echo "===================="

for service in "${services[@]}"; do
  name="${service%%:*}"
  port="${service##*:}"
  
  # Check if container is running
  if docker ps --format '{{.Names}}' | grep -q "^${name}$"; then
    # Check health endpoint
    if curl -sf "http://localhost:${port}/health" > /dev/null 2>&1; then
      echo "✓ ${name} - HEALTHY"
    else
      echo "✗ ${name} - UNHEALTHY (running but not responding)"
    fi
  else
    echo "✗ ${name} - NOT RUNNING"
  fi
done
```

### Network Troubleshooting

```bash
# Inspect network
docker network inspect vstack-network

# List containers on network
docker network inspect vstack-network --format '{{range .Containers}}{{.Name}} {{end}}'

# Test connectivity between containers
docker exec vstack-demo curl http://metadata-service:8080/health
docker exec vstack-uploader-service curl http://storage-node-1:8081/health

# Recreate network if needed
docker network rm vstack-network
docker network create vstack-network

# Reconnect containers to network
docker network connect vstack-network vstack-metadata-service
docker network connect vstack-network vstack-storage-node-1
# ... etc
```

---

**Last Updated:** November 2024  
**Version:** 1.0.0
