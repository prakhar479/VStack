# V-Stack Quick Start Guide

Get V-Stack up and running in 5 minutes!

## Prerequisites

- Docker and Docker Compose installed
- Python 3.8+ (for testing scripts)
- 4GB RAM minimum
- 10GB disk space

## Step 1: Start the System

```bash
# Make scripts executable
chmod +x scripts/*.sh

# Initialize and start all services
./scripts/init_system.sh
```

This will:
- Build all Docker images (~5 minutes first time)
- Start services in correct order
- Wait for health checks
- Display service URLs

## Step 2: Verify System is Running

```bash
# Check system health
python3 scripts/monitor_system.py
```

You should see:
- ✓ Metadata service healthy
- ✓ All 3 storage nodes healthy
- ✓ System operational with quorum

## Step 3: Run a Test

```bash
# Run end-to-end workflow test
python3 scripts/test_e2e_workflow.py
```

This tests:
- Video upload workflow
- Chunk storage and retrieval
- Playback workflow
- Error handling

## Service URLs

Once running, access services at:

- **Metadata Service**: http://localhost:8080
- **Storage Node 1**: http://localhost:8081
- **Storage Node 2**: http://localhost:8082
- **Storage Node 3**: http://localhost:8083
- **Uploader Service**: http://localhost:8084
- **Demo Interface**: http://localhost:8085
- **Smart Client**: http://localhost:8086

## Common Commands

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f metadata-service
```

### Monitor System
```bash
# One-time check
python3 scripts/monitor_system.py

# Continuous monitoring (every 10 seconds)
python3 scripts/monitor_system.py --continuous 10
```

### Run Tests
```bash
# Integration tests
./scripts/run_integration_tests.sh

# End-to-end workflow tests
python3 scripts/test_e2e_workflow.py
```

### Stop System
```bash
# Stop services (keep data)
docker-compose down

# Stop and remove all data
docker-compose down -v
```

### Restart System
```bash
# Restart all services
docker-compose restart

# Restart specific service
docker-compose restart metadata-service
```

## Testing the System

### 1. Upload a Video (Manual Test)

```bash
# Create a test video record
curl -X POST http://localhost:8080/video \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Video", "duration_sec": 60}'

# Response will include video_id
```

### 2. Check Storage Nodes

```bash
# Check node health
curl http://localhost:8081/health
curl http://localhost:8082/health
curl http://localhost:8083/health
```

### 3. View Manifest

```bash
# Get video manifest (replace VIDEO_ID)
curl http://localhost:8080/manifest/VIDEO_ID
```

## Troubleshooting

### Services won't start
```bash
# Check Docker is running
docker info

# Clean restart
docker-compose down -v
./scripts/init_system.sh
```

### Health checks failing
```bash
# Wait longer (services can take 30-60 seconds to start)
sleep 30
python3 scripts/monitor_system.py

# Check logs
docker-compose logs metadata-service
```

### Port conflicts
```bash
# Check what's using the ports
netstat -tulpn | grep -E '808[0-6]'

# Stop conflicting services or change ports in docker-compose.yml
```

## Next Steps

1. **Review Architecture**: Check `ARCHITECTURE.md` for system design
2. **Run Performance Tests**: Use `scripts/test_e2e_workflow.py`
3. **Explore the Demo**: Visit http://localhost:8085

## Getting Help

- Check logs: `docker-compose logs [service-name]`
- Run system validation: `python3 scripts/validate_system.py`
- Run recovery manager: `python3 scripts/recovery_manager.py`

## System Requirements Met

✓ Docker Compose orchestration with all services
✓ Service networking and port mapping configured
✓ Volume mounts for persistent data
✓ Service dependencies and startup ordering
✓ Environment-based configuration
✓ Service discovery and health checks
✓ Configuration validation
✓ End-to-end upload workflow
✓ End-to-end playback workflow
✓ System-wide error handling
✓ Performance monitoring and metrics
✓ Comprehensive logging
✓ Integration tests for all workflows
✓ Failure scenario testing
✓ Concurrent operation testing
✓ Performance target validation

Enjoy using V-Stack! 🚀
