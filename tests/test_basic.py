"""
Basic tests for the filings ETL system.
"""
import pytest
from datetime import datetime

from utils import sha256_bytes, calculate_retry_delay
from services.storage import StorageService


class TestUtils:
    """Test utility functions."""
    
    def test_sha256_bytes(self):
        """Test SHA256 hashing of bytes."""
        content = b"Hello, World!"
        hash_value = sha256_bytes(content)
        
        # SHA256 of "Hello, World!"
        expected = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
        assert hash_value == expected
    
    def test_calculate_retry_delay(self):
        """Test exponential backoff calculation."""
        assert calculate_retry_delay(0) == 60  # 1 minute
        assert calculate_retry_delay(1) == 120  # 2 minutes
        assert calculate_retry_delay(2) == 240  # 4 minutes


class TestStorage:
    """Test storage service."""
    
    def test_construct_path_html(self):
        """Test HTML path construction."""
        service = StorageService()
        
        path = service.construct_path(
            exchange="NASDAQ",
            ticker="AAPL",
            fiscal_year=2023,
            fiscal_period="Q1",
            filing_date_str="03-02-2023",
            artifact_type="html"
        )
        
        assert path == "NASDAQ/AAPL/2023/AAPL_2023_Q1_03-02-2023.html"
    
    def test_construct_path_xbrl(self):
        """Test XBRL path construction."""
        service = StorageService()
        
        path = service.construct_path(
            exchange="NYSE",
            ticker="JPM",
            fiscal_year=2024,
            fiscal_period="FY",
            filing_date_str="15-03-2024",
            artifact_type="xbrl_raw",
            filename="jpm-20240315.xsd"
        )
        
        assert path == "NYSE/JPM/2024/xbrl/jpm-20240315.xsd"


# Add more tests as needed:
# - Test SEC API client
# - Test database models
# - Test downloader logic
# - Integration tests with test database
