"""
Retry decorator and hashing utilities.
"""
import hashlib
import time
from functools import wraps
from typing import Callable, Any

import structlog

logger = structlog.get_logger()


def retry_with_backoff(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    Decorator for retrying functions with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        backoff_factor: Multiplier for delay on each retry
        exceptions: Tuple of exceptions to catch and retry
    
    Usage:
        @retry_with_backoff(max_attempts=3, initial_delay=1.0)
        def my_function():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            delay = initial_delay
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts:
                        logger.error(
                            "retry_exhausted",
                            function=func.__name__,
                            attempts=attempt,
                            error=str(e)
                        )
                        raise
                    
                    logger.warning(
                        "retry_attempt",
                        function=func.__name__,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        delay=delay,
                        error=str(e)
                    )
                    
                    time.sleep(delay)
                    delay *= backoff_factor
            
            return None  # Should never reach here
        
        return wrapper
    return decorator


def calculate_retry_delay(retry_count: int, base_delay: int = 60) -> int:
    """
    Calculate exponential backoff delay.
    
    Args:
        retry_count: Number of previous retries
        base_delay: Base delay in seconds (default 60)
    
    Returns:
        Delay in seconds
    
    Examples:
        retry_count=0 -> 60s (1 minute)
        retry_count=1 -> 120s (2 minutes)
        retry_count=2 -> 240s (4 minutes)
    """
    return base_delay * (2 ** retry_count)


def sha256_file(file_path: str, chunk_size: int = 8192) -> str:
    """
    Calculate SHA256 hash of a file.
    
    Args:
        file_path: Path to file
        chunk_size: Size of chunks to read (bytes)
    
    Returns:
        SHA256 hash as hex string
    """
    sha256_hash = hashlib.sha256()
    
    with open(file_path, 'rb') as f:
        while chunk := f.read(chunk_size):
            sha256_hash.update(chunk)
    
    return sha256_hash.hexdigest()


def sha256_bytes(content: bytes) -> str:
    """
    Calculate SHA256 hash of bytes.
    
    Args:
        content: Bytes to hash
    
    Returns:
        SHA256 hash as hex string
    """
    return hashlib.sha256(content).hexdigest()
