"""
Safe Cleanup Tool for Failed Artifacts
安全清理无效的artifacts，带多重确认机制
"""
import argparse
from datetime import datetime, date
import structlog
from sqlalchemy import func

from config.db import get_db_session
from models import Artifact, Filing, Company, ErrorLog

logger = structlog.get_logger()


class SafeCleanupTool:
    """安全清理工具"""

    def __init__(self, dry_run: bool = True):
        """
        Args:
            dry_run: True=只预览不执行，False=实际执行
        """
        self.dry_run = dry_run

    def preview_cleanup_404_errors(self, min_retries: int = 3):
        """
        预览404错误的清理计划

        Args:
            min_retries: 最少重试次数（避免误删临时404）
        """
        with get_db_session() as session:
            # 查找404错误
            artifacts_404 = session.query(Artifact).join(Filing).join(Company).filter(
                Artifact.status == 'failed',
                Artifact.retry_count >= min_retries,
                Artifact.error_message.like('%404%')
            ).all()

            print("\n" + "="*80)
            print(f"404 NOT FOUND Artifacts (min {min_retries} retries)")
            print("="*80)
            print(f"\nTotal to clean: {len(artifacts_404):,}\n")

            # 按form type分组
            form_type_counts = {}
            company_examples = []

            for artifact in artifacts_404[:20]:  # 只显示前20个样例
                filing = artifact.filing
                company = filing.company

                if filing.form_type not in form_type_counts:
                    form_type_counts[filing.form_type] = 0
                form_type_counts[filing.form_type] += 1

                company_examples.append({
                    'id': artifact.id,
                    'ticker': company.ticker,
                    'cik': company.cik,
                    'form': filing.form_type,
                    'date': filing.filing_date,
                    'url': artifact.url[:80]
                })

            print(f"{'Form Type':<15} {'Count':<10}")
            print("-"*25)
            for form, count in sorted(form_type_counts.items(), key=lambda x: -x[1]):
                total = session.query(func.count(Artifact.id)).join(Filing).filter(
                    Filing.form_type == form,
                    Artifact.status == 'failed',
                    Artifact.retry_count >= min_retries,
                    Artifact.error_message.like('%404%')
                ).scalar()
                print(f"{form:<15} {total:,}")

            print("\nExamples:")
            print(f"{'ID':<8} {'Ticker':<10} {'Form':<10} {'Date':<12} {'URL'}")
            print("-"*80)
            for ex in company_examples:
                print(f"{ex['id']:<8} {ex['ticker']:<10} {ex['form']:<10} {str(ex['date']):<12} {ex['url']}")

            return len(artifacts_404)

    def preview_cleanup_future_dated(self):
        """预览未来日期filings的清理计划"""
        with get_db_session() as session:
            today = date.today()

            # 查找未来日期的失败artifacts
            future_artifacts = session.query(Artifact).join(Filing).filter(
                Artifact.status == 'failed',
                Filing.filing_date > today
            ).all()

            print("\n" + "="*80)
            print("FUTURE-DATED Filings (don't exist yet)")
            print("="*80)
            print(f"\nTotal to clean: {len(future_artifacts):,}\n")

            if future_artifacts:
                print(f"{'Ticker':<10} {'Form':<10} {'Filing Date':<15} {'Status'}")
                print("-"*50)

                for artifact in future_artifacts[:20]:
                    filing = artifact.filing
                    company = filing.company
                    print(f"{company.ticker:<10} {filing.form_type:<10} {filing.filing_date!s:<15} {artifact.status}")

            return len(future_artifacts)

    def preview_cleanup_invalid_cik(self, invalid_ciks: dict):
        """
        预览错误CIK的artifacts

        Args:
            invalid_ciks: {ticker: wrong_cik} mapping
        """
        if not invalid_ciks:
            print("\n(No invalid CIKs provided - skip this step)")
            return 0

        with get_db_session() as session:
            total = 0

            print("\n" + "="*80)
            print("INVALID CIK Mappings")
            print("="*80 + "\n")

            for ticker, wrong_cik in invalid_ciks.items():
                # 找出使用错误CIK的公司
                companies = session.query(Company).filter(
                    Company.ticker == ticker,
                    Company.cik == wrong_cik
                ).all()

                for company in companies:
                    # 统计该公司的失败artifacts
                    failed_count = session.query(func.count(Artifact.id)).join(Filing).filter(
                        Filing.company_id == company.id,
                        Artifact.status == 'failed'
                    ).scalar()

                    print(f"{ticker} (CIK {wrong_cik}): {failed_count:,} failed artifacts")
                    total += failed_count

            return total

    def execute_cleanup(
        self,
        clean_404: bool = False,
        clean_future: bool = False,
        min_retries: int = 3
    ):
        """
        执行清理（需要确认）

        Args:
            clean_404: 是否清理404错误
            clean_future: 是否清理未来日期
            min_retries: 404最少重试次数
        """
        if self.dry_run:
            print("\n⚠️  DRY RUN MODE - No data will be deleted")
            print("To execute cleanup, run with --execute flag\n")
            return

        with get_db_session() as session:
            deleted_total = 0

            # 清理404
            if clean_404:
                print("\n🗑️  Cleaning 404 errors...")

                deleted_404 = session.query(Artifact).filter(
                    Artifact.status == 'failed',
                    Artifact.retry_count >= min_retries,
                    Artifact.error_message.like('%404%')
                ).delete(synchronize_session=False)

                session.commit()
                deleted_total += deleted_404
                print(f"   Deleted {deleted_404:,} artifacts with 404 errors")

            # 清理未来日期
            if clean_future:
                print("\n🗑️  Cleaning future-dated filings...")

                today = date.today()

                # 先删除artifacts
                deleted_future_artifacts = session.query(Artifact).filter(
                    Artifact.filing_id.in_(
                        session.query(Filing.id).filter(
                            Filing.filing_date > today
                        )
                    )
                ).delete(synchronize_session=False)

                # 再删除filings
                deleted_future_filings = session.query(Filing).filter(
                    Filing.filing_date > today
                ).delete(synchronize_session=False)

                session.commit()
                deleted_total += deleted_future_artifacts

                print(f"   Deleted {deleted_future_artifacts:,} artifacts")
                print(f"   Deleted {deleted_future_filings:,} filings")

            # 最终统计
            remaining_failed = session.query(func.count(Artifact.id)).filter(
                Artifact.status == 'failed'
            ).scalar()

            print("\n" + "="*80)
            print("CLEANUP SUMMARY")
            print("="*80)
            print(f"Total deleted: {deleted_total:,}")
            print(f"Remaining failed artifacts: {remaining_failed:,}")
            print("="*80 + "\n")

    def backup_failed_artifacts_to_csv(self, output_file: str = 'failed_artifacts_backup.csv'):
        """
        在清理前备份所有失败的artifacts到CSV

        Args:
            output_file: 输出文件名
        """
        import csv

        with get_db_session() as session:
            failed_artifacts = session.query(Artifact).join(Filing).join(Company).filter(
                Artifact.status == 'failed'
            ).all()

            print(f"\n💾 Backing up {len(failed_artifacts):,} failed artifacts to {output_file}...")

            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Header
                writer.writerow([
                    'artifact_id', 'ticker', 'cik', 'company_name', 'exchange', 'is_foreign',
                    'form_type', 'filing_date', 'accession_number',
                    'artifact_type', 'filename', 'url', 'status', 'retry_count',
                    'error_message', 'last_attempt_at'
                ])

                # Data
                for artifact in failed_artifacts:
                    filing = artifact.filing
                    company = filing.company

                    writer.writerow([
                        artifact.id,
                        company.ticker,
                        company.cik,
                        company.company_name,
                        company.exchange,
                        company.is_foreign,
                        filing.form_type,
                        filing.filing_date,
                        filing.accession_number,
                        artifact.artifact_type,
                        artifact.filename,
                        artifact.url,
                        artifact.status,
                        artifact.retry_count,
                        artifact.error_message,
                        artifact.last_attempt_at
                    ])

            print(f"✅ Backup saved to {output_file}\n")


