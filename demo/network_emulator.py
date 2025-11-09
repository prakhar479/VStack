#!/usr/bin/env python3
"""
Network Emulator - Simulates various network conditions for demonstration
"""

import asyncio
import logging
import random
import time
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NetworkCondition(Enum):
    """Network condition scenarios."""
    NORMAL = "normal"
    HIGH_LATENCY = "high_latency"
    LOW_BANDWIDTH = "low_bandwidth"
    PACKET_LOSS = "packet_loss"
    NODE_FAILURE = "node_failure"
    DEGRADED = "degraded"
    RECOVERY = "recovery"


@dataclass
class NetworkProfile:
    """Network profile configuration."""
    name: str
    latency_ms: float  # Base latency
    latency_variance_ms: float  # Random variance
    bandwidth_mbps: float  # Available bandwidth
    packet_loss_rate: float  # 0.0 to 1.0
    failure_rate: float  # 0.0 to 1.0 (probability of complete failure)
    
    
class NetworkEmulator:
    """
    Emulates various network conditions for demonstration purposes.
    Can inject latency, bandwidth limitations, packet loss, and node failures.
    """
    
    # Predefined network profiles
    PROFILES = {
        NetworkCondition.NORMAL: NetworkProfile(
            name="Normal",
            latency_ms=20.0,
            latency_variance_ms=5.0,
            bandwidth_mbps=50.0,
            packet_loss_rate=0.0,
            failure_rate=0.0
        ),
        NetworkCondition.HIGH_LATENCY: NetworkProfile(
            name="High Latency",
            latency_ms=150.0,
            latency_variance_ms=50.0,
            bandwidth_mbps=50.0,
            packet_loss_rate=0.05,
            failure_rate=0.0
        ),
        NetworkCondition.LOW_BANDWIDTH: NetworkProfile(
            name="Low Bandwidth",
            latency_ms=20.0,
            latency_variance_ms=5.0,
            bandwidth_mbps=10.0,
            packet_loss_rate=0.0,
            failure_rate=0.0
        ),
        NetworkCondition.PACKET_LOSS: NetworkProfile(
            name="Packet Loss",
            latency_ms=30.0,
            latency_variance_ms=10.0,
            bandwidth_mbps=40.0,
            packet_loss_rate=0.15,
            failure_rate=0.0
        ),
        NetworkCondition.NODE_FAILURE: NetworkProfile(
            name="Node Failure",
            latency_ms=0.0,
            latency_variance_ms=0.0,
            bandwidth_mbps=0.0,
            packet_loss_rate=1.0,
            failure_rate=1.0
        ),
        NetworkCondition.DEGRADED: NetworkProfile(
            name="Degraded",
            latency_ms=100.0,
            latency_variance_ms=30.0,
            bandwidth_mbps=20.0,
            packet_loss_rate=0.10,
            failure_rate=0.05
        ),
        NetworkCondition.RECOVERY: NetworkProfile(
            name="Recovery",
            latency_ms=50.0,
            latency_variance_ms=20.0,
            bandwidth_mbps=35.0,
            packet_loss_rate=0.02,
            failure_rate=0.0
        )
    }
    
    def __init__(self):
        """Initialize network emulator."""
        self.node_conditions = {}  # node_url -> NetworkCondition
        self.node_profiles = {}  # node_url -> NetworkProfile
        self.active = False
        
    def set_node_condition(self, node_url: str, condition: NetworkCondition):
        """
        Set network condition for a specific node.
        
        Args:
            node_url: URL of the storage node
            condition: Network condition to apply
        """
        self.node_conditions[node_url] = condition
        self.node_profiles[node_url] = self.PROFILES[condition]
        logger.info(f"Set {node_url} to {condition.value} condition")
        
    def set_all_nodes_condition(self, node_urls: List[str], condition: NetworkCondition):
        """
        Set network condition for all nodes.
        
        Args:
            node_urls: List of node URLs
            condition: Network condition to apply
        """
        for node_url in node_urls:
            self.set_node_condition(node_url, condition)
            
    def get_simulated_latency(self, node_url: str) -> float:
        """
        Get simulated latency for a node in milliseconds.
        
        Args:
            node_url: URL of the storage node
            
        Returns:
            Simulated latency in milliseconds
        """
        if node_url not in self.node_profiles:
            return 20.0  # Default latency
            
        profile = self.node_profiles[node_url]
        
        # Add random variance
        variance = random.uniform(-profile.latency_variance_ms, profile.latency_variance_ms)
        latency = max(0, profile.latency_ms + variance)
        
        return latency
        
    def get_simulated_bandwidth(self, node_url: str) -> float:
        """
        Get simulated bandwidth for a node in Mbps.
        
        Args:
            node_url: URL of the storage node
            
        Returns:
            Simulated bandwidth in Mbps
        """
        if node_url not in self.node_profiles:
            return 50.0  # Default bandwidth
            
        profile = self.node_profiles[node_url]
        
        # Add some random variation (±10%)
        variation = random.uniform(0.9, 1.1)
        bandwidth = profile.bandwidth_mbps * variation
        
        return max(0, bandwidth)
        
    def should_drop_packet(self, node_url: str) -> bool:
        """
        Determine if a packet should be dropped (simulating packet loss).
        
        Args:
            node_url: URL of the storage node
            
        Returns:
            True if packet should be dropped
        """
        if node_url not in self.node_profiles:
            return False
            
        profile = self.node_profiles[node_url]
        return random.random() < profile.packet_loss_rate
        
    def should_fail(self, node_url: str) -> bool:
        """
        Determine if a node should fail completely.
        
        Args:
            node_url: URL of the storage node
            
        Returns:
            True if node should fail
        """
        if node_url not in self.node_profiles:
            return False
            
        profile = self.node_profiles[node_url]
        return random.random() < profile.failure_rate
        
    async def apply_network_delay(self, node_url: str):
        """
        Apply simulated network delay.
        
        Args:
            node_url: URL of the storage node
        """
        latency = self.get_simulated_latency(node_url)
        await asyncio.sleep(latency / 1000.0)  # Convert ms to seconds
        
    def get_node_status(self, node_url: str) -> Dict:
        """
        Get current network status for a node.
        
        Args:
            node_url: URL of the storage node
            
        Returns:
            Dictionary with node network status
        """
        if node_url not in self.node_profiles:
            return {
                'condition': 'normal',
                'latency_ms': 20.0,
                'bandwidth_mbps': 50.0,
                'packet_loss_rate': 0.0,
                'is_healthy': True
            }
            
        profile = self.node_profiles[node_url]
        condition = self.node_conditions[node_url]
        
        return {
            'condition': condition.value,
            'profile_name': profile.name,
            'latency_ms': profile.latency_ms,
            'bandwidth_mbps': profile.bandwidth_mbps,
            'packet_loss_rate': profile.packet_loss_rate,
            'failure_rate': profile.failure_rate,
            'is_healthy': condition != NetworkCondition.NODE_FAILURE
        }
        
    def get_all_status(self) -> Dict[str, Dict]:
        """
        Get network status for all nodes.
        
        Returns:
            Dictionary mapping node URLs to their status
        """
        return {
            node_url: self.get_node_status(node_url)
            for node_url in self.node_conditions.keys()
        }


