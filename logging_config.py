"""
Centralized logging configuration for V-Stack services.
Provides consistent logging across all components.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional
import os


class VStackLogger:
    """Centralized logger for V-Stack services"""
    
    @staticmethod
    def setup_logger(
        name: str,
        log_level: str = 'INFO',
        log_file: Optional[str] = None,
        max_bytes: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5
    ) -> logging.Logger:
        """
        Setup a logger with consistent formatting and handlers.
        
        Args:
            name: Logger name (usually service name)
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_file: Optional file path for file logging
            max_bytes: Maximum size of log file before rotation
            backup_count: Number of backup files to keep
        
        Returns:
            Configured logger instance
        """
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        
        # Remove existing handlers
        logger.handlers.clear()
        
        # Create formatter
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # File handler (if specified)
        if log_file:
            # Create log directory if it doesn't exist
            log_dir = os.path.dirname(log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=backup_count
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        
        return logger
    
    @staticmethod
    def log_request(logger: logging.Logger, method: str, path: str, status: int, duration_ms: float):
        """Log HTTP request with consistent format"""
        logger.info(f"{method} {path} - {status} - {duration_ms:.2f}ms")
    
    @staticmethod
    def log_error(logger: logging.Logger, error: Exception, context: str = ""):
        """Log error with context"""
        if context:
            logger.error(f"{context}: {type(error).__name__}: {str(error)}", exc_info=True)
        else:
            logger.error(f"{type(error).__name__}: {str(error)}", exc_info=True)
    
    @staticmethod
    def log_performance(logger: logging.Logger, operation: str, duration_ms: float, threshold_ms: float = 100):
        """Log performance metrics with warning if threshold exceeded"""
        if duration_ms > threshold_ms:
            logger.warning(f"SLOW: {operation} took {duration_ms:.2f}ms (threshold: {threshold_ms}ms)")
        else:
            logger.debug(f"{operation} took {duration_ms:.2f}ms")
    
    @staticmethod
    def log_system_event(logger: logging.Logger, event: str, details: dict = None):
        """Log system events with structured data"""
        if details:
            details_str = ", ".join([f"{k}={v}" for k, v in details.items()])
            logger.info(f"SYSTEM EVENT: {event} | {details_str}")
        else:
            logger.info(f"SYSTEM EVENT: {event}")


# Predefined log levels for different environments
LOG_LEVELS = {
    'development': 'DEBUG',
    'testing': 'INFO',
    'production': 'WARNING'
}


def get_log_level() -> str:
    """Get log level based on environment"""
    env = os.getenv('ENVIRONMENT', 'development').lower()
    return os.getenv('LOG_LEVEL', LOG_LEVELS.get(env, 'INFO'))


def setup_service_logger(service_name: str) -> logging.Logger:
    """
    Setup logger for a V-Stack service.
    
    Args:
        service_name: Name of the service (e.g., 'metadata-service', 'storage-node-1')
    
    Returns:
        Configured logger instance
    """
    log_level = get_log_level()
    log_dir = os.getenv('LOG_DIR', '/var/log/vstack')
    log_file = os.path.join(log_dir, f"{service_name}.log") if log_dir else None
    
    return VStackLogger.setup_logger(
        name=service_name,
        log_level=log_level,
        log_file=log_file
    )


# Example usage for each service:
# from logging_config import setup_service_logger
# logger = setup_service_logger('metadata-service')
