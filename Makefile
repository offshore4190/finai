PYTHON?=python
PIP?=pip
VENV?=venv
PYTEST?=pytest
DOCKER_COMPOSE?=docker compose
DB_CONTAINER?=postgres
DB_NAME?=filings_db
DB_USER?=postgres
MIGRATION?=migrations/006_fix_sha256_constraint.sql
STORAGE_ROOT?=/tmp/filings

.PHONY: help venv install env docker-up docker-down migrate test-unit test-downloader test-isolated test-utils test-all downloader-smoke clean-storage clean nyse-backfill nasdaq-backfill all-exchanges-backfill monitor nyse-discover nyse-download nasdaq-discover nasdaq-download backfill-fast backfill-turbo backfill-concurrent diagnose compliance fix-html-preview fix-html-test fix-html-all test-html-links fix-nasdaq fix-nyse fix-nasdaq-preview fix-nyse-preview fix-all-exchanges

help:
	@echo "═══════════════════════════════════════════════════════════════════"
	@echo "                  Filing ETL - Available Commands                   "
	@echo "═══════════════════════════════════════════════════════════════════"
	@echo ""
	@echo "🚀 FAST CONCURRENT BACKFILL (Recommended!):"
	@echo "  make backfill-fast        10x faster! (10 parallel, 5 downloads)"
	@echo "  make backfill-turbo       20x faster! (20 parallel, 10 downloads)"
	@echo ""
	@echo "Setup & Testing:"
	@echo "  venv              Create virtualenv in $(VENV)"
	@echo "  install           Install Python deps into venv"
	@echo "  env               Copy .env.example if .env missing"
	@echo "  docker-up         Start Postgres via docker compose"
	@echo "  docker-down       Stop docker compose services"
	@echo "  migrate           Apply migration $(MIGRATION)"
	@echo "  test-unit         Run fast pytest suite"
	@echo "  test-downloader   Run downloader unit tests"
	@echo "  test-isolated     Run isolated tests (no DB)"
	@echo "  test-utils        Run utility tests"
	@echo "  test-all          Run all pytest suites"
	@echo "  downloader-smoke  Download first artifact smoke test"
	@echo ""
	@echo "Exchange Backfills (Original - Slower):"
	@echo "  nyse-backfill     Full NYSE backfill (discover + download)"
	@echo "  nasdaq-backfill   Full NASDAQ backfill (discover + download)"
	@echo "  all-exchanges-backfill  Full backfill for all exchanges"
	@echo "  nyse-discover     Discover NYSE filings only"
	@echo "  nyse-download     Download NYSE artifacts only"
	@echo "  nasdaq-discover   Discover NASDAQ filings only"
	@echo "  nasdaq-download   Download NASDAQ artifacts only"
	@echo "  monitor           Monitor backfill progress"
	@echo ""
	@echo "📊 Diagnostics:"
	@echo "  make diagnose     Coverage diagnostic"
	@echo "  make compliance   Compliance check"
	@echo ""
	@echo "🔧 HTML Image Link Fixes:"
	@echo "  make fix-html-preview    Preview fixes (20 files, safe)"
	@echo "  make fix-html-test       Test fix (50 files)"
	@echo "  make fix-html-all        Fix all HTML files (with confirmation)"
	@echo "  make test-html-links     Test link rewrite status"
	@echo ""
	@echo "🔧 Batch Fix by Exchange:"
	@echo "  make fix-nasdaq-preview  Preview NASDAQ fixes"
	@echo "  make fix-nasdaq          Fix all NASDAQ HTML files"
	@echo "  make fix-nyse-preview    Preview NYSE fixes"
	@echo "  make fix-nyse            Fix all NYSE HTML files"
	@echo "  make fix-all-exchanges   Fix ALL exchanges (with confirmation)"
	@echo ""
	@echo "Cleanup:"
	@echo "  clean-storage     Remove artifacts under $(STORAGE_ROOT)"
	@echo "  clean             Remove venv and temp files"
	@echo ""
	@echo "═══════════════════════════════════════════════════════════════════"

venv:
	test -d $(VENV) || $(PYTHON) -m venv $(VENV)

install: venv
	. $(VENV)/bin/activate && $(PIP) install -r requirements.txt

env:
	test -f .env || cp .env.example .env

docker-up:
	$(DOCKER_COMPOSE) up -d postgres

docker-down:
	$(DOCKER_COMPOSE) down

migrate:
	$(DOCKER_COMPOSE) exec $(DB_CONTAINER) psql -U $(DB_USER) -d $(DB_NAME) -f $(MIGRATION)

test-unit: test-downloader test-isolated test-utils

test-downloader:
	. $(VENV)/bin/activate && $(PYTEST) tests/test_image_download.py -q

test-isolated:
	. $(VENV)/bin/activate && $(PYTEST) tests/test_isolated.py -q

test-utils:
	. $(VENV)/bin/activate && $(PYTEST) tests/test_comprehensive.py::TestUtilities -q

