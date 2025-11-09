#!/bin/bash

# V-Stack Cleanup Script

set -e

echo "🧹 Cleaning up V-Stack development environment..."

# Stop and remove containers
echo "🛑 Stopping and removing containers..."
docker-compose down -v

# Remove Docker images (optional)
read -p "🗑️  Remove Docker images? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🗑️  Removing Docker images..."
    docker-compose down --rmi all
fi

# Clean up data directories
read -p "🗑️  Remove persistent data? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🗑️  Removing data directories..."
    rm -rf storage-node/data/*
    rm -rf metadata-service/data/*
    rm -rf client/cache/*
    rm -rf uploader/temp/*
    rm -rf logs/*
fi

# Clean up Python virtual environments
read -p "🗑️  Remove Python virtual environments? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🗑️  Removing Python virtual environments..."
    rm -rf metadata-service/venv
    rm -rf uploader/venv
    rm -rf client/venv
fi

# Clean up Go build artifacts
echo "🗑️  Cleaning Go build artifacts..."
cd storage-node
go clean
cd ..

echo "✅ Cleanup complete!"