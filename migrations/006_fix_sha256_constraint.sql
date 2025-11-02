-- Migration 006: Fix SHA256 constraint to allow duplicate content across filings
--
-- Problem: The unique constraint on sha256 prevents the same image from being
-- associated with multiple filings, which is incorrect. The same image content
-- can appear in different filings and each filing should have its own artifact record.
--
-- Solution:
-- 1. Drop the unique constraint on sha256
-- 2. Add a composite unique constraint on (filing_id, url) for idempotency
-- 3. Keep sha256 as a regular index for efficient duplicate detection

-- Drop the unique constraint on sha256
DROP INDEX IF EXISTS idx_artifacts_sha256_unique;

-- Create a regular (non-unique) index on sha256 for efficient lookups
CREATE INDEX IF NOT EXISTS idx_artifacts_sha256 ON artifacts(sha256);

-- Add composite unique constraint on (filing_id, url) to ensure idempotency
-- This prevents downloading the same URL twice for the same filing
CREATE UNIQUE INDEX IF NOT EXISTS idx_artifacts_filing_url ON artifacts(filing_id, url);

-- Note: This allows the same content (sha256) to exist multiple times in the database,
-- once for each filing that references it. The local_path may be shared (deduplicated)
-- or different, depending on the download logic.
