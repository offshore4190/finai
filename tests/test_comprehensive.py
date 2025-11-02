"""
Comprehensive unit tests for the filings ETL system.
Run with: pytest -v tests/
"""
import pytest
from datetime import datetime, date
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os

# Test utilities
from utils import sha256_bytes, calculate_retry_delay
from utils.rate_limiter import SECRateLimiter


class TestUtilities:
    """Test utility functions."""
    
    def test_sha256_bytes_known_hash(self):
        """Test SHA256 hashing with known input."""
        content = b"Hello, World!"
        hash_value = sha256_bytes(content)
        expected = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
        assert hash_value == expected
        assert len(hash_value) == 64  # SHA256 is always 64 hex chars
    
    def test_sha256_bytes_empty(self):
        """Test SHA256 with empty bytes."""
        hash_value = sha256_bytes(b"")
        expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert hash_value == expected
    
    def test_calculate_retry_delay_exponential(self):
        """Test exponential backoff calculation."""
        assert calculate_retry_delay(0) == 60    # 1 minute
        assert calculate_retry_delay(1) == 120   # 2 minutes
        assert calculate_retry_delay(2) == 240   # 4 minutes
        assert calculate_retry_delay(3) == 480   # 8 minutes
    
    def test_calculate_retry_delay_custom_base(self):
        """Test retry delay with custom base."""
        assert calculate_retry_delay(0, base_delay=30) == 30
        assert calculate_retry_delay(1, base_delay=30) == 60
        assert calculate_retry_delay(2, base_delay=30) == 120


class TestRateLimiter:
    """Test SEC rate limiter."""
    
    def test_rate_limiter_initialization(self):
        """Test rate limiter creates with correct settings."""
        limiter = SECRateLimiter(requests_per_second=10)
        assert limiter.requests_per_second == 10
        assert limiter.min_interval == 0.1  # 1/10 second
        assert limiter.request_count == 0
    
    def test_rate_limiter_wait_enforces_delay(self):
        """Test that rate limiter actually delays requests."""
        import time
        limiter = SECRateLimiter(requests_per_second=10)
        
        start = time.time()
        limiter.wait()
        limiter.wait()
        limiter.wait()
        elapsed = time.time() - start
        
        # Should take at least 0.2 seconds for 3 requests at 10 req/sec
        assert elapsed >= 0.2
        assert limiter.request_count == 3


class TestStorageService:
    """Test storage service."""
    
    def test_construct_path_html(self):
        """Test HTML path construction."""
        from services.storage import StorageService
        service = StorageService()
        
        path = service.construct_path(
            exchange="NASDAQ",
            ticker="AAPL",
            fiscal_year=2023,
            fiscal_period="Q1",
            filing_date_str="03-02-2023",
            artifact_type="html"
        )
        
        expected = "NASDAQ/AAPL/2023/AAPL_2023_Q1_03-02-2023.html"
        assert path == expected
    
    def test_construct_path_xbrl(self):
        """Test XBRL path construction."""
        from services.storage import StorageService
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
        
        expected = "NYSE/JPM/2024/xbrl/jpm-20240315.xsd"
        assert path == expected
    
    def test_construct_path_image(self):
        """Test image path construction with placeholder."""
        from services.storage import StorageService
        service = StorageService()
        
        path = service.construct_path(
            exchange="NASDAQ",
            ticker="MSFT",
            fiscal_year=2023,
            fiscal_period="Q2",
            filing_date_str="15-06-2023",
            artifact_type="image",
            filename="chart.png"
        )
        
        assert "NASDAQ/MSFT/2023/MSFT_2023_Q2_15-06-2023_{seq}.png" == path
    
    def test_construct_path_invalid_type(self):
        """Test that invalid artifact type raises error."""
        from services.storage import StorageService
        service = StorageService()
        
        with pytest.raises(ValueError, match="Unknown artifact type"):
            service.construct_path(
                exchange="NASDAQ",
                ticker="AAPL",
                fiscal_year=2023,
                fiscal_period="Q1",
                filing_date_str="03-02-2023",
                artifact_type="invalid_type"
            )


class TestLocalFileSystemAdapter:
    """Test local filesystem storage adapter."""
    
    def test_write_and_read(self):
        """Test writing and reading files."""
        from services.storage import LocalFileSystemAdapter
        
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = LocalFileSystemAdapter(tmpdir)
            
            # Write file
            content = b"Test content"
            path = "test/file.txt"
            success = adapter.write(path, content)
            assert success
            
            # Read file
            read_content = adapter.read(path)
            assert read_content == content
    
    def test_exists(self):
        """Test file existence check."""
        from services.storage import LocalFileSystemAdapter
        
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = LocalFileSystemAdapter(tmpdir)
            
            path = "test/file.txt"
            assert not adapter.exists(path)
            
            adapter.write(path, b"content")
            assert adapter.exists(path)
    
    def test_ensure_directory(self):
        """Test directory creation."""
        from services.storage import LocalFileSystemAdapter
        
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter = LocalFileSystemAdapter(tmpdir)
            
            success = adapter.ensure_directory("test/nested/dir")
            assert success
            
            # Directory should exist
            full_path = os.path.join(tmpdir, "test/nested/dir")
            assert os.path.isdir(full_path)


