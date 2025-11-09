"""
Shared configuration module for V-Stack distributed video storage system.
Provides environment-based configuration and service discovery.
"""

import os
import logging
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class ServiceConfig:
    """Base configuration for all services"""
    port: int
    log_level: str
    
    def __post_init__(self):
        """Setup logging after initialization"""
        self.setup_logging()
    
    def setup_logging(self):
        """Configure logging based on log level"""
        numeric_level = getattr(logging, self.log_level.upper(), logging.INFO)
        logging.basicConfig(
            level=numeric_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )


@dataclass
class MetadataServiceConfig(ServiceConfig):
    """Configuration for Metadata Service"""
    database_url: str
    heartbeat_interval: int
    node_timeout: int
    storage_nodes: List[str]
    
    @classmethod
    def from_env(cls) -> 'MetadataServiceConfig':
        """Load configuration from environment variables"""
        storage_nodes_str = os.getenv('STORAGE_NODES', '')
        storage_nodes = [node.strip() for node in storage_nodes_str.split(',') if node.strip()]
        
        return cls(
            port=int(os.getenv('PORT', '8080')),
            log_level=os.getenv('LOG_LEVEL', 'INFO'),
            database_url=os.getenv('DATABASE_URL', '/data/metadata.db'),
            heartbeat_interval=int(os.getenv('HEARTBEAT_INTERVAL', '10')),
            node_timeout=int(os.getenv('NODE_TIMEOUT', '30')),
            storage_nodes=storage_nodes
        )


@dataclass
class StorageNodeConfig(ServiceConfig):
    """Configuration for Storage Node"""
    node_id: str
    node_url: str
    data_dir: str
    metadata_service_url: str
    max_superblock_size: int
    
    @classmethod
    def from_env(cls) -> 'StorageNodeConfig':
        """Load configuration from environment variables"""
        return cls(
            port=int(os.getenv('PORT', '8081')),
            log_level=os.getenv('LOG_LEVEL', 'INFO'),
            node_id=os.getenv('NODE_ID', 'storage-node-1'),
            node_url=os.getenv('NODE_URL', 'http://localhost:8081'),
            data_dir=os.getenv('DATA_DIR', '/data'),
            metadata_service_url=os.getenv('METADATA_SERVICE_URL', 'http://localhost:8080'),
            max_superblock_size=int(os.getenv('MAX_SUPERBLOCK_SIZE', '1073741824'))
        )


@dataclass
class UploaderServiceConfig(ServiceConfig):
    """Configuration for Uploader Service"""
    metadata_service_url: str
    storage_nodes: List[str]
    chunk_size: int
    chunk_duration: int
    max_concurrent_uploads: int
    temp_dir: str
    
    @classmethod
    def from_env(cls) -> 'UploaderServiceConfig':
        """Load configuration from environment variables"""
        storage_nodes_str = os.getenv('STORAGE_NODES', '')
        storage_nodes = [node.strip() for node in storage_nodes_str.split(',') if node.strip()]
        
        return cls(
            port=int(os.getenv('PORT', '8082')),
            log_level=os.getenv('LOG_LEVEL', 'INFO'),
            metadata_service_url=os.getenv('METADATA_SERVICE_URL', 'http://localhost:8080'),
            storage_nodes=storage_nodes,
            chunk_size=int(os.getenv('CHUNK_SIZE', '2097152')),
            chunk_duration=int(os.getenv('CHUNK_DURATION', '10')),
            max_concurrent_uploads=int(os.getenv('MAX_CONCURRENT_UPLOADS', '5')),
            temp_dir=os.getenv('TEMP_DIR', '/tmp/uploads')
        )


@dataclass
class SmartClientConfig(ServiceConfig):
    """Configuration for Smart Client"""
    metadata_service_url: str
    storage_nodes: List[str]
    monitoring_interval: int
    target_buffer_sec: int
    low_water_mark_sec: int
    max_concurrent_downloads: int
    
    @classmethod
    def from_env(cls) -> 'SmartClientConfig':
        """Load configuration from environment variables"""
        storage_nodes_str = os.getenv('STORAGE_NODES', '')
        storage_nodes = [node.strip() for node in storage_nodes_str.split(',') if node.strip()]
        
        return cls(
            port=int(os.getenv('PORT', '8083')),
            log_level=os.getenv('LOG_LEVEL', 'INFO'),
            metadata_service_url=os.getenv('METADATA_SERVICE_URL', 'http://localhost:8080'),
            storage_nodes=storage_nodes,
            monitoring_interval=int(os.getenv('MONITORING_INTERVAL', '3')),
            target_buffer_sec=int(os.getenv('TARGET_BUFFER_SEC', '30')),
            low_water_mark_sec=int(os.getenv('LOW_WATER_MARK_SEC', '15')),
            max_concurrent_downloads=int(os.getenv('MAX_CONCURRENT_DOWNLOADS', '4'))
        )


