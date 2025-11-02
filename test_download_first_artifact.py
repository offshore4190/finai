#!/usr/bin/env python
"""
Test script to download the first artifact from the backfill.
"""
import os
import structlog
from datetime import datetime
from pathlib import Path

from config.db import get_db_session
from models import Artifact, Filing, Company, ExecutionRun
from services.downloader import ArtifactDownloader
from services.storage import storage_service

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


def test_download_first_artifact():
    """Download and verify the first artifact."""

    print("=" * 80)
    print("DOWNLOAD TEST: First Artifact")
    print("=" * 80)
    print()

    with get_db_session() as session:
        # Get first pending artifact
        artifact = session.query(Artifact).filter(
            Artifact.status == 'pending_download'
        ).first()

        if not artifact:
            print("ERROR: No pending artifacts found!")
            return False

        # Get related objects
        filing = artifact.filing
        company = filing.company

        # Display artifact info
        print("ARTIFACT DETAILS:")
        print(f"  ID: {artifact.id}")
        print(f"  Company: {company.ticker} ({company.company_name})")
        print(f"  CIK: {company.cik}")
        print(f"  Exchange: {company.exchange}")
        print(f"  Form: {filing.form_type}")
        print(f"  Filing Date: {filing.filing_date}")
        print(f"  Fiscal Year: {filing.fiscal_year}")
        print(f"  Fiscal Period: {filing.fiscal_period}")
        print(f"  Filename: {artifact.filename}")
        print(f"  Type: {artifact.artifact_type}")
        print(f"  URL: {artifact.url}")
        print(f"  Local Path: {artifact.local_path}")
        print(f"  Status: {artifact.status}")
        print()

        # Create execution run for tracking
        run = ExecutionRun(
            run_type='download_test',
            started_at=datetime.utcnow(),
            status='running',
            meta_data={'test': 'first_artifact'}
        )
        session.add(run)
        session.commit()

        print("=" * 80)
        print("Starting download...")
        print("=" * 80)
        print()

        # Download the artifact
        downloader = ArtifactDownloader()

        try:
            success = downloader.download_artifact(session, artifact, run.id)

            # Refresh to get updated values
            session.refresh(artifact)

            if success:
                print("=" * 80)
                print("✓ DOWNLOAD SUCCESSFUL")
                print("=" * 80)
                print()
                print("DOWNLOAD RESULTS:")
                print(f"  Status: {artifact.status}")
                print(f"  File Size: {artifact.file_size:,} bytes ({artifact.file_size / 1024:.2f} KB)")
                print(f"  SHA256: {artifact.sha256}")
                print(f"  Downloaded At: {artifact.downloaded_at}")
                print(f"  Local Path: {artifact.local_path}")
                print()

                # Verify file exists
                storage_root = os.environ.get('STORAGE_ROOT', '/tmp/filings')
                full_path = Path(storage_root) / artifact.local_path

                if full_path.exists():
                    file_size = full_path.stat().st_size
                    print("FILE VERIFICATION:")
                    print(f"  ✓ File exists at: {full_path}")
                    print(f"  ✓ File size on disk: {file_size:,} bytes")
                    print(f"  ✓ Size matches DB: {file_size == artifact.file_size}")

                    # Show first few lines of content
                    print()
                    print("FILE PREVIEW (first 500 chars):")
                    print("-" * 80)
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        preview = f.read(500)
                        print(preview)
                        if len(preview) >= 500:
                            print("...")
                    print("-" * 80)
                else:
                    print("✗ ERROR: File not found on disk!")
                    success = False

                # Update execution run
                run.status = 'completed'
                run.completed_at = datetime.utcnow()
                run.duration_seconds = int((run.completed_at - run.started_at).total_seconds())
                run.artifacts_succeeded = 1
                session.commit()

            else:
                print("=" * 80)
                print("✗ DOWNLOAD FAILED")
                print("=" * 80)
                print(f"  Status: {artifact.status}")
                if artifact.error_message:
                    print(f"  Error: {artifact.error_message}")

                run.status = 'failed'
                run.completed_at = datetime.utcnow()
                run.artifacts_failed = 1
                session.commit()

            return success

        except Exception as e:
            logger.error("download_test_failed", error=str(e), exc_info=True)
            print()
            print("=" * 80)
            print(f"✗ EXCEPTION: {str(e)}")
            print("=" * 80)

            run.status = 'failed'
            run.error_summary = str(e)
            run.completed_at = datetime.utcnow()
            session.commit()

            return False


if __name__ == '__main__':
    try:
        success = test_download_first_artifact()
        exit(0 if success else 1)
    except Exception as e:
        logger.error("test_failed", error=str(e), exc_info=True)
        exit(1)
