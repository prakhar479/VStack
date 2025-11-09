#!/bin/bash

# V-Stack Development Environment Setup Script

set -e

echo "🚀 Setting up V-Stack development environment..."

# Check if Docker and Docker Compose are installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Check if Go is installed (for storage node development)
if ! command -v go &> /dev/null; then
    echo "⚠️  Go is not installed. Storage node development will require Go 1.21+."
fi

# Check if Python is installed (for services development)
if ! command -v python3 &> /dev/null; then
    echo "⚠️  Python 3 is not installed. Service development will require Python 3.11+."
fi

# Create necessary directories
echo "📁 Creating project directories..."
mkdir -p storage-node/data/{chunks,index}
mkdir -p metadata-service/data
mkdir -p client/cache
mkdir -p uploader/temp
mkdir -p demo/assets
mkdir -p logs

# Set up Go module for storage node
echo "🔧 Setting up Go module for storage node..."
cd storage-node
if [ ! -f "go.sum" ]; then
    go mod tidy
fi
cd ..

# Set up Python virtual environments (optional for local development)
echo "🐍 Setting up Python environments..."

# Metadata service
if [ ! -d "metadata-service/venv" ]; then
    echo "Creating virtual environment for metadata service..."
    cd metadata-service
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    deactivate
    cd ..
fi

# Uploader service
if [ ! -d "uploader/venv" ]; then
    echo "Creating virtual environment for uploader service..."
    cd uploader
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    deactivate
    cd ..
fi

# Client
if [ ! -d "client/venv" ]; then
    echo "Creating virtual environment for client..."
    cd client
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    deactivate
    cd ..
fi

# Build Docker images
echo "🐳 Building Docker images..."
docker-compose build

# Create sample configuration files
echo "⚙️  Creating configuration files..."

# Create environment file
cat > .env << EOF
# V-Stack Environment Configuration

# Service Ports
METADATA_SERVICE_PORT=8080
STORAGE_NODE_1_PORT=8081
STORAGE_NODE_2_PORT=8082
STORAGE_NODE_3_PORT=8083
UPLOADER_SERVICE_PORT=8084
DEMO_PORT=8085

# Storage Configuration
CHUNK_SIZE_BYTES=2097152
CHUNK_DURATION_SEC=10
SUPERBLOCK_SIZE_BYTES=1073741824

# Network Configuration
NETWORK_MONITOR_INTERVAL_SEC=3
BUFFER_TARGET_SEC=30
BUFFER_LOW_WATER_MARK_SEC=15
MAX_CONCURRENT_DOWNLOADS=4

# Development Settings
LOG_LEVEL=INFO
DEBUG_MODE=true
EOF

# Create sample video for testing (placeholder)
echo "📹 Setting up test assets..."
mkdir -p demo/assets/sample-videos
echo "Sample video files can be placed in demo/assets/sample-videos/" > demo/assets/sample-videos/README.txt

# Set permissions
echo "🔐 Setting file permissions..."
chmod +x scripts/*.sh
chmod +x storage-node/main.go 2>/dev/null || true
chmod +x metadata-service/main.py
chmod +x uploader/main.py
chmod +x client/main.py

echo "✅ V-Stack development environment setup complete!"
echo ""
echo "🎯 Next steps:"
echo "1. Run 'scripts/run_demo.sh' to start all services"
echo "2. Open http://localhost:8085 to access the demo interface"
echo "3. Check service health at:"
echo "   - Metadata Service: http://localhost:8080/health"
echo "   - Storage Node 1: http://localhost:8081/health"
echo "   - Storage Node 2: http://localhost:8082/health"
echo "   - Storage Node 3: http://localhost:8083/health"
echo "   - Uploader Service: http://localhost:8084/health"
echo ""
echo "📚 For development:"
echo "- Use 'docker-compose logs <service-name>' to view logs"
echo "- Use 'docker-compose exec <service-name> /bin/bash' to access containers"
echo "- Modify code and run 'docker-compose up --build' to rebuild"