class TestSECAPIClient:
    """Test SEC API client."""
    
    def test_construct_document_url(self):
        """Test document URL construction."""
        from services.sec_api import SECAPIClient
        
        client = SECAPIClient()
        url = client.construct_document_url(
            cik="0000320193",
            accession="0001234567-23-000123",
            filename="aapl-20230930.htm"
        )
        
        expected = "https://www.sec.gov/Archives/edgar/data/320193/000123456723000123/aapl-20230930.htm"
        assert url == expected
    
    def test_construct_document_url_removes_leading_zeros(self):
        """Test that CIK leading zeros are removed in URL."""
        from services.sec_api import SECAPIClient
        
        client = SECAPIClient()
        url = client.construct_document_url(
            cik="0000000123",
            accession="0001234567-23-000001",
            filename="test.htm"
        )
        
        assert "/data/123/" in url
        assert "/data/0000000123/" not in url
    
    def test_parse_filings_filters_by_form_type(self):
        """Test that parse_filings filters by form type."""
        from services.sec_api import SECAPIClient
        
        client = SECAPIClient()
        
        # Mock submissions data
        submissions_data = {
            'filings': {
                'recent': {
                    'accessionNumber': ['0001-23-001', '0001-23-002', '0001-23-003'],
                    'form': ['10-K', '8-K', '10-Q'],
                    'filingDate': ['2023-03-01', '2023-04-01', '2023-05-01'],
                    'reportDate': ['2023-12-31', '2023-03-31', '2023-03-31'],
                    'primaryDocument': ['doc1.htm', 'doc2.htm', 'doc3.htm']
                }
            }
        }
        
        filings = client.parse_filings(
            submissions_data,
            form_types=['10-K', '10-Q']
        )
        
        assert len(filings) == 2
        assert filings[0]['form_type'] == '10-K'
        assert filings[1]['form_type'] == '10-Q'
    
    def test_parse_filings_filters_by_date(self):
        """Test that parse_filings filters by date range."""
        from services.sec_api import SECAPIClient
        
        client = SECAPIClient()
        
        submissions_data = {
            'filings': {
                'recent': {
                    'accessionNumber': ['0001-23-001', '0001-23-002', '0001-23-003'],
                    'form': ['10-K', '10-K', '10-K'],
                    'filingDate': ['2023-01-01', '2023-06-01', '2023-12-01'],
                    'reportDate': [None, None, None],
                    'primaryDocument': ['doc1.htm', 'doc2.htm', 'doc3.htm']
                }
            }
        }
        
        filings = client.parse_filings(
            submissions_data,
            form_types=['10-K'],
            start_date=datetime(2023, 5, 1),
            end_date=datetime(2023, 12, 31)
        )
        
        assert len(filings) == 2  # Only June and December
        assert filings[0]['filing_date'] >= date(2023, 5, 1)
    
    def test_parse_filings_detects_amendments(self):
        """Test that amendments are properly detected."""
        from services.sec_api import SECAPIClient
        
        client = SECAPIClient()
        
        submissions_data = {
            'filings': {
                'recent': {
                    'accessionNumber': ['0001-23-001', '0001-23-002'],
                    'form': ['10-K', '10-K/A'],
                    'filingDate': ['2023-03-01', '2023-04-01'],
                    'reportDate': [None, None],
                    'primaryDocument': ['doc1.htm', 'doc2.htm']
                }
            }
        }
        
        filings = client.parse_filings(
            submissions_data,
            form_types=['10-K', '10-K/A']
        )
        
        assert len(filings) == 2
        assert filings[0]['is_amendment'] == False
        assert filings[1]['is_amendment'] == True


