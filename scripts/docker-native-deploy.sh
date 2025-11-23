#!/bin/bash
# V-Stack Native Docker Deployment Script
# This script deploys V-Stack using native Docker commands (without docker-compose)

set -e

echo "=========================================="
echo "V-Stack Native Docker Deployment"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi

print_status "Docker is installed"

# Step 1: Create network
echo ""
echo "Step 1: Creating Docker network..."
if docker network inspect vstack-network &> /dev/null; then
    print_warning "Network vstack-network already exists"
else
    docker network create vstack-network
    print_status "Network created"
fi

# Step 2: Create volumes
echo ""
echo "Step 2: Creating Docker volumes..."
volumes=(
    "vstack-metadata-data"
    "vstack-storage-node-1-data"
    "vstack-storage-node-2-data"
    "vstack-storage-node-3-data"
    "vstack-upload-temp"
)

for volume in "${volumes[@]}"; do
    if docker volume inspect "$volume" &> /dev/null; then
        print_warning "Volume $volume already exists"
    else
        docker volume create "$volume"
        print_status "Volume $volume created"
    fi
done

# Step 3: Build images
echo ""
echo "Step 3: Building Docker images..."
echo "This may take 5-10 minutes..."

docker build -t vstack-metadata -f metadata-service/Dockerfile . && print_status "Metadata image built"
docker build -t vstack-storage-node -f storage-node/Dockerfile . && print_status "Storage node image built"
docker build -t vstack-uploader -f uploader/Dockerfile . && print_status "Uploader image built"
docker build -t vstack-client -f client/Dockerfile . && print_status "Client image built"
docker build -t vstack-demo -f demo/Dockerfile . && print_status "Demo image built"

# Step 4: Start Metadata Service
echo ""
echo "Step 4: Starting Metadata Service..."
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

print_status "Metadata service started"
echo "Waiting for metadata service to be ready..."
sleep 10

# Step 5: Start Storage Nodes
echo ""
echo "Step 5: Starting Storage Nodes..."

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

print_status "Storage Node 1 started"

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

print_status "Storage Node 2 started"

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

print_status "Storage Node 3 started"
echo "Waiting for storage nodes to be ready..."
sleep 10

# Step 6: Start Uploader Service
echo ""
echo "Step 6: Starting Uploader Service..."
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

print_status "Uploader service started"

# Step 7: Start Smart Client
echo ""
echo "Step 7: Starting Smart Client..."
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

print_status "Smart client started"

# Step 8: Start Demo Interface
echo ""
echo "Step 8: Starting Demo Interface..."
docker run -d --name vstack-demo \
  --network vstack-network \
  --network-alias demo \
  -p 8085:8085 \
  -e PORT=8085 \
  -e METADATA_SERVICE_URL=http://metadata-service:8080 \
  -e UPLOADER_SERVICE_URL=http://uploader-service:8084 \
  -e CLIENT_DASHBOARD_URL=http://smart-client:8086 \
  vstack-demo

print_status "Demo interface started"

# Step 9: Wait for services to be ready
echo ""
echo "Step 9: Waiting for all services to be ready..."
sleep 20

# Step 10: Health check
echo ""
echo "Step 10: Running health checks..."
echo ""

services=(
  "Metadata Service:8080"
  "Storage Node 1:8081"
  "Storage Node 2:8082"
  "Storage Node 3:8083"
  "Uploader Service:8084"
  "Smart Client:8086"
  "Demo Interface:8085"
)

all_healthy=true

for service in "${services[@]}"; do
  name="${service%%:*}"
  port="${service##*:}"
  
  if curl -sf "http://localhost:${port}/health" > /dev/null 2>&1; then
    print_status "$name is healthy"
  else
    print_error "$name is not responding"
    all_healthy=false
  fi
done

echo ""
echo "=========================================="
if [ "$all_healthy" = true ]; then
    print_status "Deployment complete! All services are healthy."
    echo ""
    echo "Access the demo interface at: http://localhost:8085"
    echo ""
    echo "Service URLs:"
    echo "  - Demo Interface:    http://localhost:8085"
    echo "  - Metadata Service:  http://localhost:8080"
    echo "  - Storage Node 1:    http://localhost:8081"
    echo "  - Storage Node 2:    http://localhost:8082"
    echo "  - Storage Node 3:    http://localhost:8083"
    echo "  - Uploader Service:  http://localhost:8084"
    echo "  - Smart Client:      http://localhost:8086"
else
    print_warning "Deployment complete but some services are not healthy."
    echo ""
    echo "Check logs with: docker logs vstack-<service-name>"
fi
echo "=========================================="
