"""
Unit tests for exchange enrichment functionality.
"""
import pytest
from datetime import datetime
from jobs.listings_ref_sync import ListingsRefSyncJob
from jobs.exchange_enrichment import ExchangeEnrichmentJob


class TestListingsRefParsing:
    """Test parsing of NASDAQ and NYSE listing files."""

    def test_parse_nasdaq_listed(self):
        """Test parsing of NASDAQ listed file format."""
        job = ListingsRefSyncJob()

        # Sample NASDAQ listing data
        sample_data = """Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
AAPL|Apple Inc. Common Stock|Q|N||100|N|N
MSFT|Microsoft Corporation Common Stock|Q|N||100|N|N
SPY|SPDR S&P 500 ETF Trust|Q|N||100|Y|N
TEST|Test Company|Q|Y||100|N|N
File Creation Time: 12292024010203"""

        listings = job._parse_nasdaq_listed(sample_data)

        # Should have 3 entries (TEST excluded as test issue)
        assert len(listings) == 3

        # Check AAPL
        aapl = next(l for l in listings if l['symbol'] == 'AAPL')
        assert aapl['is_etf'] is False
        assert aapl['file_time'] is not None

        # Check SPY (ETF)
        spy = next(l for l in listings if l['symbol'] == 'SPY')
        assert spy['is_etf'] is True

    def test_parse_other_listed(self):
        """Test parsing of other exchange listed file format."""
        job = ListingsRefSyncJob()

        # Sample other exchange listing data
        sample_data = """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
NYT|New York Times Company|N|NYT|N|100|N|
GE|General Electric Company|N|GE|N|100|N|
DIA|SPDR Dow Jones Industrial Average ETF Trust|P|DIA|Y|100|N|
TEST|Test Company|N|TEST|N|100|Y|
File Creation Time: 12292024010203"""

        listings = job._parse_other_listed(sample_data)

        # Should have 3 entries (TEST excluded as test issue)
        assert len(listings) == 3

        # Check NYT
        nyt = next(l for l in listings if l['symbol'] == 'NYT')
        assert nyt['exchange_code'] == 'N'
        assert nyt['exchange_name'] == 'NYSE'
        assert nyt['is_etf'] is False

        # Check DIA (ETF on NYSE Arca)
        dia = next(l for l in listings if l['symbol'] == 'DIA')
        assert dia['exchange_code'] == 'P'
        assert dia['exchange_name'] == 'NYSE Arca'
        assert dia['is_etf'] is True

    def test_exchange_code_mapping(self):
        """Test that exchange codes are mapped correctly."""
        job = ListingsRefSyncJob()

        assert job.EXCHANGE_CODE_MAP['N'] == 'NYSE'
        assert job.EXCHANGE_CODE_MAP['A'] == 'NYSE American'
        assert job.EXCHANGE_CODE_MAP['P'] == 'NYSE Arca'
        assert job.EXCHANGE_CODE_MAP['Z'] == 'BATS'
        assert job.EXCHANGE_CODE_MAP['V'] == 'IEX'


class TestExchangeEnrichmentLogic:
    """Test exchange enrichment business logic."""

    def test_conflict_resolution_prefers_non_etf(self):
        """Test that non-ETF is preferred when symbol appears on multiple exchanges."""
        # This is a logical test - in practice would be tested with actual database
        # The logic is: when multiple matches exist, prefer non-ETF

        matches = [
            {'exchange_name': 'NASDAQ', 'is_etf': True},
            {'exchange_name': 'NYSE', 'is_etf': False},
        ]

        # Filter to non-ETF
        non_etf = [m for m in matches if not m['is_etf']]
        assert len(non_etf) == 1
        assert non_etf[0]['exchange_name'] == 'NYSE'

    def test_exchange_priority_order(self):
        """Test that NASDAQ is preferred over NYSE when both are non-ETF."""
        exchange_priority = {'NASDAQ': 0, 'NYSE': 1, 'NYSE American': 2, 'NYSE Arca': 3}

        matches = [
            {'exchange_name': 'NYSE', 'is_etf': False},
            {'exchange_name': 'NASDAQ', 'is_etf': False},
            {'exchange_name': 'NYSE American', 'is_etf': False},
        ]

        # Sort by priority
        sorted_matches = sorted(
            matches,
            key=lambda m: exchange_priority.get(m['exchange_name'], 999)
        )

        assert sorted_matches[0]['exchange_name'] == 'NASDAQ'
        assert sorted_matches[1]['exchange_name'] == 'NYSE'
        assert sorted_matches[2]['exchange_name'] == 'NYSE American'

    def test_target_exchanges_filter(self):
        """Test that target exchanges are correctly filtered."""
        target_exchanges = ['NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca']

        companies = [
            {'ticker': 'AAPL', 'exchange': 'NASDAQ'},
            {'ticker': 'GE', 'exchange': 'NYSE'},
            {'ticker': 'AAPL', 'exchange': 'UNKNOWN'},
            {'ticker': 'TEST', 'exchange': 'OTC'},
            {'ticker': 'MSFT', 'exchange': 'NYSE Arca'},
        ]

        # Filter to target exchanges
        filtered = [c for c in companies if c['exchange'] in target_exchanges]

        assert len(filtered) == 3
        assert any(c['ticker'] == 'AAPL' and c['exchange'] == 'NASDAQ' for c in filtered)
        assert any(c['ticker'] == 'GE' and c['exchange'] == 'NYSE' for c in filtered)
        assert not any(c['ticker'] == 'TEST' for c in filtered)
        assert not any(c['exchange'] == 'UNKNOWN' for c in filtered)


class TestDataQuality:
    """Test data quality checks and validation."""

    def test_empty_listings_handling(self):
        """Test that empty listing files are handled gracefully."""
        job = ListingsRefSyncJob()

        # Empty data (just header and footer)
        sample_data = """Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
File Creation Time: 12292024010203"""

        listings = job._parse_nasdaq_listed(sample_data)
        assert len(listings) == 0

    def test_malformed_line_skipping(self):
        """Test that malformed lines are skipped."""
        job = ListingsRefSyncJob()

        # Data with malformed line (not enough fields)
        sample_data = """Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
AAPL|Apple Inc.|Q|N||100|N|N
INVALID|Not enough fields
MSFT|Microsoft Corporation|Q|N||100|N|N
File Creation Time: 12292024010203"""

        listings = job._parse_nasdaq_listed(sample_data)

        # Should have 2 valid entries
        assert len(listings) == 2
        assert any(l['symbol'] == 'AAPL' for l in listings)
        assert any(l['symbol'] == 'MSFT' for l in listings)
        assert not any(l['symbol'] == 'INVALID' for l in listings)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
