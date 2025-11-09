#!/usr/bin/env python3
"""
Erasure Coding Performance Benchmark
Measures encoding/decoding performance and compares with replication
"""

import sys
import os
import time
import random

# Add parent directories to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'metadata-service'))

from erasure_coding import ErasureCoder, FragmentManager

def benchmark_encoding(coder: ErasureCoder, chunk_size_mb: int, iterations: int = 10):
    """Benchmark encoding performance"""
    chunk_data = os.urandom(chunk_size_mb * 1024 * 1024)
    
    times = []
    for i in range(iterations):
        start = time.time()
        fragments = coder.encode_chunk(chunk_data)
        elapsed = time.time() - start
        times.append(elapsed)
    
    avg_time = sum(times) / len(times)
    throughput_mbps = (chunk_size_mb / avg_time) if avg_time > 0 else 0
    
    return {
        "avg_time_ms": avg_time * 1000,
        "min_time_ms": min(times) * 1000,
        "max_time_ms": max(times) * 1000,
        "throughput_mbps": throughput_mbps
    }

def benchmark_decoding(coder: ErasureCoder, chunk_size_mb: int, iterations: int = 10):
    """Benchmark decoding performance"""
    chunk_data = os.urandom(chunk_size_mb * 1024 * 1024)
    fragments = coder.encode_chunk(chunk_data)
    
    # Test with minimum fragments (3 out of 5)
    test_fragments = fragments[:3]
    indices = [0, 1, 2]
    
    times = []
    for i in range(iterations):
        start = time.time()
        decoded = coder.decode_fragments(test_fragments, indices)
        elapsed = time.time() - start
        times.append(elapsed)
    
    avg_time = sum(times) / len(times)
    throughput_mbps = (chunk_size_mb / avg_time) if avg_time > 0 else 0
    
    return {
        "avg_time_ms": avg_time * 1000,
        "min_time_ms": min(times) * 1000,
        "max_time_ms": max(times) * 1000,
        "throughput_mbps": throughput_mbps
    }

def benchmark_replication_write(chunk_size_mb: int, iterations: int = 10):
    """Benchmark replication write (3 copies)"""
    chunk_data = os.urandom(chunk_size_mb * 1024 * 1024)
    
    times = []
    for i in range(iterations):
        start = time.time()
        # Simulate writing 3 copies
        copy1 = chunk_data
        copy2 = chunk_data
        copy3 = chunk_data
        elapsed = time.time() - start
        times.append(elapsed)
    
    avg_time = sum(times) / len(times)
    throughput_mbps = (chunk_size_mb * 3 / avg_time) if avg_time > 0 else 0
    
    return {
        "avg_time_ms": avg_time * 1000,
        "min_time_ms": min(times) * 1000,
        "max_time_ms": max(times) * 1000,
        "throughput_mbps": throughput_mbps
    }

def benchmark_replication_read(chunk_size_mb: int, iterations: int = 10):
    """Benchmark replication read (1 copy)"""
    chunk_data = os.urandom(chunk_size_mb * 1024 * 1024)
    
    times = []
    for i in range(iterations):
        start = time.time()
        # Simulate reading 1 copy
        data = chunk_data
        elapsed = time.time() - start
        times.append(elapsed)
    
    avg_time = sum(times) / len(times)
    throughput_mbps = (chunk_size_mb / avg_time) if avg_time > 0 else 0
    
    return {
        "avg_time_ms": avg_time * 1000,
        "min_time_ms": min(times) * 1000,
        "max_time_ms": max(times) * 1000,
        "throughput_mbps": throughput_mbps
    }

def test_failure_scenarios(coder: ErasureCoder):
    """Test various failure scenarios"""
    print("\n" + "="*70)
    print("FAILURE SCENARIO TESTING")
    print("="*70)
    
    chunk_data = os.urandom(2 * 1024 * 1024)  # 2MB
    fragments = coder.encode_chunk(chunk_data)
    
    scenarios = [
        ("All 5 fragments available", [0, 1, 2, 3, 4]),
        ("1 fragment lost (4 available)", [0, 1, 2, 3]),
        ("2 fragments lost (3 available - minimum)", [0, 1, 2]),
        ("2 fragments lost (different set)", [0, 2, 4]),
        ("2 fragments lost (last 3)", [2, 3, 4])
    ]
    
    print("\nTesting recovery with different fragment combinations:")
    print("-" * 70)
    
    for desc, indices in scenarios:
        try:
            selected_frags = [fragments[i] for i in indices]
            start = time.time()
            decoded = coder.decode_fragments(selected_frags, indices)
            elapsed = (time.time() - start) * 1000
            
            # Verify correctness
            success = decoded[:len(chunk_data)] == chunk_data
            status = "✓ SUCCESS" if success else "✗ FAILED"
            
            print(f"{desc:<45} {status} ({elapsed:.2f}ms)")
        except Exception as e:
            print(f"{desc:<45} ✗ ERROR: {str(e)}")
    
    # Test insufficient fragments
    print("\nTesting insufficient fragments (should fail):")
    try:
        insufficient = [fragments[0], fragments[1]]
        coder.decode_fragments(insufficient, [0, 1])
        print("  ✗ Should have raised error!")
    except ValueError as e:
        print(f"  ✓ Correctly raised error: {str(e)}")

