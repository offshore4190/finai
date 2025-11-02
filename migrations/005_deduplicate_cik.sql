-- Migration 005: Add status column and deduplicate CIKs
-- Date: 2025-10-29
-- Purpose: Ensure each active CIK appears only once, prevent future duplicates

-- Step 1: Add status column to companies table
ALTER TABLE companies ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active';

-- Step 2: Update existing records to have status='active'
UPDATE companies SET status = 'active' WHERE status IS NULL;

-- Step 3: Make status NOT NULL
ALTER TABLE companies ALTER COLUMN status SET NOT NULL;

-- Step 4: Create index on status
CREATE INDEX IF NOT EXISTS idx_companies_status ON companies(status);

-- Step 5: Mark duplicate CIK entries as 'merged'
-- Keep the preferred one based on priority:
--   1. Known exchange (NASDAQ, NYSE, NYSE American, NYSE Arca) over UNKNOWN
--   2. Then by exchange name alphabetically
--   3. Then by lowest ID (oldest record)

WITH ranked_companies AS (
    SELECT
        id,
        cik,
        exchange,
        ROW_NUMBER() OVER (
            PARTITION BY cik
            ORDER BY
                CASE
                    WHEN exchange IN ('NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca') THEN 0
                    ELSE 1
                END,
                exchange,
                id
        ) as rn
    FROM companies
    WHERE is_active = true
      AND status = 'active'
),
companies_to_merge AS (
    SELECT id
    FROM ranked_companies
    WHERE rn > 1
)
UPDATE companies
SET status = 'merged', is_active = false
WHERE id IN (SELECT id FROM companies_to_merge);

-- Step 6: Create partial unique index to prevent future duplicates
-- Only one active company per CIK allowed
CREATE UNIQUE INDEX IF NOT EXISTS uq_companies_cik_active
ON companies (cik)
WHERE status = 'active';
