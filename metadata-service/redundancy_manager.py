#!/usr/bin/env python3
"""
Redundancy Manager for adaptive redundancy selection
Determines whether to use replication or erasure coding based on video popularity
"""

import logging
from typing import Tuple, Optional
from enum import Enum

logger = logging.getLogger(__name__)

class RedundancyMode(str, Enum):
    REPLICATION = "replication"
    ERASURE_CODING = "erasure_coding"

class RedundancyManager:
    """
    Manages adaptive redundancy selection based on video popularity
    
    Strategy:
    - Hot videos (>1000 views): Use replication for fast reads
    - Cold videos (<=1000 views): Use erasure coding for storage savings
    """
    
    def __init__(self, popularity_threshold: int = 1000, 
                 replication_factor: int = 3,
                 erasure_data_shards: int = 3,
                 erasure_parity_shards: int = 2):
        """
        Initialize redundancy manager
        
        Args:
            popularity_threshold: View count threshold for hot vs cold videos
            replication_factor: Number of full copies for replication mode
            erasure_data_shards: Number of data fragments for erasure coding
            erasure_parity_shards: Number of parity fragments for erasure coding
        """
        self.popularity_threshold = popularity_threshold
        self.replication_factor = replication_factor
        self.erasure_data_shards = erasure_data_shards
        self.erasure_parity_shards = erasure_parity_shards
        self.erasure_total_shards = erasure_data_shards + erasure_parity_shards
        
        # Manual override settings
        self.manual_overrides = {}  # video_id -> RedundancyMode
        
        logger.info(f"Redundancy manager initialized: threshold={popularity_threshold} views")
        logger.info(f"Replication: {replication_factor} copies")
        logger.info(f"Erasure coding: {erasure_data_shards}+{erasure_parity_shards} shards")
    
    def determine_redundancy_mode(self, video_id: str, view_count: int, 
                                 manual_override: Optional[str] = None) -> Tuple[RedundancyMode, dict]:
        """
        Determine redundancy mode for a video based on popularity
        
        Args:
            video_id: Video identifier
            view_count: Current view count
            manual_override: Optional manual mode selection ("replication" or "erasure_coding")
            
        Returns:
            Tuple of (RedundancyMode, config_dict)
        """
        # Check for manual override
        if manual_override:
            mode = RedundancyMode(manual_override)
            self.manual_overrides[video_id] = mode
            logger.info(f"Manual override for {video_id}: {mode.value}")
        elif video_id in self.manual_overrides:
            mode = self.manual_overrides[video_id]
            logger.info(f"Using stored override for {video_id}: {mode.value}")
        else:
            # Automatic selection based on popularity
            if view_count > self.popularity_threshold:
                mode = RedundancyMode.REPLICATION
                logger.info(f"Hot video {video_id} ({view_count} views): using replication")
            else:
                mode = RedundancyMode.ERASURE_CODING
                logger.info(f"Cold video {video_id} ({view_count} views): using erasure coding")
        
        # Generate configuration
        if mode == RedundancyMode.REPLICATION:
            config = {
                "mode": mode.value,
                "copies": self.replication_factor,
                "description": f"Store {self.replication_factor} full copies"
            }
        else:
            config = {
                "mode": mode.value,
                "data_shards": self.erasure_data_shards,
                "parity_shards": self.erasure_parity_shards,
                "total_shards": self.erasure_total_shards,
                "min_shards_for_recovery": self.erasure_data_shards,
                "description": f"Store {self.erasure_total_shards} fragments, any {self.erasure_data_shards} can recover"
            }
        
        return mode, config
    
    def set_manual_override(self, video_id: str, mode: RedundancyMode):
        """Set manual redundancy mode override for a video"""
        self.manual_overrides[video_id] = mode
        logger.info(f"Set manual override for {video_id}: {mode.value}")
    
    def clear_manual_override(self, video_id: str):
        """Clear manual redundancy mode override for a video"""
        if video_id in self.manual_overrides:
            del self.manual_overrides[video_id]
            logger.info(f"Cleared manual override for {video_id}")
    
    def get_storage_efficiency(self) -> dict:
        """
        Calculate storage efficiency metrics
        
        Returns:
            Dictionary with efficiency metrics
        """
        # Replication storage overhead
        replication_overhead = self.replication_factor  # 3x storage
        
        # Erasure coding storage overhead
        erasure_overhead = self.erasure_total_shards / self.erasure_data_shards  # 5/3 = 1.67x storage
        
        # Savings compared to full replication
        savings_percent = ((replication_overhead - erasure_overhead) / replication_overhead) * 100
        
        return {
            "replication_overhead_factor": replication_overhead,
            "erasure_coding_overhead_factor": erasure_overhead,
            "storage_savings_percent": savings_percent,
            "description": f"Erasure coding saves {savings_percent:.1f}% storage vs replication"
        }
    
    def calculate_storage_cost(self, chunk_size_bytes: int, mode: RedundancyMode) -> int:
        """
        Calculate total storage cost for a chunk
        
        Args:
            chunk_size_bytes: Size of original chunk
            mode: Redundancy mode
            
        Returns:
            Total storage bytes required
        """
        if mode == RedundancyMode.REPLICATION:
            return chunk_size_bytes * self.replication_factor
        else:
            # Erasure coding: total_shards / data_shards
            return int(chunk_size_bytes * (self.erasure_total_shards / self.erasure_data_shards))
    
    def get_required_nodes(self, mode: RedundancyMode) -> int:
        """
        Get number of storage nodes required for a mode
        
        Args:
            mode: Redundancy mode
            
        Returns:
            Number of nodes required
        """
        if mode == RedundancyMode.REPLICATION:
            return self.replication_factor
        else:
            return self.erasure_total_shards
    
    def can_tolerate_failures(self, mode: RedundancyMode) -> int:
        """
        Get number of node failures that can be tolerated
        
        Args:
            mode: Redundancy mode
            
        Returns:
            Number of failures tolerable
        """
        if mode == RedundancyMode.REPLICATION:
            # Can lose (replication_factor - 1) nodes
            return self.replication_factor - 1
        else:
            # Can lose (total_shards - data_shards) nodes
            return self.erasure_parity_shards
    
    def get_mode_comparison(self) -> dict:
        """
        Get comparison between replication and erasure coding modes
        
        Returns:
            Dictionary with mode comparison
        """
        chunk_size = 2 * 1024 * 1024  # 2MB
        
        replication_storage = self.calculate_storage_cost(chunk_size, RedundancyMode.REPLICATION)
        erasure_storage = self.calculate_storage_cost(chunk_size, RedundancyMode.ERASURE_CODING)
        
        return {
            "replication": {
                "mode": "replication",
                "storage_per_chunk_mb": replication_storage / (1024 * 1024),
                "nodes_required": self.get_required_nodes(RedundancyMode.REPLICATION),
                "failures_tolerated": self.can_tolerate_failures(RedundancyMode.REPLICATION),
                "read_performance": "fast",
                "use_case": "Hot videos with high view counts"
            },
            "erasure_coding": {
                "mode": "erasure_coding",
                "storage_per_chunk_mb": erasure_storage / (1024 * 1024),
                "nodes_required": self.get_required_nodes(RedundancyMode.ERASURE_CODING),
                "failures_tolerated": self.can_tolerate_failures(RedundancyMode.ERASURE_CODING),
                "read_performance": "moderate (requires reconstruction)",
                "use_case": "Cold videos with low view counts"
            },
            "savings": {
                "storage_saved_mb": (replication_storage - erasure_storage) / (1024 * 1024),
                "savings_percent": ((replication_storage - erasure_storage) / replication_storage) * 100
            }
        }


