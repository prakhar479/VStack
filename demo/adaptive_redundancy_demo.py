#!/usr/bin/env python3
"""
Adaptive Redundancy Demonstration
Shows storage efficiency benefits of erasure coding vs replication
"""

import sys
import os
import random
from typing import List, Dict

# Add parent directories to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'metadata-service'))

from redundancy_manager import RedundancyManager, RedundancyMode

class StorageSimulator:
    """Simulates storage usage for different redundancy modes"""
    
    def __init__(self):
        self.chunk_size_mb = 2  # 2MB per chunk
        self.videos = []
        self.redundancy_manager = RedundancyManager(popularity_threshold=1000)
    
    def add_video(self, video_id: str, title: str, num_chunks: int, view_count: int):
        """Add a video to the simulation"""
        mode, config = self.redundancy_manager.determine_redundancy_mode(video_id, view_count)
        
        storage_cost = self.redundancy_manager.calculate_storage_cost(
            self.chunk_size_mb * 1024 * 1024,  # Convert to bytes
            mode
        )
        
        total_storage_mb = (storage_cost * num_chunks) / (1024 * 1024)
        
        video = {
            "video_id": video_id,
            "title": title,
            "num_chunks": num_chunks,
            "view_count": view_count,
            "redundancy_mode": mode.value,
            "storage_mb": total_storage_mb
        }
        
        self.videos.append(video)
        return video
    
    def calculate_totals(self) -> Dict:
        """Calculate total storage statistics"""
        total_chunks = sum(v["num_chunks"] for v in self.videos)
        total_storage_mb = sum(v["storage_mb"] for v in self.videos)
        
        replication_videos = [v for v in self.videos if v["redundancy_mode"] == "replication"]
        erasure_videos = [v for v in self.videos if v["redundancy_mode"] == "erasure_coding"]
        
        replication_storage = sum(v["storage_mb"] for v in replication_videos)
        erasure_storage = sum(v["storage_mb"] for v in erasure_videos)
        
        # Calculate what storage would be with full replication
        baseline_storage_mb = total_chunks * self.chunk_size_mb * 3  # 3x replication
        
        savings_mb = baseline_storage_mb - total_storage_mb
        savings_percent = (savings_mb / baseline_storage_mb) * 100 if baseline_storage_mb > 0 else 0
        
        return {
            "total_videos": len(self.videos),
            "total_chunks": total_chunks,
            "replication_videos": len(replication_videos),
            "erasure_coded_videos": len(erasure_videos),
            "total_storage_mb": total_storage_mb,
            "replication_storage_mb": replication_storage,
            "erasure_storage_mb": erasure_storage,
            "baseline_storage_mb": baseline_storage_mb,
            "savings_mb": savings_mb,
            "savings_percent": savings_percent
        }
    
    def print_summary(self):
        """Print storage summary"""
        stats = self.calculate_totals()
        
        print("\n" + "="*70)
        print("ADAPTIVE REDUNDANCY STORAGE ANALYSIS")
        print("="*70)
        
        print(f"\nVideo Statistics:")
        print(f"  Total Videos: {stats['total_videos']}")
        print(f"  Total Chunks: {stats['total_chunks']}")
        print(f"  Hot Videos (Replication): {stats['replication_videos']}")
        print(f"  Cold Videos (Erasure Coding): {stats['erasure_coded_videos']}")
        
        print(f"\nStorage Usage:")
        print(f"  Replication Storage: {stats['replication_storage_mb']:.1f} MB")
        print(f"  Erasure Coding Storage: {stats['erasure_storage_mb']:.1f} MB")
        print(f"  Total Storage Used: {stats['total_storage_mb']:.1f} MB")
        
        print(f"\nStorage Efficiency:")
        print(f"  Baseline (Full Replication): {stats['baseline_storage_mb']:.1f} MB")
        print(f"  Actual Storage: {stats['total_storage_mb']:.1f} MB")
        print(f"  Storage Saved: {stats['savings_mb']:.1f} MB")
        print(f"  Savings Percentage: {stats['savings_percent']:.1f}%")
        
        print("\n" + "="*70)
    
    def print_video_details(self, limit: int = 10):
        """Print details of individual videos"""
        print(f"\nVideo Details (showing {limit} of {len(self.videos)}):")
        print("-" * 70)
        print(f"{'Title':<25} {'Views':<10} {'Mode':<15} {'Storage (MB)':<12}")
        print("-" * 70)
        
        for video in self.videos[:limit]:
            title = video['title'][:24]
            views = video['view_count']
            mode = video['redundancy_mode']
            storage = video['storage_mb']
            
            print(f"{title:<25} {views:<10} {mode:<15} {storage:<12.1f}")


