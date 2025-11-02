#!/usr/bin/env python3
"""
State Audit Script
Provides comprehensive view of database completeness and identifies gaps.
Read-only - makes no modifications.
"""
import sys
import argparse
from datetime import datetime
from collections import defaultdict
from pathlib import Path

import structlog
from sqlalchemy import func, and_, or_, Integer
from sqlalchemy.orm import Session

from config.db import get_db_session
from config.settings import settings
from models import Company, Filing, Artifact

logger = structlog.get_logger()


def print_section(title: str):
    """Print formatted section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def audit_companies(session: Session):
    """Audit company counts by exchange."""
    print_section("COMPANIES BY EXCHANGE")

    exchanges = session.query(
        Company.exchange,
        func.count(Company.id).label('total'),
        func.sum(func.cast(Company.is_active, Integer)).label('active')
    ).group_by(Company.exchange).all()

    total_companies = 0
    total_active = 0

    for exchange, total, active in exchanges:
        print(f"{exchange:20s} Total: {total:5d}  Active: {active:5d}")
        total_companies += total
        total_active += active or 0

    print(f"{'TOTAL':20s} Total: {total_companies:5d}  Active: {total_active:5d}")

    return total_companies, total_active


def audit_filings(session: Session):
    """Audit filings by exchange and year."""
    print_section("FILINGS 2023-2025 BY EXCHANGE")

    results = session.query(
        Company.exchange,
        Filing.fiscal_year,
        Filing.form_type,
        func.count(Filing.id).label('count')
    ).join(Company).filter(
        Filing.fiscal_year >= 2023,
        Filing.fiscal_year <= 2025
    ).group_by(
        Company.exchange,
        Filing.fiscal_year,
        Filing.form_type
    ).order_by(
        Company.exchange,
        Filing.fiscal_year,
        Filing.form_type
    ).all()

    # Organize by exchange
    by_exchange = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    for exchange, year, form_type, count in results:
        by_exchange[exchange][year][form_type] = count

    total_filings = 0

    for exchange in sorted(by_exchange.keys()):
        print(f"\n{exchange}:")
        for year in sorted(by_exchange[exchange].keys()):
            year_total = sum(by_exchange[exchange][year].values())
            print(f"  {year}: {year_total:5d} filings", end="")
            form_breakdown = ", ".join(f"{ft}={cnt}" for ft, cnt in sorted(by_exchange[exchange][year].items()))
            print(f" ({form_breakdown})")
            total_filings += year_total

    print(f"\nTOTAL FILINGS (2023-2025): {total_filings:,}")

    return total_filings


def audit_artifacts(session: Session):
    """Audit artifacts by status."""
    print_section("ARTIFACTS BY STATUS")

    results = session.query(
        Artifact.status,
        func.count(Artifact.id).label('count')
    ).group_by(Artifact.status).all()

    status_counts = {}
    total = 0

    for status, count in results:
        status_counts[status] = count
        total += count
        print(f"{status:20s} {count:8,d}")

    print(f"{'TOTAL':20s} {total:8,d}")

    return status_counts


def audit_artifacts_by_exchange(session: Session):
    """Audit artifacts by exchange and status."""
    print_section("ARTIFACTS BY EXCHANGE AND STATUS")

    results = session.query(
        Company.exchange,
        Artifact.status,
        func.count(Artifact.id).label('count')
    ).select_from(Artifact).join(
        Filing, Artifact.filing_id == Filing.id
    ).join(
        Company, Filing.company_id == Company.id
    ).group_by(
        Company.exchange,
        Artifact.status
    ).order_by(
        Company.exchange,
        Artifact.status
    ).all()

    # Organize by exchange
    by_exchange = defaultdict(lambda: defaultdict(int))

    for exchange, status, count in results:
        by_exchange[exchange][status] = count

    # Print table
    statuses = ['pending_download', 'downloading', 'downloaded', 'skipped', 'failed']

    print(f"{'Exchange':15s}", end="")
    for status in statuses:
        print(f" {status:>12s}", end="")
    print(f" {'TOTAL':>12s}")
    print("-" * 90)

    for exchange in sorted(by_exchange.keys()):
        print(f"{exchange:15s}", end="")
        row_total = 0
        for status in statuses:
            count = by_exchange[exchange].get(status, 0)
            row_total += count
            print(f" {count:12,d}", end="")
        print(f" {row_total:12,d}")


def find_failed_artifacts(session: Session, max_retry: int = 3):
    """Find retryable failed artifacts."""
    print_section("GAP A: FAILED ARTIFACTS (RETRYABLE)")

    results = session.query(
        Company.exchange,
        func.count(Artifact.id).label('count')
    ).select_from(Artifact).join(
        Filing, Artifact.filing_id == Filing.id
    ).join(
        Company, Filing.company_id == Company.id
    ).filter(
        Artifact.status == 'failed',
        Artifact.retry_count < max_retry
    ).group_by(Company.exchange).all()

    total_retryable = 0

    if results:
        for exchange, count in results:
            print(f"{exchange:15s} {count:6,d} retryable failed artifacts")
            total_retryable += count
        print(f"{'TOTAL':15s} {total_retryable:6,d} retryable failed artifacts")
    else:
        print("No retryable failed artifacts found.")

    # Also show failed artifacts that exceeded retry limit
    exceeded = session.query(func.count(Artifact.id)).filter(
        Artifact.status == 'failed',
        Artifact.retry_count >= max_retry
    ).scalar()

    if exceeded:
        print(f"\nNote: {exceeded:,d} artifacts have exceeded max retry limit ({max_retry})")

    return total_retryable


def find_companies_without_filings(session: Session):
    """Find active companies with no filings in 2023-2025."""
    print_section("GAP B: COMPANIES WITHOUT 2023-2025 FILINGS")

    # Subquery: companies with at least one filing in 2023-2025
    companies_with_filings = session.query(Filing.company_id).join(Company).filter(
        Filing.fiscal_year >= 2023,
        Filing.fiscal_year <= 2025
    ).distinct().subquery()

    # Companies without any filings in this range
    results = session.query(
        Company.exchange,
        func.count(Company.id).label('count')
    ).filter(
        Company.is_active == True,
        ~Company.id.in_(session.query(companies_with_filings.c.company_id))
    ).group_by(Company.exchange).all()

    total_missing = 0

    if results:
        for exchange, count in results:
            print(f"{exchange:15s} {count:6,d} active companies without filings")
            total_missing += count
        print(f"{'TOTAL':15s} {total_missing:6,d} active companies without filings")
    else:
        print("All active companies have at least one filing in 2023-2025.")

    return total_missing


def sample_filesystem(storage_root: str):
    """Sample filesystem counts under STORAGE_ROOT."""
    print_section("FILESYSTEM SAMPLE COUNTS")

    root_path = Path(storage_root)

    if not root_path.exists():
        print(f"Storage root does not exist: {storage_root}")
        return

    print(f"Storage Root: {storage_root}")

    # Count files by exchange
    for exchange in ['NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca']:
        exchange_path = root_path / exchange
        if not exchange_path.exists():
            print(f"{exchange:15s} Directory does not exist")
            continue

        # Count HTML and image files
        html_files = list(exchange_path.glob("*/*/*.html"))
        image_files = list(exchange_path.glob("*/*/*_image-*.*"))

        print(f"{exchange:15s} {len(html_files):6,d} HTML files, {len(image_files):6,d} image files")


def coverage_by_exchange(session: Session):
    """Calculate coverage percentage by exchange."""
    print_section("COVERAGE BY EXCHANGE (2023-2025)")

    # Companies with at least one filing
    results = session.query(
        Company.exchange,
        func.count(func.distinct(Company.id)).label('total_active'),
        func.count(func.distinct(Filing.company_id)).label('with_filings')
    ).outerjoin(
        Filing,
        and_(
            Filing.company_id == Company.id,
            Filing.fiscal_year >= 2023,
            Filing.fiscal_year <= 2025
        )
    ).filter(
        Company.is_active == True
    ).group_by(Company.exchange).all()

    print(f"{'Exchange':15s} {'Total Active':>12s} {'With Filings':>12s} {'Coverage':>10s}")
    print("-" * 55)

    for exchange, total_active, with_filings in results:
        # with_filings might count nulls, so need to recalculate properly
        actual_with_filings = session.query(func.count(func.distinct(Company.id))).join(
            Filing
        ).filter(
            Company.exchange == exchange,
            Company.is_active == True,
            Filing.fiscal_year >= 2023,
            Filing.fiscal_year <= 2025
        ).scalar()

        coverage_pct = (actual_with_filings / total_active * 100) if total_active > 0 else 0

        print(f"{exchange:15s} {total_active:12,d} {actual_with_filings:12,d} {coverage_pct:9.1f}%")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Audit database state and identify gaps')
    parser.add_argument(
        '--final-report',
        action='store_true',
        help='Generate final completion report with coverage analysis'
    )
    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("  FILINGS ETL STATE AUDIT")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    with get_db_session() as session:
        # Basic counts
        audit_companies(session)
        audit_filings(session)
        audit_artifacts(session)
        audit_artifacts_by_exchange(session)

        # Filesystem sample
        sample_filesystem(settings.storage_root)

        # Gap analysis
        find_failed_artifacts(session, max_retry=settings.artifact_retry_max)
        find_companies_without_filings(session)

        # Coverage
        coverage_by_exchange(session)

    print("\n" + "=" * 80)
    print("  AUDIT COMPLETE")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
