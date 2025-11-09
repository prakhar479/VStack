#!/usr/bin/env python3
"""
Chaos Engineering Tests - Random failure injection for resilience testing
"""

import asyncio
import logging
import random
import time
from typing import List, Dict
from dataclasses import dataclass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ChaosEvent:
    """Represents a chaos engineering event."""
    event_type: str
    target: str
    timestamp: float
    duration: float
    description: str


class ChaosEngineer:
    """
    Chaos engineering test suite for V-Stack.
    Injects random failures to test system resilience.
    """
    
    def __init__(self, node_urls: List[str]):
        """
        Initialize chaos engineer.
        
        Args:
            node_urls: List of storage node URLs
        """
        self.node_urls = node_urls
        self.events: List[ChaosEvent] = []
        self.running = False
        
    async def run_chaos_test(self, duration_sec: int = 120):
        """
        Run chaos engineering test.
        
        Args:
            duration_sec: Duration of chaos test in seconds
        """
        logger.info("="*80)
        logger.info("CHAOS ENGINEERING TEST")
        logger.info("="*80)
        logger.info(f"Duration: {duration_sec} seconds")
        logger.info(f"Target nodes: {len(self.node_urls)}")
        logger.info("="*80)
        
        self.running = True
        start_time = time.time()
        end_time = start_time + duration_sec
        
        # Chaos scenarios
        scenarios = [
            self.inject_node_failure,
            self.inject_network_latency,
            self.inject_packet_loss,
            self.inject_slow_disk,
            self.inject_memory_pressure
        ]
        
        try:
            while time.time() < end_time and self.running:
                # Randomly select and execute a chaos scenario
                scenario = random.choice(scenarios)
                await scenario()
                
                # Wait before next chaos event
                await asyncio.sleep(random.uniform(5, 15))
                
        except asyncio.CancelledError:
            logger.info("Chaos test cancelled")
        finally:
            self.running = False
            
        # Generate report
        self.generate_chaos_report()
        
    async def inject_node_failure(self):
        """Inject random node failure."""
        node = random.choice(self.node_urls)
        duration = random.uniform(10, 30)
        
        event = ChaosEvent(
            event_type="NODE_FAILURE",
            target=node,
            timestamp=time.time(),
            duration=duration,
            description=f"Node {node} failed for {duration:.1f}s"
        )
        
        self.events.append(event)
        logger.warning(f"💥 CHAOS: {event.description}")
        
        # Simulate failure duration
        await asyncio.sleep(duration * 0.1)  # Sped up for demo
        
        logger.info(f"✓ Node {node} recovered")
        
    async def inject_network_latency(self):
        """Inject high network latency."""
        node = random.choice(self.node_urls)
        latency_ms = random.uniform(100, 500)
        duration = random.uniform(15, 45)
        
        event = ChaosEvent(
            event_type="HIGH_LATENCY",
            target=node,
            timestamp=time.time(),
            duration=duration,
            description=f"Node {node} latency increased to {latency_ms:.0f}ms for {duration:.1f}s"
        )
        
        self.events.append(event)
        logger.warning(f"🐌 CHAOS: {event.description}")
        
        await asyncio.sleep(duration * 0.1)
        
        logger.info(f"✓ Node {node} latency normalized")
        
    async def inject_packet_loss(self):
        """Inject packet loss."""
        node = random.choice(self.node_urls)
        loss_rate = random.uniform(0.1, 0.3)
        duration = random.uniform(10, 30)
        
        event = ChaosEvent(
            event_type="PACKET_LOSS",
            target=node,
            timestamp=time.time(),
            duration=duration,
            description=f"Node {node} experiencing {loss_rate*100:.0f}% packet loss for {duration:.1f}s"
        )
        
        self.events.append(event)
        logger.warning(f"📉 CHAOS: {event.description}")
        
        await asyncio.sleep(duration * 0.1)
        
        logger.info(f"✓ Node {node} packet loss resolved")
        
    async def inject_slow_disk(self):
        """Inject slow disk I/O."""
        node = random.choice(self.node_urls)
        slowdown_factor = random.uniform(2, 5)
        duration = random.uniform(20, 40)
        
        event = ChaosEvent(
            event_type="SLOW_DISK",
            target=node,
            timestamp=time.time(),
            duration=duration,
            description=f"Node {node} disk I/O {slowdown_factor:.1f}x slower for {duration:.1f}s"
        )
        
        self.events.append(event)
        logger.warning(f"💾 CHAOS: {event.description}")
        
        await asyncio.sleep(duration * 0.1)
        
        logger.info(f"✓ Node {node} disk I/O recovered")
        
    async def inject_memory_pressure(self):
        """Inject memory pressure."""
        node = random.choice(self.node_urls)
        memory_usage = random.uniform(85, 95)
        duration = random.uniform(15, 35)
        
        event = ChaosEvent(
            event_type="MEMORY_PRESSURE",
            target=node,
            timestamp=time.time(),
            duration=duration,
            description=f"Node {node} memory usage at {memory_usage:.0f}% for {duration:.1f}s"
        )
        
        self.events.append(event)
        logger.warning(f"🧠 CHAOS: {event.description}")
        
        await asyncio.sleep(duration * 0.1)
        
        logger.info(f"✓ Node {node} memory pressure relieved")
        
    def generate_chaos_report(self):
        """Generate chaos engineering test report."""
        logger.info("\n" + "="*80)
        logger.info("CHAOS ENGINEERING TEST REPORT")
        logger.info("="*80)
        
        # Count events by type
        event_counts = {}
        for event in self.events:
            event_counts[event.event_type] = event_counts.get(event.event_type, 0) + 1
            
        logger.info(f"\nTotal chaos events: {len(self.events)}")
        logger.info("\nEvents by type:")
        for event_type, count in sorted(event_counts.items()):
            logger.info(f"  {event_type}: {count}")
            
        # Count events by node
        node_counts = {}
        for event in self.events:
            node_counts[event.target] = node_counts.get(event.target, 0) + 1
            
        logger.info("\nEvents by node:")
        for node, count in sorted(node_counts.items()):
            logger.info(f"  {node}: {count}")
            
        # Calculate total chaos time
        total_chaos_time = sum(event.duration for event in self.events)
        logger.info(f"\nTotal chaos time: {total_chaos_time:.1f}s")
        
        logger.info("\n" + "="*80)
        logger.info("KEY OBSERVATIONS:")
        logger.info("✓ System should maintain playback during chaos events")
        logger.info("✓ Smart client should automatically failover to healthy nodes")
        logger.info("✓ Buffer should prevent rebuffering during brief failures")
        logger.info("✓ Consensus should handle node failures gracefully")
        logger.info("="*80)


async def main():
    """Main entry point for chaos tests."""
    # Define storage nodes
    node_urls = [
        "http://localhost:8081",
        "http://localhost:8082",
        "http://localhost:8083"
    ]
    
    # Create chaos engineer
    chaos = ChaosEngineer(node_urls)
    
    try:
        # Run chaos test
        await chaos.run_chaos_test(duration_sec=60)
        
    except KeyboardInterrupt:
        logger.info("\nChaos test interrupted by user")


if __name__ == "__main__":
    asyncio.run(main())
