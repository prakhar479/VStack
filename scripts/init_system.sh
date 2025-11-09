#!/bin/bash
# System initialization script for V-Stack
# Ensures proper startup order and configuration validation

set -e

echo "=========================================="
echo "V-Stack System Initialization"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

# Check if Docker is running
print_info "Checking Docker..."
if ! docker info > /dev/null 2>&1; then
    print_error "Docker is not running. Please start Docker first."
    exit 1
fi
print_success "Docker is running"

# Check if docker-compose is available
print_info "Checking docker-compose..."
if ! command -v docker-compose &> /dev/null; then
    print_error "docker-compose is not installed"
    exit 1
fi
print_success "docker-compose is available"

# Create necessary directories
print_info "Creating data directories..."
mkdir -p data/metadata
mkdir -p data/storage-node-1
mkdir -p data/storage-node-2
mkdir -p data/storage-node-3
mkdir -p data/uploads
print_success "Data directories created"

# Stop any existing containers
print_info "Stopping existing containers..."
docker-compose down -v 2>/dev/null || true
print_success "Existing containers stopped"

# Build images
print_info "Building Docker images..."
if docker-compose build; then
    print_success "Docker images built successfully"
else
    print_error "Failed to build Docker images"
    exit 1
fi

# Start services in order
print_info "Starting metadata service..."
docker-compose up -d metadata-service
sleep 5

# Wait for metadata service to be healthy
print_info "Waiting for metadata service to be healthy..."
MAX_RETRIES=30
RETRY_COUNT=0
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    # Check using curl from host machine
    if curl -f http://localhost:8080/health > /dev/null 2>&1; then
        print_success "Metadata service is healthy"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
        print_error "Metadata service failed to start"
        docker-compose logs metadata-service
        exit 1
    fi
    sleep 2
done

# Start storage nodes
print_info "Starting storage nodes..."
docker-compose up -d storage-node-1 storage-node-2 storage-node-3
sleep 5

# Wait for storage nodes to be healthy
print_info "Waiting for storage nodes to be healthy..."
PORTS=(8081 8082 8083)
NODES=(storage-node-1 storage-node-2 storage-node-3)
for i in 0 1 2; do
    node=${NODES[$i]}
    port=${PORTS[$i]}
    RETRY_COUNT=0
    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        # Check using curl from host machine
        if curl -f http://localhost:$port/health > /dev/null 2>&1; then
            print_success "$node is healthy"
            break
        fi
        RETRY_COUNT=$((RETRY_COUNT + 1))
        if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
            print_error "$node failed to start"
            docker-compose logs $node
            exit 1
        fi
        sleep 2
    done
done

# Start remaining services
print_info "Starting uploader service..."
docker-compose up -d uploader-service
sleep 3

print_info "Starting smart client..."
docker-compose up -d smart-client
sleep 3

print_info "Starting demo interface..."
docker-compose up -d demo
sleep 3

# Final health check
print_info "Running system validation..."
echo ""
docker-compose ps

echo ""
echo "=========================================="
print_success "V-Stack system initialized successfully!"
echo "=========================================="
echo ""
echo "Service URLs:"
echo "  - Metadata Service:  http://localhost:8080"
echo "  - Storage Node 1:    http://localhost:8081"
echo "  - Storage Node 2:    http://localhost:8082"
echo "  - Storage Node 3:    http://localhost:8083"
echo "  - Uploader Service:  http://localhost:8084"
echo "  - Smart Client:      http://localhost:8086"
echo "  - Demo Interface:    http://localhost:8085"
echo ""
echo "To view logs: docker-compose logs -f [service-name]"
echo "To stop system: docker-compose down"
echo ""
