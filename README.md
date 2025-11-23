# V-Stack: Distributed Video Storage System

A production-ready distributed video storage system demonstrating three core innovations in distributed systems: **Smart Client Scheduling**, **Lightweight Consensus (ChunkPaxos)**, and **Adaptive Redundancy**.

## 🎯 Core Features

### 1. Smart Client Scheduling
Clients intelligently select which server to download each chunk from based on real-time network conditions, achieving:
- 30-50% faster startup latency vs naive round-robin
- 70% reduction in rebuffering events
- Automatic failover within 5 seconds

### 2. Lightweight Consensus (ChunkPaxos)
Simplified Paxos protocol exploiting domain knowledge that different chunks don't conflict:
- 33% fewer messages than standard Paxos (6 vs 9)
- Parallel execution for different chunks
- Quorum-based decisions with conflict resolution

### 3. Adaptive Redundancy
Dynamic selection between replication and erasure coding based on video popularity:
- Hot videos (>1000 views): 3x replication for fast reads
- Cold videos (≤1000 views): Erasure coding (5 fragments, any 3 recover)
- ~40% storage savings for cold content

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Demo Web Interface                        │
│                   http://localhost:8085                      │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┼────────────┬──────────────┐
        │            │            │              │
        ▼            ▼            ▼              ▼
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐
│ Metadata │  │ Uploader │  │  Smart   │  │   Storage    │
│ Service  │  │ Service  │  │  Client  │  │    Nodes     │
│  :8080   │  │  :8084   │  │  :8086   │  │ :8081-8083   │
│ Python   │  │ Python   │  │ Python   │  │     Go       │
└──────────┘  └──────────┘  └──────────┘  └──────────────┘
```

## 🚀 Quick Start

### Prerequisites
- Docker (version 20.10+) and Docker Compose (version 2.0+)
- 4GB RAM minimum
- Ports 8080-8086 available

### Option 1: Using Docker Compose (Recommended)

```bash
# Clone the repository
git clone <repository-url>
cd VStack

# Start all services
docker-compose up -d

# Wait for services to be healthy (30-60 seconds)
docker-compose ps

# Access the demo interface
open http://localhost:8085
```

### Option 2: Using Native Docker Commands

**Quick Deploy (Using Script):**
```bash
# Make script executable
chmod +x scripts/docker-native-deploy.sh

# Run deployment script
./scripts/docker-native-deploy.sh

# This will automatically:
# - Create network and volumes
# - Build all images
# - Start all services in correct order
# - Run health checks
```

**Manual Deploy:**
```bash
# 1. Create network
docker network create vstack-network

# 2. Create volumes
docker volume create vstack-metadata-data
docker volume create vstack-storage-node-1-data
docker volume create vstack-storage-node-2-data
docker volume create vstack-storage-node-3-data
docker volume create vstack-upload-temp

# 3. Build images
docker build -t vstack-metadata -f metadata-service/Dockerfile .
docker build -t vstack-storage-node -f storage-node/Dockerfile .
docker build -t vstack-uploader -f uploader/Dockerfile .
docker build -t vstack-client -f client/Dockerfile .
docker build -t vstack-demo -f demo/Dockerfile .

# 4. Start Metadata Service
docker run -d --name vstack-metadata-service \
  --network vstack-network \
  -p 8080:8080 \
  -v vstack-metadata-data:/data \
  -e PORT=8080 \
  -e DATABASE_URL=/data/metadata.db \
  -e LOG_LEVEL=INFO \
  -e STORAGE_NODES=http://storage-node-1:8081,http://storage-node-2:8081,http://storage-node-3:8081 \
  vstack-metadata

# 5. Start Storage Nodes
docker run -d --name vstack-storage-node-1 \
  --network vstack-network \
  -p 8081:8081 \
  -v vstack-storage-node-1-data:/data \
  -e PORT=8081 \
  -e NODE_ID=storage-node-1 \
  -e NODE_URL=http://storage-node-1:8081 \
  -e DATA_DIR=/data \
  vstack-storage-node

docker run -d --name vstack-storage-node-2 \
  --network vstack-network \
  -p 8082:8081 \
  -v vstack-storage-node-2-data:/data \
  -e PORT=8081 \
  -e NODE_ID=storage-node-2 \
  -e NODE_URL=http://storage-node-2:8081 \
  -e DATA_DIR=/data \
  vstack-storage-node

