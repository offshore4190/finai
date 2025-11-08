"""
Coverage Progress Tracker
追踪和可视化覆盖率改进进度
"""
import argparse
from datetime import datetime, date
from collections import defaultdict
import structlog
from sqlalchemy import func, and_

from config.db import get_db_session
from models import Company, Filing, Artifact, ExecutionRun

logger = structlog.get_logger()


class CoverageTracker:
    """覆盖率进度追踪器"""

    def __init__(self):
        pass

    def get_current_stats(self) -> dict:
        """获取当前统计数据"""
        with get_db_session() as session:
            # 总体统计
            total_companies = session.query(func.count(Company.id)).filter(
                Company.status == 'active',
                Company.is_active == True
            ).scalar()

            companies_with_filings = session.query(
                func.count(func.distinct(Company.id))
            ).join(Filing).filter(
                Company.status == 'active',
                Company.is_active == True
            ).scalar()

            coverage_pct = (companies_with_filings / total_companies * 100) if total_companies > 0 else 0

            # 按交易所统计
            exchange_stats = {}
            exchanges = ['NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca']

            for exchange in exchanges:
                total = session.query(func.count(Company.id)).filter(
                    Company.exchange == exchange,
                    Company.status == 'active',
                    Company.is_active == True
                ).scalar()

                with_data = session.query(
                    func.count(func.distinct(Company.id))
                ).join(Filing).filter(
                    Company.exchange == exchange,
                    Company.status == 'active',
                    Company.is_active == True
                ).scalar()

                pct = (with_data / total * 100) if total > 0 else 0

                exchange_stats[exchange] = {
                    'total': total,
                    'with_data': with_data,
                    'coverage': pct,
                    'missing': total - with_data
                }

            # Artifacts统计
            artifact_stats = {}
            artifact_counts = session.query(
                Artifact.status,
                func.count(Artifact.id)
            ).group_by(Artifact.status).all()

            total_artifacts = sum(count for _, count in artifact_counts)

            for status, count in artifact_counts:
                artifact_stats[status] = {
                    'count': count,
                    'pct': (count / total_artifacts * 100) if total_artifacts > 0 else 0
                }

            # Filings统计
            total_filings = session.query(func.count(Filing.id)).scalar()

            filings_by_type = session.query(
                Filing.form_type,
                func.count(Filing.id)
            ).group_by(Filing.form_type).order_by(
                func.count(Filing.id).desc()
            ).all()

            # 海外公司统计
            foreign_total = session.query(func.count(Company.id)).filter(
                Company.status == 'active',
                Company.is_active == True,
                Company.is_foreign == True
            ).scalar()

            foreign_with_data = session.query(
                func.count(func.distinct(Company.id))
            ).join(Filing).filter(
                Company.status == 'active',
                Company.is_active == True,
                Company.is_foreign == True
            ).scalar()

            foreign_coverage = (foreign_with_data / foreign_total * 100) if foreign_total > 0 else 0

            return {
                'timestamp': datetime.now(),
                'overall': {
                    'total': total_companies,
                    'with_data': companies_with_filings,
                    'coverage': coverage_pct,
                    'missing': total_companies - companies_with_filings
                },
                'by_exchange': exchange_stats,
                'artifacts': {
                    'total': total_artifacts,
                    'by_status': artifact_stats
                },
                'filings': {
                    'total': total_filings,
                    'by_type': dict(filings_by_type)
                },
                'foreign': {
                    'total': foreign_total,
                    'with_data': foreign_with_data,
                    'coverage': foreign_coverage,
                    'missing': foreign_total - foreign_with_data
                }
            }

    def print_dashboard(self, stats: dict):
        """打印仪表板"""
        print("\n" + "="*80)
        print(f"COVERAGE DASHBOARD - {stats['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")

        # 总体覆盖率
        overall = stats['overall']
        print("📊 OVERALL COVERAGE")
        print("-"*80)
        print(f"Total Target Companies:  {overall['total']:,}")
        print(f"Companies with Data:     {overall['with_data']:,}")
        print(f"Coverage Rate:           {overall['coverage']:.2f}%")
        print(f"Missing Companies:       {overall['missing']:,}")

        # 进度条
        bar_length = 50
        filled = int(bar_length * overall['coverage'] / 100)
        bar = '█' * filled + '░' * (bar_length - filled)
        print(f"\n[{bar}] {overall['coverage']:.1f}%\n")

        # 按交易所
        print("📈 COVERAGE BY EXCHANGE")
        print("-"*80)
        print(f"{'Exchange':<20} {'Total':<10} {'With Data':<10} {'Coverage':<12} {'Missing':<10}")
        print("-"*80)

        for exchange, data in stats['by_exchange'].items():
            bar_mini = '█' * int(data['coverage'] / 10) + '░' * (10 - int(data['coverage'] / 10))
            print(
                f"{exchange:<20} "
                f"{data['total']:<10,} "
                f"{data['with_data']:<10,} "
                f"{bar_mini} {data['coverage']:>5.1f}%  "
                f"{data['missing']:<10,}"
            )

        # 海外公司
        foreign = stats['foreign']
        if foreign['total'] > 0:
            print(f"\n🌐 FOREIGN COMPANIES (is_foreign=TRUE)")
            print("-"*80)
            print(f"Total Foreign Companies: {foreign['total']:,}")
            print(f"With Data:               {foreign['with_data']:,}")
            print(f"Coverage:                {foreign['coverage']:.2f}%")
            print(f"Missing:                 {foreign['missing']:,}")

        # Artifacts状态
        artifacts = stats['artifacts']
        print(f"\n📦 ARTIFACTS STATUS")
        print("-"*80)
        print(f"Total Artifacts:         {artifacts['total']:,}\n")

        for status, data in sorted(
            artifacts['by_status'].items(),
            key=lambda x: -x[1]['count']
        ):
            status_icon = {
                'downloaded': '✓',
                'skipped': '◯',
                'pending_download': '⧗',
                'downloading': '⟳',
                'failed': '✗'
            }.get(status, '?')

            print(f"  {status_icon} {status:<20} {data['count']:>8,}  ({data['pct']:>5.1f}%)")

        # Filings类型
        filings = stats['filings']
        print(f"\n📄 FILINGS BY TYPE (Top 10)")
        print("-"*80)
        print(f"Total Filings:           {filings['total']:,}\n")

        sorted_types = sorted(
            filings['by_type'].items(),
            key=lambda x: -x[1]
        )[:10]

        for form_type, count in sorted_types:
            pct = (count / filings['total'] * 100) if filings['total'] > 0 else 0
            print(f"  {form_type:<15} {count:>8,}  ({pct:>5.1f}%)")

        print("\n" + "="*80 + "\n")

    def save_snapshot(self, stats: dict):
        """保存统计快照到数据库"""
        with get_db_session() as session:
            run = ExecutionRun(
                run_type='coverage_snapshot',
                started_at=stats['timestamp'],
                completed_at=stats['timestamp'],
                status='completed',
                meta_data={
                    'overall': stats['overall'],
                    'by_exchange': stats['by_exchange'],
                    'foreign': stats['foreign'],
                    'artifacts_total': stats['artifacts']['total']
                }
            )
            session.add(run)
            session.commit()

            logger.info(
                "snapshot_saved",
                coverage=stats['overall']['coverage'],
                companies=stats['overall']['with_data']
            )

    def compare_with_previous(self) -> dict:
        """与上次快照对比"""
        with get_db_session() as session:
            # 获取最近两次快照
            snapshots = session.query(ExecutionRun).filter(
                ExecutionRun.run_type == 'coverage_snapshot'
            ).order_by(ExecutionRun.started_at.desc()).limit(2).all()

            if len(snapshots) < 2:
                return None

            current = snapshots[0].meta_data
            previous = snapshots[1].meta_data

            # 计算差异
            diff = {
                'time_diff': snapshots[0].started_at - snapshots[1].started_at,
                'coverage_change': current['overall']['coverage'] - previous['overall']['coverage'],
                'companies_change': current['overall']['with_data'] - previous['overall']['with_data'],
                'by_exchange': {}
            }

            for exchange in current['by_exchange']:
                if exchange in previous['by_exchange']:
                    diff['by_exchange'][exchange] = {
                        'coverage_change': current['by_exchange'][exchange]['coverage'] - previous['by_exchange'][exchange]['coverage'],
                        'companies_change': current['by_exchange'][exchange]['with_data'] - previous['by_exchange'][exchange]['with_data']
                    }

            return diff

    def print_comparison(self, diff: dict):
        """打印对比结果"""
        if not diff:
            print("\n⚠️  No previous snapshot found for comparison.\n")
            return

        print("\n" + "="*80)
        print("PROGRESS SINCE LAST SNAPSHOT")
        print("="*80 + "\n")

        time_str = str(diff['time_diff']).split('.')[0]  # 去掉微秒
        print(f"Time since last snapshot: {time_str}")

        # 总体变化
        coverage_icon = '📈' if diff['coverage_change'] > 0 else '📉' if diff['coverage_change'] < 0 else '➡️'
        companies_icon = '⬆️' if diff['companies_change'] > 0 else '⬇️' if diff['companies_change'] < 0 else '➡️'

        print(f"\n{coverage_icon} Coverage: {diff['coverage_change']:+.2f}%")
        print(f"{companies_icon} Companies with data: {diff['companies_change']:+,}\n")

        # 按交易所
        print("By Exchange:")
        print("-"*60)
        for exchange, data in diff['by_exchange'].items():
            if data['coverage_change'] != 0 or data['companies_change'] != 0:
                print(
                    f"  {exchange:<20} "
                    f"Coverage: {data['coverage_change']:+.2f}%  "
                    f"Companies: {data['companies_change']:+,}"
                )

        print("\n" + "="*80 + "\n")

    def generate_report(self, save: bool = False, compare: bool = False):
        """生成完整报告"""
        stats = self.get_current_stats()
        self.print_dashboard(stats)

        if save:
            self.save_snapshot(stats)
            print("✅ Snapshot saved to database.\n")

        if compare:
            diff = self.compare_with_previous()
            self.print_comparison(diff)


def main():
    parser = argparse.ArgumentParser(
        description='Track and visualize coverage improvement progress',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show current dashboard
  python coverage_progress_tracker.py

  # Save snapshot and compare
  python coverage_progress_tracker.py --save --compare

  # Daily routine
  python coverage_progress_tracker.py --save

Recommended usage:
  Run daily or after major operations to track progress:
  - After processing pending downloads
  - After marking foreign companies
  - After backfill operations
        """
    )
    parser.add_argument(
        '--save',
        action='store_true',
        help='Save current stats as snapshot'
    )
    parser.add_argument(
        '--compare',
        action='store_true',
        help='Compare with previous snapshot'
    )

    args = parser.parse_args()

    tracker = CoverageTracker()
    tracker.generate_report(save=args.save, compare=args.compare)


if __name__ == '__main__':
    main()
