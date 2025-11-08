# Foreign Filings (FPI) Feature - Changelog

## Overview
Added comprehensive support for Foreign Private Issuers (FPIs) including forms 20-F, 40-F, and 6-K without disrupting the existing domestic (10-K/10-Q) pipeline.

## ✅ Completed Tasks

### 1. Schema & Migration (Migration 008)
- ✅ Added `is_foreign` BOOLEAN column to `companies` table (default FALSE)
- ✅ Added `fpi_category` VARCHAR(32) for FPI classification
- ✅ Added `country_code` VARCHAR(2) for ISO country codes
- ✅ Added partial index on `is_foreign` for query performance
- ✅ Added composite index on `artifacts(artifact_type, status)`
- ✅ All changes backward-compatible with existing data

### 2. Constants & Configuration
- ✅ Created `constants.py` module with centralized definitions
- ✅ Added `FORM_TYPES_FOREIGN` for 20-F, 40-F, 6-K forms
- ✅ Added `FORM_TYPES_DOMESTIC` for existing 10-K/10-Q forms
- ✅ Added fiscal period mappings for foreign forms
- ✅ Added FPI category constants (FPI, Canadian FPI, Unknown)

### 3. Foreign Company Identification (TDD)
**Tests:** `tests/test_foreign_identification.py` (11 tests, all pass)

**Implementation:** `jobs/foreign_company_identification.py`

Features:
- ✅ Multi-signal FPI detection:
  - Presence of 20-F/40-F/6-K forms in recent filings
  - Non-US country of incorporation
  - Historical F-1/F-3/F-4 registration forms
- ✅ Intelligent country code extraction with US state disambiguation
- ✅ Canadian FPI vs general FPI categorization
- ✅ Dry-run mode for safe testing
- ✅ Comprehensive error handling
- ✅ Structured logging with per-company signals

Test Coverage:
- 20-F form detection → FPI category
- 40-F form detection → Canadian FPI category
- Non-US country code detection
- US state code disambiguation (CA/DE)
- Multiple signal aggregation
- Error handling without crashes

### 4. Foreign Backfill Job (TDD)
**Tests:** `tests/test_backfill_foreign_artifacts.py` (13 tests, all pass)

**Implementation:** `jobs/backfill_foreign.py`

Features:
- ✅ Backfills 20-F, 40-F, 6-K filings for identified FPIs
- ✅ Date window filtering (2023-01-01 to 2025-12-31)
- ✅ 6-K volume control with three policies:
  - `minimal`: Primary document only
  - `financial`: Only 6-Ks with financial exhibits
  - `all`: All 6-K filings with exhibits
- ✅ Exchange filtering (NASDAQ, NYSE)
- ✅ Filing and artifact deduplication
- ✅ Dry-run mode for testing
- ✅ Proper fiscal period mapping (20-F/40-F → FY, 6-K → 6K)

Test Coverage:
- Foreign form parsing from SEC API
- Fiscal period mapping for all foreign forms
- Filing and artifact creation
- 6-K volume control policies
- Deduplication logic
- Date window filtering
- Error handling

### 5. CLI Commands
**Implementation:** Updated `main.py`

New Commands:
```bash
# Identify Foreign Private Issuers
python main.py foreign-identify [--limit N] [--dry-run]

# Backfill foreign filings
python main.py foreign-backfill [--limit N] [--exchange {NASDAQ,NYSE}] \
  [--include-6k {minimal,financial,all}] [--dry-run]
```

Features:
- ✅ Registered migration 008 in `init-db` workflow
- ✅ Added two new subcommands with full argument parsing
- ✅ Dry-run support for safe testing
- ✅ Configurable limits for incremental testing
- ✅ Exchange and 6-K policy filtering

### 6. Testing & Quality
- ✅ **24 new tests, all passing**
- ✅ **0 regressions** in existing test suite
- ✅ TDD methodology: tests written before implementation
- ✅ Comprehensive coverage of edge cases
- ✅ Mock-based testing for SEC API calls
- ✅ Error handling verification

## 🎯 Key Design Principles Met

### ✅ No Breaking Changes
- `is_foreign` defaults to FALSE for all existing companies
- Domestic pipeline (10-K/10-Q) unchanged
- New commands are opt-in only
- Existing tests continue to pass

### ✅ Minimal Byte Replacement
- No full-document HTML reserialization
- Follows existing project patterns
- Artifact deduplication via (filing_id, filename)

### ✅ Small, Reviewable Commits
1. `60a66b9` - Schema and constants
2. `43ca802` - Foreign identification (tests + implementation)
3. `d2aef82` - Foreign backfill (tests + implementation)
4. `056ad1e` - CLI commands and migration registration

### ✅ TDD Approach
- All tests written before implementation
- Tests guide the API design
- High confidence in correctness

## 📊 Test Results Summary

```
tests/test_foreign_identification.py .............. 11 PASSED
tests/test_backfill_foreign_artifacts.py ......... 13 PASSED
tests/test_basic.py .............................. 4 PASSED (no regression)
                                                  ================
                                                  28 PASSED
```

## 🚀 Usage Examples

### Identify FPIs in the registry
```bash
# Test with limit and dry-run
python main.py foreign-identify --limit 5 --dry-run

# Production: scan all companies
python main.py foreign-identify
```

### Backfill foreign filings
```bash
# Test with NASDAQ companies only
python main.py foreign-backfill --limit 3 --exchange NASDAQ --dry-run

# Production: backfill with 6-K financial policy
python main.py foreign-backfill --include-6k financial

# Production: backfill all 6-K filings
python main.py foreign-backfill --include-6k all
```

## 📝 Files Added
- `constants.py` - Centralized constants
- `migrations/008_add_foreign_company_support.sql` - Schema migration
- `jobs/foreign_company_identification.py` - FPI identification job
- `jobs/backfill_foreign.py` - Foreign backfill job
- `tests/test_foreign_identification.py` - Identification tests
- `tests/test_backfill_foreign_artifacts.py` - Backfill tests

## 📝 Files Modified
- `models/__init__.py` - Added FPI fields to Company model
- `main.py` - Added CLI commands and migration registration

## 🔍 What Was Skipped (Out of Scope)
- ❌ Full incremental job routing tests (basic implementation ready)
- ❌ Artifact constraints tests (constraints already enforced)
- ❌ PDF download support for foreign filings
- ❌ XBRL/iXBRL detection and parsing
- ❌ Exhibit enumeration from index files

These can be added in future PRs as needed.

## ✅ Acceptance Criteria Met

- [x] All new tests pass
- [x] No regression on existing tests
- [x] Schema migration applies cleanly
- [x] Foreign companies identified correctly
- [x] Foreign filings backfilled with proper deduplication
- [x] No changes to domestic behavior unless foreign commands invoked
- [x] Dry-run mode works for safe testing
- [x] Small, reviewable commits
- [x] TDD approach followed

## 🎉 Ready for PR

The feature is complete and ready for review. All acceptance criteria have been met, tests are green, and the implementation follows project patterns.
