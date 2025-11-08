"""
SEC EDGAR API client for fetching company and filing data.
"""
import json
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urljoin

import httpx
import structlog

from config.settings import settings
from utils.rate_limiter import SECRateLimiter
from utils import retry_with_backoff

logger = structlog.get_logger()


class SECAPIClient:
    """Client for SEC EDGAR API interactions."""
    
    BASE_URL = "https://www.sec.gov"
    DATA_URL = "https://data.sec.gov"
    
    def __init__(self):
        """Initialize SEC API client."""
        self.rate_limiter = SECRateLimiter(requests_per_second=settings.sec_rate_limit)
        self.headers = {
            "User-Agent": settings.sec_user_agent,
            "Accept": "application/json"
        }
        self.timeout = httpx.Timeout(settings.sec_timeout, read=60.0)
        
        logger.info("sec_api_client_initialized", user_agent=settings.sec_user_agent)
    
    def _make_request(self, url: str, stream: bool = False) -> httpx.Response:
        """
        Make rate-limited HTTP request to SEC.
        
        Args:
            url: Full URL to request
            stream: Whether to stream the response
        
        Returns:
            Response object
        
        Raises:
            httpx.HTTPError: On request failure
        """
        self.rate_limiter.wait()
        
        with httpx.Client(timeout=self.timeout, follow_redirects=True, http2=False) as client:
            response = client.get(url, headers=self.headers, follow_redirects=True)
            response.raise_for_status()
            return response
    
    @retry_with_backoff(max_attempts=3, initial_delay=10.0, exceptions=(httpx.HTTPError,))
    def fetch_company_tickers(self) -> Dict[str, Dict]:
        """
        Fetch all company tickers from SEC.
        
        Returns:
            Dictionary mapping CIK to company info:
            {
                "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
                ...
            }
        """
        url = f"{self.BASE_URL}/files/company_tickers.json"
        logger.info("fetching_company_tickers", url=url)
        
        response = self._make_request(url)
        data = response.json()
        
        logger.info("company_tickers_fetched", count=len(data))
        return data
    
    @retry_with_backoff(max_attempts=3, initial_delay=10.0, exceptions=(httpx.HTTPError,))
    def fetch_company_submissions(self, cik: str) -> Dict:
        """
        Fetch all submissions for a company.

        Args:
            cik: Company CIK (will be zero-padded to 10 digits)

        Returns:
            Submissions JSON data containing filings metadata
        """
        # SEC API requires CIK zero-padded to 10 digits
        cik_padded = cik.zfill(10)
        url = f"{self.DATA_URL}/submissions/CIK{cik_padded}.json"

        logger.debug("fetching_submissions", cik=cik, cik_padded=cik_padded, url=url)

        response = self._make_request(url)
        data = response.json()

        return data
    
    def download_file(self, url: str, output_path: str, chunk_size: int = 8192) -> int:
        """
        Download a file from SEC to local path.
        
        Args:
            url: URL to download
            output_path: Local path to save file
            chunk_size: Size of download chunks
        
        Returns:
            File size in bytes
        """
        self.rate_limiter.wait()
        
        logger.debug("downloading_file", url=url, output=output_path)
        
        with httpx.Client(timeout=self.timeout, follow_redirects=True, http2=False) as client:
            with client.stream("GET", url, headers=self.headers, follow_redirects=True) as response:
                response.raise_for_status()
                
                total_size = 0
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_bytes(chunk_size=chunk_size):
                        f.write(chunk)
                        total_size += len(chunk)
        
        logger.debug("file_downloaded", url=url, size_bytes=total_size)
        return total_size
    
    def construct_document_url(self, cik: str, accession: str, filename: str) -> str:
        """
        Construct URL for a specific document.

        Args:
            cik: Company CIK
            accession: Accession number (format: 0001234567-23-000123)
            filename: Document filename

        Returns:
            Full URL to document

        Example:
            https://www.sec.gov/Archives/edgar/data/320193/000032019323000123/aapl-20230930.htm
        """
        # Remove dashes from accession number for URL path
        accession_clean = accession.replace('-', '')
        cik_clean = cik.lstrip('0')  # Remove leading zeros

        url = f"{self.BASE_URL}/Archives/edgar/data/{cik_clean}/{accession_clean}/{filename}"
        return url

    def get_primary_document_from_index(self, cik: str, accession: str) -> Optional[str]:
        """
        从filing index页面获取主文档文件名

        当SEC API的submissions数据中primaryDocument字段为空时，
        通过访问filing的index页面来获取实际的主文档文件名。

        Args:
            cik: 公司CIK（可以带前导零）
            accession: Accession number (格式: 0000950170-25-040545)

        Returns:
            主文档文件名，如 "sndl-20241231.htm" 或 "abevform20f_2023.htm"
            如果找不到，返回 None
        """
        # 构造index页面URL
        accession_clean = accession.replace('-', '')
        cik_clean = cik.lstrip('0')

        index_url = f"{self.BASE_URL}/Archives/edgar/data/{cik_clean}/{accession_clean}/{accession}-index.htm"

        logger.debug("fetching_index_page", url=index_url, cik=cik, accession=accession)

        try:
            # 下载index页面
            response = self._make_request(index_url)
            html_content = response.text

            # 解析HTML找到主文档
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'lxml')

            # 查找Document Format Files表格
            htm_files = []

            # 查找所有指向.htm/.html的链接
            for link in soup.find_all('a'):
                href = link.get('href', '')

                if (href.endswith('.htm') or href.endswith('.html')) and \
                   'index' not in href.lower() and \
                   not href.startswith('http'):

                    htm_files.append(href)

            if htm_files:
                # 策略：选择文件名最长的.htm文件
                primary = max(htm_files, key=len)

                logger.info(
                    "primary_document_found_from_index",
                    accession=accession,
                    filename=primary,
                    total_htm_files=len(htm_files),
                    all_files=htm_files
                )

                return primary
            else:
                logger.warning(
                    "no_htm_files_found_in_index",
                    accession=accession,
                    index_url=index_url
                )
                return None

        except Exception as e:
            logger.error(
                "index_parsing_failed",
                accession=accession,
                index_url=index_url,
                error=str(e),
                exc_info=True
            )
            return None

    def parse_filings(
        self,
        submissions_data: Dict,
        form_types: List[str],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Parse filings from submissions data.
        
        Args:
            submissions_data: Data from fetch_company_submissions
            form_types: List of form types to include (e.g., ['10-K', '10-Q'])
            start_date: Filter filings on or after this date
            end_date: Filter filings before or on this date
        
        Returns:
            List of filing dictionaries with relevant metadata
        """
        filings = []
        
        recent_filings = submissions_data.get('filings', {}).get('recent', {})
        if not recent_filings:
            return filings
        
        # Parse recent filings
        for i in range(len(recent_filings.get('accessionNumber', []))):
            form = recent_filings['form'][i]
            
            # Filter by form type
            if form not in form_types:
                continue
            
            filing_date_str = recent_filings['filingDate'][i]
            filing_date = datetime.strptime(filing_date_str, '%Y-%m-%d').date()
            
            # Filter by date range
            if start_date and filing_date < start_date.date():
                continue
            if end_date and filing_date > end_date.date():
                continue
            
            filing = {
                'accession_number': recent_filings['accessionNumber'][i],
                'form_type': form,
                'filing_date': filing_date,
                'report_date': recent_filings.get('reportDate', [None] * len(recent_filings['accessionNumber']))[i],
                'primary_document': recent_filings['primaryDocument'][i],
                'is_amendment': form.endswith('/A')
            }
            
            filings.append(filing)
        
        logger.debug("filings_parsed", count=len(filings))
        return filings