def run_realistic_scenario():
    """Run a realistic video streaming scenario"""
    print("\n" + "="*70)
    print("SCENARIO: Video Streaming Platform with 100 Videos")
    print("="*70)
    
    simulator = StorageSimulator()
    
    # Simulate a realistic distribution of videos
    # Most videos are cold (low views), few are hot (high views)
    
    # 10 hot videos (>1000 views) - will use replication
    hot_videos = [
        ("Viral Cat Video", 50000),
        ("Breaking News", 25000),
        ("Popular Music Video", 15000),
        ("Trending Tutorial", 8000),
        ("Funny Compilation", 5000),
        ("Sports Highlight", 3500),
        ("Movie Trailer", 2800),
        ("Gaming Stream", 2200),
        ("Cooking Show", 1500),
        ("Tech Review", 1200)
    ]
    
    print("\nAdding hot videos (>1000 views)...")
    for i, (title, views) in enumerate(hot_videos):
        num_chunks = random.randint(30, 60)  # 5-10 minute videos
        simulator.add_video(f"hot-{i}", title, num_chunks, views)
    
    # 90 cold videos (<1000 views) - will use erasure coding
    print("Adding cold videos (<1000 views)...")
    cold_titles = [
        "Personal Vlog", "Tutorial", "Review", "Gameplay", "Unboxing",
        "Interview", "Documentary", "Short Film", "Music Cover", "Podcast"
    ]
    
    for i in range(90):
        title = f"{random.choice(cold_titles)} #{i+1}"
        views = random.randint(10, 900)
        num_chunks = random.randint(20, 50)  # 3-8 minute videos
        simulator.add_video(f"cold-{i}", title, num_chunks, views)
    
    # Print results
    simulator.print_summary()
    simulator.print_video_details(limit=15)
    
    # Show mode comparison
    print("\n" + "="*70)
    print("REDUNDANCY MODE COMPARISON")
    print("="*70)
    
    comparison = simulator.redundancy_manager.get_mode_comparison()
    
    print("\nReplication Mode (Hot Videos):")
    rep = comparison['replication']
    print(f"  Storage per chunk: {rep['storage_per_chunk_mb']:.1f} MB")
    print(f"  Nodes required: {rep['nodes_required']}")
    print(f"  Failures tolerated: {rep['failures_tolerated']}")
    print(f"  Read performance: {rep['read_performance']}")
    print(f"  Use case: {rep['use_case']}")
    
    print("\nErasure Coding Mode (Cold Videos):")
    ec = comparison['erasure_coding']
    print(f"  Storage per chunk: {ec['storage_per_chunk_mb']:.1f} MB")
    print(f"  Nodes required: {ec['nodes_required']}")
    print(f"  Failures tolerated: {ec['failures_tolerated']}")
    print(f"  Read performance: {ec['read_performance']}")
    print(f"  Use case: {ec['use_case']}")
    
    print("\nStorage Savings:")
    savings = comparison['savings']
    print(f"  Storage saved per chunk: {savings['storage_saved_mb']:.1f} MB")
    print(f"  Savings percentage: {savings['savings_percent']:.1f}%")
    
    print("\n" + "="*70)


def run_comparison_demo():
    """Compare full replication vs adaptive redundancy"""
    print("\n" + "="*70)
    print("COMPARISON: Full Replication vs Adaptive Redundancy")
    print("="*70)
    
    # Scenario: 1000 videos, 50 chunks each
    num_videos = 1000
    chunks_per_video = 50
    chunk_size_mb = 2
    
    # Assume 5% are hot (>1000 views), 95% are cold
    hot_videos = int(num_videos * 0.05)
    cold_videos = num_videos - hot_videos
    
    total_chunks = num_videos * chunks_per_video
    
    # Full replication: 3 copies of everything
    full_replication_mb = total_chunks * chunk_size_mb * 3
    
    # Adaptive redundancy:
    # Hot videos: 3 copies
    # Cold videos: 5/3 copies (erasure coding)
    hot_storage_mb = (hot_videos * chunks_per_video) * chunk_size_mb * 3
    cold_storage_mb = (cold_videos * chunks_per_video) * chunk_size_mb * (5/3)
    adaptive_total_mb = hot_storage_mb + cold_storage_mb
    
    savings_mb = full_replication_mb - adaptive_total_mb
    savings_percent = (savings_mb / full_replication_mb) * 100
    
    print(f"\nScenario: {num_videos} videos, {chunks_per_video} chunks each")
    print(f"  Hot videos (5%): {hot_videos}")
    print(f"  Cold videos (95%): {cold_videos}")
    print(f"  Total chunks: {total_chunks:,}")
    
    print(f"\nFull Replication (3 copies):")
    print(f"  Total storage: {full_replication_mb:,.1f} MB ({full_replication_mb/1024:.1f} GB)")
    
    print(f"\nAdaptive Redundancy:")
    print(f"  Hot video storage: {hot_storage_mb:,.1f} MB")
    print(f"  Cold video storage: {cold_storage_mb:,.1f} MB")
    print(f"  Total storage: {adaptive_total_mb:,.1f} MB ({adaptive_total_mb/1024:.1f} GB)")
    
    print(f"\nStorage Savings:")
    print(f"  Saved: {savings_mb:,.1f} MB ({savings_mb/1024:.1f} GB)")
    print(f"  Percentage: {savings_percent:.1f}%")
    
    print("\n" + "="*70)


def main():
    """Main demonstration"""
    print("\n" + "="*70)
    print("V-STACK ADAPTIVE REDUNDANCY DEMONSTRATION")
    print("Showing 40% storage savings with erasure coding")
    print("="*70)
    
    # Run realistic scenario
    run_realistic_scenario()
    
    # Run comparison
    run_comparison_demo()
    
    print("\n" + "="*70)
    print("KEY TAKEAWAYS")
    print("="*70)
    print("""
1. Hot videos (>1000 views) use replication for fast reads
   - 3 full copies stored
   - Optimal for frequently accessed content
   
2. Cold videos (≤1000 views) use erasure coding for storage efficiency
   - 5 fragments stored, any 3 can recover original
   - Saves ~40% storage compared to full replication
   
3. Adaptive selection based on popularity
   - Automatically chooses best mode for each video
   - Can manually override for specific videos
   
4. Real-world impact
   - For 1000 videos: Save ~40GB of storage
   - For 10,000 videos: Save ~400GB of storage
   - Scales linearly with content library size
""")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