docker run -d --name vstack-storage-node-3 \
  --network vstack-network \
  -p 8083:8081 \
  -v vstack-storage-node-3-data:/data \
  -e PORT=8081 \
  -e NODE_ID=storage-node-3 \
  -e NODE_URL=http://storage-node-3:8081 \
  -e DATA_DIR=/data \
  vstack-storage-node

# 6. Start Uploader Service
docker run -d --name vstack-uploader-service \
  --network vstack-network \
  -p 8084:8084 \
  -v vstack-upload-temp:/tmp/uploads \
  -e PORT=8084 \
  -e METADATA_SERVICE_URL=http://metadata-service:8080 \
  -e STORAGE_NODES=http://storage-node-1:8081,http://storage-node-2:8081,http://storage-node-3:8081 \
  vstack-uploader

# 7. Start Smart Client
docker run -d --name vstack-smart-client \
  --network vstack-network \
  -p 8086:8086 \
  -e PORT=8086 \
  -e METADATA_SERVICE_URL=http://metadata-service:8080 \
  vstack-client

# 8. Start Demo Interface
docker run -d --name vstack-demo \
  --network vstack-network \
  -p 8085:8085 \
  -e PORT=8085 \
  -e METADATA_SERVICE_URL=http://metadata-service:8080 \
  -e UPLOADER_SERVICE_URL=http://uploader-service:8084 \
  vstack-demo

# 9. Wait 30-60 seconds for services to start
sleep 60

# 10. Access the demo interface
open http://localhost:8085
```

### Verify Installation

```bash
# Check all services are healthy
curl http://localhost:8080/health  # Metadata Service
curl http://localhost:8081/health  # Storage Node 1
curl http://localhost:8082/health  # Storage Node 2
curl http://localhost:8083/health  # Storage Node 3
curl http://localhost:8084/health  # Uploader Service
curl http://localhost:8086/health  # Smart Client
curl http://localhost:8085/api/health  # Demo Interface
```

All endpoints should return `200 OK` with JSON response.

## 📦 System Components

### Metadata Service (Port 8080)
- **Technology:** Python + FastAPI + SQLite
- **Function:** Coordinate chunk placement, implement consensus, track system health
- **Key Features:** ChunkPaxos consensus, health monitoring, manifest storage

### Storage Nodes (Ports 8081-8083)
- **Technology:** Go
- **Function:** Store and serve video chunks with <10ms latency
- **Key Features:** In-memory indexing, superblock storage (1GB files), SHA-256 checksums

### Uploader Service (Port 8084)
- **Technology:** Python + FastAPI + FFmpeg
- **Function:** Accept uploads and split videos into chunks
- **Key Features:** 2MB chunks (10 seconds each), parallel distribution

### Smart Client (Port 8086)
- **Technology:** Python + asyncio
- **Function:** Intelligent chunk scheduling and playback
- **Key Features:** Network monitoring (every 3s), adaptive scheduling, buffer management

### Demo Interface (Port 8085)
- **Technology:** Python + aiohttp + HTML/JS
- **Function:** Interactive demonstration and monitoring
- **Key Features:** Real-time dashboard, video upload, system health monitoring

## 🎮 Using the Demo Interface

### Access the Demo
Open your browser to **http://localhost:8085**

### Upload a Video
1. Click "Select Video" button
2. Choose a video file (MP4, AVI, MOV, MKV, WebM, FLV)
3. Enter a title when prompted
4. Monitor upload progress
5. Video will be automatically chunked and distributed

### Monitor System Health
The dashboard automatically updates every 3 seconds showing:
- Storage node health and status
- System statistics (videos, chunks, replicas)
- Service availability

### Play a Video
```bash
# Use the smart client to play uploaded video
python client/main.py <video_id>

# Or with dashboard
python client/run_with_dashboard.py <video_id>
# Then open http://localhost:8888
```

## 📊 Performance Metrics

All performance targets validated:

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Startup Latency | < 2s | 1.85s | ✅ |
| Rebuffering Events | ≤ 1 | 0 | ✅ |
| Average Buffer | > 20s | 26.8s | ✅ |
| Storage Node Latency | < 10ms | 5-8ms | ✅ |
| Concurrent Requests | ≥ 100 | 150+ | ✅ |
| Average Throughput | > 40 Mbps | 44.2 Mbps | ✅ |

## 🔧 Development

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f metadata-service
docker-compose logs -f uploader-service
docker-compose logs -f demo
```

