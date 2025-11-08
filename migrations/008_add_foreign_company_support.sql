-- Migration 008: Add foreign company support (FPI - Foreign Private Issuers)
--
-- Purpose: Enable tracking of foreign companies that file forms 20-F, 40-F, and 6-K
--
-- Changes:
-- 1. Add is_foreign flag to companies table (default FALSE for existing companies)
-- 2. Add fpi_category to track FPI type (FPI, Canadian FPI, Unknown)
-- 3. Add country_code for issuer's country (ISO 3166-1 alpha-2)
-- 4. Add performance index on artifacts for foreign filing queries
--
-- Date: 2025-11-08

-- 1. Add foreign company identification columns to companies table
ALTER TABLE companies
    ADD COLUMN IF NOT EXISTS is_foreign BOOLEAN DEFAULT FALSE NOT NULL;

COMMENT ON COLUMN companies.is_foreign IS 'True if company is a Foreign Private Issuer (files 20-F/40-F instead of 10-K)';

ALTER TABLE companies
    ADD COLUMN IF NOT EXISTS fpi_category VARCHAR(32);

COMMENT ON COLUMN companies.fpi_category IS 'FPI category: FPI (general), Canadian FPI (uses 40-F), or Unknown';

ALTER TABLE companies
    ADD COLUMN IF NOT EXISTS country_code VARCHAR(2);

COMMENT ON COLUMN companies.country_code IS 'Country of incorporation (ISO 3166-1 alpha-2 code, e.g., CA, GB, JP)';

-- 2. Add index for foreign company queries
CREATE INDEX IF NOT EXISTS idx_companies_is_foreign
    ON companies(is_foreign) WHERE is_foreign = TRUE;

-- 3. Add composite index on artifacts for efficient foreign filing queries
-- This improves performance when filtering by artifact_type and status
CREATE INDEX IF NOT EXISTS idx_artifacts_type_status
    ON artifacts(artifact_type, status);

-- Note: The UNIQUE constraint on (filing_id, filename) already exists from schema.sql
-- and provides deduplication within a filing. No changes needed to artifact constraints.

-- Migration summary:
-- - Existing domestic (10-K/10-Q) companies will have is_foreign=FALSE by default
-- - Foreign company identification job will set is_foreign=TRUE and populate fpi_category/country_code
-- - No breaking changes to existing pipeline
-- - New indexes improve query performance for foreign filing operations
