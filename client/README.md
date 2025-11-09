# V-Stack Smart Client

The Smart Client is the core novelty of V-Stack, implementing intelligent chunk scheduling based on real-time network conditions.

## Features

### 1. Network Monitoring
- Continuously pings all storage nodes every 3 seconds
- Tracks latency, bandwidth, and reliability using exponentially weighted moving averages
- Maintains historical performance data (10 recent measurements per node)

### 2. Intelligent Chunk Scheduling
- Selects optimal storage nodes using the scoring formula: `(bandwidth × reliability) / (1 + latency × 0.1)`
- Supports parallel downloads (up to 4 concurrent chunks)
- Automatic failover to alternative replicas when nodes become unavailable
- Load balancing to avoid overloading individual nodes

### 3. Buffer Management
- Maintains 30-second target playback buffer
- Triggers downloads when buffer drops below 15-second low water mark
- Smooth playback feed to video player at constant frame rate
- Tracks rebuffering events and startup latency

### 4. Real-time Dashboard
- Web-based visualization of buffer levels, node scores, and chunk sources
- Live performance metrics and statistics
- Shows which storage node each chunk was downloaded from

## Architecture

```
┌─────────────────────────────────────────┐
│         Smart Client                     │
│                                          │
│  ┌────────────────────────────────────┐ │
│  │  Network Monitor                   │ │
│  │  - Ping nodes every 3s             │ │
│  │  - Track latency, bandwidth        │ │
│  │  - Calculate node scores           │ │
│  └────────────────────────────────────┘ │
│                                          │
│  ┌────────────────────────────────────┐ │
│  │  Chunk Scheduler                   │ │
│  │  - Select best nodes               │ │
│  │  - Parallel downloads (max 4)      │ │
│  │  - Automatic failover              │ │
│  └────────────────────────────────────┘ │
│                                          │
│  ┌────────────────────────────────────┐ │
│  │  Buffer Manager                    │ │
│  │  - 30s target buffer               │ │
│  │  - 15s low water mark              │ │
│  │  - Smooth playback                 │ │
│  └────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Basic Playback

```bash
python main.py <video_id>
```

Example:
```bash
python main.py test-video-001
```

### With Dashboard

1. Start the smart client with dashboard server:
```bash
python main.py test-video-001
```

2. In another terminal, start the dashboard server:
```bash
python dashboard_server.py
```

3. Open your browser to `http://localhost:8888` to view the real-time dashboard

### Programmatic Usage

```python
from main import SmartClient
import asyncio

async def play_video():
    client = SmartClient(metadata_service_url="http://localhost:8080")
    
    if await client.initialize():
        await client.play_video("test-video-001")
        
        # Print status
        client.print_status()
        
        # Get detailed status
        status = client.get_status()
        print(f"Buffer level: {status['buffer']['buffer_level_sec']}s")
        print(f"Rebuffering events: {status['buffer_stats']['rebuffering_events']}")

asyncio.run(play_video())
```

## Components

### NetworkMonitor (`network_monitor.py`)

Monitors network performance to all storage nodes.

**Key Methods:**
- `start_monitoring(node_urls)` - Start background monitoring
- `stop_monitoring()` - Stop monitoring
- `get_node_score(node_url)` - Get performance score for a node
- `get_all_node_scores()` - Get scores for all nodes
- `is_node_healthy(node_url)` - Check if node is healthy
- `update_bandwidth(node_url, bandwidth_mbps)` - Update bandwidth measurement

### ChunkScheduler (`scheduler.py`)

Intelligently schedules chunk downloads based on node performance.

**Key Methods:**
- `select_best_node(chunk_id, available_replicas)` - Select optimal node
- `download_chunk(chunk_id, available_replicas)` - Download with failover
- `download_chunks_parallel(chunks_to_download)` - Parallel downloads
- `get_statistics()` - Get download statistics
- `get_chunk_source(chunk_id)` - Get node that served a chunk

### BufferManager (`buffer_manager.py`)

Manages playback buffer and smooth video delivery.

**Key Methods:**
- `add_chunk(chunk_id, sequence_num, chunk_data)` - Add chunk to buffer
- `get_next_chunk_for_playback()` - Get next chunk for player
- `needs_more_chunks()` - Check if buffer needs refilling
- `can_start_playback()` - Check if ready to start playback
- `get_buffer_status()` - Get current buffer status
- `get_statistics()` - Get buffer statistics

### SmartClient (`main.py`)

Main client orchestrating all components.

**Key Methods:**
- `initialize()` - Initialize and connect to metadata service
- `play_video(video_id)` - Start video playback
- `stop()` - Stop playback and cleanup
- `get_status()` - Get comprehensive client status
- `print_status()` - Print status to console

## Testing

Run the comprehensive test suite:

```bash
pytest test_smart_client.py -v
```

Run specific test class:

```bash
pytest test_smart_client.py::TestNetworkMonitor -v
```

Run with coverage:

```bash
pytest test_smart_client.py --cov=. --cov-report=html
```

## Performance Targets

- **Startup Latency**: < 2 seconds
- **Rebuffering Events**: 0-1 per session
- **Average Buffer Size**: > 20 seconds
- **Concurrent Downloads**: Up to 4 simultaneous chunks
- **Node Scoring Update**: Every 3 seconds

## Configuration

Default configuration values can be modified when initializing components:

```python
# Network Monitor
monitor = NetworkMonitor(
    ping_interval=3.0,      # Seconds between pings
    history_size=10         # Number of measurements to keep
)

# Chunk Scheduler
scheduler = ChunkScheduler(
    network_monitor=monitor,
    max_concurrent_downloads=4  # Max parallel downloads
)

# Buffer Manager
buffer = BufferManager(
    target_buffer_sec=30,       # Target buffer size
    low_water_mark_sec=15,      # Refill threshold
    chunk_duration_sec=10,      # Chunk duration
    start_playback_sec=10       # Min buffer to start
)
```

## Dashboard

The web dashboard provides real-time visualization of:

- **Buffer Status**: Current level, health percentage, state
- **Playback Statistics**: Startup latency, rebuffering events, chunks played
- **Storage Node Performance**: Scores, latency, bandwidth, success rates
- **Download Statistics**: Total downloads, success rate, failovers
- **Chunk Source Visualization**: Which node served each chunk

Access the dashboard at `http://localhost:8888` after starting the dashboard server.

## Docker Usage

Build the Docker image:

```bash
docker build -t vstack-client .
```

Run the client:

```bash
docker run --network vstack-network \
  -e METADATA_SERVICE_URL=http://metadata-service:8080 \
  vstack-client python main.py test-video-001
```

## Troubleshooting

### Connection Issues

If the client cannot connect to the metadata service:

```bash
# Check metadata service is running
curl http://localhost:8080/health

# Check network connectivity
ping metadata-service
```

### Performance Issues

If experiencing rebuffering:

1. Check node scores: `client.network_monitor.get_all_node_scores()`
2. Check buffer level: `client.buffer_manager.get_buffer_status()`
3. Check download statistics: `client.scheduler.get_statistics()`

### Test Failures

If tests hang or fail:

```bash
# Run with verbose output
pytest test_smart_client.py -v -s

# Run specific test
pytest test_smart_client.py::TestBufferManager::test_buffer_level_calculation -v
```

## Contributing

When adding new features:

1. Add tests to `test_smart_client.py`
2. Update this README
3. Ensure all tests pass: `pytest test_smart_client.py -v`
4. Check code style: `pylint *.py`

## License

Part of the V-Stack distributed video storage system.