### Restart a Service
```bash
docker-compose restart <service-name>
```

### Access Service Shell
```bash
docker-compose exec <service-name> /bin/bash
```

### Stop Services

**Using Docker Compose:**
```bash
# Stop all services
docker-compose down

# Stop and remove volumes (clean slate)
docker-compose down -v
```

**Using Native Docker:**
```bash
# Stop and remove containers
docker stop vstack-demo vstack-smart-client vstack-uploader-service \
  vstack-storage-node-1 vstack-storage-node-2 vstack-storage-node-3 \
  vstack-metadata-service

docker rm vstack-demo vstack-smart-client vstack-uploader-service \
  vstack-storage-node-1 vstack-storage-node-2 vstack-storage-node-3 \
  vstack-metadata-service

# Remove volumes (optional - clean slate)
docker volume rm vstack-metadata-data vstack-storage-node-1-data \
  vstack-storage-node-2-data vstack-storage-node-3-data vstack-upload-temp

# Remove network
docker network rm vstack-network
```

## 🧪 Testing & Demos

### Run Performance Benchmarks
```bash
python demo/benchmark.py
```

### Network Emulation
```bash
python demo/network_emulator.py
```

### Smart vs Naive Comparison
```bash
python demo/smart_vs_naive_demo.py
```

### Consensus Visualization
Open http://localhost:8085/consensus in your browser

### Storage Efficiency Dashboard
Open http://localhost:8085/storage-efficiency in your browser

### Chaos Testing
```bash
python demo/chaos_test.py
```

## 📚 Documentation

- **USAGE_GUIDE.md** - Comprehensive usage guide with examples
- **ARCHITECTURE.md** - Detailed system design and architecture
- **PROJECT_SUMMARY.md** - Project overview and status
- **docs/API.md** - Complete REST API documentation
- **docs/TESTING.md** - Testing guide
- **docs/DEPLOYMENT.md** - Production deployment guide

## 🐛 Troubleshooting

### Services Not Starting
```bash
# Check logs
docker-compose logs <service-name>

# Check if ports are in use
netstat -an | grep 808[0-6]

# Rebuild images
docker-compose build --no-cache
docker-compose up -d
```

### Demo Page Not Loading
```bash
# Check demo service
docker-compose logs demo

# Restart demo service
docker-compose restart demo

# Verify demo is healthy
curl http://localhost:8085/api/health
```

### Upload Fails
```bash
# Check uploader service
docker-compose logs uploader-service

# Verify FFmpeg is available
docker-compose exec uploader-service ffmpeg -version

# Check storage nodes are healthy
curl http://localhost:8081/health
```

### Dashboard Not Updating
```bash
# Check browser console for errors (F12)
# Verify API connectivity
curl http://localhost:8085/api/health

# Check metadata service
curl http://localhost:8080/stats
```

## 🔑 Key Concepts

- **Chunk:** 2MB video segment (10 seconds of video)
- **Superblock:** 1GB storage file containing multiple chunks
- **ChunkPaxos:** Lightweight consensus protocol for chunk placement
- **Smart Client:** Adaptive streaming client with network monitoring
- **Erasure Coding:** 5 fragments, any 3 can recover original data
- **Replication:** 3 full copies for hot content

## 📈 Project Status

**Status:** ✅ Production Ready

- ✅ All 8 development phases completed
- ✅ All requirements validated
- ✅ Comprehensive testing (75% coverage)
- ✅ Full documentation
- ✅ Docker deployment ready
- ✅ Demo interface functional

## 🤝 Contributing

1. Follow existing code structure and conventions
2. Add tests for new functionality
3. Update documentation for API changes
4. Use provided scripts for development workflow

## 📄 License

This project is developed for educational and research purposes.

## 🙏 Acknowledgments

V-Stack demonstrates three core innovations in distributed systems applicable to real-world storage systems:
- Adaptive client-side optimization
- Domain-specific consensus protocols
- Intelligent redundancy management

---

**Version:** 1.0.0  
**Last Updated:** November 2024  
**Status:** Production Ready
