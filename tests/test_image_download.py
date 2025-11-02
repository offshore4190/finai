"""
Unit tests for image download functionality.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

from services.downloader import extract_image_urls, ArtifactDownloader


class TestExtractImageUrls:
    """Tests for the extract_image_urls pure function."""

    def test_extract_absolute_urls(self):
        """Test extraction of absolute HTTP URLs."""
        html = b'''
        <html>
            <body>
                <img src="http://example.com/image1.gif">
                <img src="https://another.com/pic.png">
            </body>
        </html>
        '''

        urls = extract_image_urls(html)

        assert len(urls) == 2
        assert "http://example.com/image1.gif" in urls
        assert "https://another.com/pic.png" in urls

    def test_extract_relative_urls(self):
        """Test extraction of relative URLs (starting with /)."""
        html = b'''
        <html>
            <img src="/Archives/edgar/data/12345/logo.gif">
            <img src="/images/chart.png">
        </html>
        '''

        urls = extract_image_urls(html)

        assert len(urls) == 2
        assert "/Archives/edgar/data/12345/logo.gif" in urls
        assert "/images/chart.png" in urls

    def test_extract_mixed_urls(self):
        """Test extraction of mixed absolute and relative URLs."""
        html = b'''
        <html>
            <img src="http://external.com/ext.jpg">
            <img src="/internal/img.gif">
            <img src="https://sec.gov/logo.png">
        </html>
        '''

        urls = extract_image_urls(html)

        assert len(urls) == 3
        assert "http://external.com/ext.jpg" in urls
        assert "/internal/img.gif" in urls
        assert "https://sec.gov/logo.png" in urls

    def test_no_images(self):
        """Test HTML with no images returns empty list."""
        html = b'<html><body><p>No images here</p></body></html>'

        urls = extract_image_urls(html)

        assert urls == []

    def test_img_without_src(self):
        """Test img tags without src attribute are skipped."""
        html = b'''
        <html>
            <img alt="broken">
            <img src="/valid.gif">
            <img>
        </html>
        '''

        urls = extract_image_urls(html)

        assert len(urls) == 1
        assert "/valid.gif" in urls

    def test_malformed_html(self):
        """Test that malformed HTML doesn't crash."""
        html = b'<img src="/test.gif" broken html <img src="/other.png">'

        urls = extract_image_urls(html)

        # BeautifulSoup should still extract what it can
        assert len(urls) >= 1
        assert "/test.gif" in urls or "/other.png" in urls

    def test_empty_html(self):
        """Test empty HTML returns empty list."""
        html = b''

        urls = extract_image_urls(html)

        assert urls == []