test-all:
	. $(VENV)/bin/activate && $(PYTEST) -q

downloader-smoke:
	STORAGE_ROOT=$(STORAGE_ROOT) . $(VENV)/bin/activate && $(PYTHON) test_download_first_artifact.py

clean-storage:
	rm -rf $(STORAGE_ROOT)

clean:
	rm -rf $(VENV) __pycache__ .pytest_cache

# Exchange backfill targets
nyse-backfill:
	. $(VENV)/bin/activate && $(PYTHON) nyse_full_backfill.py

nasdaq-backfill:
	. $(VENV)/bin/activate && $(PYTHON) nasdaq_full_backfill.py

all-exchanges-backfill:
	. $(VENV)/bin/activate && $(PYTHON) all_exchanges_backfill.py

nyse-discover:
	. $(VENV)/bin/activate && $(PYTHON) nyse_full_backfill.py --discover-only

nyse-download:
	. $(VENV)/bin/activate && $(PYTHON) nyse_full_backfill.py --download-only

nasdaq-discover:
	. $(VENV)/bin/activate && $(PYTHON) nasdaq_full_backfill.py --discover-only

nasdaq-download:
	. $(VENV)/bin/activate && $(PYTHON) nasdaq_full_backfill.py --download-only

monitor:
	. $(VENV)/bin/activate && $(PYTHON) monitor_backfill_progress.py

# ============================================================================
# FAST CONCURRENT BACKFILL (New!)
# ============================================================================

backfill-fast:
	@echo "🚀 Starting FAST concurrent backfill (10 parallel companies, 5 downloads)..."
	. $(VENV)/bin/activate && $(PYTHON) backfill_concurrent.py \
		--max-concurrent-companies 10 \
		--max-concurrent-downloads 5 \
		--batch-size 100 \
		--progress-interval 30

backfill-turbo:
	@echo "⚡ Starting TURBO concurrent backfill (20 parallel, 10 downloads)..."
	@echo "⚠️  WARNING: High concurrency - monitor SEC rate limits!"
	. $(VENV)/bin/activate && $(PYTHON) backfill_concurrent.py \
		--max-concurrent-companies 20 \
		--max-concurrent-downloads 10 \
		--batch-size 200 \
		--progress-interval 20

backfill-concurrent:
	@echo "🔄 Starting concurrent backfill with custom settings..."
	. $(VENV)/bin/activate && $(PYTHON) backfill_concurrent.py

# ============================================================================
# DIAGNOSTICS
# ============================================================================

diagnose:
	@echo "🔬 Running coverage diagnostic..."
	. $(VENV)/bin/activate && $(PYTHON) diagnose_coverage.py

compliance:
	@echo "✅ Running compliance check..."
	. $(VENV)/bin/activate && $(PYTHON) check_nyse_compliance.py

# ============================================================================
# HTML IMAGE LINK FIXES
# ============================================================================

fix-html-preview:
	@echo "🔍 Previewing HTML image link fixes (20 files)..."
	. $(VENV)/bin/activate && $(PYTHON) fix_html_image_links_simple.py --dry-run --sample 20 --verbose

fix-html-test:
	@echo "🔧 Fixing HTML image links (test with 50 files)..."
	. $(VENV)/bin/activate && $(PYTHON) fix_html_image_links_simple.py --sample 50

fix-html-all:
	@echo "🔧 Fixing ALL HTML image links..."
	@echo "⚠️  This will modify all HTML files (backups will be created)"
	@read -p "Continue? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	. $(VENV)/bin/activate && $(PYTHON) fix_html_image_links_simple.py

test-html-links:
	@echo "🧪 Testing HTML image link rewrite status..."
	. $(VENV)/bin/activate && $(PYTHON) test_html_image_rewrite.py --sample 50

# Batch fix by exchange
fix-nasdaq:
	@echo "🔧 Fixing NASDAQ HTML image links..."
	. $(VENV)/bin/activate && $(PYTHON) batch_fix_html_by_exchange.py --exchange NASDAQ

fix-nyse:
	@echo "🔧 Fixing NYSE HTML image links..."
	. $(VENV)/bin/activate && $(PYTHON) batch_fix_html_by_exchange.py --exchange NYSE

fix-nasdaq-preview:
	@echo "🔍 Preview NASDAQ fixes..."
	. $(VENV)/bin/activate && $(PYTHON) batch_fix_html_by_exchange.py --exchange NASDAQ --dry-run --verbose

fix-nyse-preview:
	@echo "🔍 Preview NYSE fixes..."
	. $(VENV)/bin/activate && $(PYTHON) batch_fix_html_by_exchange.py --exchange NYSE --dry-run --verbose

fix-all-exchanges:
	@echo "🔧 Fixing ALL exchanges..."
	@echo "⚠️  This will process NASDAQ, NYSE, NYSE American, NYSE Arca"
	@read -p "Continue? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	chmod +x batch_fix_all_exchanges.sh
	./batch_fix_all_exchanges.sh
