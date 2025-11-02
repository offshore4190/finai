"""
Listings Reference Sync Job
Downloads and syncs NASDAQ and NYSE listing reference data.
"""
from datetime import datetime
from typing import List, Dict
import io

import httpx
import structlog

from config.db import get_db_session
from models import ListingsRef, ExecutionRun

logger = structlog.get_logger()


class ListingsRefSyncJob:
    """Job to sync exchange reference data from NASDAQ/NYSE listing files."""

    # NASDAQ listing file URLs
    NASDAQ_LISTED_URL = "ftp://ftp.nasdaqtrader.com/symboldirectory/nasdaqlisted.txt"
    OTHER_LISTED_URL = "ftp://ftp.nasdaqtrader.com/symboldirectory/otherlisted.txt"

    # Exchange code mappings from otherlisted.txt
    EXCHANGE_CODE_MAP = {
        'N': 'NYSE',
        'A': 'NYSE American',
        'P': 'NYSE Arca',
        'Z': 'BATS',
        'V': 'IEX'
    }

    def __init__(self):
        """Initialize job."""
        pass

    def run(self):
        """Execute listings reference sync job."""
        logger.info("listings_ref_sync_started")

        with get_db_session() as session:
            # Create execution run
            run = ExecutionRun(
                run_type='listings_ref_sync',
                started_at=datetime.utcnow(),
                status='running'
            )
            session.add(run)
            session.commit()

            try:
                # Fetch both listing files
                nasdaq_data = self._fetch_nasdaq_listed()
                other_data = self._fetch_other_listed()

                # Parse both files
                nasdaq_listings = self._parse_nasdaq_listed(nasdaq_data)
                other_listings = self._parse_other_listed(other_data)

                # Truncate existing data (idempotent)
                logger.info("truncating_listings_ref_table")
                session.query(ListingsRef).delete()
                session.commit()

                # Insert NASDAQ listings
                nasdaq_count = 0
                for listing in nasdaq_listings:
                    ref = ListingsRef(
                        symbol=listing['symbol'],
                        exchange_code='Q',  # NASDAQ code
                        exchange_name='NASDAQ',
                        is_etf=listing['is_etf'],
                        source='nasdaqlisted',
                        file_time=listing.get('file_time'),
                        created_at=datetime.utcnow()
                    )
                    session.add(ref)
                    nasdaq_count += 1

                session.commit()
                logger.info("nasdaq_listings_inserted", count=nasdaq_count)

                # Insert other exchange listings
                other_count = 0
                for listing in other_listings:
                    ref = ListingsRef(
                        symbol=listing['symbol'],
                        exchange_code=listing['exchange_code'],
                        exchange_name=listing['exchange_name'],
                        is_etf=listing['is_etf'],
                        source='otherlisted',
                        file_time=listing.get('file_time'),
                        created_at=datetime.utcnow()
                    )
                    session.add(ref)
                    other_count += 1

                session.commit()
                logger.info("other_listings_inserted", count=other_count)

                # Update execution run
                run.completed_at = datetime.utcnow()
                run.status = 'completed'
                run.duration_seconds = int((run.completed_at - run.started_at).total_seconds())
                run.meta_data = {
                    'nasdaq_listings': nasdaq_count,
                    'other_listings': other_count,
                    'total_listings': nasdaq_count + other_count
                }
                session.commit()

                logger.info(
                    "listings_ref_sync_completed",
                    nasdaq_count=nasdaq_count,
                    other_count=other_count,
                    total=nasdaq_count + other_count,
                    duration_seconds=run.duration_seconds
                )

            except Exception as e:
                run.status = 'failed'
                run.error_summary = str(e)
                run.completed_at = datetime.utcnow()
                session.commit()

                logger.error("listings_ref_sync_failed", error=str(e), exc_info=True)
                raise

    def _fetch_nasdaq_listed(self) -> str:
        """
        Fetch NASDAQ listed companies file.

        Returns:
            Raw file content as string
        """
        logger.info("fetching_nasdaq_listed", url=self.NASDAQ_LISTED_URL)

        # FTP URLs need special handling - use HTTP alternative
        http_url = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"

        try:
            response = httpx.get(http_url, timeout=30.0, follow_redirects=True)
            response.raise_for_status()
            content = response.text
            logger.info("nasdaq_listed_fetched", size=len(content))
            return content
        except Exception as e:
            logger.error("nasdaq_listed_fetch_failed", error=str(e))
            raise

    def _fetch_other_listed(self) -> str:
        """
        Fetch other exchange listed companies file.

        Returns:
            Raw file content as string
        """
        logger.info("fetching_other_listed", url=self.OTHER_LISTED_URL)

        # FTP URLs need special handling - use HTTP alternative
        http_url = "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt"

        try:
            response = httpx.get(http_url, timeout=30.0, follow_redirects=True)
            response.raise_for_status()
            content = response.text
            logger.info("other_listed_fetched", size=len(content))
            return content
        except Exception as e:
            logger.error("other_listed_fetch_failed", error=str(e))
            raise

    def _parse_nasdaq_listed(self, content: str) -> List[Dict]:
        """
        Parse NASDAQ listed file.

        Format: Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares

        Args:
            content: Raw file content

        Returns:
            List of parsed listings
        """
        listings = []
        lines = content.strip().split('\n')

        # First line is header, last line is file creation time
        header = lines[0]
        file_time_line = lines[-1] if lines else None

        # Parse file creation time if available
        file_time = None
        if file_time_line and 'File Creation Time' in file_time_line:
            # Extract timestamp if possible
            try:
                time_str = file_time_line.split(':')[1].strip()
                file_time = datetime.strptime(time_str, '%m%d%Y%H%M%S')
            except:
                pass

        # Parse data lines (skip header and footer)
        for line in lines[1:-1]:
            if not line.strip():
                continue

            parts = line.split('|')
            if len(parts) < 8:
                continue

            symbol = parts[0].strip()
            etf = parts[6].strip()

            # Skip test issues
            test_issue = parts[3].strip()
            if test_issue == 'Y':
                continue

            listings.append({
                'symbol': symbol,
                'is_etf': etf == 'Y',
                'file_time': file_time
            })

        logger.info("nasdaq_listed_parsed", count=len(listings))
        return listings

    def _parse_other_listed(self, content: str) -> List[Dict]:
        """
        Parse other exchange listed file.

        Format: ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol

        Args:
            content: Raw file content

        Returns:
            List of parsed listings
        """
        listings = []
        lines = content.strip().split('\n')

        # First line is header, last line is file creation time
        header = lines[0]
        file_time_line = lines[-1] if lines else None

        # Parse file creation time if available
        file_time = None
        if file_time_line and 'File Creation Time' in file_time_line:
            try:
                time_str = file_time_line.split(':')[1].strip()
                file_time = datetime.strptime(time_str, '%m%d%Y%H%M%S')
            except:
                pass

        # Parse data lines (skip header and footer)
        for line in lines[1:-1]:
            if not line.strip():
                continue

            parts = line.split('|')
            if len(parts) < 7:
                continue

            symbol = parts[0].strip()
            exchange_code = parts[2].strip()
            etf = parts[4].strip()
            test_issue = parts[6].strip() if len(parts) > 6 else 'N'

            # Skip test issues
            if test_issue == 'Y':
                continue

            # Map exchange code to name
            exchange_name = self.EXCHANGE_CODE_MAP.get(exchange_code, f'OTHER-{exchange_code}')

            listings.append({
                'symbol': symbol,
                'exchange_code': exchange_code,
                'exchange_name': exchange_name,
                'is_etf': etf == 'Y',
                'file_time': file_time
            })

        logger.info("other_listed_parsed", count=len(listings))
        return listings


def main():
    """Main entry point."""
    job = ListingsRefSyncJob()
    job.run()


if __name__ == '__main__':
    main()
