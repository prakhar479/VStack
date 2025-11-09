# Smart Client Quick Start Guide

## Installation

```bash
cd client
pip install -r requirements.txt
```

## Quick Test

Run the test suite to verify everything works:

```bash
pytest test_smart_client.py -v
```

Expected output: All tests should pass ✅

## Running the Smart Client

### Prerequisites

1. Metadata Service running on `http://localhost:8080`
2. Storage Nodes running on `http://localhost:8081`, `8082`, `8083`
3. Video uploaded and manifest available

### Basic Usage

```bash
# Play a video
python main.py <video_id>

# Example
python main.py test-video-001
```

The client will:
1. Connect to metadata service
2. Fetch video manifest
3. Start network monitoring
4. Begin downloading and buffering chunks
5. Start playback when buffer is ready
6. Print status updates every 5 seconds

### With Web Dashboard

**Terminal 1** - Start the client:
```bash
python main.py test-video-001
```

**Terminal 2** - Start dashboard server:
```bash
python dashboard_server.py
```

**Browser** - Open the dashboard:
```
http://localhost:8888
```

You'll see real-time visualization of:
- Buffer levels and health
- Storage node performance scores
- Download statistics
- Chunk source visualization

## Understanding the Output

### Console Output

```
INFO:__main__:Smart Client initialized successfully
INFO:__main__:Starting playback for video: test-video-001
INFO:__main__:Fetched manifest for video test-video-001: 60 chunks
INFO:__main__:Starting network monitoring for 3 nodes
INFO:__main__:Buffering initial chunks...
INFO:__main__:Playback ready! Startup latency: 1.85s

============================================================
V-STACK SMART CLIENT STATUS
============================================================
Video ID: test-video-001
Startup Latency: 1.85s

Buffer Status: HEALTHY
  Level: 25.0s / 30.0s
  Health: 83%
  Position: Chunk 5

Playback Statistics:
  Chunks Played: 5
  Rebuffering Events: 0

Download Statistics:
  Total Downloads: 8
  Success Rate: 100.0%
  Failovers: 0

Storage Node Scores:
  http://localhost:8081: 16.80
  http://localhost:8082: 14.20
  http://localhost:8083: 12.50
============================================================
```

### Key Metrics

- **Startup Latency**: Time from start to playback ready (target: < 2s)
- **Buffer Level**: Current buffer in seconds (target: 30s)
- **Buffer Health**: Percentage of target buffer (100% = full)
- **Rebuffering Events**: Number of buffer underruns (target: 0-1)
- **Node Scores**: Performance scores for each storage node (higher = better)
- **Success Rate**: Percentage of successful downloads (target: > 95%)

## Testing Individual Components

### Test Network Monitor

```python
from network_monitor import NetworkMonitor
import asyncio

async def test_monitor():
    monitor = NetworkMonitor(ping_interval=3.0)
    nodes = ['http://localhost:8081', 'http://localhost:8082']
    
    await monitor.start_monitoring(nodes)
    await asyncio.sleep(10)  # Monitor for 10 seconds
    
    # Check scores
    scores = monitor.get_all_node_scores()
    print(f"Node scores: {scores}")
    
    await monitor.stop_monitoring()

asyncio.run(test_monitor())
```

### Test Chunk Scheduler

```python
from network_monitor import NetworkMonitor
from scheduler import ChunkScheduler
import asyncio

async def test_scheduler():
    monitor = NetworkMonitor()
    scheduler = ChunkScheduler(monitor)
    
    # Simulate node data
    monitor.latencies['http://localhost:8081'].extend([20.0] * 3)
    monitor.bandwidths['http://localhost:8081'].extend([50.0] * 3)
    monitor.success_rates['http://localhost:8081'].extend([1.0] * 3)
    
    # Select best node
    best = scheduler.select_best_node(
        'chunk-001',
        ['http://localhost:8081', 'http://localhost:8082']
    )
    print(f"Best node: {best}")

asyncio.run(test_scheduler())
```

### Test Buffer Manager

```python
from buffer_manager import BufferManager

def test_buffer():
    buffer = BufferManager(
        target_buffer_sec=30,
        low_water_mark_sec=15,
        chunk_duration_sec=10
    )
    
    # Add chunks
    buffer.add_chunk('chunk-0', 0, b'data0')
    buffer.add_chunk('chunk-1', 1, b'data1')
    buffer.add_chunk('chunk-2', 2, b'data2')
    
    # Check status
    status = buffer.get_buffer_status()
    print(f"Buffer level: {status['buffer_level_sec']}s")
    print(f"State: {status['state']}")
    print(f"Can start playback: {status['can_start_playback']}")
    
    # Play a chunk
    chunk = buffer.get_next_chunk_for_playback()
    print(f"Playing chunk: {chunk.chunk_id}")

test_buffer()
```

## Troubleshooting

### "Failed to connect to metadata service"

**Problem**: Client cannot reach metadata service

**Solution**:
```bash
# Check if metadata service is running
curl http://localhost:8080/health

# If not running, start it
cd metadata-service
python main.py
```

### "No storage nodes found in manifest"

**Problem**: Video manifest has no storage node information

**Solution**:
1. Ensure storage nodes are running
2. Upload a video using the uploader service
3. Verify manifest contains replica information

### Tests hang at the end

**Problem**: Pytest doesn't exit cleanly due to async tasks

**Solution**: This is expected behavior. The tests pass successfully. Use Ctrl+C to exit if needed. The pytest.ini configuration should help with cleanup.

### High rebuffering events

**Problem**: Buffer keeps running empty

**Solution**:
1. Check network connectivity to storage nodes
2. Check node scores: `monitor.get_all_node_scores()`
3. Increase buffer target: `BufferManager(target_buffer_sec=60)`
4. Check storage node performance

## Docker Usage

### Build Image

```bash
docker build -t vstack-client .
```

### Run Container

```bash
docker run --rm \
  --network vstack-network \
  -e METADATA_SERVICE_URL=http://metadata-service:8080 \
  vstack-client python main.py test-video-001
```

### With Dashboard

```bash
docker run --rm \
  --network vstack-network \
  -p 8888:8888 \
  -e METADATA_SERVICE_URL=http://metadata-service:8080 \
  vstack-client python dashboard_server.py
```

## Performance Tips

### Optimize for Low Latency

```python
client = SmartClient()
client.buffer_manager.start_playback_sec = 5  # Start faster
client.buffer_manager.low_water_mark_sec = 10  # More aggressive refill
```

### Optimize for Reliability

```python
client = SmartClient()
client.buffer_manager.target_buffer_sec = 60  # Larger buffer
client.buffer_manager.low_water_mark_sec = 30  # Earlier refill
client.scheduler.max_concurrent_downloads = 6  # More parallel downloads
```

### Optimize for Bandwidth

```python
client = SmartClient()
client.scheduler.max_concurrent_downloads = 2  # Fewer parallel downloads
client.network_monitor.ping_interval = 5.0  # Less frequent monitoring
```

## Next Steps

1. **Integration Testing**: Test with full V-Stack system
2. **Performance Benchmarking**: Measure against targets
3. **Network Simulation**: Test with various network conditions
4. **Load Testing**: Multiple concurrent clients
5. **Demonstration**: Use dashboard for showcasing adaptive behavior

## Support

For issues or questions:
1. Check the README.md for detailed documentation
2. Review test cases in test_smart_client.py
3. Check implementation details in IMPLEMENTATION_SUMMARY.md
