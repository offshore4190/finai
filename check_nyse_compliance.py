#!/usr/bin/env python3
"""
NYSE Database Compliance Checker
Validates NYSE data integrity and compliance with schema requirements
"""

import sys
import os
from datetime import datetime
from config.db import engine

def check_nyse_compliance():
    """Comprehensive NYSE database compliance check"""

    print("=" * 80)
    print("NYSE DATABASE COMPLIANCE REPORT")
    print("=" * 80)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    conn = engine.raw_connection()
    cur = conn.cursor()

    issues = []
    warnings = []

    # 1. Check NYSE companies count and basic stats
    print("1. NYSE COMPANIES OVERVIEW")
    print("-" * 80)
    cur.execute("""
        SELECT
            COUNT(*) as total_companies,
            COUNT(CASE WHEN is_active THEN 1 END) as active_companies,
            COUNT(CASE WHEN NOT is_active THEN 1 END) as inactive_companies,
            COUNT(DISTINCT cik) as unique_ciks,
            COUNT(DISTINCT ticker) as unique_tickers
        FROM companies
        WHERE exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')
    """)
    row = cur.fetchone()
    print(f"Total NYSE Companies: {row[0]}")
    print(f"Active Companies: {row[1]}")
    print(f"Inactive Companies: {row[2]}")
    print(f"Unique CIKs: {row[3]}")
    print(f"Unique Tickers: {row[4]}")

    if row[0] == 0:
        issues.append("CRITICAL: No NYSE companies found in database!")

    # 2. Check for data integrity issues
    print("\n2. DATA INTEGRITY CHECKS")
    print("-" * 80)

    # Check for NULL required fields
    cur.execute("""
        SELECT COUNT(*)
        FROM companies
        WHERE exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')
        AND (ticker IS NULL OR cik IS NULL OR exchange IS NULL)
    """)
    null_count = cur.fetchone()[0]
    if null_count > 0:
        issues.append(f"Found {null_count} NYSE companies with NULL required fields (ticker/cik/exchange)")
        print(f"❌ NULL Required Fields: {null_count} records")
    else:
        print(f"✓ No NULL required fields")

    # Check for invalid CIK format (should be 10 digits)
    cur.execute("""
        SELECT COUNT(*), ticker, cik
        FROM companies
        WHERE exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')
        AND (LENGTH(cik) != 10 OR cik !~ '^[0-9]+$')
        GROUP BY ticker, cik
        LIMIT 5
    """)
    invalid_cik_rows = cur.fetchall()
    if invalid_cik_rows:
        count = sum(row[0] for row in invalid_cik_rows)
        issues.append(f"Found {count} NYSE companies with invalid CIK format")
        print(f"❌ Invalid CIK Format: {count} records")
        for row in invalid_cik_rows[:5]:
            print(f"   - Ticker: {row[1]}, CIK: {row[2]}")
    else:
        print(f"✓ All CIKs properly formatted")

    # Check for duplicate ticker/exchange combinations (should be prevented by UNIQUE constraint)
    cur.execute("""
        SELECT ticker, exchange, COUNT(*) as cnt
        FROM companies
        WHERE exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')
        GROUP BY ticker, exchange
        HAVING COUNT(*) > 1
    """)
    dupes = cur.fetchall()
    if dupes:
        issues.append(f"Found {len(dupes)} duplicate ticker/exchange combinations")
        print(f"❌ Duplicate Ticker/Exchange: {len(dupes)} combinations")
        for row in dupes[:5]:
            print(f"   - {row[0]} on {row[1]}: {row[2]} records")
    else:
        print(f"✓ No duplicate ticker/exchange combinations")

    # 3. Check filings data
    print("\n3. FILINGS DATA CHECKS")
    print("-" * 80)

    cur.execute("""
        SELECT
            COUNT(DISTINCT f.id) as total_filings,
            COUNT(DISTINCT f.accession_number) as unique_accessions,
            COUNT(DISTINCT f.company_id) as companies_with_filings,
            MIN(f.filing_date) as earliest_filing,
            MAX(f.filing_date) as latest_filing
        FROM filings f
        JOIN companies c ON f.company_id = c.id
        WHERE c.exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')
    """)
    row = cur.fetchone()
    print(f"Total Filings: {row[0]:,}")
    print(f"Unique Accessions: {row[1]:,}")
    print(f"Companies with Filings: {row[2]:,}")
    print(f"Date Range: {row[3]} to {row[4]}")

    if row[0] != row[1]:
        issues.append(f"Duplicate accession numbers detected ({row[0]} filings vs {row[1]} unique)")

    # Check for orphaned filings (companies that don't exist)
    cur.execute("""
        SELECT COUNT(*)
        FROM filings f
        LEFT JOIN companies c ON f.company_id = c.id
        WHERE c.id IS NULL
    """)
    orphaned = cur.fetchone()[0]
    if orphaned > 0:
        issues.append(f"Found {orphaned} orphaned filings (company_id references non-existent companies)")
        print(f"❌ Orphaned Filings: {orphaned}")
    else:
        print(f"✓ No orphaned filings")

    # Check for filings with missing required fields
    cur.execute("""
        SELECT COUNT(*)
        FROM filings f
        JOIN companies c ON f.company_id = c.id
        WHERE c.exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')
        AND (f.accession_number IS NULL OR f.form_type IS NULL OR f.filing_date IS NULL OR f.fiscal_year IS NULL)
    """)
    missing_fields = cur.fetchone()[0]
    if missing_fields > 0:
        issues.append(f"Found {missing_fields} filings with missing required fields")
        print(f"❌ Missing Required Fields: {missing_fields} filings")
    else:
        print(f"✓ All filings have required fields")

    # 4. Check artifacts data
    print("\n4. ARTIFACTS DATA CHECKS")
    print("-" * 80)

    cur.execute("""
        SELECT
            COUNT(*) as total_artifacts,
            COUNT(CASE WHEN a.status = 'downloaded' THEN 1 END) as downloaded,
            COUNT(CASE WHEN a.status = 'failed' THEN 1 END) as failed,
            COUNT(CASE WHEN a.status = 'pending_download' THEN 1 END) as pending,
            COUNT(CASE WHEN a.sha256 IS NULL THEN 1 END) as missing_hash
        FROM artifacts a
        JOIN filings f ON a.filing_id = f.id
        JOIN companies c ON f.company_id = c.id
        WHERE c.exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')
    """)
    row = cur.fetchone()
    print(f"Total Artifacts: {row[0]:,}")
    print(f"Downloaded: {row[1]:,} ({row[1]*100/row[0]:.1f}%)" if row[0] > 0 else "Downloaded: 0")
    print(f"Failed: {row[2]:,} ({row[2]*100/row[0]:.1f}%)" if row[0] > 0 else "Failed: 0")
    print(f"Pending: {row[3]:,} ({row[3]*100/row[0]:.1f}%)" if row[0] > 0 else "Pending: 0")
    print(f"Missing SHA256: {row[4]:,}")

    if row[2] > row[0] * 0.05 and row[0] > 100:  # More than 5% failed (if we have significant data)
        warnings.append(f"High failure rate: {row[2]*100/row[0]:.1f}% of artifacts failed")

    # Check for artifacts with excessive retry counts
    cur.execute("""
        SELECT COUNT(*)
        FROM artifacts a
        JOIN filings f ON a.filing_id = f.id
        JOIN companies c ON f.company_id = c.id
        WHERE c.exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')
        AND a.retry_count >= a.max_retries
        AND a.status = 'failed'
    """)
    max_retries = cur.fetchone()[0]
    if max_retries > 0:
        warnings.append(f"{max_retries} artifacts exhausted all retry attempts")
        print(f"⚠ Max Retries Exhausted: {max_retries} artifacts")
    else:
        print(f"✓ No artifacts exhausted retries")

    # 5. Exchange value consistency
    print("\n5. EXCHANGE VALUE CONSISTENCY")
    print("-" * 80)

    cur.execute("""
        SELECT exchange, COUNT(*) as count
        FROM companies
        WHERE exchange LIKE '%NYSE%'
        GROUP BY exchange
        ORDER BY count DESC
    """)
    exchanges = cur.fetchall()
    print("Exchange Distribution:")
    for row in exchanges:
        print(f"  {row[0]}: {row[1]:,} companies")

    # Check for unexpected exchange values
    cur.execute("""
        SELECT DISTINCT exchange
        FROM companies
        WHERE exchange LIKE '%NYSE%'
        AND exchange NOT IN ('NYSE', 'NYSE American', 'NYSE Arca')
    """)
    unexpected = cur.fetchall()
    if unexpected:
        warnings.append(f"Found unexpected NYSE exchange values: {[r[0] for r in unexpected]}")
        print(f"⚠ Unexpected Exchange Values:")
        for row in unexpected:
            print(f"   - {row[0]}")

    # 6. Companies without filings (potential data quality issue)
    print("\n6. DATA COMPLETENESS CHECKS")
    print("-" * 80)

    cur.execute("""
        SELECT COUNT(*)
        FROM companies c
        LEFT JOIN filings f ON c.id = f.company_id
        WHERE c.exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')
        AND c.is_active = true
        AND f.id IS NULL
    """)
    no_filings = cur.fetchone()[0]
    if no_filings > 0:
        warnings.append(f"{no_filings} active NYSE companies have no filings")
        print(f"⚠ Active Companies Without Filings: {no_filings}")

        # Show some examples
        cur.execute("""
            SELECT c.ticker, c.cik, c.company_name, c.exchange
            FROM companies c
            LEFT JOIN filings f ON c.id = f.company_id
            WHERE c.exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')
            AND c.is_active = true
            AND f.id IS NULL
            LIMIT 10
        """)
        examples = cur.fetchall()
        print("  Examples:")
        for row in examples:
            print(f"    - {row[0]} (CIK: {row[1]}) - {row[2]} on {row[3]}")
    else:
        print(f"✓ All active companies have filings")

    # 7. Recent activity check
    print("\n7. RECENT ACTIVITY")
    print("-" * 80)

    cur.execute("""
        SELECT
            MAX(filing_date) as latest_filing,
            COUNT(*) as filings_last_30_days
        FROM filings f
        JOIN companies c ON f.company_id = c.id
        WHERE c.exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')
        AND f.filing_date >= CURRENT_DATE - INTERVAL '30 days'
    """)
    row = cur.fetchone()
    print(f"Latest Filing Date: {row[0]}")
    print(f"Filings in Last 30 Days: {row[1]:,}")

    if row[0] and (datetime.now().date() - row[0]).days > 7:
        warnings.append(f"No recent filings in last 7 days (latest: {row[0]})")

    # Summary
    print("\n" + "=" * 80)
    print("COMPLIANCE SUMMARY")
    print("=" * 80)

    if not issues and not warnings:
        print("✅ ALL CHECKS PASSED - NYSE database is fully compliant")
        result = 0
    else:
        if issues:
            print(f"\n❌ CRITICAL ISSUES ({len(issues)}):")
            for i, issue in enumerate(issues, 1):
                print(f"   {i}. {issue}")

        if warnings:
            print(f"\n⚠ WARNINGS ({len(warnings)}):")
            for i, warning in enumerate(warnings, 1):
                print(f"   {i}. {warning}")

        result = 1 if issues else 0

    cur.close()
    conn.close()

    print("\n" + "=" * 80)
    return result

if __name__ == "__main__":
    try:
        sys.exit(check_nyse_compliance())
    except Exception as e:
        print(f"\n❌ ERROR: Failed to run compliance check: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)
