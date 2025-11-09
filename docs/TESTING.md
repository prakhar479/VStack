# V-Stack Testing Guide

Comprehensive testing documentation for V-Stack distributed video storage system.

## Table of Contents

- [Testing Overview](#testing-overview)
- [Unit Tests](#unit-tests)
- [Integration Tests](#integration-tests)
- [End-to-End Tests](#end-to-end-tests)
- [Performance Tests](#performance-tests)
- [Chaos Engineering](#chaos-engineering)
- [Test Coverage](#test-coverage)

---

## Testing Overview

V-Stack implements multiple testing layers to ensure reliability, performance, and correctness.

### Test Pyramid

```
           ┌─────────────┐
           │   E2E Tests │  (Slow, High Value)
           └─────────────┘
         ┌─────────────────┐
         │Integration Tests│  (Medium Speed)
         └─────────────────┘
      ┌──────────────────────┐
      │     Unit Tests       │  (Fast, Low Level)
      └──────────────────────┘
```

### Running All Tests

```bash
# Run complete test suite
./scripts/run_integration_tests.sh

# Run specific test categories
python -m pytest tests/ -v                    # All tests
python -m pytest tests/ -k "unit"            # Unit tests only
python -m pytest tests/ -k "integration"     # Integration tests only
python -m pytest tests/ -k "e2e"             # E2E tests only
```

---

## Unit Tests

### Metadata Service Tests

Location: `metadata-service/test_*.py`


#### Database Tests

```bash
cd metadata-service
python test_simple.py
```

Tests cover:
- Video creation and retrieval
- Chunk registration
- Replica tracking
- Node health monitoring
- Consensus state management

#### Erasure Coding Tests

```bash
cd metadata-service
python test_erasure_coding.py
```

Tests cover:
- Reed-Solomon encoding/decoding
- Fragment reconstruction
- Minimum fragment requirements
- Checksum verification
- Storage efficiency calculations

#### Metadata Service API Tests

```bash
cd metadata-service
python -m pytest test_metadata_service.py -v
```

Tests cover:
- Video CRUD operations
- Manifest generation
- Chunk commit consensus
- Node registration
- Redundancy mode selection

### Storage Node Tests

Location: `storage-node/main_test.go`

```bash
cd storage-node
go test -v
```

Tests cover:
- Chunk storage and retrieval
- Index persistence
- Checksum validation
- Superblock rotation
- Concurrent access
- Error handling

### Smart Client Tests

Location: `client/test_smart_client.py`

```bash
cd client
python -m pytest test_smart_client.py -v
```

Tests cover:
- Network monitoring accuracy
- Node scoring algorithm
- Chunk scheduling logic
- Buffer management
- Failover mechanisms

### Uploader Service Tests

Location: `uploader/test_uploader.py`

```bash
cd uploader
python -m pytest test_uploader.py -v
```

Tests cover:
- Video processing
- Chunk generation
- Upload coordination
- Error recovery
- Cleanup procedures

---

## Integration Tests

### End-to-End Workflow Test

Location: `tests/test_integration_e2e.py`

```bash
python tests/test_integration_e2e.py
```

This comprehensive test validates:

1. **System Initialization**
   - All services start successfully
   - Health checks pass
   - Nodes register with metadata service

2. **Upload Workflow**
   - Video upload and processing
   - Chunk distribution to storage nodes
   - Consensus-based commit
   - Manifest generation

3. **Playback Workflow**
   - Manifest retrieval
   - Network monitoring
   - Intelligent chunk scheduling
   - Buffer management
   - Smooth playback

4. **Fault Tolerance**
   - Node failure handling
   - Automatic failover
   - Recovery procedures

### Running Integration Tests

```bash
# Start system first
docker-compose up -d

# Wait for services to be ready
sleep 30

# Run integration tests
./scripts/run_integration_tests.sh

# Or run specific test
python tests/test_integration_e2e.py
```

---

## End-to-End Tests

### Complete Upload and Playback

```bash
python scripts/test_e2e_workflow.py
```

This script tests:
- Video upload from file
- Processing and chunking
- Storage distribution
- Manifest creation
- Smart client playback
- Performance metrics collection

### Expected Results

```
✓ System health check passed
✓ Video uploaded successfully
✓ 60 chunks created and stored
✓ Manifest generated correctly
✓ Playback started (startup latency: 1.85s)
✓ Buffer maintained above 20s
✓ Zero rebuffering events
✓ Playback completed successfully

Performance Summary:
- Startup Latency: 1.85s (target: <2s) ✓
- Average Throughput: 44.2 Mbps (target: >40 Mbps) ✓
- Rebuffering Events: 0 (target: ≤1) ✓
- Average Buffer: 26.8s (target: >20s) ✓
```

---

## Performance Tests

### Benchmark Suite

Location: `demo/benchmark.py`

```bash
python demo/benchmark.py
```

Tests all performance requirements:

| Test | Target | Validates |
|------|--------|-----------|
| Startup Latency | <2s | Req 6.3 |
| Rebuffering Events | ≤1 | Req 8.5 |
| Buffer Management | >20s avg | Req 9.5 |
| Storage Node Latency | <10ms | Req 2.4 |
| Concurrent Requests | ≥100 | Req 9.1 |
| Node Response Time | <50ms | Req 9.1 |
| Concurrent Uploads | ≥10 | Req 9.2 |
| Concurrent Playback | ≥100 | Req 9.1 |
| Average Throughput | >40 Mbps | Req 9.3 |
| Load Distribution | <15% std | Req 9.4 |
| Automatic Failover | <5s | Req 8.1 |

### Erasure Coding Benchmark

```bash
python demo/erasure_coding_benchmark.py
```

Measures:
- Encoding throughput
- Decoding throughput
- Fragment reconstruction time
- Storage efficiency
- Comparison with replication

### Load Testing

```bash
# Simulate 100 concurrent clients
python demo/load_test.py --clients 100 --duration 300

# Simulate 10 concurrent uploads
python demo/upload_load_test.py --uploads 10
```

---

## Chaos Engineering

### Chaos Test Suite

Location: `demo/chaos_test.py`

```bash
python demo/chaos_test.py
```

Injects random failures:
- Node crashes
- Network latency spikes
- Packet loss
- Disk I/O delays
- Memory pressure

### Network Emulation

```bash
python demo/network_emulator.py
```

Simulates network conditions:
- High latency (150ms)
- Low bandwidth (10 Mbps)
- Packet loss (15%)
- Node failures
- Degraded conditions

### Failure Scenarios

```python
# Test node failure during upload
async def test_node_failure_during_upload():
    # Start upload
    upload_task = asyncio.create_task(upload_video())
    
    # Kill node mid-upload
    await asyncio.sleep(5)
    await kill_storage_node(1)
    
    # Verify upload completes with remaining nodes
    result = await upload_task
    assert result.success
    assert len(result.committed_nodes) >= 2

# Test node failure during playback
async def test_node_failure_during_playback():
    client = SmartClient()
    playback_task = asyncio.create_task(client.play_video(video_id))
    
    # Kill node during playback
    await asyncio.sleep(10)
    await kill_storage_node(2)
    
    # Verify automatic failover
    await asyncio.sleep(5)
    assert client.buffer_manager.rebuffering_events <= 1
    assert client.playing
```

---

## Test Coverage

### Measuring Coverage

```bash
# Python coverage
pip install pytest-cov

# Run with coverage
pytest --cov=metadata-service --cov=client --cov=uploader tests/

# Generate HTML report
pytest --cov=. --cov-report=html tests/
open htmlcov/index.html
```

### Go Coverage

```bash
cd storage-node
go test -coverprofile=coverage.out
go tool cover -html=coverage.out
```

### Coverage Targets

- Unit Tests: >80% code coverage
- Integration Tests: >60% feature coverage
- E2E Tests: 100% critical path coverage

---

## Continuous Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/test.yml
name: V-Stack Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.11'
    
    - name: Set up Go
      uses: actions/setup-go@v2
      with:
        go-version: '1.21'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        sudo apt-get install ffmpeg
    
    - name: Run unit tests
      run: |
        pytest tests/ -v
        cd storage-node && go test -v
    
    - name: Start services
      run: docker-compose up -d
    
    - name: Run integration tests
      run: ./scripts/run_integration_tests.sh
    
    - name: Run benchmarks
      run: python demo/benchmark.py
```

---

## Test Data

### Sample Videos

```bash
# Generate test videos
ffmpeg -f lavfi -i testsrc=duration=60:size=1280x720:rate=30 \
  -c:v libx264 -pix_fmt yuv420p test_video_60s.mp4

ffmpeg -f lavfi -i testsrc=duration=300:size=1920x1080:rate=30 \
  -c:v libx264 -pix_fmt yuv420p test_video_300s.mp4
```

### Mock Data

```python
# Generate mock chunks
def generate_mock_chunk(size_mb=2):
    return os.urandom(size_mb * 1024 * 1024)

# Generate mock manifest
def generate_mock_manifest(video_id, num_chunks=60):
    return {
        "video_id": video_id,
        "total_chunks": num_chunks,
        "chunks": [
            {
                "chunk_id": f"{video_id}-chunk-{i:03d}",
                "sequence_num": i,
                "replicas": ["http://localhost:8081", "http://localhost:8082"]
            }
            for i in range(num_chunks)
        ]
    }
```

---

## Debugging Tests

### Verbose Output

```bash
# Python tests with verbose output
pytest -v -s tests/

# Show print statements
pytest -v -s --capture=no tests/

# Stop on first failure
pytest -x tests/
```

### Test Isolation

```bash
# Run single test
pytest tests/test_integration_e2e.py::test_upload_workflow -v

# Run tests matching pattern
pytest -k "upload" tests/
```

### Debug Mode

```python
# Add breakpoint in test
import pdb; pdb.set_trace()

# Or use pytest's built-in debugger
pytest --pdb tests/
```

---

## Test Maintenance

### Updating Tests

When adding new features:
1. Write unit tests first (TDD)
2. Add integration tests for workflows
3. Update E2E tests if needed
4. Run full test suite
5. Update documentation

### Test Review Checklist

- [ ] Tests are isolated and independent
- [ ] Tests have clear names describing what they test
- [ ] Tests include both positive and negative cases
- [ ] Tests clean up resources after execution
- [ ] Tests are deterministic (no flaky tests)
- [ ] Tests run in reasonable time
- [ ] Tests are documented

---

## See Also

- [Architecture Documentation](../ARCHITECTURE.md)
- [API Documentation](API.md)
- [Deployment Guide](DEPLOYMENT.md)
- [Demo Tools](../demo/README.md)