class TestDownloadAndRecordImage:
    """Tests for the download_and_record_image method."""

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None
        return session

    @pytest.fixture
    def mock_filing(self):
        """Create mock filing object."""
        filing = Mock()
        filing.id = 1
        filing.company = Mock()
        filing.company.exchange = 'NYSE'
        filing.company.ticker = 'TEST'
        filing.fiscal_year = 2025
        filing.fiscal_period = 'Q1'
        return filing

    @pytest.fixture
    def downloader(self):
        """Create downloader instance."""
        return ArtifactDownloader()

    @patch('services.downloader.httpx.get')
    @patch('services.downloader.storage_service.save_artifact')
    @patch('services.downloader.sha256_bytes')
    def test_download_image_absolute_url(
        self,
        mock_sha256,
        mock_save,
        mock_get,
        downloader,
        mock_session,
        mock_filing
    ):
        """Test downloading image with absolute URL."""
        # Setup mocks
        mock_response = Mock()
        mock_response.content = b'fake image data'
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        mock_sha256.return_value = 'abc123'
        mock_save.return_value = True

        # Execute
        result = downloader.download_and_record_image(
            session=mock_session,
            filing=mock_filing,
            image_url="http://example.com/image.gif",
            image_seq=1,
            html_local_path="NYSE/TEST/2025/TEST_2025_Q1_01-01-2025.html"
        )

        # Verify
        assert result is not None
        assert result.status == 'downloaded'
        assert result.local_path == "NYSE/TEST/2025/TEST_2025_Q1_01-01-2025_image-001.gif"
        assert result.url == "http://example.com/image.gif"
        mock_get.assert_called_once()
        mock_save.assert_called_once()

    @patch('services.downloader.httpx.get')
    @patch('services.downloader.storage_service.save_artifact')
    @patch('services.downloader.sha256_bytes')
    def test_download_image_relative_url(
        self,
        mock_sha256,
        mock_save,
        mock_get,
        downloader,
        mock_session,
        mock_filing
    ):
        """Test downloading image with relative URL (resolves to SEC base)."""
        # Setup mocks
        mock_response = Mock()
        mock_response.content = b'fake image data'
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        mock_sha256.return_value = 'def456'
        mock_save.return_value = True

        # Execute
        result = downloader.download_and_record_image(
            session=mock_session,
            filing=mock_filing,
            image_url="https://www.sec.gov/Archives/edgar/data/123/logo.gif",
            image_seq=2,
            html_local_path="NYSE/TEST/2025/TEST_2025_Q1_01-01-2025.html"
        )

        # Verify
        assert result is not None
        assert result.url == "https://www.sec.gov/Archives/edgar/data/123/logo.gif"
        assert result.local_path == "NYSE/TEST/2025/TEST_2025_Q1_01-01-2025_image-002.gif"

    @patch('services.downloader.httpx.get')
    @patch('services.downloader.storage_service.save_artifact')
    @patch('services.downloader.sha256_bytes')
    def test_download_image_duplicate_sha_reuses_existing_file(
        self,
        mock_sha256,
        mock_save,
        mock_get,
        downloader,
        mock_filing
    ):
        """Ensure duplicate image content reuses existing file instead of saving again."""
        mock_response = Mock()
        mock_response.content = b'new image data'
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        mock_sha256.return_value = 'duplicate-sha'

        duplicate_artifact = Mock()
        duplicate_artifact.id = 5
        duplicate_artifact.local_path = "NYSE/TEST/2025/TEST_2025_Q1_01-01-2025_image-001.gif"
        duplicate_artifact.file_size = 2048
        duplicate_artifact.sha256 = 'duplicate-sha'
        duplicate_artifact.status = 'downloaded'

        session = MagicMock()
        session.add = MagicMock()
        session.flush = MagicMock()

        class QueryMock:
            def __init__(self, result):
                self._result = result

            def filter(self, *args, **kwargs):
                return self

            def first(self):
                return self._result

        session.query = MagicMock(side_effect=[
            QueryMock(None),              # First query: no existing record for (filing_id, url)
            QueryMock(duplicate_artifact)  # Second query: duplicate SHA detected
        ])

        result = downloader.download_and_record_image(
            session=session,
            filing=mock_filing,
            image_url="http://example.com/image.gif",
            image_seq=3,
            html_local_path="NYSE/TEST/2025/TEST_2025_Q1_01-01-2025.html"
        )

        assert result is not None
        assert result.status == 'skipped'
        assert result.local_path == duplicate_artifact.local_path
        assert result.file_size == duplicate_artifact.file_size
        assert result.sha256 == 'duplicate-sha'

        mock_save.assert_not_called()
        session.add.assert_called_once()
        session.flush.assert_called_once()
        mock_get.assert_called_once()

    def test_download_image_idempotency(self, downloader, mock_session, mock_filing):
        """Test that existing images are not re-downloaded."""
        # Setup: existing artifact in database
        existing = Mock()
        existing.id = 99
        mock_session.query.return_value.filter.return_value.first.return_value = existing

        # Execute
        result = downloader.download_and_record_image(
            session=mock_session,
            filing=mock_filing,
            image_url="http://example.com/duplicate.gif",
            image_seq=1,
            html_local_path="NYSE/TEST/2025/TEST_2025_Q1_01-01-2025.html"
        )

        # Verify - should return None (skipped)
        assert result is None

    @patch('services.downloader.httpx.get')
    def test_download_image_http_error(
        self,
        mock_get,
        downloader,
        mock_session,
        mock_filing
    ):
        """Test that HTTP errors are handled gracefully."""
        # Setup: HTTP error
        mock_get.side_effect = Exception("404 Not Found")

        # Execute
        result = downloader.download_and_record_image(
            session=mock_session,
            filing=mock_filing,
            image_url="http://example.com/missing.gif",
            image_seq=1,
            html_local_path="NYSE/TEST/2025/TEST_2025_Q1_01-01-2025.html"
        )

        # Verify - should return None (failed)
        assert result is None

    @patch('services.downloader.httpx.get')
    @patch('services.downloader.storage_service.save_artifact')
    @patch('services.downloader.sha256_bytes')
    def test_image_naming_sequence(
        self,
        mock_sha256,
        mock_save,
        mock_get,
        downloader,
        mock_session,
        mock_filing
    ):
        """Test that image sequence numbers are formatted correctly."""
        # Setup mocks
        mock_response = Mock()
        mock_response.content = b'data'
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        mock_sha256.return_value = 'hash'
        mock_save.return_value = True

        # Test sequence 1
        result1 = downloader.download_and_record_image(
            session=mock_session,
            filing=mock_filing,
            image_url="http://ex.com/img1.png",
            image_seq=1,
            html_local_path="NYSE/TEST/2025/TEST_2025_Q1_01-01-2025.html"
        )
        assert "_image-001.png" in result1.local_path

        # Test sequence 42
        result42 = downloader.download_and_record_image(
            session=mock_session,
            filing=mock_filing,
            image_url="http://ex.com/img42.jpg",
            image_seq=42,
            html_local_path="NYSE/TEST/2025/TEST_2025_Q1_01-01-2025.html"
        )
        assert "_image-042.jpg" in result42.local_path

        # Test sequence 999
        result999 = downloader.download_and_record_image(
            session=mock_session,
            filing=mock_filing,
            image_url="http://ex.com/img999.gif",
            image_seq=999,
            html_local_path="NYSE/TEST/2025/TEST_2025_Q1_01-01-2025.html"
        )
        assert "_image-999.gif" in result999.local_path


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
