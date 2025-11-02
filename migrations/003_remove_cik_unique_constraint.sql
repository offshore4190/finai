-- Migration 003: Remove UNIQUE(cik) constraint
-- Date: 2025-10-29
-- Reason: Multiple tickers can share the same CIK (e.g., different share classes, ADRs)

-- Drop the unique constraint on CIK if it exists
ALTER TABLE companies DROP CONSTRAINT IF EXISTS companies_cik_key;

-- The index idx_companies_cik already exists as a non-unique index, which is what we want
-- This allows fast lookups by CIK while permitting multiple tickers per CIK
