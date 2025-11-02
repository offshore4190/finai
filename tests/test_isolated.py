"""
Isolated unit tests that don't require database connection.
These tests mock database operations to avoid PostgreSQL dependency.
"""
import pytest
from datetime import datetime, date
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Prevent database engine creation during imports
sys.modules['psycopg2'] = MagicMock()

# Test model classes without database
class TestModelsWithoutDB:
    """Test database models without actual database connection."""
    
    def test_company_model_structure(self):
        """Test Company model class structure."""
        # Import after mocking psycopg2
        from models import Company
        
        # Check that class has expected attributes
        assert hasattr(Company, '__tablename__')
        assert Company.__tablename__ == 'companies'
        
        # Create instance (won't persist to DB)
        company = Company()
        company.ticker = "AAPL"
        company.cik = "0000320193"
        company.company_name = "Apple Inc."
        company.exchange = "NASDAQ"
        
        assert company.ticker == "AAPL"
        assert company.cik == "0000320193"
    
    def test_filing_model_structure(self):
        """Test Filing model class structure."""
        from models import Filing
        
        assert hasattr(Filing, '__tablename__')
        assert Filing.__tablename__ == 'filings'
        
        filing = Filing()
        filing.accession_number = "0001234567-23-000123"
        filing.form_type = "10-K"
        filing.fiscal_year = 2023
        
        assert filing.accession_number == "0001234567-23-000123"
        assert filing.form_type == "10-K"
    
    def test_artifact_model_structure(self):
        """Test Artifact model class structure."""
        from models import Artifact
        
        assert hasattr(Artifact, '__tablename__')
        assert Artifact.__tablename__ == 'artifacts'
        
        artifact = Artifact()
        artifact.artifact_type = "html"
        artifact.status = "pending_download"
        artifact.retry_count = 0
        
        assert artifact.artifact_type == "html"
        assert artifact.retry_count == 0


class TestJobLogicIsolated:
    """Test job logic without database."""
    
    def test_fiscal_period_determination_10k(self):
        """Test fiscal period for 10-K forms."""
        # Mock the database imports
        with patch.dict('sys.modules', {
            'config.db': MagicMock(),
            'models': MagicMock()
        }):
            from jobs.backfill import BackfillJob
            
            job = BackfillJob()
            
            # 10-K should always return FY
            assert job.determine_fiscal_period("10-K", "2023-12-31") == "FY"
            assert job.determine_fiscal_period("10-K/A", "2023-03-31") == "FY"
    
    def test_fiscal_period_determination_10q_quarters(self):
        """Test fiscal period for 10-Q by quarter."""
        with patch.dict('sys.modules', {
            'config.db': MagicMock(),
            'models': MagicMock()
        }):
            from jobs.backfill import BackfillJob
            
            job = BackfillJob()
            
            # Test each quarter
            assert job.determine_fiscal_period("10-Q", "2023-01-31") == "Q1"  # January
            assert job.determine_fiscal_period("10-Q", "2023-03-31") == "Q1"  # March
            assert job.determine_fiscal_period("10-Q", "2023-04-30") == "Q2"  # April
            assert job.determine_fiscal_period("10-Q", "2023-06-30") == "Q2"  # June
            assert job.determine_fiscal_period("10-Q", "2023-07-31") == "Q3"  # July
            assert job.determine_fiscal_period("10-Q", "2023-09-30") == "Q3"  # September
            assert job.determine_fiscal_period("10-Q", "2023-10-31") == "Q4"  # October
            assert job.determine_fiscal_period("10-Q", "2023-12-31") == "Q4"  # December
    
    def test_fiscal_period_no_report_date(self):
        """Test default fiscal period when no report date."""
        with patch.dict('sys.modules', {
            'config.db': MagicMock(),
            'models': MagicMock()
        }):
            from jobs.backfill import BackfillJob
            
            job = BackfillJob()
            
            # Should default to Q4
            assert job.determine_fiscal_period("10-Q", None) == "Q4"


def run_isolated_tests():
    """Run isolated tests that don't require database."""
    import sys
    exit_code = pytest.main([__file__, '-v', '--tb=short'])
    sys.exit(exit_code)


if __name__ == '__main__':
    run_isolated_tests()
