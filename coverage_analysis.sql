-- ============================================================================
-- NYSE & NASDAQ Filing Coverage Analysis - SQL Queries
-- Run these in psql to get detailed insights
-- ============================================================================

\echo '========================================='
\echo 'QUERY 1: Basic Company Counts'
\echo '========================================='

SELECT
    exchange,
    COUNT(*) as total_companies,
    COUNT(CASE WHEN is_active THEN 1 END) as active_companies,
    COUNT(CASE WHEN NOT is_active THEN 1 END) as inactive_companies
FROM companies
WHERE exchange IN ('NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca')
GROUP BY exchange
ORDER BY total_companies DESC;

\echo ''
\echo '========================================='
\echo 'QUERY 2: Companies with Filings (2023-2025)'
\echo '========================================='

SELECT
    c.exchange,
    COUNT(DISTINCT c.id) as companies_with_filings,
    COUNT(f.id) as total_filings,
    MIN(f.filing_date) as earliest_filing,
    MAX(f.filing_date) as latest_filing
FROM companies c
JOIN filings f ON c.id = f.company_id
WHERE c.exchange IN ('NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca')
    AND f.fiscal_year BETWEEN 2023 AND 2025
GROUP BY c.exchange
ORDER BY companies_with_filings DESC;

\echo ''
\echo '========================================='
\echo 'QUERY 3: Companies with 10-K/10-Q Forms'
\echo '========================================='

SELECT
    c.exchange,
    COUNT(DISTINCT c.id) as companies_with_10kq,
    COUNT(CASE WHEN f.form_type = '10-K' THEN 1 END) as count_10k,
    COUNT(CASE WHEN f.form_type = '10-Q' THEN 1 END) as count_10q
FROM companies c
JOIN filings f ON c.id = f.company_id
WHERE c.exchange IN ('NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca')
    AND f.form_type IN ('10-K', '10-Q')
    AND f.fiscal_year BETWEEN 2023 AND 2025
GROUP BY c.exchange
ORDER BY companies_with_10kq DESC;

\echo ''
\echo '========================================='
\echo 'QUERY 4: Foreign/Fund Filers (Top 20)'
\echo '========================================='

SELECT
    c.exchange,
    c.ticker,
    c.company_name,
    array_agg(DISTINCT f.form_type ORDER BY f.form_type) as form_types,
    COUNT(f.id) as filing_count
FROM companies c
JOIN filings f ON c.id = f.company_id
WHERE c.exchange IN ('NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca')
    AND c.is_active = true
    AND f.fiscal_year BETWEEN 2023 AND 2025
GROUP BY c.id, c.exchange, c.ticker, c.company_name
HAVING NOT bool_or(f.form_type IN ('10-K', '10-Q'))
    AND bool_or(f.form_type IN ('20-F', '6-K', 'N-CSR', 'N-PORT', 'N-CEN', 'N-Q'))
ORDER BY c.exchange, filing_count DESC
LIMIT 20;

\echo ''
\echo '========================================='
\echo 'QUERY 5: Active Companies with NO Filings (First 30)'
\echo '========================================='

SELECT
    exchange,
    ticker,
    cik,
    company_name,
    created_at
FROM companies c
WHERE c.exchange IN ('NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca')
    AND c.is_active = true
    AND NOT EXISTS (
        SELECT 1 FROM filings f
        WHERE f.company_id = c.id
    )
ORDER BY exchange, ticker
LIMIT 30;

\echo ''
\echo '========================================='
\echo 'QUERY 6: Filing Patterns by Exchange'
\echo '========================================='

WITH company_patterns AS (
    SELECT
        c.id,
        c.exchange,
        c.ticker,
        CASE
            WHEN bool_or(f.form_type IN ('10-K', '10-Q')) THEN 'US_DOMESTIC'
            WHEN bool_or(f.form_type IN ('20-F', '6-K')) THEN 'FOREIGN_PRIVATE'
            WHEN bool_or(f.form_type IN ('N-CSR', 'N-PORT', 'N-CEN', 'N-Q', 'NPORT-P')) THEN 'FUND'
            WHEN COUNT(f.id) > 0 THEN 'OTHER'
            ELSE 'NO_FILINGS'
        END as filing_pattern
    FROM companies c
    LEFT JOIN filings f ON c.id = f.company_id AND f.fiscal_year BETWEEN 2023 AND 2025
    WHERE c.exchange IN ('NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca')
        AND c.is_active = true
    GROUP BY c.id, c.exchange, c.ticker
)
SELECT
    exchange,
    filing_pattern,
    COUNT(*) as company_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY exchange), 1) as percentage
FROM company_patterns
GROUP BY exchange, filing_pattern
ORDER BY exchange, company_count DESC;

\echo ''
\echo '========================================='
\echo 'QUERY 7: Companies with Filings but No Artifacts (Top 20)'
\echo '========================================='

SELECT
    c.exchange,
    c.ticker,
    c.company_name,
    COUNT(f.id) as filing_count,
    COUNT(a.id) as artifact_count
FROM companies c
JOIN filings f ON c.id = f.company_id
LEFT JOIN artifacts a ON f.id = a.filing_id
WHERE c.exchange IN ('NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca')
    AND c.is_active = true
    AND f.fiscal_year BETWEEN 2023 AND 2025
GROUP BY c.id, c.exchange, c.ticker, c.company_name
HAVING COUNT(f.id) > 0 AND COUNT(a.id) = 0
ORDER BY filing_count DESC
LIMIT 20;

\echo ''
\echo '========================================='
\echo 'QUERY 8: Form Type Distribution'
\echo '========================================='

SELECT
    c.exchange,
    f.form_type,
    COUNT(*) as filing_count,
    COUNT(DISTINCT f.company_id) as unique_companies
FROM filings f
JOIN companies c ON f.company_id = c.id
WHERE c.exchange IN ('NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca')
    AND f.fiscal_year BETWEEN 2023 AND 2025
GROUP BY c.exchange, f.form_type
ORDER BY c.exchange, filing_count DESC;

\echo ''
\echo '========================================='
\echo 'QUERY 9: Recently Added Companies (Last 30 days)'
\echo '========================================='

SELECT
    exchange,
    COUNT(*) as new_companies,
    COUNT(CASE WHEN EXISTS(SELECT 1 FROM filings f WHERE f.company_id = c.id) THEN 1 END) as with_filings
FROM companies c
WHERE c.exchange IN ('NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca')
    AND c.created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY exchange
ORDER BY exchange;

\echo ''
\echo '========================================='
\echo 'Analysis Complete'
\echo '========================================='
