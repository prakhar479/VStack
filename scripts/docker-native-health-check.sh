#!/bin/bash
# V-Stack Native Docker Health Check Script
# Checks the health status of all V-Stack services

echo "=========================================="
echo "V-Stack Health Check"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

services=(
  "vstack-metadata-service:8080:/health"
  "vstack-storage-node-1:8081:/health"
  "vstack-storage-node-2:8082:/health"
  "vstack-storage-node-3:8083:/health"
  "vstack-uploader-service:8084:/health"
  "vstack-smart-client:8086:/health"
  "vstack-demo:8085:/api/health"
)

all_healthy=true

for service in "${services[@]}"; do
  IFS=':' read -r name port endpoint <<< "$service"
  
  # Check if container is running
  if docker ps --format '{{.Names}}' | grep -q "^${name}$"; then
    # Check health endpoint
    if response=$(curl -sf "http://localhost:${port}${endpoint}" 2>&1); then
      echo -e "${GREEN}✓${NC} ${name} - HEALTHY"
      
      # Show additional info if available
      if echo "$response" | jq -e '.status' &> /dev/null; then
        status=$(echo "$response" | jq -r '.status')
        echo "  Status: $status"
      fi
    else
      echo -e "${RED}✗${NC} ${name} - UNHEALTHY (running but not responding)"
      all_healthy=false
    fi
  else
    echo -e "${RED}✗${NC} ${name} - NOT RUNNING"
    all_healthy=false
  fi
  echo ""
done

echo "=========================================="
if [ "$all_healthy" = true ]; then
  echo -e "${GREEN}All services are healthy!${NC}"
  echo ""
  echo "Access the demo interface at: http://localhost:8085"
else
  echo -e "${YELLOW}Some services are not healthy.${NC}"
  echo ""
  echo "Check logs with: docker logs <container-name>"
  echo "Example: docker logs vstack-metadata-service"
fi
echo "=========================================="

exit $([ "$all_healthy" = true ] && echo 0 || echo 1)