class DemoScenario:
    """Demonstration scenario that changes network conditions over time."""
    
    def __init__(self, emulator: NetworkEmulator, node_urls: List[str]):
        """
        Initialize demo scenario.
        
        Args:
            emulator: NetworkEmulator instance
            node_urls: List of storage node URLs
        """
        self.emulator = emulator
        self.node_urls = node_urls
        self.running = False
        
    async def run_normal_operation(self, duration_sec: int = 30):
        """
        Scenario: Normal operation with good network conditions.
        
        Args:
            duration_sec: Duration to run scenario
        """
        logger.info("=== SCENARIO: Normal Operation ===")
        logger.info("All nodes operating under normal network conditions")
        
        self.emulator.set_all_nodes_condition(self.node_urls, NetworkCondition.NORMAL)
        
        await asyncio.sleep(duration_sec)
        
    async def run_network_degradation(self, duration_sec: int = 30):
        """
        Scenario: Network degradation affecting all nodes.
        
        Args:
            duration_sec: Duration to run scenario
        """
        logger.info("=== SCENARIO: Network Degradation ===")
        logger.info("Network conditions degrading across all nodes")
        
        # Start with normal
        self.emulator.set_all_nodes_condition(self.node_urls, NetworkCondition.NORMAL)
        await asyncio.sleep(5)
        
        # Gradually degrade
        logger.info("Introducing high latency...")
        self.emulator.set_all_nodes_condition(self.node_urls, NetworkCondition.HIGH_LATENCY)
        await asyncio.sleep(10)
        
        logger.info("Reducing bandwidth...")
        self.emulator.set_all_nodes_condition(self.node_urls, NetworkCondition.LOW_BANDWIDTH)
        await asyncio.sleep(10)
        
        logger.info("Adding packet loss...")
        self.emulator.set_all_nodes_condition(self.node_urls, NetworkCondition.PACKET_LOSS)
        await asyncio.sleep(duration_sec - 25)
        
    async def run_node_failure(self, duration_sec: int = 30):
        """
        Scenario: Single node failure with automatic failover.
        
        Args:
            duration_sec: Duration to run scenario
        """
        logger.info("=== SCENARIO: Node Failure ===")
        logger.info("Simulating failure of one storage node")
        
        # Start with normal
        self.emulator.set_all_nodes_condition(self.node_urls, NetworkCondition.NORMAL)
        await asyncio.sleep(5)
        
        # Fail one node
        if len(self.node_urls) > 0:
            failed_node = self.node_urls[0]
            logger.info(f"Failing node: {failed_node}")
            self.emulator.set_node_condition(failed_node, NetworkCondition.NODE_FAILURE)
            await asyncio.sleep(duration_sec - 5)
            
    async def run_recovery(self, duration_sec: int = 30):
        """
        Scenario: Recovery from degraded conditions.
        
        Args:
            duration_sec: Duration to run scenario
        """
        logger.info("=== SCENARIO: Recovery ===")
        logger.info("Recovering from degraded network conditions")
        
        # Start degraded
        self.emulator.set_all_nodes_condition(self.node_urls, NetworkCondition.DEGRADED)
        await asyncio.sleep(10)
        
        # Begin recovery
        logger.info("Network conditions improving...")
        self.emulator.set_all_nodes_condition(self.node_urls, NetworkCondition.RECOVERY)
        await asyncio.sleep(10)
        
        # Return to normal
        logger.info("Returning to normal operation...")
        self.emulator.set_all_nodes_condition(self.node_urls, NetworkCondition.NORMAL)
        await asyncio.sleep(duration_sec - 20)
        
    async def run_chaos_test(self, duration_sec: int = 60):
        """
        Scenario: Chaos engineering test with random failures.
        
        Args:
            duration_sec: Duration to run scenario
        """
        logger.info("=== SCENARIO: Chaos Test ===")
        logger.info("Random network conditions and node failures")
        
        conditions = [
            NetworkCondition.NORMAL,
            NetworkCondition.HIGH_LATENCY,
            NetworkCondition.LOW_BANDWIDTH,
            NetworkCondition.PACKET_LOSS,
            NetworkCondition.DEGRADED
        ]
        
        end_time = time.time() + duration_sec
        
        while time.time() < end_time:
            # Randomly change conditions for each node
            for node_url in self.node_urls:
                condition = random.choice(conditions)
                self.emulator.set_node_condition(node_url, condition)
                
            logger.info(f"Applied random conditions: {[self.emulator.node_conditions[n].value for n in self.node_urls]}")
            
            # Wait before next change
            await asyncio.sleep(random.uniform(5, 15))
            
    async def run_full_demo(self):
        """Run complete demonstration sequence."""
        logger.info("="*60)
        logger.info("STARTING FULL DEMONSTRATION SEQUENCE")
        logger.info("="*60)
        
        self.running = True
        
        try:
            # Scenario 1: Normal operation
            await self.run_normal_operation(duration_sec=20)
            
            # Scenario 2: Network degradation
            await self.run_network_degradation(duration_sec=30)
            
            # Scenario 3: Node failure
            await self.run_node_failure(duration_sec=30)
            
            # Scenario 4: Recovery
            await self.run_recovery(duration_sec=30)
            
            # Scenario 5: Chaos test
            await self.run_chaos_test(duration_sec=40)
            
            logger.info("="*60)
            logger.info("DEMONSTRATION COMPLETE")
            logger.info("="*60)
            
        except asyncio.CancelledError:
            logger.info("Demonstration cancelled")
        finally:
            self.running = False
            # Reset to normal
            self.emulator.set_all_nodes_condition(self.node_urls, NetworkCondition.NORMAL)


async def main():
    """Main entry point for network emulator demo."""
    # Example usage
    emulator = NetworkEmulator()
    
    # Define storage nodes
    node_urls = [
        "http://localhost:8081",
        "http://localhost:8082",
        "http://localhost:8083"
    ]
    
    # Create and run demo scenario
    scenario = DemoScenario(emulator, node_urls)
    
    try:
        await scenario.run_full_demo()
    except KeyboardInterrupt:
        logger.info("Demo interrupted by user")


if __name__ == "__main__":
    asyncio.run(main())