def main():
    parser = argparse.ArgumentParser(
        description='Safely cleanup failed artifacts with multiple safety checks',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview what would be deleted (safe)
  python safe_cleanup_failed_artifacts.py --preview-all

  # Backup before cleanup
  python safe_cleanup_failed_artifacts.py --backup

  # Execute cleanup for 404 errors only (after preview!)
  python safe_cleanup_failed_artifacts.py --execute --clean-404

  # Execute cleanup for both 404 and future-dated
  python safe_cleanup_failed_artifacts.py --execute --clean-404 --clean-future

Recommended workflow:
  1. python safe_cleanup_failed_artifacts.py --backup
  2. python safe_cleanup_failed_artifacts.py --preview-all
  3. Review the preview carefully
  4. python safe_cleanup_failed_artifacts.py --execute --clean-404 --clean-future
        """
    )

    parser.add_argument('--preview-all', action='store_true', help='Preview all cleanup operations')
    parser.add_argument('--backup', action='store_true', help='Backup failed artifacts to CSV')
    parser.add_argument('--execute', action='store_true', help='Actually execute cleanup (default is dry-run)')
    parser.add_argument('--clean-404', action='store_true', help='Clean 404 errors')
    parser.add_argument('--clean-future', action='store_true', help='Clean future-dated filings')
    parser.add_argument('--min-retries', type=int, default=3, help='Minimum retries for 404 cleanup (default: 3)')

    args = parser.parse_args()

    # 创建清理工具
    tool = SafeCleanupTool(dry_run=not args.execute)

    # 备份
    if args.backup:
        tool.backup_failed_artifacts_to_csv()
        return

    # 预览
    if args.preview_all:
        count_404 = tool.preview_cleanup_404_errors(min_retries=args.min_retries)
        count_future = tool.preview_cleanup_future_dated()

        print("\n" + "="*80)
        print("TOTAL PREVIEW SUMMARY")
        print("="*80)
        print(f"404 Errors: {count_404:,}")
        print(f"Future-dated: {count_future:,}")
        print(f"TOTAL: {count_404 + count_future:,}")
        print("="*80 + "\n")

        print("⚠️  To execute cleanup, run:")
        print("   python safe_cleanup_failed_artifacts.py --execute --clean-404 --clean-future\n")
        return

    # 执行清理
    if args.execute:
        if not args.clean_404 and not args.clean_future:
            print("Error: Must specify at least one of --clean-404 or --clean-future")
            return

        print("\n" + "⚠️ "*40)
        print("WARNING: You are about to DELETE data from the database!")
        print("⚠️ "*40 + "\n")

        confirm = input("Type 'DELETE' to confirm: ")
        if confirm != 'DELETE':
            print("Cancelled.")
            return

        tool.execute_cleanup(
            clean_404=args.clean_404,
            clean_future=args.clean_future,
            min_retries=args.min_retries
        )
    else:
        print("No action specified. Use --preview-all, --backup, or --execute")
        parser.print_help()


if __name__ == '__main__':
    main()
