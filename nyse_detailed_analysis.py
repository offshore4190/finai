#!/usr/bin/env python3
"""
Detailed NYSE Database Analysis
Provides additional insights beyond the compliance check
"""

from datetime import datetime
from config.db import engine

def analyze_nyse_data():
    """Generate detailed NYSE database analysis"""

    conn = engine.raw_connection()
    cur = conn.cursor()

    print("=" * 80)
    print("NYSE DATABASE DETAILED ANALYSIS")
    print("=" * 80)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 1. Top companies by filing count
    print("TOP 20 NYSE COMPANIES BY FILING COUNT")
    print("-" * 80)
    cur.execute("""
        SELECT c.ticker, c.company_name, c.exchange, COUNT(f.id) as filing_count
        FROM companies c
        JOIN filings f ON c.id = f.company_id
        WHERE c.exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')
        GROUP BY c.ticker, c.company_name, c.exchange
        ORDER BY filing_count DESC
        LIMIT 20
    """)
    for i, row in enumerate(cur.fetchall(), 1):
        print(f"{i:2}. {row[0]:6} - {row[1][:50]:50} ({row[2]}) - {row[3]:4} filings")

    # 2. Filing types distribution
    print("\n\nFILING TYPES DISTRIBUTION (NYSE)")
    print("-" * 80)
    cur.execute("""
        SELECT f.form_type, COUNT(*) as count
        FROM filings f
        JOIN companies c ON f.company_id = c.id
        WHERE c.exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')
        GROUP BY f.form_type
        ORDER BY count DESC
        LIMIT 20
    """)
    for row in cur.fetchall():
        print(f"{row[0]:10} - {row[1]:5,} filings")

    # 3. Filings by year
    print("\n\nFILINGS BY FISCAL YEAR (NYSE)")
    print("-" * 80)
    cur.execute("""
        SELECT f.fiscal_year, COUNT(*) as count
        FROM filings f
        JOIN companies c ON f.company_id = c.id
        WHERE c.exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')
        GROUP BY f.fiscal_year
        ORDER BY f.fiscal_year DESC
    """)
    for row in cur.fetchall():
        print(f"{row[0]} - {row[1]:6,} filings")

    # 4. Amendment statistics
    print("\n\nAMENDMENT STATISTICS (NYSE)")
    print("-" * 80)
    cur.execute("""
        SELECT
            COUNT(*) as total_filings,
            COUNT(CASE WHEN is_amendment THEN 1 END) as amendments,
            COUNT(CASE WHEN amends_accession IS NOT NULL THEN 1 END) as linked_amendments
        FROM filings f
        JOIN companies c ON f.company_id = c.id
        WHERE c.exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')
    """)
    row = cur.fetchone()
    print(f"Total Filings: {row[0]:,}")
    print(f"Amendments: {row[1]:,} ({row[1]*100/row[0]:.2f}%)")
    print(f"Linked Amendments: {row[2]:,}")

    # 5. Artifact status breakdown
    print("\n\nARTIFACT STATUS BREAKDOWN (NYSE)")
    print("-" * 80)
    cur.execute("""
        SELECT a.status, COUNT(*) as count
        FROM artifacts a
        JOIN filings f ON a.filing_id = f.id
        JOIN companies c ON f.company_id = c.id
        WHERE c.exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')
        GROUP BY a.status
        ORDER BY count DESC
    """)
    for row in cur.fetchall():
        print(f"{row[0]:20} - {row[1]:6,} artifacts")

    # 6. Artifact types
    print("\n\nARTIFACT TYPES (NYSE)")
    print("-" * 80)
    cur.execute("""
        SELECT a.artifact_type, COUNT(*) as count
        FROM artifacts a
        JOIN filings f ON a.filing_id = f.id
        JOIN companies c ON f.company_id = c.id
        WHERE c.exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')
        GROUP BY a.artifact_type
        ORDER BY count DESC
    """)
    for row in cur.fetchall():
        print(f"{row[0]:20} - {row[1]:6,} artifacts")

    # 7. Companies with most artifacts
    print("\n\nTOP 10 COMPANIES BY ARTIFACT COUNT (NYSE)")
    print("-" * 80)
    cur.execute("""
        SELECT c.ticker, c.company_name, COUNT(a.id) as artifact_count
        FROM companies c
        JOIN filings f ON c.id = f.company_id
        JOIN artifacts a ON f.id = a.filing_id
        WHERE c.exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')
        GROUP BY c.ticker, c.company_name
        ORDER BY artifact_count DESC
        LIMIT 10
    """)
    for i, row in enumerate(cur.fetchall(), 1):
        print(f"{i:2}. {row[0]:6} - {row[1][:50]:50} - {row[2]:5,} artifacts")

    # 8. Storage statistics
    print("\n\nSTORAGE STATISTICS (NYSE)")
    print("-" * 80)
    cur.execute("""
        SELECT
            COUNT(*) as total_artifacts,
            COUNT(CASE WHEN a.status = 'downloaded' THEN 1 END) as downloaded,
            SUM(CASE WHEN a.status = 'downloaded' THEN a.file_size ELSE 0 END) as total_size,
            AVG(CASE WHEN a.status = 'downloaded' THEN a.file_size END) as avg_size
        FROM artifacts a
        JOIN filings f ON a.filing_id = f.id
        JOIN companies c ON f.company_id = c.id
        WHERE c.exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')
    """)
    row = cur.fetchone()
    total_gb = row[2] / (1024**3) if row[2] else 0
    avg_kb = row[3] / 1024 if row[3] else 0
    print(f"Total Artifacts: {row[0]:,}")
    print(f"Downloaded: {row[1]:,}")
    print(f"Total Storage: {total_gb:.2f} GB")
    print(f"Average File Size: {avg_kb:.2f} KB")

    # 9. Recent filing activity (last 7 days)
    print("\n\nRECENT FILING ACTIVITY (Last 7 Days)")
    print("-" * 80)
    cur.execute("""
        SELECT DATE(f.filing_date) as date, COUNT(*) as filings
        FROM filings f
        JOIN companies c ON f.company_id = c.id
        WHERE c.exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')
        AND f.filing_date >= CURRENT_DATE - INTERVAL '7 days'
        GROUP BY DATE(f.filing_date)
        ORDER BY date DESC
    """)
    rows = cur.fetchall()
    if rows:
        for row in rows:
            print(f"{row[0]} - {row[1]:3} filings")
    else:
        print("No recent filings in the last 7 days")

    # 10. Data quality score
    print("\n\nDATA QUALITY SCORE")
    print("-" * 80)

    # Calculate various quality metrics
    cur.execute("""
        SELECT
            -- Companies metrics
            (SELECT COUNT(*) FROM companies WHERE exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')) as total_companies,
            (SELECT COUNT(*) FROM companies WHERE exchange IN ('NYSE', 'NYSE American', 'NYSE Arca') AND is_active = true) as active_companies,

            -- Filings metrics
            (SELECT COUNT(DISTINCT company_id) FROM filings f
             JOIN companies c ON f.company_id = c.id
             WHERE c.exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')) as companies_with_filings,

            -- Artifacts metrics
            (SELECT COUNT(*) FROM artifacts a
             JOIN filings f ON a.filing_id = f.id
             JOIN companies c ON f.company_id = c.id
             WHERE c.exchange IN ('NYSE', 'NYSE American', 'NYSE Arca')) as total_artifacts,

            (SELECT COUNT(*) FROM artifacts a
             JOIN filings f ON a.filing_id = f.id
             JOIN companies c ON f.company_id = c.id
             WHERE c.exchange IN ('NYSE', 'NYSE American', 'NYSE Arca') AND a.status = 'downloaded') as downloaded_artifacts,

            (SELECT COUNT(*) FROM artifacts a
             JOIN filings f ON a.filing_id = f.id
             JOIN companies c ON f.company_id = c.id
             WHERE c.exchange IN ('NYSE', 'NYSE American', 'NYSE Arca') AND a.status = 'failed') as failed_artifacts
    """)
    row = cur.fetchone()

    total_companies = row[0]
    active_companies = row[1]
    companies_with_filings = row[2]
    total_artifacts = row[3]
    downloaded_artifacts = row[4]
    failed_artifacts = row[5]

    coverage_score = (companies_with_filings / active_companies * 100) if active_companies > 0 else 0
    download_success_rate = (downloaded_artifacts / total_artifacts * 100) if total_artifacts > 0 else 0
    failure_rate = (failed_artifacts / total_artifacts * 100) if total_artifacts > 0 else 0

    print(f"Company Coverage: {coverage_score:.1f}% ({companies_with_filings}/{active_companies} active companies have filings)")
    print(f"Download Success Rate: {download_success_rate:.1f}% ({downloaded_artifacts:,}/{total_artifacts:,} artifacts)")
    print(f"Failure Rate: {failure_rate:.2f}% ({failed_artifacts:,} failed)")

    # Overall quality score (weighted average)
    quality_score = (coverage_score * 0.5 + download_success_rate * 0.5)
    print(f"\nOverall Data Quality Score: {quality_score:.1f}/100")

    if quality_score >= 90:
        print("Rating: ⭐⭐⭐⭐⭐ EXCELLENT")
    elif quality_score >= 80:
        print("Rating: ⭐⭐⭐⭐ GOOD")
    elif quality_score >= 70:
        print("Rating: ⭐⭐⭐ FAIR")
    elif quality_score >= 60:
        print("Rating: ⭐⭐ NEEDS IMPROVEMENT")
    else:
        print("Rating: ⭐ POOR")

    print("\n" + "=" * 80)

    cur.close()
    conn.close()

if __name__ == "__main__":
    analyze_nyse_data()
