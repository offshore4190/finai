#!/usr/bin/env python3
"""
Benchmark script to demonstrate concurrent download performance improvement.

This script simulates downloads with different worker counts to show speedup.
"""
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch
import sys

from utils.rate_limiter import SECRateLimiter
from config.settings import settings
import structlog

logger = structlog.get_logger()


def simulate_download(artifact_id, rate_limiter, network_delay=0.5):
    """
    Simulate downloading a single artifact.

    Args:
        artifact_id: Artifact identifier
        rate_limiter: Global rate limiter instance
        network_delay: Simulated network I/O time in seconds

    Returns:
        Tuple of (artifact_id, success, duration)
    """
    start = time.time()

    # Respect rate limit (simulates SEC API rate limit)
    rate_limiter.wait()

    # Simulate network I/O (this is what we parallelize)
    time.sleep(network_delay)

    # Simulate file write and DB update
    time.sleep(0.01)

    duration = time.time() - start
    return (artifact_id, True, duration)


def benchmark_sequential(artifact_count=50, network_delay=0.1):
    """
    Benchmark sequential download (baseline).

    Args:
        artifact_count: Number of artifacts to download
        network_delay: Simulated network delay per artifact

    Returns:
        Tuple of (total_time, throughput)
    """
    print(f"\n{'='*70}")
    print(f"BASELINE: Sequential Downloads (workers=1)")
    print(f"{'='*70}")
    print(f"Artifacts: {artifact_count}")
    print(f"Network delay per artifact: {network_delay}s")

    rate_limiter = SECRateLimiter(requests_per_second=10)

    start_time = time.time()
    results = []

    for i in range(artifact_count):
        result = simulate_download(i, rate_limiter, network_delay)
        results.append(result)

        if (i + 1) % 10 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            print(f"  Progress: {i+1}/{artifact_count} ({rate:.1f} files/min)")

    total_time = time.time() - start_time
    throughput = artifact_count / total_time * 60  # files per minute

    print(f"\nResults:")
    print(f"  Total time: {total_time:.2f}s")
    print(f"  Throughput: {throughput:.1f} files/min")
    print(f"  Average per file: {total_time/artifact_count:.3f}s")

    return total_time, throughput


def benchmark_concurrent(artifact_count=50, workers=8, network_delay=0.1):
    """
    Benchmark concurrent download (optimized).

    Args:
        artifact_count: Number of artifacts to download
        workers: Number of concurrent workers
        network_delay: Simulated network delay per artifact

    Returns:
        Tuple of (total_time, throughput)
    """
    print(f"\n{'='*70}")
    print(f"OPTIMIZED: Concurrent Downloads (workers={workers})")
    print(f"{'='*70}")
    print(f"Artifacts: {artifact_count}")
    print(f"Workers: {workers}")
    print(f"Network delay per artifact: {network_delay}s")

    rate_limiter = SECRateLimiter(requests_per_second=10)

    def download_one(artifact_id):
        return simulate_download(artifact_id, rate_limiter, network_delay)

    start_time = time.time()
    results = []
    completed = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_id = {
            executor.submit(download_one, aid): aid
            for aid in range(artifact_count)
        }

        from concurrent.futures import as_completed
        for future in as_completed(future_to_id):
            result = future.result()
            results.append(result)
            completed += 1

            if completed % 10 == 0:
                elapsed = time.time() - start_time
                rate = completed / elapsed * 60
                print(f"  Progress: {completed}/{artifact_count} ({rate:.1f} files/min)")

    total_time = time.time() - start_time
    throughput = artifact_count / total_time * 60  # files per minute

    print(f"\nResults:")
    print(f"  Total time: {total_time:.2f}s")
    print(f"  Throughput: {throughput:.1f} files/min")
    print(f"  Average per file: {total_time/artifact_count:.3f}s")

    return total_time, throughput


def main():
    """Run comprehensive benchmark."""
    print("\n" + "="*70)
    print("📊 CONCURRENT DOWNLOAD PERFORMANCE BENCHMARK")
    print("="*70)
    print("\nThis benchmark simulates downloading SEC filings with:")
    print("  - Global rate limit: 10 req/s (SEC EDGAR requirement)")
    print("  - Network I/O: 0.1s per file (simulated)")
    print("  - File write + DB update: 0.01s per file")
    print("\nThe optimization parallelizes network I/O while respecting rate limits.")

    # Test with different scenarios
    artifact_count = 50
    network_delay = 0.1

    # Baseline: Sequential
    baseline_time, baseline_throughput = benchmark_sequential(
        artifact_count=artifact_count,
        network_delay=network_delay
    )

    # Optimized: Concurrent with 4 workers
    time_4w, throughput_4w = benchmark_concurrent(
        artifact_count=artifact_count,
        workers=4,
        network_delay=network_delay
    )

    # Optimized: Concurrent with 8 workers (default)
    time_8w, throughput_8w = benchmark_concurrent(
        artifact_count=artifact_count,
        workers=8,
        network_delay=network_delay
    )

    # Summary
    print(f"\n{'='*70}")
    print("📈 PERFORMANCE SUMMARY")
    print(f"{'='*70}")
    print(f"\n{'Configuration':<25} {'Time (s)':<12} {'Throughput':<18} {'Speedup':<10}")
    print("-" * 70)
    print(f"{'Sequential (baseline)':<25} {baseline_time:>8.2f}    {baseline_throughput:>8.1f} files/min   {'1.00x':<10}")
    print(f"{'Concurrent (4 workers)':<25} {time_4w:>8.2f}    {throughput_4w:>8.1f} files/min   {throughput_4w/baseline_throughput:>4.2f}x")
    print(f"{'Concurrent (8 workers)':<25} {time_8w:>8.2f}    {throughput_8w:>8.1f} files/min   {throughput_8w/baseline_throughput:>4.2f}x")

    # Rate limit verification
    print(f"\n{'='*70}")
    print("✅ RATE LIMIT COMPLIANCE")
    print(f"{'='*70}")

    # All scenarios should take at least artifact_count / 10 seconds
    # (due to 10 req/s limit)
    min_expected_time = artifact_count / 10.0

    for name, actual_time in [
        ("Sequential", baseline_time),
        ("4 workers", time_4w),
        ("8 workers", time_8w)
    ]:
        status = "✅ PASS" if actual_time >= min_expected_time * 0.95 else "⚠️  WARNING"
        print(f"  {name:<15} {actual_time:>6.2f}s (min: {min_expected_time:.2f}s) {status}")

    print(f"\n{'='*70}")
    print("🎯 CONCLUSION")
    print(f"{'='*70}")

    best_speedup = max(throughput_4w, throughput_8w) / baseline_throughput

    if best_speedup >= 3.0:
        print(f"✅ Optimization successful! {best_speedup:.1f}x speedup achieved.")
        print("   The concurrent implementation significantly improves throughput")
        print("   while maintaining SEC rate limit compliance.")
    elif best_speedup >= 2.0:
        print(f"✅ Good improvement! {best_speedup:.1f}x speedup achieved.")
        print("   Further optimization may be possible with tuning.")
    else:
        print(f"⚠️  Limited improvement: {best_speedup:.1f}x speedup.")
        print("   This may be due to rate limit constraints.")

    print(f"\n{'='*70}")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nBenchmark interrupted.")
        sys.exit(1)
