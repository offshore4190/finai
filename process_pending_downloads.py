#!/usr/bin/env python3
"""
Process Pending Downloads
Processes all pending artifact downloads for NYSE companies
"""

import asyncio
from datetime import datetime
from config.db import engine, get_db_session
from models import Artifact, Filing, Company
from services.downloader import ArtifactDownloader
import structlog

logger = structlog.get_logger()

# Initialize downloader
downloader = ArtifactDownloader()


def get_pending_artifacts(exchange_filter=None, limit=None):
    """Get list of pending artifacts for specified exchange."""
    conn = engine.raw_connection()
    cur = conn.cursor()

    query = """
        SELECT a.id, a.artifact_type, a.filename, a.url,
               c.ticker, c.exchange, f.accession_number
        FROM artifacts a
        JOIN filings f ON a.filing_id = f.id
        JOIN companies c ON f.company_id = c.id
        WHERE a.status = 'pending_download'
    """

    if exchange_filter:
        if isinstance(exchange_filter, list):
            placeholders = ','.join(['%s'] * len(exchange_filter))
            query += f" AND c.exchange IN ({placeholders})"
            params = exchange_filter
        else:
            query += " AND c.exchange = %s"
            params = [exchange_filter]
    else:
        params = []

    query += " ORDER BY a.created_at"

    if limit:
        query += f" LIMIT {limit}"

    cur.execute(query, params)

    artifacts = []
    for row in cur.fetchall():
        artifacts.append({
            'id': row[0],
            'artifact_type': row[1],
            'filename': row[2],
            'url': row[3],
            'ticker': row[4],
            'exchange': row[5],
            'accession_number': row[6]
        })

    cur.close()
    conn.close()

    return artifacts


def process_artifact_sync(artifact_info):
    """Process a single pending artifact (synchronous version)."""
    try:
        logger.info(
            "processing_artifact",
            artifact_id=artifact_info['id'],
            ticker=artifact_info['ticker'],
            filename=artifact_info['filename']
        )

        with get_db_session() as session:
            artifact = session.query(Artifact).filter_by(id=artifact_info['id']).first()
            if not artifact:
                return {
                    'id': artifact_info['id'],
                    'success': False,
                    'error': 'Artifact not found'
                }

            # Download the artifact
            success = downloader.download_artifact(session, artifact)

            if success or artifact.status in ('downloaded', 'skipped'):
                logger.info(
                    "artifact_downloaded",
                    artifact_id=artifact_info['id'],
                    ticker=artifact_info['ticker'],
                    status=artifact.status
                )
                return {
                    'id': artifact_info['id'],
                    'ticker': artifact_info['ticker'],
                    'filename': artifact_info['filename'],
                    'success': True,
                    'status': artifact.status
                }
            else:
                return {
                    'id': artifact_info['id'],
                    'ticker': artifact_info['ticker'],
                    'filename': artifact_info['filename'],
                    'success': False,
                    'error': 'Download failed',
                    'status': artifact.status
                }

    except Exception as e:
        logger.error(
            "artifact_processing_failed",
            artifact_id=artifact_info['id'],
            error=str(e)
        )
        return {
            'id': artifact_info['id'],
            'ticker': artifact_info['ticker'],
            'filename': artifact_info['filename'],
            'success': False,
            'error': str(e)
        }


async def process_artifact(artifact_info):
    """Async wrapper for process_artifact_sync."""
    # Run in executor to avoid blocking
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, process_artifact_sync, artifact_info)


