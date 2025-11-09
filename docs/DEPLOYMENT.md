# V-Stack Deployment Guide

Complete guide for deploying V-Stack in various environments.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Local Development](#local-development)
- [Docker Deployment](#docker-deployment)
- [Production Deployment](#production-deployment)
- [Configuration](#configuration)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)
- [Scaling](#scaling)

---

## Prerequisites

### System Requirements

**Minimum:**
- CPU: 4 cores
- RAM: 8 GB
- Disk: 50 GB
- OS: Linux (Ubuntu 20.04+), macOS, Windows with WSL2

**Recommended:**
- CPU: 8+ cores
- RAM: 16+ GB
- Disk: 200+ GB SSD
- OS: Linux (Ubuntu 22.04+)

### Software Dependencies

**Required:**
- Docker 20.10+
- Docker Compose 2.0+
- Python 3.11+
- Go 1.21+ (for storage node development)
- FFmpeg 4.4+ (for video processing)

**Optional:**
- Node.js 18+ (for dashboard development)
- PostgreSQL 14+ (for production metadata storage)
- Nginx (for reverse proxy)
- Prometheus + Grafana (for monitoring)

### Installation

#### Ubuntu/Debian
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo apt install docker-compose-plugin

# Install Python
sudo apt install python3.11 python3.11-venv python3-pip

# Install Go
wget https://go.dev/dl/go1.21.5.linux-amd64.tar.gz
sudo tar -C /usr/local -xzf go1.21.5.linux-amd64.tar.gz
echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.bashrc

# Install FFmpeg
sudo apt install ffmpeg

# Verify installations
docker --version
docker compose version
python3.11 --version
go version
ffmpeg -version
```

#### macOS
```bash
# Install Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install dependencies
brew install docker docker-compose python@3.11 go ffmpeg

# Start Docker Desktop
open -a Docker
```

#### Windows (WSL2)
```powershell
# Install WSL2
wsl --install

# Inside WSL2, follow Ubuntu instructions above
```

---

## Local Development

### Quick Start

```bash
# Clone repository
git clone https://github.com/yourusername/vstack.git
cd vstack

# Make scripts executable
chmod +x scripts/*.sh

# Initialize system
./scripts/init_system.sh

# Verify system is running
python3 scripts/monitor_system.py
```

### Manual Setup

```bash
# 1. Create Python virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 2. Install Python dependencies
pip install -r metadata-service/requirements.txt
pip install -r uploader/requirements.txt
pip install -r client/requirements.txt

# 3. Build storage nodes
cd storage-node
go build -o storage-node main.go
cd ..

# 4. Create data directories
mkdir -p data/{metadata,storage-node-{1,2,3},uploads}
mkdir -p logs

# 5. Start services manually
# Terminal 1: Metadata Service
cd metadata-service
python main.py

# Terminal 2-4: Storage Nodes
cd storage-node
NODE_ID=storage-node-1 PORT=8081 DATA_DIR=../data/storage-node-1 ./storage-node
NODE_ID=storage-node-2 PORT=8082 DATA_DIR=../data/storage-node-2 ./storage-node
NODE_ID=storage-node-3 PORT=8083 DATA_DIR=../data/storage-node-3 ./storage-node

# Terminal 5: Uploader Service
cd uploader
python main.py

# Terminal 6: Smart Client (optional)
cd client
python main.py
```

### Development Workflow

```bash
# Run tests
./scripts/run_integration_tests.sh

# Run specific service tests
cd metadata-service && python -m pytest
cd storage-node && go test -v
cd client && python -m pytest

# View logs
docker-compose logs -f [service-name]

# Restart service
docker-compose restart [service-name]

# Rebuild after code changes
docker-compose up --build -d [service-name]

# Clean and restart
docker-compose down -v
./scripts/init_system.sh
```

---

## Docker Deployment

### Using Docker Compose

The recommended deployment method for development and small-scale production.

#### Configuration

Edit `docker-compose.yml` to customize:

```yaml
version: '3.8'

services:
  metadata-service:
    build: ./metadata-service
    ports:
      - "8080:8080"
    environment:
      - PORT=8080
      - DATABASE_PATH=/data/metadata.db
      - POPULARITY_THRESHOLD=1000
    volumes:
      - ./data/metadata:/data
    networks:
      - vstack-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 10s
      timeout: 5s
      retries: 3

  storage-node-1:
    build: ./storage-node
    ports:
      - "8081:8081"
    environment:
      - NODE_ID=storage-node-1
      - PORT=8081
      - DATA_DIR=/data
    volumes:
      - ./data/storage-node-1:/data
    networks:
      - vstack-network

  # ... additional services ...

networks:
  vstack-network:
    driver: bridge

volumes:
  metadata-data:
  storage-node-1-data:
  storage-node-2-data:
  storage-node-3-data:
```

#### Deployment Commands

```bash
# Start all services
docker-compose up -d

# Start specific services
docker-compose up -d metadata-service storage-node-1

# Scale storage nodes
docker-compose up -d --scale storage-node=5

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Stop and remove volumes
docker-compose down -v

# Update and restart
docker-compose pull
docker-compose up -d --force-recreate
```

### Using Docker Swarm

For multi-host deployments with orchestration.

```bash
# Initialize swarm
docker swarm init

# Deploy stack
docker stack deploy -c docker-compose.yml vstack

# List services
docker service ls

# Scale service
docker service scale vstack_storage-node=5

# View logs
docker service logs vstack_metadata-service

# Update service
docker service update --image vstack/metadata-service:latest vstack_metadata-service

# Remove stack
docker stack rm vstack
```

---

## Production Deployment

### Architecture Overview

```
                    ┌─────────────┐
                    │   Nginx     │
                    │ Load Balancer│
                    └──────┬──────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼────┐       ┌────▼────┐       ┌────▼────┐
   │Metadata │       │Metadata │       │Metadata │
   │Service 1│       │Service 2│       │Service 3│
   └────┬────┘       └────┬────┘       └────┬────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                    ┌──────▼──────┐
                    │  PostgreSQL │
                    │   Cluster   │
                    └─────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼────┐       ┌────▼────┐       ┌────▼────┐
   │Storage  │       │Storage  │       │Storage  │
   │ Node 1  │       │ Node 2  │       │ Node 3  │
   └─────────┘       └─────────┘       └─────────┘
```

### PostgreSQL Setup

Replace SQLite with PostgreSQL for production:

```bash
# Install PostgreSQL
sudo apt install postgresql-14

# Create database and user
sudo -u postgres psql
CREATE DATABASE vstack;
CREATE USER vstack WITH ENCRYPTED PASSWORD 'your-secure-password';
GRANT ALL PRIVILEGES ON DATABASE vstack TO vstack;
\q

# Update metadata-service configuration
export DATABASE_URL="postgresql://vstack:password@localhost:5432/vstack"
```

### Nginx Configuration

```nginx
# /etc/nginx/sites-available/vstack

upstream metadata_backend {
    least_conn;
    server 10.0.1.10:8080 max_fails=3 fail_timeout=30s;
    server 10.0.1.11:8080 max_fails=3 fail_timeout=30s;
    server 10.0.1.12:8080 max_fails=3 fail_timeout=30s;
}

upstream storage_backend {
    least_conn;
    server 10.0.2.10:8081 max_fails=3 fail_timeout=30s;
    server 10.0.2.11:8081 max_fails=3 fail_timeout=30s;
    server 10.0.2.12:8081 max_fails=3 fail_timeout=30s;
}

server {
    listen 80;
    server_name vstack.example.com;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name vstack.example.com;

    ssl_certificate /etc/letsencrypt/live/vstack.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/vstack.example.com/privkey.pem;

    # Metadata Service
    location /api/ {
        proxy_pass http://metadata_backend/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Storage Nodes
    location /storage/ {
        proxy_pass http://storage_backend/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        
        # Large file uploads
        client_max_body_size 100M;
        proxy_request_buffering off;
    }

    # Upload Service
    location /upload/ {
        proxy_pass http://10.0.3.10:8084/;
        client_max_body_size 2G;
        proxy_request_buffering off;
        
        # Upload timeouts
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }
}
```

### SSL/TLS Setup

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d vstack.example.com

# Auto-renewal
sudo certbot renew --dry-run
```

### Systemd Services

Create systemd service files for each component:

```ini
# /etc/systemd/system/vstack-metadata.service
[Unit]
Description=V-Stack Metadata Service
After=network.target postgresql.service

[Service]
Type=simple
User=vstack
WorkingDirectory=/opt/vstack/metadata-service
Environment="DATABASE_URL=postgresql://vstack:password@localhost:5432/vstack"
Environment="PORT=8080"
ExecStart=/opt/vstack/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/vstack-storage-node@.service
[Unit]
Description=V-Stack Storage Node %i
After=network.target

[Service]
Type=simple
User=vstack
WorkingDirectory=/opt/vstack/storage-node
Environment="NODE_ID=storage-node-%i"
Environment="PORT=808%i"
Environment="DATA_DIR=/var/lib/vstack/storage-node-%i"
ExecStart=/opt/vstack/storage-node/storage-node
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start services:

```bash
# Enable services
sudo systemctl enable vstack-metadata
sudo systemctl enable vstack-storage-node@1
sudo systemctl enable vstack-storage-node@2
sudo systemctl enable vstack-storage-node@3

# Start services
sudo systemctl start vstack-metadata
sudo systemctl start vstack-storage-node@{1,2,3}

# Check status
sudo systemctl status vstack-metadata
sudo systemctl status vstack-storage-node@1
```

---

## Configuration

### Environment Variables

#### Metadata Service

```bash
# Server
PORT=8080
HOST=0.0.0.0

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/vstack
DATABASE_PATH=/data/metadata.db  # For SQLite

# Redundancy
POPULARITY_THRESHOLD=1000

# Monitoring
LOG_LEVEL=INFO
METRICS_ENABLED=true
```

#### Storage Node

```bash
# Server
NODE_ID=storage-node-1
PORT=8081
HOST=0.0.0.0

# Storage
DATA_DIR=/data
MAX_SUPERBLOCK_SIZE=1073741824  # 1GB

# Performance
ENABLE_DIRECT_IO=true
FSYNC_ENABLED=true
```

#### Uploader Service

```bash
# Server
PORT=8084
HOST=0.0.0.0

# Metadata Service
METADATA_SERVICE_URL=http://metadata-service:8080

# Processing
TEMP_DIR=/tmp/uploads
CHUNK_SIZE=2097152  # 2MB
CHUNK_DURATION=10   # seconds
MAX_UPLOAD_SIZE=2147483648  # 2GB
```

#### Smart Client

```bash
# Metadata Service
METADATA_SERVICE_URL=http://localhost:8080

# Buffer Management
TARGET_BUFFER_SEC=30
LOW_WATER_MARK_SEC=15
START_PLAYBACK_SEC=10

# Network Monitoring
PING_INTERVAL=3.0
HISTORY_SIZE=10
MAX_CONCURRENT_DOWNLOADS=4
```

### Configuration Files

Create `.env` file in project root:

```bash
# .env
COMPOSE_PROJECT_NAME=vstack

# Metadata Service
METADATA_PORT=8080
METADATA_DATABASE_PATH=./data/metadata/metadata.db
POPULARITY_THRESHOLD=1000

# Storage Nodes
STORAGE_NODE_1_PORT=8081
STORAGE_NODE_2_PORT=8082
STORAGE_NODE_3_PORT=8083

# Uploader Service
UPLOADER_PORT=8084
UPLOADER_TEMP_DIR=./data/uploads

# Logging
LOG_LEVEL=INFO
```

---

## Monitoring

### Prometheus Configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'vstack-metadata'
    static_configs:
      - targets: ['localhost:8080']
    metrics_path: '/metrics'

  - job_name: 'vstack-storage'
    static_configs:
      - targets: 
        - 'localhost:8081'
        - 'localhost:8082'
        - 'localhost:8083'
    metrics_path: '/metrics'
```

### Grafana Dashboards

Import pre-built dashboards:

1. **System Overview**
   - Total videos and chunks
   - Storage utilization
   - Request rates
   - Error rates

2. **Performance Metrics**
   - Startup latency
   - Throughput
   - Buffer levels
   - Node scores

3. **Health Monitoring**
   - Node status
   - Disk usage
   - Heartbeat status
   - Consensus success rate

### Log Aggregation

Using ELK Stack (Elasticsearch, Logstash, Kibana):

```yaml
# logstash.conf
input {
  file {
    path => "/var/log/vstack/*.log"
    type => "vstack"
  }
}

filter {
  grok {
    match => { "message" => "%{TIMESTAMP_ISO8601:timestamp} %{LOGLEVEL:level} %{GREEDYDATA:message}" }
  }
}

output {
  elasticsearch {
    hosts => ["localhost:9200"]
    index => "vstack-%{+YYYY.MM.dd}"
  }
}
```

### Health Checks

Automated health monitoring script:

```bash
#!/bin/bash
# scripts/health_check.sh

check_service() {
    local name=$1
    local url=$2
    
    if curl -sf "$url/health" > /dev/null; then
        echo "✓ $name is healthy"
        return 0
    else
        echo "✗ $name is unhealthy"
        return 1
    fi
}

check_service "Metadata Service" "http://localhost:8080"
check_service "Storage Node 1" "http://localhost:8081"
check_service "Storage Node 2" "http://localhost:8082"
check_service "Storage Node 3" "http://localhost:8083"
check_service "Uploader Service" "http://localhost:8084"
```

Add to cron for periodic checks:

```bash
# Run every 5 minutes
*/5 * * * * /opt/vstack/scripts/health_check.sh >> /var/log/vstack/health.log 2>&1
```

---

## Troubleshooting

### Common Issues

#### Services Won't Start

```bash
# Check Docker status
sudo systemctl status docker

# Check logs
docker-compose logs [service-name]

# Check ports
sudo netstat -tulpn | grep -E '808[0-4]'

# Restart Docker
sudo systemctl restart docker
```

#### Database Connection Errors

```bash
# Check database status
sudo systemctl status postgresql

# Test connection
psql -h localhost -U vstack -d vstack

# Check permissions
sudo -u postgres psql -c "\du"
```

#### Storage Node Disk Full

```bash
# Check disk usage
df -h

# Clean old superblocks (if implemented)
# Or add more storage

# Increase disk space
# Resize volume or add new disk
```

#### High Latency

```bash
# Check network latency
ping storage-node-1

# Check system load
top
htop

# Check disk I/O
iostat -x 1

# Optimize database
VACUUM ANALYZE;  # PostgreSQL
```

### Debug Mode

Enable debug logging:

```bash
# Metadata Service
export LOG_LEVEL=DEBUG
python metadata-service/main.py

# Storage Node
export LOG_LEVEL=debug
./storage-node/storage-node
```

### Performance Profiling

```bash
# Python profiling
python -m cProfile -o profile.stats metadata-service/main.py

# Go profiling
go test -cpuprofile=cpu.prof -memprofile=mem.prof -bench=.

# Analyze profiles
python -m pstats profile.stats
go tool pprof cpu.prof
```

---

## Scaling

### Horizontal Scaling

#### Add Storage Nodes

```bash
# Using Docker Compose
docker-compose up -d --scale storage-node=5

# Manual deployment
NODE_ID=storage-node-4 PORT=8084 DATA_DIR=/data/node4 ./storage-node
NODE_ID=storage-node-5 PORT=8085 DATA_DIR=/data/node5 ./storage-node

# Register with metadata service
curl -X POST "http://localhost:8080/nodes/register?node_url=http://storage-node-4:8084&node_id=storage-node-4"
```

#### Add Metadata Service Replicas

```bash
# Deploy additional instances
docker-compose up -d --scale metadata-service=3

# Configure load balancer
# Update nginx upstream configuration
```

### Vertical Scaling

#### Increase Resources

```yaml
# docker-compose.yml
services:
  metadata-service:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G
```

#### Optimize Database

```sql
-- PostgreSQL tuning
ALTER SYSTEM SET shared_buffers = '4GB';
ALTER SYSTEM SET effective_cache_size = '12GB';
ALTER SYSTEM SET maintenance_work_mem = '1GB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET default_statistics_target = 100;
ALTER SYSTEM SET random_page_cost = 1.1;
ALTER SYSTEM SET effective_io_concurrency = 200;
ALTER SYSTEM SET work_mem = '64MB';
ALTER SYSTEM SET min_wal_size = '1GB';
ALTER SYSTEM SET max_wal_size = '4GB';

-- Restart PostgreSQL
sudo systemctl restart postgresql
```

### Geographic Distribution

Deploy across multiple regions:

```
Region 1 (US-East)          Region 2 (EU-West)          Region 3 (Asia-Pacific)
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│ Metadata + 3    │◄───────►│ Metadata + 3    │◄───────►│ Metadata + 3    │
│ Storage Nodes   │         │ Storage Nodes   │         │ Storage Nodes   │
└─────────────────┘         └─────────────────┘         └─────────────────┘
```

Configure region-aware routing:

```python
# Region selection based on client location
def select_region(client_ip):
    if is_in_region(client_ip, "us-east"):
        return "http://us-east.vstack.example.com"
    elif is_in_region(client_ip, "eu-west"):
        return "http://eu-west.vstack.example.com"
    else:
        return "http://ap-south.vstack.example.com"
```

---

## Backup and Recovery

### Database Backup

```bash
# PostgreSQL backup
pg_dump -U vstack vstack > backup_$(date +%Y%m%d).sql

# Automated daily backups
0 2 * * * pg_dump -U vstack vstack | gzip > /backups/vstack_$(date +\%Y\%m\%d).sql.gz

# Restore
psql -U vstack vstack < backup_20241106.sql
```

### Storage Node Backup

```bash
# Backup superblocks and index
tar -czf storage-node-1-backup.tar.gz data/storage-node-1/

# Incremental backup using rsync
rsync -av --delete data/storage-node-1/ /backup/storage-node-1/
```

### Disaster Recovery

```bash
# 1. Stop services
docker-compose down

# 2. Restore database
psql -U vstack vstack < backup.sql

# 3. Restore storage nodes
tar -xzf storage-node-1-backup.tar.gz -C data/

# 4. Start services
docker-compose up -d

# 5. Verify system
python scripts/monitor_system.py
```

---

## Security

### Network Security

```bash
# Firewall rules (UFW)
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw deny 8080/tcp   # Block direct metadata access
sudo ufw deny 8081:8083/tcp  # Block direct storage access
sudo ufw enable
```

### Application Security

- Use HTTPS for all external communication
- Implement API authentication (JWT tokens)
- Rate limiting on upload endpoints
- Input validation and sanitization
- Regular security updates
- Secrets management (HashiCorp Vault)

### Data Security

- Encrypt data at rest
- Encrypt data in transit (TLS 1.3)
- Regular security audits
- Access control lists (ACLs)
- Audit logging

---

## Maintenance

### Regular Tasks

**Daily:**
- Monitor system health
- Check error logs
- Verify backups

**Weekly:**
- Review performance metrics
- Update dependencies
- Clean temporary files

**Monthly:**
- Security updates
- Database optimization
- Capacity planning review

**Quarterly:**
- Disaster recovery drill
- Security audit
- Performance tuning

### Update Procedure

```bash
# 1. Backup current state
./scripts/backup.sh

# 2. Pull latest changes
git pull origin main

# 3. Rebuild images
docker-compose build

# 4. Rolling update (zero downtime)
docker-compose up -d --no-deps --build metadata-service
docker-compose up -d --no-deps --build storage-node-1
# ... repeat for each service

# 5. Verify health
python scripts/monitor_system.py

# 6. Rollback if needed
docker-compose down
docker-compose up -d --force-recreate
```

---

## Support

For issues and questions:

- GitHub Issues: https://github.com/yourusername/vstack/issues
- Documentation: https://vstack.example.com/docs
- Email: support@vstack.example.com

---

## See Also

- [Architecture Documentation](../ARCHITECTURE.md)
- [API Documentation](API.md)
- [Quick Start Guide](../QUICKSTART.md)
- [Demo Tools](../demo/README.md)
