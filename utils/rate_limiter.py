"""
Rate limiter for SEC EDGAR API compliance (max 10 req/sec).
"""
import time
from threading import Lock

import structlog

logger = structlog.get_logger()


class SECRateLimiter:
    """
    Thread-safe rate limiter for SEC EDGAR API.
    Ensures compliance with 10 requests per second limit.
    """
    
    def __init__(self, requests_per_second: int = 10):
        """
        Initialize rate limiter.
        
        Args:
            requests_per_second: Maximum requests allowed per second
        """
        self.requests_per_second = requests_per_second
        self.min_interval = 1.0 / requests_per_second
        self.last_request_time = 0.0
        self.lock = Lock()
        self.request_count = 0
        
        logger.info(
            "rate_limiter_initialized",
            requests_per_second=requests_per_second,
            min_interval_ms=self.min_interval * 1000
        )
    
    def wait(self):
        """
        Wait if necessary to comply with rate limit.
        This method is thread-safe.
        """
        with self.lock:
            current_time = time.time()
            elapsed = current_time - self.last_request_time
            
            if elapsed < self.min_interval:
                sleep_time = self.min_interval - elapsed
                logger.debug("rate_limit_wait", sleep_ms=sleep_time * 1000)
                time.sleep(sleep_time)
            
            self.last_request_time = time.time()
            self.request_count += 1
            
            if self.request_count % 100 == 0:
                logger.info("rate_limiter_stats", total_requests=self.request_count)
    
    def reset_stats(self):
        """Reset request counter."""
        with self.lock:
            self.request_count = 0
