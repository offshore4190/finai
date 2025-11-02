#!/usr/bin/env python3
"""
Filing Coverage Diagnostic Tool
Compares filesystem folders vs database records to identify coverage gaps.
"""

import os
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from config.db import engine
import structlog

logger = structlog.get_logger()

# Storage root
STORAGE_ROOT = os.getenv('STORAGE_ROOT', '/tmp/filings')

# Expected filing patterns by company type
FILING_PATTERNS = {
    'US_DOMESTIC': ['10-K', '10-Q'],
    'FOREIGN_PRIVATE': ['20-F', '6-K'],
    'FUND': ['N-CSR', 'N-PORT', 'N-CEN', 'N-Q', 'NPORT-P', 'NPORT-EX']
}


def get_filesystem_folders(exchange):
    """Get list of company ticker folders from filesystem."""
    exchange_path = Path(STORAGE_ROOT) / exchange

    if not exchange_path.exists():
        logger.warning(f"Exchange path does not exist: {exchange_path}")
        return set()

    # Get all direct subdirectories (company tickers)
    folders = set()
    try:
        for item in exchange_path.iterdir():
            if item.is_dir():
                folders.add(item.name)
    except Exception as e:
        logger.error(f"Error reading {exchange_path}: {e}")
        return set()

    return folders


def get_db_companies(conn, exchange_filter=None):
    """Get companies from database."""
    cur = conn.cursor()

    query = """
        SELECT
            id,
            ticker,
            cik,
            company_name,
            exchange,
            is_active
        FROM companies
        WHERE 1=1
    """
    params = []

    if exchange_filter:
        if isinstance(exchange_filter, list):
            placeholders = ','.join(['%s'] * len(exchange_filter))
            query += f" AND exchange IN ({placeholders})"
            params.extend(exchange_filter)
        else:
            query += " AND exchange = %s"
            params.append(exchange_filter)

    query += " ORDER BY exchange, ticker"

    cur.execute(query, params)

    companies = {}
    for row in cur.fetchall():
        companies[row[0]] = {
            'id': row[0],
            'ticker': row[1],
            'cik': row[2],
            'company_name': row[3],
            'exchange': row[4],
            'is_active': row[5]
        }

    cur.close()
    return companies


def get_db_companies_with_filings(conn, exchange_filter=None, fiscal_years=None):
    """Get companies that have filings in database."""
    cur = conn.cursor()

    fiscal_years = fiscal_years or [2023, 2024, 2025]

    query = """
        SELECT DISTINCT
            c.id,
            c.ticker,
            c.exchange,
            array_agg(DISTINCT f.form_type ORDER BY f.form_type) as form_types,
            COUNT(f.id) as filing_count
        FROM companies c
        JOIN filings f ON c.id = f.company_id
        WHERE f.fiscal_year = ANY(%s)
    """
    params = [fiscal_years]

    if exchange_filter:
        if isinstance(exchange_filter, list):
            placeholders = ','.join(['%s'] * len(exchange_filter))
            query += f" AND c.exchange IN ({placeholders})"
            params.extend(exchange_filter)
        else:
            query += " AND c.exchange = %s"
            params.append(exchange_filter)

    query += """
        GROUP BY c.id, c.ticker, c.exchange
        ORDER BY c.exchange, c.ticker
    """

    cur.execute(query, params)

    companies_with_filings = {}
    for row in cur.fetchall():
        company_id = row[0]
        ticker = row[1]
        exchange = row[2]
        form_types = row[3] if row[3] else []
        filing_count = row[4]

        companies_with_filings[company_id] = {
            'ticker': ticker,
            'exchange': exchange,
            'form_types': form_types,
            'filing_count': filing_count
        }

    cur.close()
    return companies_with_filings


def classify_company_by_filings(form_types):
    """Classify company by their filing types."""
    if not form_types:
        return 'NO_FILINGS'

    form_set = set(form_types)

    # Check for US domestic (10-K/10-Q)
    if any(f in FILING_PATTERNS['US_DOMESTIC'] for f in form_set):
        return 'US_DOMESTIC'

    # Check for foreign private issuer
    if any(f in FILING_PATTERNS['FOREIGN_PRIVATE'] for f in form_set):
        return 'FOREIGN_PRIVATE'

    # Check for fund
    if any(f in FILING_PATTERNS['FUND'] for f in form_set):
        return 'FUND'

    return 'OTHER'


