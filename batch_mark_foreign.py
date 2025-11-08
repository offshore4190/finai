"""
Batch Mark Foreign Companies
批量自动标记海外公司（基于SEC数据）
"""
import time
import structlog
from datetime import datetime
from sqlalchemy import func

from config.db import get_db_session
from models import Company, Filing, ExecutionRun
from services.sec_api import SECAPIClient

logger = structlog.get_logger()


class BatchForeignMarker:
    """批量标记海外公司"""

    FOREIGN_FORM_TYPES = ['20-F', '20-F/A', '6-K', '6-K/A', '40-F', '40-F/A']

    def __init__(self, dry_run: bool = True):
        """
        Args:
            dry_run: True=只预览不执行，False=实际更新数据库
        """
        self.sec_client = SECAPIClient()
        self.dry_run = dry_run
        self.marked_count = 0
        self.skipped_count = 0
        self.error_count = 0

    def check_is_foreign(self, company: Company) -> tuple:
        """
        检查公司是否为海外公司

        Returns:
            (is_foreign: bool, reason: str, form_types: list)
        """
        try:
            # 获取submissions
            submissions = self.sec_client.fetch_company_submissions(company.cik)

            if not submissions or 'filings' not in submissions:
                return False, 'NO_DATA', []

            recent_filings = submissions.get('filings', {}).get('recent', {})
            form_types = recent_filings.get('form', [])

            if not form_types:
                return False, 'NO_FILINGS', []

            # 检查是否有海外表格
            has_foreign = any(
                any(foreign_form in form for foreign_form in self.FOREIGN_FORM_TYPES)
                for form in form_types
            )

            # 检查是否有国内表格
            has_domestic = any(
                form in form_types
                for form in ['10-K', '10-K/A', '10-Q', '10-Q/A']
            )

            # 判断逻辑
            if has_foreign and not has_domestic:
                return True, 'ONLY_FOREIGN_FORMS', list(set(form_types))
            elif has_foreign and has_domestic:
                return False, 'MIXED_FORMS', list(set(form_types))
            else:
                return False, 'ONLY_DOMESTIC_FORMS', list(set(form_types))

        except Exception as e:
            logger.error(
                "check_failed",
                ticker=company.ticker,
                cik=company.cik,
                error=str(e)
            )
            return False, f'ERROR: {str(e)}', []

    def mark_foreign_companies(
        self,
        exchanges: list = None,
        limit: int = None,
        skip_already_marked: bool = True
    ):
        """
        批量标记海外公司

        Args:
            exchanges: 指定交易所列表
            limit: 限制检查的公司数量
            skip_already_marked: 跳过已标记为is_foreign的公司
        """
        logger.info(
            "batch_marking_started",
            dry_run=self.dry_run,
            exchanges=exchanges,
            limit=limit
        )

        with get_db_session() as session:
            # 创建执行记录
            run = ExecutionRun(
                run_type='batch_mark_foreign',
                started_at=datetime.utcnow(),
                status='running',
                meta_data={
                    'dry_run': self.dry_run,
                    'exchanges': exchanges,
                    'limit': limit
                }
            )
            session.add(run)
            session.commit()

            try:
                # 查询没有filings的公司
                query = session.query(Company).outerjoin(Filing).filter(
                    Company.status == 'active',
                    Company.is_active == True,
                    Filing.id == None  # 没有filings
                )

                if exchanges:
                    query = query.filter(Company.exchange.in_(exchanges))

                if skip_already_marked:
                    query = query.filter(Company.is_foreign == False)

                if limit:
                    query = query.limit(limit)

                companies = query.all()

                print("\n" + "="*80)
                print("BATCH FOREIGN COMPANY MARKING")
                print("="*80)
                print(f"\nMode: {'DRY RUN (preview only)' if self.dry_run else 'LIVE (will update database)'}")
                print(f"Companies to check: {len(companies):,}\n")

                if self.dry_run:
                    print("⚠️  This is a preview. No changes will be made to the database.")
                    print("    Run with --execute to actually update.\n")

                marked_companies = []
                skipped_companies = []

                for i, company in enumerate(companies, 1):
                    if i % 10 == 0:
                        print(f"  Progress: {i}/{len(companies)} ({i/len(companies)*100:.1f}%)")
                        logger.info("progress", checked=i, total=len(companies))

                    # 检查是否为海外公司
                    is_foreign, reason, form_types = self.check_is_foreign(company)

                    if is_foreign:
                        logger.info(
                            "foreign_company_detected",
                            ticker=company.ticker,
                            cik=company.cik,
                            reason=reason,
                            form_types=form_types[:5]  # 只记录前5个
                        )

                        marked_companies.append({
                            'ticker': company.ticker,
                            'cik': company.cik,
                            'exchange': company.exchange,
                            'reason': reason,
                            'form_types': form_types[:10]
                        })

                        # 如果不是dry run，更新数据库
                        if not self.dry_run:
                            company.is_foreign = True
                            company.updated_at = datetime.utcnow()
                            session.flush()

                        self.marked_count += 1

                        # 批量提交
                        if not self.dry_run and self.marked_count % 20 == 0:
                            session.commit()
                    else:
                        self.skipped_count += 1

                        if reason.startswith('ERROR'):
                            self.error_count += 1
                            skipped_companies.append({
                                'ticker': company.ticker,
                                'cik': company.cik,
                                'reason': reason
                            })

                    # Rate limiting
                    time.sleep(0.12)  # ~8 req/s to be safe

                # 最终提交
                if not self.dry_run:
                    session.commit()

                # 更新执行记录
                run.completed_at = datetime.utcnow()
                run.status = 'completed'
                run.duration_seconds = int((run.completed_at - run.started_at).total_seconds())
                run.meta_data['marked_count'] = self.marked_count
                run.meta_data['skipped_count'] = self.skipped_count
                run.meta_data['error_count'] = self.error_count
                session.commit()

                # 打印结果
                print("\n" + "="*80)
                print("RESULTS")
                print("="*80 + "\n")

                print(f"Total Checked:     {len(companies):,}")
                print(f"Marked as Foreign: {self.marked_count:,}")
                print(f"Skipped:           {self.skipped_count:,}")
                print(f"Errors:            {self.error_count:,}")
                print(f"Duration:          {run.duration_seconds:,} seconds\n")

                if marked_companies:
                    print("-"*80)
                    print("FOREIGN COMPANIES DETECTED (first 20):")
                    print("-"*80)
                    print(f"{'Ticker':<10} {'CIK':<12} {'Exchange':<15} {'Reason':<30}")
                    print("-"*80)

                    for company_info in marked_companies[:20]:
                        print(
                            f"{company_info['ticker']:<10} "
                            f"{company_info['cik']:<12} "
                            f"{company_info['exchange']:<15} "
                            f"{company_info['reason']:<30}"
                        )

                    if len(marked_companies) > 20:
                        print(f"\n... and {len(marked_companies) - 20} more")

                    # 显示form types样例
                    print("\n" + "-"*80)
                    print("SAMPLE FORM TYPES:")
                    print("-"*80)
                    for company_info in marked_companies[:5]:
                        print(f"\n{company_info['ticker']}:")
                        print(f"  Forms: {', '.join(company_info['form_types'])}")

                if self.error_count > 0 and skipped_companies:
                    print("\n" + "-"*80)
                    print("ERRORS (first 10):")
                    print("-"*80)
                    for company_info in skipped_companies[:10]:
                        print(f"  {company_info['ticker']}: {company_info['reason']}")

                print("\n" + "="*80)
                if self.dry_run:
                    print("DRY RUN COMPLETE - No changes made")
                    print("\nTo apply these changes, run:")
                    print("  python batch_mark_foreign.py --execute")
                else:
                    print("MARKING COMPLETE - Database updated")
                    print(f"\n{self.marked_count:,} companies marked as is_foreign=TRUE")
                    print("\nNext step: Run foreign backfill")
                    print("  python -m jobs.backfill_foreign_improved")
                print("="*80 + "\n")

                logger.info(
                    "batch_marking_completed",
                    total=len(companies),
                    marked=self.marked_count,
                    skipped=self.skipped_count,
                    errors=self.error_count,
                    duration=run.duration_seconds
                )

            except Exception as e:
                run.status = 'failed'
                run.error_summary = str(e)
                run.completed_at = datetime.utcnow()
                session.commit()

                logger.error("batch_marking_failed", error=str(e), exc_info=True)
                raise


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='Batch mark foreign companies based on SEC filing types',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview mode (safe - no changes)
  python batch_mark_foreign.py --limit 50

  # Preview all companies without filings
  python batch_mark_foreign.py

  # Execute marking for NASDAQ only
  python batch_mark_foreign.py --execute --exchange NASDAQ

  # Execute marking for all exchanges
  python batch_mark_foreign.py --execute

Recommended workflow:
  1. python batch_mark_foreign.py --limit 100        # Preview
  2. Review the output
  3. python batch_mark_foreign.py --execute          # Apply changes
  4. python -m jobs.backfill_foreign_improved        # Download data
        """
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually update database (default is dry-run preview)'
    )
    parser.add_argument(
        '--exchange',
        choices=['NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca'],
        help='Only check companies from specific exchange'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of companies to check (for testing)'
    )

    args = parser.parse_args()

    exchanges = [args.exchange] if args.exchange else None

    marker = BatchForeignMarker(dry_run=not args.execute)
    marker.mark_foreign_companies(
        exchanges=exchanges,
        limit=args.limit
    )


if __name__ == '__main__':
    main()