class RedundancyPolicy:
    """
    Policy engine for redundancy decisions
    Supports different policies beyond simple popularity threshold
    """
    
    def __init__(self, manager: RedundancyManager):
        self.manager = manager
    
    def evaluate_policy(self, video_id: str, video_metadata: dict) -> Tuple[RedundancyMode, dict]:
        """
        Evaluate redundancy policy based on video metadata
        
        Args:
            video_id: Video identifier
            video_metadata: Dictionary with video metadata (view_count, size, age, etc.)
            
        Returns:
            Tuple of (RedundancyMode, config_dict)
        """
        view_count = video_metadata.get("view_count", 0)
        manual_override = video_metadata.get("redundancy_override")
        
        # Future policies could consider:
        # - Video age (newer videos might be more popular)
        # - Video size (larger videos might benefit more from erasure coding)
        # - Storage capacity (switch to erasure coding when running low)
        # - Time of day (different modes for peak vs off-peak)
        
        return self.manager.determine_redundancy_mode(video_id, view_count, manual_override)
    
    def recommend_migration(self, video_id: str, current_mode: RedundancyMode, 
                          current_views: int, view_trend: str) -> Optional[RedundancyMode]:
        """
        Recommend migration to different redundancy mode based on trends
        
        Args:
            video_id: Video identifier
            current_mode: Current redundancy mode
            current_views: Current view count
            view_trend: Trend indicator ("increasing", "decreasing", "stable")
            
        Returns:
            Recommended mode or None if no change needed
        """
        threshold = self.manager.popularity_threshold
        
        # Video becoming popular - migrate to replication
        if (current_mode == RedundancyMode.ERASURE_CODING and 
            current_views > threshold and 
            view_trend == "increasing"):
            logger.info(f"Recommend migrating {video_id} to replication (views: {current_views}, trend: {view_trend})")
            return RedundancyMode.REPLICATION
        
        # Video becoming cold - migrate to erasure coding
        if (current_mode == RedundancyMode.REPLICATION and 
            current_views < threshold * 0.5 and  # 50% below threshold
            view_trend == "decreasing"):
            logger.info(f"Recommend migrating {video_id} to erasure coding (views: {current_views}, trend: {view_trend})")
            return RedundancyMode.ERASURE_CODING
        
        return None
