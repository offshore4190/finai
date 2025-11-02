-- Migration 002: Add listings reference table and target companies view
-- Date: 2025-10-29
-- Purpose: Support exchange enrichment and downstream filtering

-- Exchange reference data from NASDAQ/NYSE listings
CREATE TABLE IF NOT EXISTS listings_ref (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    exchange_code VARCHAR(10) NOT NULL,  -- 'Q' for NASDAQ, 'N' for NYSE, etc.
    exchange_name VARCHAR(50) NOT NULL,  -- 'NASDAQ', 'NYSE', 'NYSE American', etc.
    is_etf BOOLEAN DEFAULT FALSE,
    source VARCHAR(20) NOT NULL,  -- 'nasdaqlisted' or 'otherlisted'
    file_time TIMESTAMP,  -- Last modified time of source file
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, exchange_code)
);

CREATE INDEX IF NOT EXISTS idx_listings_ref_symbol ON listings_ref(symbol);
CREATE INDEX IF NOT EXISTS idx_listings_ref_exchange ON listings_ref(exchange_code);
CREATE INDEX IF NOT EXISTS idx_listings_ref_source ON listings_ref(source);

-- View for target ~6k companies (NASDAQ + NYSE family, excluding ETFs)
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

-- Add comment for documentation
COMMENT ON TABLE listings_ref IS 'Reference data from NASDAQ and NYSE listing files for exchange enrichment';
COMMENT ON VIEW v_target_companies IS 'Filtered view of ~6k target companies (NASDAQ/NYSE family, excluding ETFs) for downstream jobs';
