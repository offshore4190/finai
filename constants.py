"""
Constants for SEC filings ETL pipeline.

Centralized definitions for form types, fiscal periods, and other constants
used across the application.
"""

# Domestic form types (10-K and 10-Q filings)
FORM_TYPES_DOMESTIC = [
    '10-K',      # Annual report
    '10-K/A',    # Amended annual report
    '10-Q',      # Quarterly report
    '10-Q/A',    # Amended quarterly report
]

# Foreign Private Issuer (FPI) form types
FORM_TYPES_FOREIGN = [
    '20-F',      # Annual report for foreign issuers
    '20-F/A',    # Amended annual report for foreign issuers
    '40-F',      # Annual report for Canadian issuers
    '40-F/A',    # Amended annual report for Canadian issuers
    '6-K',       # Current report for foreign issuers
    '6-K/A',     # Amended current report for foreign issuers
]

# All supported form types
FORM_TYPES_ALL = FORM_TYPES_DOMESTIC + FORM_TYPES_FOREIGN

# Fiscal period mapping for domestic filings
FISCAL_PERIODS_DOMESTIC = {
    '10-K': 'FY',
    '10-K/A': 'FY',
    '10-Q': None,  # Determined dynamically from report date
    '10-Q/A': None,
}

# Fiscal period mapping for foreign filings
FISCAL_PERIODS_FOREIGN = {
    '20-F': 'FY',
    '20-F/A': 'FY',
    '40-F': 'FY',
    '40-F/A': 'FY',
    '6-K': '6K',     # Special period for current reports
    '6-K/A': '6K',
}

# FPI categories
FPI_CATEGORY_GENERAL = 'FPI'
FPI_CATEGORY_CANADIAN = 'Canadian FPI'
FPI_CATEGORY_UNKNOWN = 'Unknown'

# Artifact types
ARTIFACT_TYPE_HTML = 'html'
ARTIFACT_TYPE_IMAGE = 'image'
ARTIFACT_TYPE_XBRL_RAW = 'xbrl_raw'
ARTIFACT_TYPE_XBRL_DERIVED = 'xbrl_derived'

# Artifact subtypes for foreign filings
ARTIFACT_SUBTYPE_PRIMARY = 'primary'
ARTIFACT_SUBTYPE_EXHIBIT_FINANCIAL = 'exhibit-financial'
ARTIFACT_SUBTYPE_EXHIBIT_PRESS = 'exhibit-press'

# Company status
COMPANY_STATUS_ACTIVE = 'active'
COMPANY_STATUS_MERGED = 'merged'

# Artifact status
ARTIFACT_STATUS_PENDING = 'pending_download'
ARTIFACT_STATUS_DOWNLOADED = 'downloaded'
ARTIFACT_STATUS_SKIPPED = 'skipped'
ARTIFACT_STATUS_FAILED = 'failed'

# Exchange codes
EXCHANGE_NASDAQ = 'NASDAQ'
EXCHANGE_NYSE = 'NYSE'
EXCHANGE_NYSE_AMERICAN = 'NYSE American'
EXCHANGE_NYSE_ARCA = 'NYSE Arca'
EXCHANGE_UNKNOWN = 'UNKNOWN'

# Date ranges for backfill operations
BACKFILL_START_DATE = '2023-01-01'
BACKFILL_END_DATE = '2025-12-31'
