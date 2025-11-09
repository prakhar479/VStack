# V-Stack Performance Monitoring Dashboard

## Overview

The V-Stack Performance Monitoring Dashboard provides real-time visualization and analytics for the smart client's performance, demonstrating the three core novelties of the system:

1. **Smart Client Scheduling** - Network-aware chunk selection
2. **Lightweight Consensus** - ChunkPaxos coordination
3. **Adaptive Redundancy** - Dynamic replication strategies

## Features

### 1. Real-Time Monitoring

- **Buffer Level Visualization**: Live buffer status with target and low water mark indicators
- **Node Performance Scores**: Real-time scoring of storage nodes based on latency, bandwidth, and reliability
- **Throughput Monitoring**: Current and average throughput with target comparison
- **Chunk Download Sources**: Visual representation of which node served each chunk

### 2. Performance Metrics

- **Buffer Level History**: Time-series chart showing buffer health over time
- **Node Performance Trends**: Historical performance scores for all storage nodes
- **Throughput History**: Bandwidth utilization over time
- **Node Utilization**: Load distribution across storage nodes

### 3. Smart vs Naive Comparison

Side-by-side comparison demonstrating the benefits of intelligent scheduling:

- **Startup Latency**: Time to begin playback
- **Rebuffering Events**: Number of buffer underruns
- **Average Throughput**: Data transfer rate
- **Buffer Health**: Average buffer level maintained

The naive client simulation uses simple round-robin node selection without network awareness, typically showing:
- 50% slower startup
- 2-3x more rebuffering events
- 30% lower throughput
- 20% lower buffer health

### 4. Analytics & Targets

- **System Health Overview**: Uptime, data transferred, download times, failover rate
- **Performance Targets**: Comparison against requirements (startup <2s, rebuffering ≤1, buffer >20s, throughput >40 Mbps)
- **Load Distribution**: Visualization of chunk distribution across nodes

## Usage

### Running with Dashboard

```bash
# Run smart client with integrated dashboard
python client/run_with_dashboard.py <video_id>

# Or with environment variables
METADATA_SERVICE_URL=http://localhost:8080 \
DASHBOARD_PORT=8888 \
python client/run_with_dashboard.py test-video-001
```

### Standalone Dashboard Server

```bash
# Run dashboard server separately
python client/dashboard_server.py
```

### Accessing the Dashboard

Open your browser to: `http://localhost:8888`

## Dashboard Tabs

### Overview Tab
- Current buffer status and health
- Playback statistics (startup latency, rebuffering events)
- Storage node performance scores
- Download statistics
- Chunk source visualization
- Real-time throughput meter

### Performance Metrics Tab
- Buffer level history chart
- Node performance scores over time
- Node utilization and load distribution
- Throughput history chart

### Smart vs Naive Tab
- Side-by-side performance comparison
- Startup latency comparison
- Rebuffering events comparison
- Throughput comparison
- Buffer health comparison
- Performance improvement summary

### Analytics Tab
- System health overview
- Performance targets vs actual
- Load distribution chart
- Detailed metrics

## API Endpoints

The dashboard server exposes the following REST API endpoints:

### GET /
Serves the dashboard HTML page

### GET /api/status
Returns current client status including:
- Video ID and playback state
- Buffer status
- Network statistics
- Node scores
- Scheduler statistics

### GET /api/stats
Returns detailed statistics including:
- Buffer history
- Scheduler statistics
- Network statistics per node

### GET /api/metrics
Returns collected metrics history:
- Average throughput
- Average buffer level
- Average download time
- Total data transferred
- Session uptime
- Historical data for charts

### GET /api/performance
Returns performance summary comparing against targets:
- Target values from requirements
- Actual measured values
- Whether each target is met
- Overall performance score

## Metrics Collection

The dashboard automatically collects metrics every 2 seconds:

- **Buffer Level**: Tracked continuously for health monitoring
- **Throughput**: Calculated from network statistics
- **Node Scores**: Performance scores for each storage node
- **Download Times**: Individual chunk download durations

Historical data is maintained for the last 100 measurements (approximately 3-4 minutes of data).

## Performance Targets

The dashboard tracks performance against these requirements:

| Metric | Target | Description |
|--------|--------|-------------|
| Startup Latency | < 2 seconds | Time from request to playback start |
| Rebuffering Events | 0-1 per session | Buffer underrun occurrences |
| Average Buffer | > 20 seconds | Maintained buffer level |
| Average Throughput | > 40 Mbps | Data transfer rate |

## Visualization Features

### Buffer Bar
- Visual representation of current buffer level
- Color-coded health status (empty/low/healthy/full)
- Low water mark indicator
- Percentage display

### Node Performance
- Color-coded node health (healthy/degraded/down)
- Real-time performance scores
- Latency, bandwidth, and success rate metrics
- Load distribution bars

### Chunk Visualization
- Grid showing which node served each chunk
- Color-coded by node (Node 1: purple, Node 2: green, Node 3: red)
- Up to 50 most recent chunks displayed
- Demonstrates intelligent load distribution

### Charts
- Line charts for time-series data (buffer, throughput, node scores)
- Bar charts for load distribution
- Responsive design with Chart.js
- Smooth animations and updates

## Customization

### Styling
The dashboard uses a modern gradient design with:
- Purple/violet color scheme (#667eea, #764ba2)
- Card-based layout
- Responsive grid system
- Smooth animations

### Update Frequency
Default update interval: 2 seconds

To change, modify the interval in `dashboard.html`:
```javascript
setInterval(fetchDashboardData, 2000); // milliseconds
```

### History Size
Default history: 100 measurements

To change, modify in `dashboard_server.py`:
```python
self.metrics_collector = MetricsCollector(history_size=100)
```

## Troubleshooting

### Dashboard shows "No data available"
- Ensure the smart client is running
- Check that the metadata service is accessible
- Verify the client has started playback

### Charts not updating
- Check browser console for JavaScript errors
- Verify API endpoints are responding: `curl http://localhost:8888/api/status`
- Ensure Chart.js CDN is accessible

### Performance comparison shows zeros
- The naive client is simulated based on smart client performance
- Requires actual playback data to generate comparison
- Wait for at least 10-20 seconds of playback

## Development

### Adding New Metrics

1. Add metric to `MetricsCollector` class in `dashboard_server.py`
2. Record metric in `_collect_metrics_loop()`
3. Add API endpoint if needed
4. Update dashboard HTML to display metric
5. Add chart or visualization as needed

### Adding New Charts

1. Add canvas element to dashboard HTML
2. Initialize chart in `initializeCharts()` function
3. Update chart in `updateCharts()` function
4. Fetch data from appropriate API endpoint

## References

- [Chart.js Documentation](https://www.chartjs.org/docs/latest/)
- [aiohttp Web Server](https://docs.aiohttp.org/en/stable/web.html)
- V-Stack Design Document: `.kiro/specs/distributed-video-storage/design.md`
- V-Stack Requirements: `.kiro/specs/distributed-video-storage/requirements.md`
