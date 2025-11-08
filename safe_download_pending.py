"""
Safe Download Pending Artifacts
改进的下载脚本，避免SEC 429限流
"""
import argparse
import time
from datetime import datetime
import structlog
from sqlalchemy import func

from config.db import get_db_session
from config.settings import settings
from models import Artifact, Filing, Company, ExecutionRun
from services.downloader import ArtifactDownloader

logger = structlog.get_logger()


class SafeDownloader:
    """安全下载器，带智能限流"""

    def __init__(
        self,
        batch_size: int = 10,
        delay_between_batches: float = 2.0,
        delay_between_downloads: float = 0.15,
        max_concurrent: int = 1
    ):
        """
        Args:
            batch_size: 每批下载数量
            delay_between_batches: 批次间延迟（秒）
            delay_between_downloads: 单个下载间延迟（秒）
            max_concurrent: 并发数（建议保持为1避免429）
        """
        self.batch_size = batch_size
        self.delay_between_batches = delay_between_batches
        self.delay_between_downloads = delay_between_downloads
        self.max_concurrent = max_concurrent
        self.downloader = ArtifactDownloader()

        # 统计
        self.total_attempted = 0
        self.total_succeeded = 0
        self.total_failed = 0
        self.total_429_errors = 0

    def download_batch(self, session, artifacts: list, run_id: int) -> dict:
        """
        下载一批artifacts

        Returns:
            {'succeeded': int, 'failed': int, 'rate_limited': int}
        """
        succeeded = 0
        failed = 0
        rate_limited = 0

        for i, artifact in enumerate(artifacts, 1):
            try:
                # 下载前延迟
                if i > 1:
                    time.sleep(self.delay_between_downloads)

                logger.info(
                    "downloading_artifact",
                    artifact_id=artifact.id,
                    filing_id=artifact.filing_id,
                    url=artifact.url[:80]
                )

                success = self.downloader.download_artifact(session, artifact, run_id)

                if success:
                    succeeded += 1
                    logger.info("download_success", artifact_id=artifact.id)
                else:
                    failed += 1

                    # 检查是否是429错误
                    if artifact.error_message and '429' in artifact.error_message:
                        rate_limited += 1
                        logger.warning(
                            "rate_limit_detected",
                            artifact_id=artifact.id,
                            consecutive_429=rate_limited
                        )

                        # 如果连续3个429，增加延迟
                        if rate_limited >= 3:
                            logger.warning("increasing_delay_due_to_rate_limits")
                            self.delay_between_downloads *= 1.5
                            rate_limited = 0  # 重置计数

            except Exception as e:
                logger.error(
                    "download_exception",
                    artifact_id=artifact.id,
                    error=str(e)
                )
                failed += 1

        return {
            'succeeded': succeeded,
            'failed': failed,
            'rate_limited': rate_limited
        }

    def run(
        self,
        exchange: str = None,
        form_types: list = None,
        limit: int = None,
        skip_429: bool = True
    ):
        """
        执行安全下载

        Args:
            exchange: 指定交易所（如'NASDAQ'）
            form_types: 指定表格类型列表（如['20-F', '6-K']）
            limit: 限制下载数量
            skip_429: 是否跳过429错误的artifacts（建议True）
        """
        logger.info(
            "safe_download_started",
            batch_size=self.batch_size,
            delay_between_batches=self.delay_between_batches,
            delay_between_downloads=self.delay_between_downloads
        )

        with get_db_session() as session:
            # 创建执行记录
            run = ExecutionRun(
                run_type='safe_pending_download',
                started_at=datetime.utcnow(),
                status='running',
                meta_data={
                    'batch_size': self.batch_size,
                    'exchange': exchange,
                    'form_types': form_types
                }
            )
            session.add(run)
            session.commit()

            try:
                # 构建查询
                query = session.query(Artifact).join(Filing).join(Company).filter(
                    Artifact.status == 'pending_download'
                )

                # 如果skip_429，排除429错误
                if skip_429:
                    query = query.filter(
                        ~Artifact.error_message.like('%429%')
                    )

                # 按交易所过滤
                if exchange:
                    query = query.filter(Company.exchange == exchange)

                # 按表格类型过滤
                if form_types:
                    query = query.filter(Filing.form_type.in_(form_types))

                # 限制数量
                if limit:
                    query = query.limit(limit)

                # 按filing_date排序（先下载旧的）
                query = query.order_by(Filing.filing_date.asc())

                pending_artifacts = query.all()

                total_count = len(pending_artifacts)

                logger.info(
                    "pending_artifacts_loaded",
                    total=total_count,
                    exchange=exchange,
                    form_types=form_types
                )

                if total_count == 0:
                    logger.info("no_pending_artifacts_found")
                    run.status = 'completed'
                    run.completed_at = datetime.utcnow()
                    session.commit()
                    return

                # 分批处理
                num_batches = (total_count + self.batch_size - 1) // self.batch_size

                for batch_num in range(num_batches):
                    start_idx = batch_num * self.batch_size
                    end_idx = min(start_idx + self.batch_size, total_count)
                    batch = pending_artifacts[start_idx:end_idx]

                    logger.info(
                        "processing_batch",
                        batch_num=batch_num + 1,
                        total_batches=num_batches,
                        batch_size=len(batch)
                    )

                    # 下载批次
                    batch_result = self.download_batch(session, batch, run.id)

                    self.total_succeeded += batch_result['succeeded']
                    self.total_failed += batch_result['failed']
                    self.total_429_errors += batch_result['rate_limited']
                    self.total_attempted += len(batch)

                    # 进度报告
                    logger.info(
                        "batch_completed",
                        batch=f"{batch_num + 1}/{num_batches}",
                        batch_succeeded=batch_result['succeeded'],
                        batch_failed=batch_result['failed'],
                        total_succeeded=self.total_succeeded,
                        total_failed=self.total_failed,
                        total_429_errors=self.total_429_errors,
                        progress_pct=f"{(end_idx/total_count)*100:.1f}%"
                    )

                    # 批次间延迟
                    if batch_num < num_batches - 1:
                        logger.info(
                            "batch_delay",
                            seconds=self.delay_between_batches
                        )
                        time.sleep(self.delay_between_batches)

                    # 如果429错误过多，停止
                    if self.total_429_errors > 10:
                        logger.error(
                            "too_many_rate_limits",
                            total_429=self.total_429_errors,
                            action="stopping_download"
                        )
                        run.error_summary = f"Stopped due to {self.total_429_errors} rate limit errors"
                        break

                # 更新执行记录
                run.completed_at = datetime.utcnow()
                run.status = 'completed' if self.total_429_errors < 10 else 'failed'
                run.duration_seconds = int((run.completed_at - run.started_at).total_seconds())
                run.artifacts_attempted = self.total_attempted
                run.artifacts_succeeded = self.total_succeeded
                run.artifacts_failed = self.total_failed
                session.commit()

                # 最终统计
                logger.info(
                    "safe_download_completed",
                    total_attempted=self.total_attempted,
                    succeeded=self.total_succeeded,
                    failed=self.total_failed,
                    rate_limit_errors=self.total_429_errors,
                    success_rate=f"{(self.total_succeeded/self.total_attempted)*100:.1f}%"
                        if self.total_attempted > 0 else "0%",
                    duration_seconds=run.duration_seconds
                )

                print("\n" + "="*80)
                print("DOWNLOAD SUMMARY")
                print("="*80)
                print(f"Total Attempted: {self.total_attempted:,}")
                print(f"Succeeded: {self.total_succeeded:,}")
                print(f"Failed: {self.total_failed:,}")
                print(f"Rate Limit Errors (429): {self.total_429_errors:,}")
                print(f"Success Rate: {(self.total_succeeded/self.total_attempted)*100:.1f}%"
                      if self.total_attempted > 0 else "0%")
                print(f"Duration: {run.duration_seconds:,} seconds")
                print("="*80 + "\n")

            except Exception as e:
                run.status = 'failed'
                run.error_summary = str(e)
                run.completed_at = datetime.utcnow()
                session.commit()

                logger.error("safe_download_failed", error=str(e), exc_info=True)
                raise


