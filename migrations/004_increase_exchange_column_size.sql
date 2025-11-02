-- Migration 004: Increase exchange column size
-- Date: 2025-10-29
-- Reason: Need to support "NYSE American" (13 chars) and other long exchange names

-- Drop view that depends on exchange column
DROP VIEW IF EXISTS v_target_companies;

-- Increase exchange column from VARCHAR(10) to VARCHAR(20)
ALTER TABLE companies ALTER COLUMN exchange TYPE VARCHAR(20);

-- Recreate view
CREATE OR REPLACE VIEW v_target_companies AS
SELECT
    c.id,
    c.ticker,
    c.cik,
    c.company_name,
    c.exchange,
    c.is_active,
    c.created_at,
    c.updated_at
FROM companies c
WHERE c.exchange IN ('NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca')
  AND c.is_active = true
ORDER BY c.ticker;

-- Comment
COMMENT ON COLUMN companies.exchange IS 'Exchange name: NASDAQ, NYSE, NYSE American, NYSE Arca, etc.';
COMMENT ON VIEW v_target_companies IS 'Filtered view of ~6k target companies (NASDAQ/NYSE family, excluding ETFs) for downstream jobs';