class ServiceDiscovery:
    """Service discovery and health checking"""
    
    def __init__(self, metadata_service_url: str):
        self.metadata_service_url = metadata_service_url
        self.logger = logging.getLogger(__name__)
    
    async def get_healthy_nodes(self) -> List[str]:
        """Get list of healthy storage nodes from metadata service"""
        import aiohttp
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.metadata_service_url}/nodes/healthy",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return [node['node_url'] for node in data]
                    else:
                        self.logger.warning(f"Failed to get healthy nodes: {response.status}")
                        return []
        except Exception as e:
            self.logger.error(f"Error getting healthy nodes: {e}")
            return []
    
    async def register_node(self, node_id: str, node_url: str) -> bool:
        """Register a storage node with the metadata service"""
        import aiohttp
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.metadata_service_url}/nodes/{node_id}/heartbeat",
                    json={"node_url": node_url, "status": "healthy"},
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        self.logger.info(f"Successfully registered node {node_id}")
                        return True
                    else:
                        self.logger.warning(f"Failed to register node: {response.status}")
                        return False
        except Exception as e:
            self.logger.error(f"Error registering node: {e}")
            return False
    
    async def send_heartbeat(self, node_id: str, disk_usage: float, chunk_count: int) -> bool:
        """Send heartbeat to metadata service"""
        import aiohttp
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.metadata_service_url}/nodes/{node_id}/heartbeat",
                    json={
                        "disk_usage": disk_usage,
                        "chunk_count": chunk_count,
                        "status": "healthy"
                    },
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    return response.status == 200
        except Exception as e:
            self.logger.error(f"Error sending heartbeat: {e}")
            return False


def validate_config(config: ServiceConfig) -> bool:
    """Validate service configuration"""
    logger = logging.getLogger(__name__)
    
    # Validate port
    if not (1024 <= config.port <= 65535):
        logger.error(f"Invalid port: {config.port}. Must be between 1024 and 65535")
        return False
    
    # Validate log level
    valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    if config.log_level.upper() not in valid_log_levels:
        logger.error(f"Invalid log level: {config.log_level}. Must be one of {valid_log_levels}")
        return False
    
    # Service-specific validation
    if isinstance(config, MetadataServiceConfig):
        if not config.database_url:
            logger.error("Database URL is required")
            return False
        if config.heartbeat_interval <= 0:
            logger.error("Heartbeat interval must be positive")
            return False
        if config.node_timeout <= 0:
            logger.error("Node timeout must be positive")
            return False
    
    elif isinstance(config, StorageNodeConfig):
        if not config.node_id:
            logger.error("Node ID is required")
            return False
        if not config.node_url:
            logger.error("Node URL is required")
            return False
        if not config.data_dir:
            logger.error("Data directory is required")
            return False
        if config.max_superblock_size <= 0:
            logger.error("Max superblock size must be positive")
            return False
    
    elif isinstance(config, UploaderServiceConfig):
        if not config.metadata_service_url:
            logger.error("Metadata service URL is required")
            return False
        if config.chunk_size <= 0:
            logger.error("Chunk size must be positive")
            return False
        if config.chunk_duration <= 0:
            logger.error("Chunk duration must be positive")
            return False
    
    elif isinstance(config, SmartClientConfig):
        if not config.metadata_service_url:
            logger.error("Metadata service URL is required")
            return False
        if config.monitoring_interval <= 0:
            logger.error("Monitoring interval must be positive")
            return False
        if config.target_buffer_sec <= 0:
            logger.error("Target buffer must be positive")
            return False
        if config.low_water_mark_sec <= 0:
            logger.error("Low water mark must be positive")
            return False
        if config.low_water_mark_sec >= config.target_buffer_sec:
            logger.error("Low water mark must be less than target buffer")
            return False
    
    logger.info("Configuration validation passed")
    return True