def get_ticker_to_company_map(companies):
    """Create ticker -> company_id mapping."""
    ticker_map = {}
    for comp_id, comp_data in companies.items():
        ticker = comp_data['ticker']
        exchange = comp_data['exchange']
        key = (ticker, exchange)
        ticker_map[key] = comp_id
    return ticker_map


def main():
    print("=" * 100)
    print("FILING COVERAGE DIAGNOSTIC REPORT")
    print("=" * 100)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Storage Root: {STORAGE_ROOT}\n")

    # Connect to database
    conn = engine.raw_connection()

    # Exchanges to check
    exchanges = {
        'NASDAQ': ['NASDAQ'],
        'NYSE': ['NYSE', 'NYSE American', 'NYSE Arca']
    }

    results = {}

    for label, exchange_list in exchanges.items():
        print(f"\n{'='*100}")
        print(f"ANALYZING: {label}")
        print(f"{'='*100}\n")

        # Get filesystem folders
        fs_folders = set()
        for exch in exchange_list:
            fs_folders.update(get_filesystem_folders(exch))

        print(f"Filesystem folders found: {len(fs_folders)}")

        # Get database companies
        db_companies = get_db_companies(conn, exchange_list)
        print(f"Database companies: {len(db_companies)}")

        # Get companies with filings
        companies_with_filings = get_db_companies_with_filings(conn, exchange_list)
        print(f"Companies with filings (2023-2025): {len(companies_with_filings)}")

        # Create ticker mappings
        ticker_to_id = get_ticker_to_company_map(db_companies)

        # Classify companies by filing pattern
        filing_patterns = defaultdict(int)
        for comp_id, filing_data in companies_with_filings.items():
            pattern = classify_company_by_filings(filing_data['form_types'])
            filing_patterns[pattern] += 1

        # Count companies with specific form types
        companies_with_10kq = sum(1 for fdata in companies_with_filings.values()
                                   if any(f in ['10-K', '10-Q'] for f in fdata['form_types']))

        # Calculate coverage
        active_companies = sum(1 for c in db_companies.values() if c['is_active'])
        coverage_pct = (len(companies_with_filings) / active_companies * 100) if active_companies > 0 else 0

        # Store results
        results[label] = {
            'db_companies': len(db_companies),
            'active_companies': active_companies,
            'db_with_filings': len(companies_with_filings),
            'db_with_10kq': companies_with_10kq,
            'fs_folders': len(fs_folders),
            'coverage_pct': coverage_pct,
            'filing_patterns': dict(filing_patterns)
        }

        # Print breakdown
        print(f"\nFiling Pattern Breakdown:")
        for pattern, count in sorted(filing_patterns.items()):
            print(f"  {pattern:20s}: {count:4d} companies")

        # Find mismatches

        # A) Companies in DB with filings but no folder
        db_tickers_with_filings = {
            (fdata['ticker'], fdata['exchange'])
            for fdata in companies_with_filings.values()
        }

        missing_folders = []
        for ticker_key in db_tickers_with_filings:
            ticker = ticker_key[0]
            if ticker not in fs_folders:
                comp_id = ticker_to_id.get(ticker_key)
                if comp_id and comp_id in companies_with_filings:
                    filing_data = companies_with_filings[comp_id]
                    missing_folders.append({
                        'ticker': ticker,
                        'exchange': ticker_key[1],
                        'form_types': filing_data['form_types'],
                        'filing_count': filing_data['filing_count'],
                        'pattern': classify_company_by_filings(filing_data['form_types'])
                    })

        # B) Folders on filesystem but no DB record
        db_tickers = {c['ticker'] for c in db_companies.values()}
        orphan_folders = fs_folders - db_tickers

        # C) Active companies with no filings
        companies_no_filings = []
        for comp_id, comp_data in db_companies.items():
            if comp_data['is_active'] and comp_id not in companies_with_filings:
                companies_no_filings.append(comp_data)

        # Print Report A: DB with filings but missing folders
        print(f"\n{'─'*100}")
        print(f"REPORT A: Companies in DB with filings but NO filesystem folder")
        print(f"{'─'*100}")
        print(f"Total: {len(missing_folders)} companies\n")

        if missing_folders:
            # Group by pattern
            by_pattern = defaultdict(list)
            for item in missing_folders:
                by_pattern[item['pattern']].append(item)

            for pattern in sorted(by_pattern.keys()):
                items = by_pattern[pattern]
                print(f"\n{pattern} ({len(items)} companies):")
                for item in sorted(items, key=lambda x: x['ticker'])[:20]:
                    forms = ','.join(item['form_types'][:5])
                    if len(item['form_types']) > 5:
                        forms += ',...'
                    print(f"  {item['ticker']:8s} ({item['exchange']:15s}) - {item['filing_count']:3d} filings - [{forms}]")
                if len(items) > 20:
                    print(f"  ... and {len(items) - 20} more")
        else:
            print("✓ All companies with DB filings have filesystem folders!")

        # Print Report B: Orphan folders
        print(f"\n{'─'*100}")
        print(f"REPORT B: Filesystem folders with NO database record")
        print(f"{'─'*100}")
        print(f"Total: {len(orphan_folders)} folders\n")

        if orphan_folders:
            for ticker in sorted(list(orphan_folders))[:50]:
                print(f"  {ticker}")
            if len(orphan_folders) > 50:
                print(f"  ... and {len(orphan_folders) - 50} more")
        else:
            print("✓ All filesystem folders have corresponding DB records!")

        # Print Report C: Active companies with no filings
        print(f"\n{'─'*100}")
        print(f"REPORT C: Active DB companies with NO filings (2023-2025)")
        print(f"{'─'*100}")
        print(f"Total: {len(companies_no_filings)} companies\n")

        if companies_no_filings:
            for comp in sorted(companies_no_filings, key=lambda x: x['ticker'])[:30]:
                print(f"  {comp['ticker']:8s} (CIK: {comp['cik']}) - {comp['company_name'][:60]:60s} ({comp['exchange']})")
            if len(companies_no_filings) > 30:
                print(f"  ... and {len(companies_no_filings) - 30} more")
        else:
            print("✓ All active companies have filings!")

    # Print Summary Table
    print(f"\n{'='*100}")
    print("SUMMARY TABLE")
    print(f"{'='*100}\n")

    print(f"{'Exchange':<10} | {'DB Total':<10} | {'DB Active':<10} | {'DB Filings':<12} | {'DB 10K/Q':<10} | {'FS Folders':<11} | {'Coverage %':<11}")
    print("─" * 100)

    for label in ['NASDAQ', 'NYSE']:
        r = results[label]
        print(f"{label:<10} | {r['db_companies']:<10} | {r['active_companies']:<10} | "
              f"{r['db_with_filings']:<12} | {r['db_with_10kq']:<10} | "
              f"{r['fs_folders']:<11} | {r['coverage_pct']:<10.1f}%")

    # Print expected vs actual
    print(f"\n{'='*100}")
    print("ANALYSIS")
    print(f"{'='*100}\n")

    for label in ['NASDAQ', 'NYSE']:
        r = results[label]
        expected = 4091  # User mentioned expected ~4091 per exchange
        print(f"\n{label}:")
        print(f"  Expected companies: ~{expected}")
        print(f"  DB Total: {r['db_companies']} ({r['db_companies'] - expected:+d})")
        print(f"  DB Active: {r['active_companies']}")
        print(f"  DB with filings: {r['db_with_filings']} ({r['coverage_pct']:.1f}% of active)")
        print(f"  FS folders: {r['fs_folders']}")
        print(f"  Gap (Active - FS folders): {r['active_companies'] - r['fs_folders']}")

        print(f"\n  Filing Patterns:")
        for pattern, count in sorted(r['filing_patterns'].items()):
            pct = (count / r['db_with_filings'] * 100) if r['db_with_filings'] > 0 else 0
            print(f"    {pattern:20s}: {count:4d} ({pct:5.1f}%)")

    conn.close()

    print(f"\n{'='*100}")
    print("DIAGNOSTIC COMPLETE")
    print(f"{'='*100}\n")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