class TestDatabaseModels:
    """Test database model relationships."""
    
    def test_company_model_attributes(self):
        """Test Company model has required attributes."""
        from models import Company
        
        company = Company(
            ticker="AAPL",
            cik="0000320193",
            company_name="Apple Inc.",
            exchange="NASDAQ",
            is_active=True
        )
        
        assert company.ticker == "AAPL"
        assert company.cik == "0000320193"
        assert company.exchange == "NASDAQ"
        assert company.is_active == True
    
    def test_filing_model_attributes(self):
        """Test Filing model has required attributes."""
        from models import Filing
        
        filing = Filing(
            company_id=1,
            accession_number="0001234567-23-000123",
            form_type="10-K",
            filing_date=date(2023, 3, 1),
            fiscal_year=2023,
            fiscal_period="FY",
            is_amendment=False,
            primary_document="aapl-20230930.htm"
        )
        
        assert filing.accession_number == "0001234567-23-000123"
        assert filing.form_type == "10-K"
        assert filing.fiscal_year == 2023
        assert filing.is_amendment == False
    
    def test_artifact_model_attributes(self):
        """Test Artifact model has required attributes."""
        from models import Artifact
        
        artifact = Artifact(
            filing_id=1,
            artifact_type="html",
            filename="test.htm",
            local_path="NASDAQ/AAPL/2023/test.html",
            url="https://sec.gov/test.htm",
            status="pending_download",
            retry_count=0,
            max_retries=3
        )
        
        assert artifact.artifact_type == "html"
        assert artifact.status == "pending_download"
        assert artifact.retry_count == 0
        assert artifact.max_retries == 3


class TestJobLogic:
    """Test ETL job logic."""
    
    def test_determine_fiscal_period_10k(self):
        """Test fiscal period determination for 10-K."""
        from jobs.backfill import BackfillJob
        
        job = BackfillJob()
        period = job.determine_fiscal_period("10-K", "2023-12-31")
        assert period == "FY"
        
        period = job.determine_fiscal_period("10-K/A", "2023-12-31")
        assert period == "FY"
    
    def test_determine_fiscal_period_10q(self):
        """Test fiscal period determination for 10-Q by quarter."""
        from jobs.backfill import BackfillJob
        
        job = BackfillJob()
        
        # Q1 (Jan-Mar)
        assert job.determine_fiscal_period("10-Q", "2023-03-31") == "Q1"
        
        # Q2 (Apr-Jun)
        assert job.determine_fiscal_period("10-Q", "2023-06-30") == "Q2"
        
        # Q3 (Jul-Sep)
        assert job.determine_fiscal_period("10-Q", "2023-09-30") == "Q3"
        
        # Q4 (Oct-Dec)
        assert job.determine_fiscal_period("10-Q", "2023-12-31") == "Q4"


class TestConfiguration:
    """Test configuration and settings."""
    
    def test_settings_loads_defaults(self):
        """Test that settings have sensible defaults."""
        from config.settings import Settings
        
        # Create settings without env vars
        settings = Settings(
            sec_user_agent="TestCompany test@test.com"  # Required field
        )
        
        assert settings.db_host == "localhost"
        assert settings.db_port == 5432
        assert settings.storage_backend == "local"
        assert settings.sec_rate_limit == 10
        assert settings.max_workers == 10
    
    def test_settings_validates_user_agent(self):
        """Test that invalid User-Agent is rejected."""
        from config.settings import Settings
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            Settings(sec_user_agent="MyCompany legal@example.com")  # Example address not allowed
    
    def test_database_url_construction(self):
        """Test database URL is constructed correctly."""
        from config.settings import Settings
        
        settings = Settings(
            sec_user_agent="TestCompany test@test.com",
            db_host="testhost",
            db_port=5433,
            db_name="testdb",
            db_user="testuser",
            db_password="testpass"
        )
        
        expected = "postgresql+psycopg://testuser:testpass@testhost:5433/testdb"
        assert settings.database_url == expected
    
    def test_sla_duration_seconds_conversion(self):
        """Test SLA duration converts hours to seconds."""
        from config.settings import Settings
        
        settings = Settings(
            sec_user_agent="TestCompany test@test.com",
            sla_duration_hours=6
        )
        
        assert settings.sla_duration_seconds == 21600  # 6 * 3600


# Integration-style test (requires mocking)
class TestIntegration:
    """Integration tests with mocking."""
    
    @patch('services.sec_api.httpx.Client')
    def test_sec_client_respects_rate_limit(self, mock_client):
        """Test that SEC client respects rate limiting."""
        from services.sec_api import SECAPIClient
        import time
        
        # Mock response
        mock_response = Mock()
        mock_response.json.return_value = {"test": "data"}
        mock_client.return_value.__enter__.return_value.get.return_value = mock_response
        
        client = SECAPIClient()
        
        # Make multiple requests
        start = time.time()
        for _ in range(3):
            try:
                client._make_request("https://test.com")
            except:
                pass  # We're just testing timing
        
        elapsed = time.time() - start
        
        # Should take at least 0.2 seconds for 3 requests at 10 req/sec
        assert elapsed >= 0.15  # Allow some tolerance


def run_tests():
    """Run all tests with pytest."""
    import sys
    exit_code = pytest.main([__file__, '-v', '--tb=short'])
    sys.exit(exit_code)


if __name__ == '__main__':
    run_tests()
