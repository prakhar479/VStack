#!/bin/bash
# V-Stack Native Docker Cleanup Script
# This script removes all V-Stack containers, volumes, and network

set -e

echo "=========================================="
echo "V-Stack Native Docker Cleanup"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

# Confirm cleanup
read -p "This will remove all V-Stack containers, volumes, and data. Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cleanup cancelled."
    exit 0
fi

# Stop containers
echo ""
echo "Stopping containers..."
containers=(
  "vstack-demo"
  "vstack-smart-client"
  "vstack-uploader-service"
  "vstack-storage-node-1"
  "vstack-storage-node-2"
  "vstack-storage-node-3"
  "vstack-metadata-service"
)

for container in "${containers[@]}"; do
  if docker ps -a --format '{{.Names}}' | grep -q "^${container}$"; then
    docker stop "$container" 2>/dev/null && print_status "Stopped $container"
  else
    print_warning "$container not found"
  fi
done

# Remove containers
echo ""
echo "Removing containers..."
for container in "${containers[@]}"; do
  if docker ps -a --format '{{.Names}}' | grep -q "^${container}$"; then
    docker rm "$container" 2>/dev/null && print_status "Removed $container"
  fi
done

# Remove volumes
echo ""
echo "Removing volumes..."
volumes=(
  "vstack-metadata-data"
  "vstack-storage-node-1-data"
  "vstack-storage-node-2-data"
  "vstack-storage-node-3-data"
  "vstack-upload-temp"
)

for volume in "${volumes[@]}"; do
  if docker volume inspect "$volume" &> /dev/null; then
    docker volume rm "$volume" 2>/dev/null && print_status "Removed volume $volume"
  else
    print_warning "Volume $volume not found"
  fi
done

# Remove network
echo ""
echo "Removing network..."
if docker network inspect vstack-network &> /dev/null; then
  docker network rm vstack-network 2>/dev/null && print_status "Removed network vstack-network"
else
  print_warning "Network vstack-network not found"
fi

# Optional: Remove images
echo ""
read -p "Remove Docker images as well? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
  echo "Removing images..."
  images=(
    "vstack-metadata"
    "vstack-storage-node"
    "vstack-uploader"
    "vstack-client"
    "vstack-demo"
  )
  
  for image in "${images[@]}"; do
    if docker images --format '{{.Repository}}' | grep -q "^${image}$"; then
      docker rmi "$image" 2>/dev/null && print_status "Removed image $image"
    else
      print_warning "Image $image not found"
    fi
  done
fi

echo ""
echo "=========================================="
print_status "Cleanup complete!"
echo "=========================================="