def main():
    parser = argparse.ArgumentParser(
        description='Safely download pending artifacts with rate limiting',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Conservative settings (recommended to start)
  python safe_download_pending.py --batch-size 5 --batch-delay 3.0 --download-delay 0.2

  # NASDAQ only, small batch
  python safe_download_pending.py --exchange NASDAQ --limit 50

  # Foreign filings only (20-F, 6-K)
  python safe_download_pending.py --form-types 20-F,6-K --batch-size 10

  # Aggressive settings (use with caution!)
  python safe_download_pending.py --batch-size 20 --batch-delay 1.0 --download-delay 0.1

Recommended workflow for avoiding 429:
  1. Start conservative: --batch-size 5 --batch-delay 3.0
  2. Monitor logs for 429 errors
  3. If no 429 after 100 downloads, increase batch-size gradually
  4. If 429 appears, script will auto-increase delays
        """
    )

    parser.add_argument(
        '--batch-size',
        type=int,
        default=10,
        help='Artifacts per batch (default: 10, recommend 5-20)'
    )
    parser.add_argument(
        '--batch-delay',
        type=float,
        default=2.0,
        help='Delay between batches in seconds (default: 2.0, recommend 2.0-5.0)'
    )
    parser.add_argument(
        '--download-delay',
        type=float,
        default=0.15,
        help='Delay between individual downloads in seconds (default: 0.15, recommend 0.1-0.3)'
    )
    parser.add_argument(
        '--exchange',
        choices=['NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca'],
        help='Download only from specific exchange'
    )
    parser.add_argument(
        '--form-types',
        type=str,
        help='Comma-separated form types (e.g., 20-F,6-K)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit total downloads (for testing)'
    )
    parser.add_argument(
        '--no-skip-429',
        action='store_true',
        help='Include artifacts that previously got 429 errors (not recommended)'
    )

    args = parser.parse_args()

    # 解析form types
    form_types = None
    if args.form_types:
        form_types = [ft.strip() for ft in args.form_types.split(',')]

    # 创建下载器
    downloader = SafeDownloader(
        batch_size=args.batch_size,
        delay_between_batches=args.batch_delay,
        delay_between_downloads=args.download_delay
    )

    # 执行下载
    downloader.run(
        exchange=args.exchange,
        form_types=form_types,
        limit=args.limit,
        skip_429=not args.no_skip_429
    )


if __name__ == '__main__':
    main()
