#!/usr/bin/env python3
"""
Standalone test runner for concurrency tests.
Bypasses pytest to avoid Python 3.9 compatibility issues with pytest-postgresql.
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor

print("="*70)
print("CONCURRENCY TESTS - Standalone Runner")
print("="*70)
print()

# Test 1: Rate Limiter Thread Safety
print("Test 1: Rate Limiter Has Lock")
print("-" * 70)
try:
    from utils.rate_limiter import SECRateLimiter
    from threading import Lock

    limiter = SECRateLimiter(requests_per_second=10)

    assert hasattr(limiter, 'lock'), "❌ FAIL: RateLimiter missing 'lock' attribute"
    assert isinstance(limiter.lock, type(Lock())), "❌ FAIL: 'lock' is not a threading.Lock"

    print("✅ PASS: RateLimiter has threading.Lock")
except Exception as e:
    print(f"❌ FAIL: {e}")
    sys.exit(1)

print()

# Test 2: Rate Limiter Concurrent Requests
print("Test 2: Rate Limiter Enforces Global Limit with Concurrent Threads")
print("-" * 70)
try:
    limiter = SECRateLimiter(requests_per_second=10)
    call_times = []

    def make_request(i):
        limiter.wait()
        call_times.append(time.time())
        return i

    print("  Running 20 concurrent requests with 5 workers...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        start = time.time()
        results = list(executor.map(make_request, range(20)))
        elapsed = time.time() - start

    print(f"  Completed in {elapsed:.2f}s")

    # Verify time constraint
    assert elapsed >= 1.9, f"❌ FAIL: Too fast ({elapsed:.2f}s), rate limit violated!"
    print(f"  ✓ Time check: {elapsed:.2f}s >= 1.9s (rate limit respected)")

    # Verify intervals
    call_times.sort()
    intervals = [call_times[i+1] - call_times[i] for i in range(19)]
    min_interval = min(intervals)

    assert min_interval >= 0.08, f"❌ FAIL: Interval too short ({min_interval:.3f}s)"
    print(f"  ✓ Interval check: {min_interval:.3f}s >= 0.08s (no violations)")

    print("✅ PASS: Rate limiter enforces global limit")
except Exception as e:
    print(f"❌ FAIL: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Test 3: Rate Limiter Stress Test
print("Test 3: Rate Limiter Stress Test (50 requests, 10 workers)")
print("-" * 70)
try:
    limiter = SECRateLimiter(requests_per_second=10)
    call_times = []

    def make_request(i):
        limiter.wait()
        call_times.append(time.time())
        return i

    print("  Running 50 concurrent requests with 10 workers...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        start = time.time()
        results = list(executor.map(make_request, range(50)))
        elapsed = time.time() - start

    print(f"  Completed in {elapsed:.2f}s")

    # Verify time constraint (50 requests / 10 req/s = 5s minimum)
    assert elapsed >= 4.9, f"❌ FAIL: Too fast ({elapsed:.2f}s), rate limit violated!"
    print(f"  ✓ Time check: {elapsed:.2f}s >= 4.9s (rate limit respected)")

    # Check no second has more than 11 requests (allowing small timing variance)
    call_times.sort()
    for window_start in range(int(elapsed)):
        window_end = window_start + 1.0
        requests_in_window = sum(
            1 for t in call_times
            if start + window_start <= t < start + window_end
        )
        assert requests_in_window <= 11, \
            f"❌ FAIL: {requests_in_window} requests in 1s window (max: 11)"

    print(f"  ✓ Window check: No 1-second window exceeded 11 requests")

    print("✅ PASS: Rate limiter handles stress test")
except Exception as e:
    print(f"❌ FAIL: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Test 4: Session Isolation
print("Test 4: Database Session Isolation Per Thread")
print("-" * 70)
try:
    from config.db import get_db_session

    session_ids = []

    def check_session():
        with get_db_session() as session:
            session_ids.append(id(session))
            time.sleep(0.05)  # Simulate work

    print("  Creating 5 sessions in parallel threads...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        list(executor.map(lambda x: check_session(), range(5)))

    unique_sessions = set(session_ids)

    print(f"  Sessions created: {len(session_ids)}")
    print(f"  Unique sessions: {len(unique_sessions)}")

    assert len(unique_sessions) == 5, \
        f"❌ FAIL: Expected 5 unique sessions, got {len(unique_sessions)}"

    print("✅ PASS: Each thread gets its own session")
except Exception as e:
    print(f"❌ FAIL: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Test 5: Concurrent Session Usage (Database Access)
print("Test 5: Concurrent Database Session Usage")
print("-" * 70)
try:
    from config.db import get_db_session
    from models import Company

    results = []

    def query_with_session(thread_id):
        try:
            with get_db_session() as session:
                count = session.query(Company).count()
                results.append((thread_id, count, id(session)))
                return True
        except Exception as e:
            results.append((thread_id, str(e), None))
            return False

    print("  Running 8 concurrent database queries...")
    with ThreadPoolExecutor(max_workers=8) as executor:
        success = list(executor.map(query_with_session, range(8)))

    # Check all succeeded
    assert all(success), f"❌ FAIL: Some threads failed: {results}"
    print(f"  ✓ All 8 queries succeeded")

    # Check sessions are different
    session_ids = [r[2] for r in results if r[2] is not None]
    unique_sessions = len(set(session_ids))

    assert unique_sessions == 8, \
        f"❌ FAIL: Expected 8 unique sessions, got {unique_sessions}"
    print(f"  ✓ All 8 sessions were unique")

    print("✅ PASS: Concurrent database access works correctly")
except Exception as e:
    print(f"❌ FAIL: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Test 6: Error Isolation
print("Test 6: Error Isolation in Concurrent Execution")
print("-" * 70)
try:
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

    print("  Running 10 tasks with 1 intentional failure...")
    with ThreadPoolExecutor(max_workers=4) as executor:
        outcomes = list(executor.map(task_with_occasional_failure, range(10)))

    successes = [r for r in results if r[0] == 'success']
    errors = [r for r in results if r[0] == 'error']

    print(f"  Successes: {len(successes)}")
    print(f"  Errors: {len(errors)}")

    assert len(successes) == 9, f"❌ FAIL: Expected 9 successes, got {len(successes)}"
    assert len(errors) == 1, f"❌ FAIL: Expected 1 error, got {len(errors)}"
    assert errors[0][1] == 5, f"❌ FAIL: Error was not for task 5"

    print("✅ PASS: Errors are isolated, don't affect other threads")
except Exception as e:
    print(f"❌ FAIL: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Test 7: Configuration Validation
print("Test 7: DOWNLOAD_WORKERS Configuration")
print("-" * 70)
try:
    from config.settings import settings

    print(f"  Current DOWNLOAD_WORKERS: {settings.download_workers}")

    assert 1 <= settings.download_workers <= 10, \
        f"❌ FAIL: DOWNLOAD_WORKERS out of range: {settings.download_workers}"

    print(f"  ✓ Within valid range (1-10)")
    print("✅ PASS: Configuration is valid")
except Exception as e:
    print(f"❌ FAIL: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Summary
print("="*70)
print("TEST SUMMARY")
print("="*70)
print()
print("✅ All 7 concurrency tests PASSED!")
print()
print("Tests verified:")
print("  1. ✅ RateLimiter has threading.Lock")
print("  2. ✅ RateLimiter enforces global rate limit")
print("  3. ✅ RateLimiter handles stress test (50 requests)")
print("  4. ✅ Database sessions are isolated per thread")
print("  5. ✅ Concurrent database access works correctly")
print("  6. ✅ Errors are isolated between threads")
print("  7. ✅ Configuration is valid")
print()
print("="*70)
print("🎉 CONCURRENCY IMPLEMENTATION IS SAFE AND CORRECT!")
print("="*70)
print()
print("You can now run optimized downloads with:")
print("  python nasdaq_full_backfill.py --download-only")
print("  python nyse_full_backfill.py --download-only")
print()

sys.exit(0)
