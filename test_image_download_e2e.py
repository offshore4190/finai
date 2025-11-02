#!/usr/bin/env python
"""
End-to-end test for image download from real HTML filing.
Tests the complete pipeline: HTML download -> image extraction -> image download.
"""
import structlog
from pathlib import Path

from config.db import get_db_session
from models import Artifact, Filing
from services.downloader import ArtifactDownloader, extract_image_urls

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


def test_image_extraction_from_real_html():
    """Test image extraction from already downloaded HTML."""

    print("=" * 80)
    print("IMAGE DOWNLOAD E2E TEST")
    print("=" * 80)
    print()

    with get_db_session() as session:
        # Get the first downloaded HTML artifact
        html_artifact = session.query(Artifact).filter(
            Artifact.artifact_type == 'html',
            Artifact.status == 'downloaded'
        ).first()

        if not html_artifact:
            print("ERROR: No downloaded HTML artifacts found. Run test_download_first_artifact.py first.")
            return False

        print("TESTING WITH ARTIFACT:")
        print(f"  ID: {html_artifact.id}")
        print(f"  Company: {html_artifact.filing.company.ticker}")
        print(f"  Form: {html_artifact.filing.form_type}")
        print(f"  Local Path: {html_artifact.local_path}")
        print(f"  File Size: {html_artifact.file_size:,} bytes")
        print()

        # Read the HTML content
        storage_root = Path("/tmp/filings")
        html_path = storage_root / html_artifact.local_path

        if not html_path.exists():
            print(f"ERROR: HTML file not found at {html_path}")
            return False

        html_content = html_path.read_bytes()

        # Extract image URLs
        print("EXTRACTING IMAGE URLS...")
        image_urls = extract_image_urls(html_content)

        print(f"Found {len(image_urls)} images in HTML")
        print()

        if image_urls:
            print("SAMPLE IMAGE URLS:")
            for i, url in enumerate(image_urls[:5], 1):
                print(f"  {i}. {url}")
            if len(image_urls) > 5:
                print(f"  ... and {len(image_urls) - 5} more")
            print()

        # Now trigger the full download pipeline by re-downloading
        # (the images will be downloaded automatically)
        print("=" * 80)
        print("TRIGGERING IMAGE DOWNLOAD PIPELINE")
        print("=" * 80)
        print()

        # Mark as pending to re-trigger download
        html_artifact.status = 'pending_download'
        session.commit()

        downloader = ArtifactDownloader()
        success = downloader.download_artifact(session, html_artifact)

        if success:
            print()
            print("=" * 80)
            print("✓ DOWNLOAD COMPLETED")
            print("=" * 80)
            print()

            # Check for downloaded images
            image_artifacts = session.query(Artifact).filter(
                Artifact.filing_id == html_artifact.filing_id,
                Artifact.artifact_type == 'image'
            ).all()

            print(f"IMAGES IN DATABASE: {len(image_artifacts)}")
            print()

            if image_artifacts:
                print("DOWNLOADED IMAGES:")
                for img in image_artifacts[:10]:
                    status_icon = "✓" if img.status == 'downloaded' else ("⊘" if img.status == 'skipped' else "✗")
                    size = f"{img.file_size:,} bytes" if img.file_size else "N/A"
                    print(f"  {status_icon} {img.filename}")
                    print(f"     Path: {img.local_path}")
                    print(f"     Size: {size}")
                    print(f"     Status: {img.status}")

                    # Verify file exists
                    img_path = storage_root / img.local_path
                    if img.status == 'downloaded' and img_path.exists():
                        print(f"     ✓ File exists on disk")
                    print()

                if len(image_artifacts) > 10:
                    print(f"  ... and {len(image_artifacts) - 10} more")
                print()

                # Statistics
                downloaded = sum(1 for img in image_artifacts if img.status == 'downloaded')
                skipped = sum(1 for img in image_artifacts if img.status == 'skipped')
                failed = sum(1 for img in image_artifacts if img.status == 'failed')

                print("STATISTICS:")
                print(f"  Total images: {len(image_artifacts)}")
                print(f"  Downloaded: {downloaded}")
                print(f"  Skipped (deduplicated): {skipped}")
                print(f"  Failed: {failed}")
                print()

                # Show example log line
                if downloaded > 0:
                    first_downloaded = next((img for img in image_artifacts if img.status == 'downloaded'), None)
                    if first_downloaded:
                        print("EXAMPLE LOG LINE:")
                        print(f"  image_downloaded filing_id={first_downloaded.filing_id} " +
                              f"artifact_id={first_downloaded.id} " +
                              f"url={first_downloaded.url[:60]}... " +
                              f"local_path={first_downloaded.local_path} " +
                              f"size_bytes={first_downloaded.file_size} " +
                              f"status={first_downloaded.status}")
                        print()

                return True
            else:
                print("No images were downloaded (HTML may not contain images)")
                return True
        else:
            print("ERROR: Download failed")
            return False


if __name__ == '__main__':
    success = test_image_extraction_from_real_html()
    exit(0 if success else 1)
