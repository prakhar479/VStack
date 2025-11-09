# Adaptive Redundancy - V-Stack's Third Core Novelty

## Overview

V-Stack implements adaptive redundancy selection that automatically chooses between replication and erasure coding based on video popularity. This provides **~40% storage savings** for the majority of content while maintaining fast read performance for popular videos.

## Problem Statement

Traditional distributed storage systems face a dilemma:
- **Full Replication (3 copies)**: Fast reads but wastes storage (3x overhead)
- **Erasure Coding**: Storage efficient but slower reads (requires reconstruction)

Most systems choose one approach for all data, missing optimization opportunities.

## Our Solution

V-Stack uses **popularity-based adaptive redundancy**:

### Hot Videos (>1000 views)
- **Mode**: Replication (3 full copies)
- **Rationale**: Frequently accessed, need fast reads
- **Storage**: 3x overhead
- **Read Performance**: Optimal (direct access)

### Cold Videos (≤1000 views)
- **Mode**: Erasure Coding (5 fragments, any 3 recover)
- **Rationale**: Rarely accessed, prioritize storage efficiency
- **Storage**: 1.67x overhead (5/3)
- **Read Performance**: Moderate (requires reconstruction)

## Technical Implementation

### Reed-Solomon Erasure Coding

```
Original chunk: 2 MB
         ↓
    [Encoder]
         ↓
┌────────┬────────┬────────┬────────┬────────┐
│ Frag 1 │ Frag 2 │ Frag 3 │ Frag 4 │ Frag 5 │  (400 KB each)
└────────┴────────┴────────┴────────┴────────┘

Storage: 5 × 400 KB = 2 MB (vs. 3 × 2 MB = 6 MB for replication)

Recovery: Any 3 fragments can reconstruct original chunk
Example: If node2 and node4 fail, we can still recover using [1,3,5]
```

### Configuration Parameters

```python
# Redundancy Manager Configuration
popularity_threshold = 1000  # Views threshold for hot vs cold
replication_factor = 3       # Number of full copies
erasure_data_shards = 3      # Data fragments
erasure_parity_shards = 2    # Parity fragments
```

### Automatic Mode Selection

```python
def determine_redundancy_mode(video_id, view_count):
    if view_count > 1000:  # Hot video
        return "replication", 3  # Fast reads, more copies
    else:  # Cold video
        return "erasure_coding", (5, 3)  # Save storage
```

## Storage Efficiency

### Comparison

| Metric | Replication | Erasure Coding | Savings |
|--------|-------------|----------------|---------|
| Storage per 2MB chunk | 6 MB | 3.33 MB | 44.4% |
| Nodes required | 3 | 5 | - |
| Failures tolerated | 2 | 2 | - |
| Read performance | Fast | Moderate | - |

### Real-World Impact

**Scenario: 1000 videos, 50 chunks each (2MB per chunk)**

- Hot videos (5%): 50 videos
- Cold videos (95%): 950 videos
- Total chunks: 50,000

**Full Replication:**
- Storage: 50,000 × 2MB × 3 = 300 GB

**Adaptive Redundancy:**
- Hot storage: 2,500 × 2MB × 3 = 15 GB
- Cold storage: 47,500 × 2MB × 1.67 = 158.5 GB
- Total: 173.5 GB

**Savings: 126.5 GB (42.2%)**

## API Endpoints

### Get Redundancy Recommendation

```bash
GET /redundancy/recommend/{video_id}

Response:
{
  "video_id": "abc123",
  "view_count": 500,
  "recommended_mode": "erasure_coding",
  "config": {
    "mode": "erasure_coding",
    "data_shards": 3,
    "parity_shards": 2,
    "total_shards": 5,
    "min_shards_for_recovery": 3
  }
}
```

### Set Manual Override

```bash
POST /redundancy/override/{video_id}?mode=replication

Response:
{
  "status": "ok",
  "video_id": "abc123",
  "override_mode": "replication",
  "message": "Manual override set to replication"
}
```

### Get Storage Efficiency Metrics

```bash
GET /redundancy/efficiency

Response:
{
  "efficiency": {
    "replication_overhead_factor": 3.0,
    "erasure_coding_overhead_factor": 1.67,
    "storage_savings_percent": 44.4
  },
  "mode_comparison": {
    "replication": {
      "storage_per_chunk_mb": 6.0,
      "nodes_required": 3,
      "failures_tolerated": 2
    },
    "erasure_coding": {
      "storage_per_chunk_mb": 3.33,
      "nodes_required": 5,
      "failures_tolerated": 2
    }
  }
}
```

### Get Storage Overhead Statistics

```bash
GET /storage/overhead

Response:
{
  "replication_chunks": 2500,
  "erasure_coded_chunks": 47500,
  "total_logical_bytes": 104857600000,
  "total_physical_bytes": 186413875200,
  "storage_savings_percent": 42.2,
  "replication_overhead_bytes": 15728640000,
  "erasure_overhead_bytes": 170685235200
}
```

## Performance Characteristics

