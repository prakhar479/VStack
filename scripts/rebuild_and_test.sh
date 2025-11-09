#!/bin/bash
# Rebuild services and run integration tests

set -e

echo "=========================================="
echo "Rebuilding V-Stack Services"
echo "=========================================="

echo "ℹ Stopping all services..."
docker-compose down

echo "ℹ Rebuilding services with fixes..."
docker-compose build metadata-service storage-node-1 storage-node-2 storage-node-3

echo "ℹ Starting all services..."
docker-compose up -d

echo "ℹ Waiting for services to initialize (15 seconds)..."
sleep 15

echo "ℹ Checking service health..."
curl -s http://localhost:8080/health > /dev/null && echo "✓ Metadata service is up" || echo "✗ Metadata service is down"
curl -s http://localhost:8081/health > /dev/null && echo "✓ Storage node 1 is up" || echo "✗ Storage node 1 is down"
curl -s http://localhost:8082/health > /dev/null && echo "✓ Storage node 2 is up" || echo "✗ Storage node 2 is down"
curl -s http://localhost:8083/health > /dev/null && echo "✓ Storage node 3 is up" || echo "✗ Storage node 3 is down"

echo ""
echo "=========================================="
echo "Running Integration Tests"
echo "=========================================="

./scripts/run_integration_tests.sh
