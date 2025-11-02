"""
Artifact downloader service.
Handles downloading HTML, images, and XBRL files with deduplication.
"""
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import httpx
import structlog
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from config.settings import settings
from models import Artifact, Filing, ErrorLog
from services.sec_api import SECAPIClient
from services.storage import storage_service
from utils import sha256_bytes

logger = structlog.get_logger()

# SEC base URL for resolving relative URLs
SEC_BASE_URL = "https://www.sec.gov"


def extract_image_urls(html_bytes: bytes) -> List[str]:
    """
    Pure function to extract all image URLs from HTML content.

    Args:
        html_bytes: Raw HTML content as bytes

    Returns:
        List of image URLs (may contain both absolute and relative URLs)

    Example:
        >>> html = b'<html><img src="/arch/img.gif"><img src="http://ex.com/img.png"></html>'
        >>> extract_image_urls(html)
        ['/arch/img.gif', 'http://ex.com/img.png']
    """
    try:
        soup = BeautifulSoup(html_bytes, 'lxml')
        img_tags = soup.find_all('img')

        urls = []
        for img in img_tags:
            src = img.get('src')
            if src:
                urls.append(src)

        return urls
    except Exception as e:
        logger.warning("image_extraction_failed", error=str(e))
        return []


class ArtifactDownloader:
    """Service for downloading and processing filing artifacts."""

    def __init__(self):
        """Initialize downloader."""
        self.sec_client = SECAPIClient()
        logger.info("artifact_downloader_initialized")

    def download_and_record_image(
        self,
        session: Session,
        filing: Filing,
        image_url: str,
        image_seq: int,
        html_local_path: str
    ) -> Optional[Artifact]:
        """
        Download a single image and create database record.

        Args:
            session: Database session
            filing: Parent filing object
            image_url: Full absolute URL to image (already resolved)
            image_seq: Sequence number for naming (1-based)
            html_local_path: Local path of HTML file (for constructing image path)

        Returns:
            Created Artifact object or None if skipped/failed

        Idempotency:
            Checks for existing (filing_id, url) pair before downloading
        """
        # image_url should already be resolved to absolute URL by caller
        full_url = image_url

        # Check if already exists (idempotency)
        existing = session.query(Artifact).filter(
            Artifact.filing_id == filing.id,
            Artifact.url == full_url
        ).first()

        if existing:
            logger.debug(
                "image_already_exists",
                filing_id=filing.id,
                url=full_url,
                artifact_id=existing.id
            )
            return None

        # Extract extension from URL
        parsed_url = urlparse(full_url)
        url_path = parsed_url.path
        ext = Path(url_path).suffix or '.png'

        # Construct local path using same prefix as HTML
        # html_local_path format: NYSE/LOW/2025/LOW_2025_Q3_28-08-2025.html
        # image format:          NYSE/LOW/2025/LOW_2025_Q3_28-08-2025_image-001.gif
        html_base = html_local_path.rsplit('.', 1)[0]  # Remove .html
        local_path = f"{html_base}_image-{image_seq:03d}{ext}"

        try:
            # Download image content
            logger.debug("downloading_image", url=full_url, seq=image_seq)
            response = httpx.get(
                full_url,
                headers={"User-Agent": settings.sec_user_agent},
                timeout=settings.sec_timeout,
                follow_redirects=True
            )
            response.raise_for_status()

            content = response.content
            file_size = len(content)
            sha256_hash = sha256_bytes(content)

            # Check for duplicate content
            duplicate = session.query(Artifact).filter(
                Artifact.sha256 == sha256_hash,
                Artifact.status.in_(['downloaded', 'skipped'])
            ).first()

            if duplicate:
                logger.info(
                    "image_deduplicated",
                    filing_id=filing.id,
                    url=full_url,
                    existing_sha256=sha256_hash,
                    reusing_artifact_id=duplicate.id
                )
                # Create artifact record for current filing, but reuse file from duplicate
                artifact = Artifact(
                    filing_id=filing.id,
                    artifact_type='image',
                    filename=Path(url_path).name,
                    local_path=duplicate.local_path,  # Reuse existing file path
                    url=full_url,
                    file_size=duplicate.file_size,
                    sha256=sha256_hash,
                    status='skipped',  # Mark as skipped since file already exists
                    downloaded_at=datetime.utcnow()
                )
            else:
                # Save to storage
                success = storage_service.save_artifact(local_path, content)
                if not success:
                    raise Exception("Failed to save image to storage")

                artifact = Artifact(
                    filing_id=filing.id,
                    artifact_type='image',
                    filename=Path(url_path).name,
                    local_path=local_path,
                    url=full_url,
                    file_size=file_size,
                    sha256=sha256_hash,
                    status='downloaded',
                    downloaded_at=datetime.utcnow()
                )

            session.add(artifact)
            session.flush()  # Get artifact ID

            logger.info(
                "image_downloaded",
                filing_id=filing.id,
                artifact_id=artifact.id,
                url=full_url,
                local_path=local_path,
                size_bytes=file_size,
                status=artifact.status
            )

            return artifact

        except Exception as e:
            logger.error(
                "image_download_failed",
                filing_id=filing.id,
                url=full_url,
                error=str(e)
            )
            return None

    def download_artifact(
        self,
        session: Session,
        artifact: Artifact,
        execution_run_id: Optional[int] = None
    ) -> bool:
        """
        Download a single artifact.
        
        Args:
            session: Database session
            artifact: Artifact object to download
            execution_run_id: Current execution run ID for error logging
        
        Returns:
            Success boolean
        """
        artifact.last_attempt_at = datetime.utcnow()
        artifact.status = 'downloading'
        session.commit()
        
        try:
            # Download file content
            response = httpx.get(
                artifact.url,
                headers={"User-Agent": settings.sec_user_agent},
                timeout=settings.sec_timeout,
                follow_redirects=True
            )
            response.raise_for_status()
            
            content = response.content
            artifact.file_size = len(content)
            
            # Calculate hash
            artifact.sha256 = sha256_bytes(content)
            
            # Check for duplicate content
            existing = session.query(Artifact).filter(
                Artifact.sha256 == artifact.sha256,
                Artifact.status == 'downloaded',
                Artifact.id != artifact.id
            ).first()
            
            if existing:
                logger.info(
                    "artifact_deduplicated",
                    artifact_id=artifact.id,
                    existing_id=existing.id,
                    sha256=artifact.sha256
                )
                # Reuse existing file path
                artifact.local_path = existing.local_path
                artifact.status = 'skipped'
            else:
                # Generate local path if not set
                if not artifact.local_path:
                    filing = artifact.filing
                    company = filing.company

                    # Determine fiscal period from form type
                    fiscal_period = filing.fiscal_period if filing.fiscal_period else (
                        'FY' if filing.form_type == '10-K' else 'Q1'
                    )

                    # Format filing date as DD-MM-YYYY
                    filing_date_str = filing.filing_date.strftime('%d-%m-%Y')

                    # Construct path
                    artifact.local_path = storage_service.construct_path(
                        exchange=company.exchange,
                        ticker=company.ticker,
                        fiscal_year=filing.fiscal_year,
                        fiscal_period=fiscal_period,
                        filing_date_str=filing_date_str,
                        artifact_type=artifact.artifact_type,
                        filename=artifact.filename
                    )

                # Save to storage
                success = storage_service.save_artifact(artifact.local_path, content)
                if success:
                    artifact.status = 'downloaded'
                    artifact.downloaded_at = datetime.utcnow()
                else:
                    raise Exception("Failed to save artifact to storage")

            # If HTML artifact, extract and download referenced images
            # Process images for both 'downloaded' and 'skipped' (deduplicated) HTML
            if artifact.artifact_type == 'html' and artifact.status in ('downloaded', 'skipped'):
                logger.info("extracting_images_from_html", artifact_id=artifact.id)

                image_urls = extract_image_urls(content)

                if image_urls:
                    logger.info(
                        "images_found_in_html",
                        artifact_id=artifact.id,
                        filing_id=artifact.filing_id,
                        image_count=len(image_urls)
                    )

                    images_downloaded = 0
                    images_skipped = 0
                    images_failed = 0

                    # Use the artifact URL as base for resolving relative image URLs
                    # artifact.url format: https://www.sec.gov/Archives/edgar/data/60667/000006066725000174/low-20250801.htm
                    base_url = artifact.url

                    for seq, img_url in enumerate(image_urls, start=1):
                        # Resolve relative URLs against the HTML document's URL
                        if not img_url.startswith('http'):
                            if img_url.startswith('/'):
                                # Absolute path on SEC server
                                resolved_url = SEC_BASE_URL + img_url
                            else:
                                # Relative path - resolve against document URL
                                resolved_url = urljoin(base_url, img_url)
                        else:
                            resolved_url = img_url

                        result = self.download_and_record_image(
                            session=session,
                            filing=artifact.filing,
                            image_url=resolved_url,
                            image_seq=seq,
                            html_local_path=artifact.local_path
                        )

                        if result:
                            if result.status == 'downloaded':
                                images_downloaded += 1
                            elif result.status == 'skipped':
                                # Skipped means deduplicated (reusing existing file)
                                images_skipped += 1
                        elif result is None:
                            # None means already exists (idempotent check before download)
                            images_skipped += 1
                        else:
                            # Should not happen, but handle gracefully
                            images_failed += 1

                    logger.info(
                        "html_images_processed",
                        artifact_id=artifact.id,
                        filing_id=artifact.filing_id,
                        total=len(image_urls),
                        downloaded=images_downloaded,
                        skipped=images_skipped,
                        failed=images_failed
                    )
                else:
                    logger.debug("no_images_in_html", artifact_id=artifact.id)

            session.commit()
            logger.info("artifact_downloaded", artifact_id=artifact.id, status=artifact.status)
            return True
            
        except Exception as e:
            error_msg = str(e)
            artifact.status = 'failed'
            artifact.retry_count += 1
            artifact.error_message = error_msg
            
            # Log error
            error_log = ErrorLog(
                execution_run_id=execution_run_id,
                artifact_id=artifact.id,
                error_type=type(e).__name__,
                error_message=error_msg,
                occurred_at=datetime.utcnow()
            )
            session.add(error_log)
            session.commit()
            
            logger.error(
                "artifact_download_failed",
                artifact_id=artifact.id,
                url=artifact.url,
                error=error_msg,
                retry_count=artifact.retry_count
            )
            return False
    
    def process_html_filing(
        self,
        session: Session,
        filing: Filing,
        html_content: bytes,
        base_url: str
    ) -> List[Artifact]:
        """
        Process HTML filing to extract and create artifact records for images.
        
        Args:
            session: Database session
            filing: Filing object
            html_content: Raw HTML content
            base_url: Base URL for resolving relative links
        
        Returns:
            List of newly created image artifacts
        """
        soup = BeautifulSoup(html_content, 'lxml')
        img_tags = soup.find_all('img')
        
        image_artifacts = []
        image_seq = 1
        
        for img in img_tags:
            src = img.get('src')
            if not src:
                continue
            
            # Resolve relative URLs
            if not src.startswith('http'):
                img_url = base_url.rsplit('/', 1)[0] + '/' + src.lstrip('./')
            else:
                img_url = src
            
            # Extract original filename
            original_filename = Path(src).name
            
            # Construct local path with sequence number
            filing_date_str = filing.filing_date.strftime("%d-%m-%Y")
            company = filing.company
            
            path_template = storage_service.construct_path(
                exchange=company.exchange,
                ticker=company.ticker,
                fiscal_year=filing.fiscal_year,
                fiscal_period=filing.fiscal_period,
                filing_date_str=filing_date_str,
                artifact_type='image',
                filename=original_filename
            )
            
            # Replace {seq} with actual sequence
            ext = Path(original_filename).suffix
            local_path = path_template.replace('{seq}', f'image{image_seq:02d}')
            
            # Check if artifact already exists
            existing = session.query(Artifact).filter(
                Artifact.filing_id == filing.id,
                Artifact.url == img_url
            ).first()
            
            if not existing:
                artifact = Artifact(
                    filing_id=filing.id,
                    artifact_type='image',
                    filename=original_filename,
                    local_path=local_path,
                    url=img_url,
                    status='pending_download'
                )
                session.add(artifact)
                image_artifacts.append(artifact)
            
            image_seq += 1
        
        if image_artifacts:
            session.commit()
            logger.info(
                "images_extracted",
                filing_id=filing.id,
                count=len(image_artifacts)
            )
        
        return image_artifacts
    
    def create_xbrl_artifacts(
        self,
        session: Session,
        filing: Filing,
        cik: str,
        accession: str
    ) -> List[Artifact]:
        """
        Create artifact records for XBRL files.
        
        XBRL files are typically named:
        - {ticker}-{date}.xml (instance document)
        - {ticker}-{date}.xsd (schema)
        - {ticker}-{date}_cal.xml, _def.xml, _lab.xml, _pre.xml (linkbases)
        
        Args:
            session: Database session
            filing: Filing object
            cik: Company CIK
            accession: Accession number
        
        Returns:
            List of created XBRL artifacts
        """
        # Common XBRL file patterns
        xbrl_patterns = [
            filing.primary_document.replace('.htm', '.xml'),
            filing.primary_document.replace('.htm', '.xsd'),
            filing.primary_document.replace('.htm', '_cal.xml'),
            filing.primary_document.replace('.htm', '_def.xml'),
            filing.primary_document.replace('.htm', '_lab.xml'),
            filing.primary_document.replace('.htm', '_pre.xml'),
        ]
        
        filing_date_str = filing.filing_date.strftime("%d-%m-%Y")
        company = filing.company
        
        xbrl_artifacts = []
        
        for filename in xbrl_patterns:
            url = self.sec_client.construct_document_url(cik, accession, filename)
            
            local_path = storage_service.construct_path(
                exchange=company.exchange,
                ticker=company.ticker,
                fiscal_year=filing.fiscal_year,
                fiscal_period=filing.fiscal_period,
                filing_date_str=filing_date_str,
                artifact_type='xbrl_raw',
                filename=filename
            )
            
            # Check if already exists
            existing = session.query(Artifact).filter(
                Artifact.filing_id == filing.id,
                Artifact.filename == filename
            ).first()
            
            if not existing:
                artifact = Artifact(
                    filing_id=filing.id,
                    artifact_type='xbrl_raw',
                    filename=filename,
                    local_path=local_path,
                    url=url,
                    status='pending_download'
                )
                session.add(artifact)
                xbrl_artifacts.append(artifact)
        
        if xbrl_artifacts:
            session.commit()
            logger.info(
                "xbrl_artifacts_created",
                filing_id=filing.id,
                count=len(xbrl_artifacts)
            )
        
        return xbrl_artifacts
