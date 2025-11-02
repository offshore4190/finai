#!/usr/bin/env python
"""
Test downloading HTML filing with automatic image extraction and download.
"""
import structlog
from pathlib import Path

from config.db import get_db_session
from models import Artifact
from services.downloader import ArtifactDownloader

# Configure logging
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


def main():
    """Download HTML filing and automatically download all referenced images."""

    print("=" * 80)
    print("DOWNLOAD TEST: HTML + AUTOMATIC IMAGE EXTRACTION")
    print("=" * 80)
    print()

    with get_db_session() as session:
        # Get artifact ID 1 (LOW Q3 2025 10-Q)
        artifact = session.query(Artifact).filter(Artifact.id == 1).first()

        if not artifact:
            print("ERROR: Artifact ID 1 not found")
            return False

        print("ARTIFACT TO DOWNLOAD:")
        print(f"  ID: {artifact.id}")
        print(f"  Company: {artifact.filing.company.ticker} ({artifact.filing.company.company_name})")
        print(f"  Form: {artifact.filing.form_type}")
        print(f"  Filing Date: {artifact.filing.filing_date}")
        print(f"  Fiscal Period: {artifact.filing.fiscal_period} {artifact.filing.fiscal_year}")
        print(f"  URL: {artifact.url}")
        print(f"  Current Status: {artifact.status}")
        print()

        # Download the HTML (images will be extracted and downloaded automatically)
        print("=" * 80)
        print("DOWNLOADING HTML (images will be auto-downloaded)...")
        print("=" * 80)
        print()

        downloader = ArtifactDownloader()
        success = downloader.download_artifact(session, artifact)

        if not success:
            print("ERROR: Download failed")
            return False

        print()
        print("=" * 80)
        print("✓ DOWNLOAD COMPLETED")
        print("=" * 80)
        print()

        # Refresh to get updated status
        session.refresh(artifact)

        print("HTML ARTIFACT:")
        print(f"  Status: {artifact.status}")
        print(f"  Size: {artifact.file_size:,} bytes ({artifact.file_size/1024:.1f} KB)")
        print(f"  SHA256: {artifact.sha256}")
        print(f"  Local Path: {artifact.local_path}")
        print()

        # Check for downloaded images
        image_artifacts = session.query(Artifact).filter(
            Artifact.filing_id == artifact.filing_id,
            Artifact.artifact_type == 'image'
        ).all()

        print("=" * 80)
        print("IMAGES AUTOMATICALLY DOWNLOADED")
        print("=" * 80)
        print()
        print(f"Total images: {len(image_artifacts)}")
        print()

        if image_artifacts:
            # Statistics
            downloaded = [img for img in image_artifacts if img.status == 'downloaded']
            skipped = [img for img in image_artifacts if img.status == 'skipped']
            failed = [img for img in image_artifacts if img.status == 'failed']

            print("STATISTICS:")
            print(f"  Downloaded: {len(downloaded)}")
            print(f"  Skipped (deduplicated): {len(skipped)}")
            print(f"  Failed: {len(failed)}")
            print()

            # Show downloaded images
            if downloaded:
                print("DOWNLOADED IMAGES:")
                storage_root = Path("/tmp/filings")

                for i, img in enumerate(downloaded, 1):
                    print(f"\n  {i}. {img.filename}")
                    print(f"     URL: {img.url}")
                    print(f"     Local Path: {img.local_path}")
                    print(f"     Size: {img.file_size:,} bytes ({img.file_size/1024:.1f} KB)")
                    print(f"     SHA256: {img.sha256[:16]}...")

                    # Verify file exists
                    img_path = storage_root / img.local_path
                    if img_path.exists():
                        print(f"     ✓ File exists on disk")
                    else:
                        print(f"     ✗ File NOT found on disk")

                print()

            # Show directory listing
            print("=" * 80)
            print("DIRECTORY CONTENTS")
            print("=" * 80)
            print()

            storage_root = Path("/tmp/filings")
            filing_dir = storage_root / artifact.local_path.rsplit('/', 1)[0]

            if filing_dir.exists():
                print(f"Directory: {filing_dir}")
                print()
                files = sorted(filing_dir.glob("*"))
                for f in files:
                    if f.is_file():
                        size_kb = f.stat().st_size / 1024
                        print(f"  {f.name:50s} {size_kb:8.1f} KB")
                print()

            # Example log line
            if downloaded:
                first = downloaded[0]
                print("=" * 80)
                print("EXAMPLE LOG LINE (image download)")
                print("=" * 80)
                print()
                print(f"[info] image_downloaded filing_id={first.filing_id} " +
                      f"artifact_id={first.id} " +
                      f"url={first.url} " +
                      f"local_path={first.local_path} " +
                      f"size_bytes={first.file_size} " +
                      f"status={first.status}")
                print()

            return True
        else:
            print("No images found in HTML (or all failed to download)")
            return True


if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)
