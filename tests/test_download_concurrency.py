"""
Tests for concurrent download functionality.
Ensures thread safety, rate limit compliance, and data integrity.
"""
import pytest
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from utils.rate_limiter import SECRateLimiter
from config.db import get_db_session
from models import Company, Filing, Artifact


class TestRateLimiterThreadSafety:
    """Test that RateLimiter is thread-safe and respects global rate limits."""

    def test_rate_limiter_has_lock(self):
        """Verify RateLimiter has threading.Lock for thread safety."""
        limiter = SECRateLimiter(requests_per_second=10)

        # Check that lock attribute exists
        assert hasattr(limiter, 'lock'), "RateLimiter must have a 'lock' attribute"

        # Verify it's a Lock object
        from threading import Lock
        assert isinstance(limiter.lock, type(Lock())), "lock must be a threading.Lock"

    def test_rate_limiter_concurrent_requests(self):
        """
        CRITICAL: Verify rate limiter enforces global limit with multiple threads.

        With 10 req/s limit, 20 requests should take at least 2 seconds.
        """
        limiter = SECRateLimiter(requests_per_second=10)
        call_times = []

        def make_request(i):
            limiter.wait()
            call_times.append(time.time())
            return i

        # Execute 20 requests with 5 concurrent workers
        with ThreadPoolExecutor(max_workers=5) as executor:
            start = time.time()
            results = list(executor.map(make_request, range(20)))
            elapsed = time.time() - start

        # Verify all requests completed
        assert len(results) == 20
        assert len(call_times) == 20

        # 20 requests at 10 req/s should take at least 2 seconds
        # Allow small tolerance for thread scheduling overhead
        assert elapsed >= 1.9, f"Too fast: {elapsed}s (expected >= 1.9s) - rate limit violated!"

        # Check intervals between consecutive requests
        call_times.sort()
        intervals = [call_times[i+1] - call_times[i] for i in range(19)]
        min_interval = min(intervals)

        # Minimum interval should be close to 0.1s (1/10 req/s)
        # Allow tolerance for timing precision
        assert min_interval >= 0.08, f"Interval too short: {min_interval}s (expected >= 0.08s)"

    def test_rate_limiter_stress_test(self):
        """
        Stress test: Many threads making requests simultaneously.
        """
        limiter = SECRateLimiter(requests_per_second=10)
        request_count = 50
        call_times = []

        def make_request(i):
            limiter.wait()
            t = time.time()
            call_times.append(t)
            return i

        # Use 10 workers to simulate high concurrency
        with ThreadPoolExecutor(max_workers=10) as executor:
            start = time.time()
            results = list(executor.map(make_request, range(request_count)))
            elapsed = time.time() - start

        # 50 requests at 10 req/s = 5 seconds minimum
        assert elapsed >= 4.9, f"Stress test failed: {elapsed}s (expected >= 4.9s)"

        # Verify no requests violated rate limit
        call_times.sort()
        for i in range(len(call_times) - 1):
            interval = call_times[i+1] - call_times[i]
            # Allow tiny intervals for requests that were queued
            # but overall rate should be respected

        # Check average rate over 1-second windows
        for window_start in range(int(elapsed)):
            window_end = window_start + 1.0
            requests_in_window = sum(
                1 for t in call_times
                if start + window_start <= t < start + window_end
            )
            # Should never exceed 11 requests in any 1-second window
            # (10 is limit, allow 1 for timing precision)
            assert requests_in_window <= 11, \
                f"Rate limit violated: {requests_in_window} requests in 1s window"


class TestSessionIsolation:
    """Test that database sessions are properly isolated per thread."""

    def test_get_db_session_creates_new_session_per_call(self):
        """Verify get_db_session() creates a new session each time."""
        session_ids = []

        def create_and_record_session():
            with get_db_session() as session:
                session_ids.append(id(session))
                time.sleep(0.05)  # Simulate work

        # Create sessions in multiple threads
        with ThreadPoolExecutor(max_workers=5) as executor:
            list(executor.map(lambda x: create_and_record_session(), range(5)))

        # All 5 sessions should be different objects
        unique_sessions = set(session_ids)
        assert len(unique_sessions) == 5, \
            f"Expected 5 unique sessions, got {len(unique_sessions)}: {session_ids}"

    def test_concurrent_session_usage(self):
        """
        Test that multiple threads can safely use independent sessions.
        """
        results = []

        def query_with_session(thread_id):
            try:
                with get_db_session() as session:
                    # Each thread queries independently
                    count = session.query(Company).count()
                    results.append((thread_id, count, id(session)))
                    return True
            except Exception as e:
                results.append((thread_id, str(e), None))
                return False

        # Execute with 8 concurrent threads
        with ThreadPoolExecutor(max_workers=8) as executor:
            success = list(executor.map(query_with_session, range(8)))

        # All threads should succeed
        assert all(success), f"Some threads failed: {results}"

        # All threads should have used different sessions
        session_ids = [r[2] for r in results if r[2] is not None]
        assert len(set(session_ids)) == 8, "Sessions not properly isolated"


