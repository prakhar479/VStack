#!/bin/bash

# V-Stack Demo Runner Script

set -e

echo "🎬 Starting V-Stack Distributed Video Storage Demo..."

# Check if setup has been run
if [ ! -f ".env" ]; then
    echo "⚠️  Environment not set up. Running setup first..."
    ./scripts/setup.sh
fi

# Load environment variables
if [ -f ".env" ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Function to check if a service is healthy
check_service_health() {
    local service_url=$1
    local service_name=$2
    local max_attempts=30
    local attempt=1

    echo "🔍 Checking $service_name health..."
    
    while [ $attempt -le $max_attempts ]; do
        if curl -f -s "$service_url/health" > /dev/null 2>&1; then
            echo "✅ $service_name is healthy"
            return 0
        fi
        
        echo "⏳ Waiting for $service_name... (attempt $attempt/$max_attempts)"
        sleep 2
        attempt=$((attempt + 1))
    done
    
    echo "❌ $service_name failed to start"
    return 1
}

# Function to display service status
show_service_status() {
    echo ""
    echo "📊 Service Status:"
    echo "===================="
    
    services=(
        "http://localhost:8080:Metadata Service"
        "http://localhost:8081:Storage Node 1"
        "http://localhost:8082:Storage Node 2" 
        "http://localhost:8083:Storage Node 3"
        "http://localhost:8084:Uploader Service"
    )
    
    for service in "${services[@]}"; do
        IFS=':' read -r url name <<< "$service"
        if curl -f -s "$url/health" > /dev/null 2>&1; then
            echo "✅ $name: Running"
        else
            echo "❌ $name: Not responding"
        fi
    done
    echo ""
}

# Stop any existing containers
echo "🛑 Stopping existing containers..."
docker-compose down

# Start services in the background
echo "🚀 Starting V-Stack services..."
docker-compose up -d

# Wait for services to be healthy
echo "⏳ Waiting for services to start..."
sleep 5

# Check service health
check_service_health "http://localhost:8080" "Metadata Service"
check_service_health "http://localhost:8081" "Storage Node 1"
check_service_health "http://localhost:8082" "Storage Node 2"
check_service_health "http://localhost:8083" "Storage Node 3"
check_service_health "http://localhost:8084" "Uploader Service"

# Show final status
show_service_status

echo "🎉 V-Stack demo is now running!"
echo ""
echo "🌐 Access points:"
echo "- Demo Interface: http://localhost:8085"
echo "- Metadata Service API: http://localhost:8080"
echo "- Uploader Service API: http://localhost:8084"
echo ""
echo "📋 Available commands:"
echo "- View logs: docker-compose logs -f [service-name]"
echo "- Stop demo: docker-compose down"
echo "- Restart service: docker-compose restart [service-name]"
echo ""
echo "🔧 Development commands:"
echo "- Rebuild and restart: docker-compose up --build"
echo "- Access container shell: docker-compose exec [service-name] /bin/bash"
echo ""

# Optional: Open demo in browser (if running on desktop)
if command -v xdg-open &> /dev/null; then
    echo "🌐 Opening demo in browser..."
    xdg-open http://localhost:8085
elif command -v open &> /dev/null; then
    echo "🌐 Opening demo in browser..."
    open http://localhost:8085
fi

echo "📊 Monitoring services... (Press Ctrl+C to stop monitoring)"
echo ""

# Monitor services (optional)
while true; do
    sleep 30
    show_service_status
done