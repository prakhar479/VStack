import os
from dataclasses import dataclass
import dotenv
dotenv.load_dotenv()

@dataclass
class ClientConfig:
    """Centralized configuration for Smart Client."""
    
    # Network Monitoring
    PING_INTERVAL: float = float(os.getenv("PING_INTERVAL", "10.0"))
    HISTORY_SIZE: int = int(os.getenv("HISTORY_SIZE", "10"))
    PING_TIMEOUT: float = float(os.getenv("PING_TIMEOUT", "10.0"))
    NODE_HEALTH_TIMEOUT: float = float(os.getenv("NODE_HEALTH_TIMEOUT", "10.0"))
    
    # Buffer Management
    TARGET_BUFFER_SEC: int = int(os.getenv("TARGET_BUFFER_SEC", "30"))
    LOW_WATER_MARK_SEC: int = int(os.getenv("LOW_WATER_MARK_SEC", "15"))
    CHUNK_DURATION_SEC: int = int(os.getenv("CHUNK_DURATION_SEC", "10"))
    START_PLAYBACK_SEC: int = int(os.getenv("START_PLAYBACK_SEC", "10"))
    MAX_MEMORY_BYTES: int = int(os.getenv("MAX_MEMORY_BYTES", str(500 * 1024 * 1024))) # 500 MB limit
    
    # Scheduler
    MAX_CONCURRENT_DOWNLOADS: int = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "4"))
    DOWNLOAD_TIMEOUT: float = float(os.getenv("DOWNLOAD_TIMEOUT", "30.0"))
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    
    # Performance Targets (for dashboard)
    TARGET_STARTUP_LATENCY: float = 2.0
    MAX_REBUFFERING_EVENTS: int = 1
    MIN_AVG_BUFFER_SEC: float = 20.0
    MIN_AVG_THROUGHPUT_MBPS: float = 40.0
    
    # Services
    METADATA_SERVICE_URL: str = os.getenv("METADATA_SERVICE_URL", "http://localhost:8080")
    DASHBOARD_PORT: int = int(os.getenv("DASHBOARD_PORT", "8888"))
    CLIENT_SERVICE_PORT: int = int(os.getenv("CLIENT_SERVICE_PORT", "8086"))

# Global config instance
config = ClientConfig()