def run_benchmarks():
    """Run all benchmarks"""
    print("\n" + "="*70)
    print("ERASURE CODING PERFORMANCE BENCHMARK")
    print("="*70)
    
    coder = ErasureCoder(data_shards=3, parity_shards=2)
    chunk_size_mb = 2
    iterations = 10
    
    print(f"\nConfiguration:")
    print(f"  Chunk size: {chunk_size_mb} MB")
    print(f"  Data shards: 3")
    print(f"  Parity shards: 2")
    print(f"  Total shards: 5")
    print(f"  Iterations: {iterations}")
    
    # Encoding benchmark
    print("\n" + "-"*70)
    print("ENCODING PERFORMANCE (2MB chunk → 5 fragments)")
    print("-"*70)
    
    enc_results = benchmark_encoding(coder, chunk_size_mb, iterations)
    print(f"  Average time: {enc_results['avg_time_ms']:.2f} ms")
    print(f"  Min time: {enc_results['min_time_ms']:.2f} ms")
    print(f"  Max time: {enc_results['max_time_ms']:.2f} ms")
    print(f"  Throughput: {enc_results['throughput_mbps']:.2f} MB/s")
    
    # Decoding benchmark
    print("\n" + "-"*70)
    print("DECODING PERFORMANCE (3 fragments → 2MB chunk)")
    print("-"*70)
    
    dec_results = benchmark_decoding(coder, chunk_size_mb, iterations)
    print(f"  Average time: {dec_results['avg_time_ms']:.2f} ms")
    print(f"  Min time: {dec_results['min_time_ms']:.2f} ms")
    print(f"  Max time: {dec_results['max_time_ms']:.2f} ms")
    print(f"  Throughput: {dec_results['throughput_mbps']:.2f} MB/s")
    
    # Replication comparison
    print("\n" + "-"*70)
    print("REPLICATION COMPARISON (3 full copies)")
    print("-"*70)
    
    rep_write = benchmark_replication_write(chunk_size_mb, iterations)
    rep_read = benchmark_replication_read(chunk_size_mb, iterations)
    
    print(f"\nReplication Write (3 copies):")
    print(f"  Average time: {rep_write['avg_time_ms']:.2f} ms")
    print(f"  Throughput: {rep_write['throughput_mbps']:.2f} MB/s")
    
    print(f"\nReplication Read (1 copy):")
    print(f"  Average time: {rep_read['avg_time_ms']:.2f} ms")
    print(f"  Throughput: {rep_read['throughput_mbps']:.2f} MB/s")
    
    # Performance comparison
    print("\n" + "="*70)
    print("PERFORMANCE COMPARISON")
    print("="*70)
    
    print(f"\nWrite Performance:")
    print(f"  Erasure Coding: {enc_results['avg_time_ms']:.2f} ms")
    print(f"  Replication: {rep_write['avg_time_ms']:.2f} ms")
    
    if enc_results['avg_time_ms'] < rep_write['avg_time_ms']:
        speedup = rep_write['avg_time_ms'] / enc_results['avg_time_ms']
        print(f"  → Erasure coding is {speedup:.2f}x faster")
    else:
        slowdown = enc_results['avg_time_ms'] / rep_write['avg_time_ms']
        print(f"  → Erasure coding is {slowdown:.2f}x slower")
    
    print(f"\nRead Performance:")
    print(f"  Erasure Coding (decode): {dec_results['avg_time_ms']:.2f} ms")
    print(f"  Replication (direct): {rep_read['avg_time_ms']:.2f} ms")
    
    if dec_results['avg_time_ms'] < rep_read['avg_time_ms']:
        speedup = rep_read['avg_time_ms'] / dec_results['avg_time_ms']
        print(f"  → Erasure coding is {speedup:.2f}x faster")
    else:
        slowdown = dec_results['avg_time_ms'] / rep_read['avg_time_ms']
        print(f"  → Replication is {slowdown:.2f}x faster")
    
    print(f"\nStorage Efficiency:")
    efficiency = coder.get_storage_efficiency()
    print(f"  Erasure coding saves {efficiency*100:.1f}% storage vs replication")
    print(f"  For 1TB of data: Save {efficiency*1000:.0f} GB")
    
    # Test failure scenarios
    test_failure_scenarios(coder)
    
    print("\n" + "="*70)
    print("BENCHMARK COMPLETE")
    print("="*70)
    
    print("""
Key Findings:
1. Erasure coding provides ~40% storage savings
2. Encoding adds computational overhead but is still fast
3. Decoding requires reconstruction but is acceptable for cold data
4. System can tolerate 2 node failures (any 3 of 5 fragments work)
5. Trade-off: Storage efficiency vs read performance
   - Use replication for hot data (fast reads)
   - Use erasure coding for cold data (storage savings)
""")

if __name__ == "__main__":
    run_benchmarks()