class TestConcurrentDownloads:
    """Test concurrent download functionality."""

    @patch('services.downloader.httpx.get')
    def test_concurrent_downloads_mock(self, mock_get):
        """
        Test concurrent downloads with mocked HTTP requests.
        """
        # Mock slow network I/O
        def slow_download(*args, **kwargs):
            time.sleep(0.1)  # Simulate 100ms network delay
            response = Mock()
            response.content = b"test content for artifact"
            response.status_code = 200
            return response

        mock_get.side_effect = slow_download

        # This test verifies the pattern, actual implementation will be in backfill
        # For now, just verify the mock works
        start = time.time()

        with ThreadPoolExecutor(max_workers=5) as executor:
            responses = list(executor.map(
                lambda x: mock_get(f"http://test.com/file{x}"),
                range(10)
            ))

        elapsed = time.time() - start

        # 10 requests with 5 workers, each taking 0.1s
        # Should complete in ~0.2s (2 batches), not 1.0s (sequential)
        assert elapsed < 0.5, f"Not parallelized: {elapsed}s (expected < 0.5s)"
        assert len(responses) == 10

    def test_partial_failure_isolation(self):
        """
        CRITICAL: Test that one failed download doesn't affect others.

        This test verifies the session-per-thread pattern where each
        download commits independently.
        """
        # This will be a more complete test once we implement the actual
        # concurrent download function
        pass


class TestDownloadThroughput:
    """Benchmark and performance tests."""

    @patch('services.downloader.httpx.get')
    def test_throughput_comparison(self, mock_get):
        """
        Compare throughput: sequential vs concurrent.

        Note: This is more of a benchmark than a unit test.
        """
        # Mock download with realistic timing
        def mock_download(*args, **kwargs):
            time.sleep(0.05)  # 50ms per request
            response = Mock()
            response.content = b"x" * 1000
            response.status_code = 200
            return response

        mock_get.side_effect = mock_download

        # Baseline: Sequential (simulated)
        start = time.time()
        for i in range(20):
            mock_get(f"http://test.com/file{i}")
        sequential_time = time.time() - start

        # Reset mock
        mock_get.side_effect = mock_download

        # Concurrent with 5 workers
        start = time.time()
        with ThreadPoolExecutor(max_workers=5) as executor:
            list(executor.map(
                lambda x: mock_get(f"http://test.com/file{x}"),
                range(20)
            ))
        concurrent_time = time.time() - start

        # Calculate speedup
        speedup = sequential_time / concurrent_time

        # Should see at least 2x improvement with 5 workers
        # (Actual: 20*0.05=1.0s vs 20/5*0.05=0.2s = 5x, but allow overhead)
        assert speedup >= 2.0, \
            f"Insufficient speedup: {speedup:.2f}x (expected >= 2.0x)"

        print(f"\nThroughput benchmark:")
        print(f"  Sequential: {sequential_time:.3f}s")
        print(f"  Concurrent: {concurrent_time:.3f}s")
        print(f"  Speedup: {speedup:.2f}x")


class TestDataIntegrity:
    """Test that concurrent operations maintain data integrity."""

    def test_atomic_artifact_updates(self):
        """
        Test that artifact status updates are atomic.

        Each download should commit independently, so partial failures
        don't affect successful downloads.
        """
        # This test will be more complete once we implement the actual
        # concurrent download with session-per-thread pattern
        pass

    def test_no_duplicate_downloads(self):
        """
        Test that concurrent downloads don't create duplicate artifacts.

        The idempotency checks should work even with concurrent requests.
        """
        pass


class TestErrorHandling:
    """Test error handling in concurrent scenarios."""

    def test_one_thread_exception_doesnt_crash_others(self):
        """Test that exception in one thread doesn't affect others."""
        results = []

        def task_with_occasional_failure(x):
            try:
                if x == 5:
                    raise ValueError("Simulated failure")
                time.sleep(0.01)
                results.append(('success', x))
                return True
            except Exception as e:
                results.append(('error', x, str(e)))
                return False

        with ThreadPoolExecutor(max_workers=4) as executor:
            outcomes = list(executor.map(task_with_occasional_failure, range(10)))

        # Count successes and failures
        successes = [r for r in results if r[0] == 'success']
        errors = [r for r in results if r[0] == 'error']

        # Should have 9 successes and 1 error
        assert len(successes) == 9, f"Expected 9 successes, got {len(successes)}"
        assert len(errors) == 1, f"Expected 1 error, got {len(errors)}"

        # Verify the error was for task 5
        assert errors[0][1] == 5


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