async def process_batch(artifacts, batch_size=20, max_concurrent=10):
    """Process artifacts in batches with concurrency control."""

    print(f"\nProcessing {len(artifacts)} pending downloads...")
    print(f"Batch size: {batch_size}, Max concurrent: {max_concurrent}\n")

    success_count = 0
    failed_count = 0

    for i in range(0, len(artifacts), batch_size):
        batch = artifacts[i:i+batch_size]
        batch_num = i//batch_size + 1
        total_batches = (len(artifacts)-1)//batch_size + 1

        print(f"\nProcessing batch {batch_num}/{total_batches}")
        print(f"Artifacts {i+1}-{min(i+batch_size, len(artifacts))} of {len(artifacts)}")

        # Process batch with semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_semaphore(artifact):
            async with semaphore:
                return await process_artifact(artifact)

        tasks = [process_with_semaphore(artifact) for artifact in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Summarize batch results
        batch_success = 0
        batch_failed = 0

        for result in results:
            if isinstance(result, Exception):
                batch_failed += 1
                failed_count += 1
                print(f"  ✗ Exception: {str(result)}")
            elif result.get('success'):
                batch_success += 1
                success_count += 1
                if batch_success <= 5:  # Show first 5 successes
                    print(f"  ✓ {result['ticker']}: {result['filename']}")
            else:
                batch_failed += 1
                failed_count += 1
                if batch_failed <= 5:  # Show first 5 failures
                    print(f"  ✗ {result['ticker']}: {result.get('error', 'Unknown error')}")

        print(f"  Batch result: {batch_success} succeeded, {batch_failed} failed")

        # Small delay between batches
        if i + batch_size < len(artifacts):
            print("  Waiting 2 seconds before next batch...")
            await asyncio.sleep(2)

    return {
        'total': len(artifacts),
        'success': success_count,
        'failed': failed_count
    }


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Process pending artifact downloads'
    )
    parser.add_argument(
        '--exchange',
        choices=['NYSE', 'NYSE American', 'NYSE Arca', 'NASDAQ'],
        help='Filter by exchange'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of artifacts to process'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=20,
        help='Batch size for processing (default: 20)'
    )
    parser.add_argument(
        '--max-concurrent',
        type=int,
        default=10,
        help='Maximum concurrent downloads (default: 10)'
    )
    parser.add_argument(
        '--nyse-only',
        action='store_true',
        help='Process only NYSE exchanges (NYSE, NYSE American, NYSE Arca)'
    )

    args = parser.parse_args()

    print("=" * 80)
    print("PROCESS PENDING DOWNLOADS")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Determine exchange filter
    exchange_filter = None
    if args.nyse_only:
        exchange_filter = ['NYSE', 'NYSE American', 'NYSE Arca']
        print("Filter: NYSE exchanges only")
    elif args.exchange:
        exchange_filter = args.exchange
        print(f"Filter: {args.exchange}")

    # Get pending artifacts
    print("Identifying pending downloads...")
    artifacts = get_pending_artifacts(exchange_filter, args.limit)

    if not artifacts:
        print("\n✓ No pending downloads found!")
        return

    print(f"\nFound {len(artifacts)} pending downloads")

    # Show summary by exchange
    exchanges = {}
    for artifact in artifacts:
        exchange = artifact['exchange']
        exchanges[exchange] = exchanges.get(exchange, 0) + 1

    print("\nBy exchange:")
    for exchange, count in sorted(exchanges.items()):
        print(f"  {exchange}: {count} artifacts")

    # Show first 10 artifacts
    print("\nFirst 10 artifacts:")
    for i, artifact in enumerate(artifacts[:10], 1):
        print(f"  {i:2}. {artifact['ticker']:6} - {artifact['filename'][:50]:50}")

    if len(artifacts) > 10:
        print(f"  ... and {len(artifacts) - 10} more")

    # Run processing
    print(f"\nProcessing {len(artifacts)} artifacts...")
    print(f"Batch size: {args.batch_size}, Max concurrent: {args.max_concurrent}")

    results = asyncio.run(
        process_batch(
            artifacts,
            batch_size=args.batch_size,
            max_concurrent=args.max_concurrent
        )
    )

    # Final summary
    print("\n" + "=" * 80)
    print("PROCESSING SUMMARY")
    print("=" * 80)
    print(f"Total Artifacts: {results['total']}")
    print(f"Successful: {results['success']} ({results['success']*100/results['total']:.1f}%)")
    print(f"Failed: {results['failed']} ({results['failed']*100/results['total']:.1f}%)")
    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)


if __name__ == '__main__':
    main()
