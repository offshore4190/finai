"""
Improved Foreign Company Backfill Job
修复版本 - 避免CIK错误和未来日期问题
"""
from datetime import datetime, date
import structlog
from sqlalchemy import func

from config.db import get_db_session
from config.settings import settings
from models import Company, Filing, Artifact, ExecutionRun
from services.sec_api import SECAPIClient
from services.storage import storage_service

logger = structlog.get_logger()


class ImprovedForeignBackfillJob:
    """改进的海外公司Backfill任务（带数据验证）"""

    # 海外公司表格类型
    FORM_TYPES = [
        '20-F',    # 年报
        '20-F/A',  # 年报修订
        '6-K',     # 当前报告
        '6-K/A',   # 当前报告修订
        '40-F',    # 加拿大公司年报
        '40-F/A'   # 加拿大公司年报修订
    ]

    # 日期范围 - 使用今天作为上限避免未来日期
    START_DATE = datetime(2023, 1, 1)
    END_DATE = datetime.now()  # ✨ 使用当前日期而非2025

    def __init__(self, limit: int = None, exchanges: list = None, verify_cik: bool = True):
        """
        Args:
            limit: 限制处理公司数量
            exchanges: 指定交易所列表
            verify_cik: 是否验证CIK（推荐True）
        """
        self.sec_client = SECAPIClient()
        self.limit = limit
        self.target_exchanges = exchanges or ['NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca']
        self.verify_cik = verify_cik

        # 统计
        self.cik_mismatches = []
        self.skipped_companies = []

    def verify_company_cik(self, company: Company) -> bool:
        """
        验证公司CIK是否正确

        Returns:
            True if CIK is valid
        """
        if not self.verify_cik:
            return True

        try:
            # 尝试获取公司submissions
            submissions = self.sec_client.fetch_company_submissions(company.cik)

            # 检查返回的CIK是否匹配
            returned_cik = submissions.get('cik')
            if returned_cik:
                returned_cik_str = str(returned_cik).zfill(10)
                company_cik_str = company.cik.zfill(10)

                if returned_cik_str != company_cik_str:
                    logger.warning(
                        "cik_mismatch_detected",
                        ticker=company.ticker,
                        db_cik=company_cik_str,
                        sec_cik=returned_cik_str
                    )
                    self.cik_mismatches.append({
                        'ticker': company.ticker,
                        'db_cik': company_cik_str,
                        'correct_cik': returned_cik_str
                    })
                    return False

            return True

        except Exception as e:
            # 如果CIK无效，SEC会返回404
            if '404' in str(e):
                logger.error(
                    "invalid_cik",
                    ticker=company.ticker,
                    cik=company.cik,
                    error="CIK not found in SEC database"
                )
                self.skipped_companies.append({
                    'ticker': company.ticker,
                    'cik': company.cik,
                    'reason': 'CIK_NOT_FOUND'
                })
                return False

            logger.error("cik_verification_failed", ticker=company.ticker, error=str(e))
            return True  # 网络错误等，继续处理

    def validate_filing_date(self, filing_date: date) -> bool:
        """
        验证filing_date是否在有效范围内

        Args:
            filing_date: 报告日期

        Returns:
            True if valid
        """
        today = date.today()

        if filing_date > today:
            logger.warning(
                "future_filing_date_detected",
                filing_date=filing_date,
                today=today,
                action="skipping"
            )
            return False

        if filing_date < self.START_DATE.date():
            return False

        return True

    def construct_and_validate_url(self, cik: str, accession: str, filename: str) -> tuple:
        """
        构造并验证URL

        Returns:
            (url, is_valid)
        """
        url = self.sec_client.construct_document_url(cik, accession, filename)

        # 基本URL格式验证
        if not url.startswith('https://www.sec.gov/Archives/edgar/data/'):
            logger.warning("invalid_url_format", url=url)
            return url, False

        return url, True

    def determine_fiscal_period(self, form_type: str, report_date: str) -> str:
        """确定财报周期"""
        if any(annual_form in form_type for annual_form in ['20-F', '40-F']):
            return 'FY'

        if '6-K' in form_type:
            return '6K'

        return 'OTHER'

    def process_company_filings(self, session, company: Company, run_id: int) -> dict:
        """
        处理单个公司的表格

        Returns:
            {'filings': int, 'artifacts': int, 'skipped': int}
        """
        stats = {'filings': 0, 'artifacts': 0, 'skipped': 0}

        try:
            # ✨ 验证CIK
            if not self.verify_company_cik(company):
                logger.warning(
                    "company_skipped_due_to_cik",
                    ticker=company.ticker,
                    cik=company.cik
                )
                return stats

            # 获取submissions
            submissions = self.sec_client.fetch_company_submissions(company.cik)

            # 解析filings
            filings_data = self.sec_client.parse_filings(
                submissions,
                form_types=self.FORM_TYPES,
                start_date=self.START_DATE,
                end_date=self.END_DATE
            )

            for filing_data in filings_data:
                filing_date = filing_data['filing_date']

                # ✨ 验证日期
                if not self.validate_filing_date(filing_date):
                    stats['skipped'] += 1
                    continue

                # 检查是否已存在
                existing = session.query(Filing).filter(
                    Filing.accession_number == filing_data['accession_number']
                ).first()

                if existing:
                    continue

                fiscal_year = filing_date.year
                fiscal_period = self.determine_fiscal_period(
                    filing_data['form_type'],
                    filing_data.get('report_date')
                )

                # 创建Filing记录
                filing = Filing(
                    company_id=company.id,
                    accession_number=filing_data['accession_number'],
                    form_type=filing_data['form_type'],
                    filing_date=filing_date,
                    report_date=filing_data.get('report_date'),
                    fiscal_year=fiscal_year,
                    fiscal_period=fiscal_period,
                    is_amendment=filing_data['is_amendment'],
                    primary_document=filing_data['primary_document']
                )
                session.add(filing)
                session.flush()

                # 确保存储目录存在
                storage_service.ensure_directory_structure(
                    company.exchange,
                    company.ticker,
                    fiscal_year
                )

                # ✨ 构造并验证URL
                filing_date_str = filing.filing_date.strftime("%d-%m-%Y")
                html_path = storage_service.construct_path(
                    exchange=company.exchange,
                    ticker=company.ticker,
                    fiscal_year=fiscal_year,
                    fiscal_period=fiscal_period,
                    filing_date_str=filing_date_str,
                    artifact_type='html'
                )

                html_url, is_valid = self.construct_and_validate_url(
                    company.cik,
                    filing.accession_number,
                    filing.primary_document
                )

                if not is_valid:
                    logger.warning(
                        "invalid_url_skipped",
                        ticker=company.ticker,
                        accession=filing.accession_number,
                        url=html_url
                    )
                    stats['skipped'] += 1
                    continue

                # 创建artifact
                artifact = Artifact(
                    filing_id=filing.id,
                    artifact_type='html',
                    filename=filing.primary_document,
                    local_path=html_path,
                    url=html_url,
                    status='pending_download'
                )
                session.add(artifact)

                stats['filings'] += 1
                stats['artifacts'] += 1

            session.commit()

            logger.info(
                "foreign_company_processed",
                ticker=company.ticker,
                cik=company.cik,
                new_filings=stats['filings'],
                skipped=stats['skipped']
            )

            return stats

        except Exception as e:
            logger.error(
                "foreign_company_processing_failed",
                ticker=company.ticker,
                error=str(e),
                exc_info=True
            )
            return stats

    def run(self):
        """执行Backfill"""
        logger.info(
            "improved_foreign_backfill_started",
            start_date=self.START_DATE,
            end_date=self.END_DATE,
            verify_cik=self.verify_cik
        )

        with get_db_session() as session:
            run = ExecutionRun(
                run_type='improved_foreign_backfill',
                started_at=datetime.utcnow(),
                status='running',
                meta_data={
                    'start_date': str(self.START_DATE),
                    'end_date': str(self.END_DATE),
                    'form_types': self.FORM_TYPES,
                    'verify_cik': self.verify_cik
                }
            )
            session.add(run)
            session.commit()

            try:
                # 获取海外公司
                query = session.query(Company).filter(
                    Company.status == 'active',
                    Company.is_active == True,
                    Company.exchange.in_(self.target_exchanges),
                    Company.is_foreign == True
                )

                if self.limit:
                    query = query.limit(self.limit)

                companies = query.all()

                logger.info(
                    "foreign_companies_loaded",
                    count=len(companies),
                    exchanges=self.target_exchanges
                )

                total_filings = 0
                total_artifacts = 0
                total_skipped = 0

                for i, company in enumerate(companies, 1):
                    logger.info(
                        "processing_foreign_company",
                        progress=f"{i}/{len(companies)}",
                        ticker=company.ticker
                    )

                    stats = self.process_company_filings(session, company, run.id)
                    total_filings += stats['filings']
                    total_artifacts += stats['artifacts']
                    total_skipped += stats['skipped']

                    if i % 50 == 0:
                        logger.info(
                            "foreign_backfill_progress",
                            processed=i,
                            total=len(companies),
                            filings=total_filings,
                            artifacts=total_artifacts,
                            skipped=total_skipped
                        )

                # 更新执行记录
                run.completed_at = datetime.utcnow()
                run.status = 'completed'
                run.duration_seconds = int((run.completed_at - run.started_at).total_seconds())
                run.filings_discovered = total_filings
                run.meta_data['total_skipped'] = total_skipped
                run.meta_data['cik_mismatches'] = len(self.cik_mismatches)
                run.meta_data['skipped_companies'] = len(self.skipped_companies)
                session.commit()

                # 打印总结
                print("\n" + "="*80)
                print("IMPROVED FOREIGN BACKFILL SUMMARY")
                print("="*80)
                print(f"Companies Processed: {len(companies):,}")
                print(f"Filings Discovered: {total_filings:,}")
                print(f"Artifacts Created: {total_artifacts:,}")
                print(f"Skipped (validation): {total_skipped:,}")
                print(f"CIK Mismatches: {len(self.cik_mismatches):,}")
                print(f"Skipped Companies: {len(self.skipped_companies):,}")
                print(f"Duration: {run.duration_seconds:,} seconds")
                print("="*80 + "\n")

                # 打印CIK错误报告
                if self.cik_mismatches:
                    print("\n⚠️  CIK MISMATCHES DETECTED:")
                    print("-"*60)
                    for mismatch in self.cik_mismatches[:20]:  # 只显示前20个
                        print(f"  {mismatch['ticker']}: {mismatch['db_cik']} → {mismatch['correct_cik']}")
                    print("\nRun verify_cik_mappings.py to fix these issues.\n")

                # 打印跳过的公司
                if self.skipped_companies:
                    print("\n⚠️  SKIPPED COMPANIES:")
                    print("-"*60)
                    for skipped in self.skipped_companies[:20]:
                        print(f"  {skipped['ticker']} (CIK: {skipped['cik']}): {skipped['reason']}")
                    print()

                logger.info(
                    "improved_foreign_backfill_completed",
                    companies=len(companies),
                    filings=total_filings,
                    duration=run.duration_seconds
                )

            except Exception as e:
                run.status = 'failed'
                run.error_summary = str(e)
                run.completed_at = datetime.utcnow()
                session.commit()

                logger.error("improved_foreign_backfill_failed", error=str(e), exc_info=True)
                raise


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='Improved foreign company backfill with data validation',
        epilog="""
Examples:
  # Test with 10 companies, verify CIKs
  python -m jobs.backfill_foreign_improved --limit 10

  # NASDAQ only, skip CIK verification (faster but risky)
  python -m jobs.backfill_foreign_improved --exchange NASDAQ --no-verify-cik

  # Full backfill with all safety checks
  python -m jobs.backfill_foreign_improved
        """
    )
    parser.add_argument('--limit', type=int, help='Limit number of companies')
    parser.add_argument('--exchange', choices=['NASDAQ', 'NYSE'], help='Specific exchange')
    parser.add_argument('--no-verify-cik', action='store_true', help='Skip CIK verification (not recommended)')

    args = parser.parse_args()

    exchanges = [args.exchange] if args.exchange else None
    job = ImprovedForeignBackfillJob(
        limit=args.limit,
        exchanges=exchanges,
        verify_cik=not args.no_verify_cik
    )
    job.run()


if __name__ == '__main__':
    main()