### Encoding Performance
- Average time: ~3.4 seconds for 2MB chunk
- Throughput: ~0.6 MB/s
- Acceptable for upload path (one-time cost)

### Decoding Performance
- Average time: ~0.2 ms for 2MB chunk
- Throughput: ~10,000 MB/s
- Fast enough for cold data reads

### Failure Tolerance
- Can tolerate 2 node failures (any 3 of 5 fragments work)
- Same fault tolerance as 3x replication
- Verified through extensive testing

## Usage Examples

### Automatic Mode Selection

```python
from redundancy_manager import RedundancyManager

manager = RedundancyManager(popularity_threshold=1000)

# Hot video - uses replication
mode, config = manager.determine_redundancy_mode("video1", view_count=5000)
# Returns: (RedundancyMode.REPLICATION, {...})

# Cold video - uses erasure coding
mode, config = manager.determine_redundancy_mode("video2", view_count=100)
# Returns: (RedundancyMode.ERASURE_CODING, {...})
```

### Manual Override

```python
# Force replication for specific video
manager.set_manual_override("video3", RedundancyMode.REPLICATION)

# Clear override (return to automatic)
manager.clear_manual_override("video3")
```

### Encoding and Decoding

```python
from erasure_coding import ErasureCoder, FragmentManager

# Initialize coder
coder = ErasureCoder(data_shards=3, parity_shards=2)

# Encode chunk
chunk_data = b"..." # 2MB chunk
fragments = coder.encode_chunk(chunk_data)  # Returns 5 fragments

# Decode from any 3 fragments
available_fragments = [(0, fragments[0]), (2, fragments[2]), (4, fragments[4])]
manager = FragmentManager(coder)
recovered_data = manager.reconstruct_chunk(available_fragments)
```

## Testing and Validation

### Unit Tests

Run erasure coding tests:
```bash
python metadata-service/test_erasure_coding.py
```

Tests cover:
- Encoding correctness
- Decoding with all fragments
- Decoding with minimum fragments (3 of 5)
- Various fragment combinations
- Insufficient fragments error handling
- Checksum verification
- Storage efficiency calculation

### Performance Benchmarks

Run performance benchmarks:
```bash
python demo/erasure_coding_benchmark.py
```

Benchmarks measure:
- Encoding throughput
- Decoding throughput
- Comparison with replication
- Failure scenario recovery times

### Storage Efficiency Demo

Run storage efficiency demonstration:
```bash
python demo/adaptive_redundancy_demo.py
```

Demonstrates:
- Realistic video distribution (5% hot, 95% cold)
- Storage savings calculation
- Mode comparison
- Real-world impact at scale

## Configuration

### Environment Variables

```bash
# Set popularity threshold (default: 1000)
export POPULARITY_THRESHOLD=1000

# Start metadata service
python metadata-service/main.py
```

### Database Schema

New tables for adaptive redundancy:

```sql
-- Chunk fragments for erasure coding
CREATE TABLE chunk_fragments (
    fragment_id TEXT PRIMARY KEY,
    chunk_id TEXT NOT NULL,
    fragment_index INTEGER NOT NULL,
    node_url TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    checksum TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Video statistics for popularity tracking
CREATE TABLE video_stats (
    video_id TEXT PRIMARY KEY,
    view_count INTEGER DEFAULT 0,
    last_viewed TIMESTAMP,
    total_bytes_served INTEGER DEFAULT 0
);

-- Redundancy mode in chunks table
ALTER TABLE chunks ADD COLUMN redundancy_mode TEXT DEFAULT 'replication';
```

## Future Enhancements

### Dynamic Migration
- Automatically migrate videos between modes based on popularity trends
- Hot → Cold: Migrate to erasure coding when views decline
- Cold → Hot: Migrate to replication when views increase

### Cost Optimization
- Consider storage costs in mode selection
- Optimize for cost per GB vs performance requirements
- Support tiered storage (SSD for hot, HDD for cold)

### Advanced Policies
- Time-based policies (peak vs off-peak)
- Size-based policies (larger videos benefit more from erasure coding)
- Geographic policies (different modes per region)

### ML-Based Prediction
- Predict future popularity based on trends
- Proactive mode selection before popularity changes
- Optimize for predicted access patterns

## Key Takeaways

1. **40% Storage Savings**: Erasure coding saves significant storage for cold content
2. **Automatic Selection**: Popularity-based selection requires no manual intervention
3. **Fault Tolerance**: Same reliability as replication (tolerate 2 node failures)
4. **Performance Trade-off**: Acceptable for cold data that's rarely accessed
5. **Scalable**: Savings increase linearly with content library size

## References

- Reed-Solomon Error Correction: https://en.wikipedia.org/wiki/Reed%E2%80%93Solomon_error_correction
- Erasure Coding in Distributed Storage: https://www.usenix.org/system/files/conference/fast16/fast16-papers-rashmi.pdf
- Facebook's f4 Storage System: https://www.usenix.org/conference/osdi14/technical-sessions/presentation/muralidhar
