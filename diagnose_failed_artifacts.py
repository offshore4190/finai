"""
Failed Artifacts Diagnostic Tool
安全地分析失败的artifacts，识别根本原因
"""
import structlog
from datetime import datetime
from collections import defaultdict
from sqlalchemy import func, and_, or_
from config.db import get_db_session
from models import Artifact, Filing, Company

logger = structlog.get_logger()


def analyze_failed_artifacts():
    """分析失败的artifacts，生成详细报告"""

    with get_db_session() as session:
        print("\n" + "="*80)
        print("FAILED ARTIFACTS DIAGNOSTIC REPORT")
        print("="*80 + "\n")

        # 1. 总体统计
        total_artifacts = session.query(func.count(Artifact.id)).scalar()
        failed_artifacts = session.query(Artifact).filter(
            Artifact.status == 'failed'
        ).all()

        print(f"Total Artifacts: {total_artifacts:,}")
        print(f"Failed Artifacts: {len(failed_artifacts):,} ({len(failed_artifacts)/total_artifacts*100:.2f}%)\n")

        # 2. 按错误类型分组
        print("-" * 80)
        print("FAILURE ANALYSIS BY ERROR TYPE")
        print("-" * 80)

        error_types = defaultdict(lambda: {'count': 0, 'examples': []})

        for artifact in failed_artifacts:
            error_msg = artifact.error_message or 'Unknown'

            # 分类错误
            if '404' in error_msg or 'Not Found' in error_msg:
                error_key = '404_NOT_FOUND'
            elif '429' in error_msg or 'Too Many Requests' in error_msg:
                error_key = '429_RATE_LIMIT'
            elif '403' in error_msg or 'Forbidden' in error_msg:
                error_key = '403_FORBIDDEN'
            elif '500' in error_msg or '503' in error_msg:
                error_key = '5XX_SERVER_ERROR'
            elif 'timeout' in error_msg.lower():
                error_key = 'TIMEOUT'
            else:
                error_key = 'OTHER'

            error_types[error_key]['count'] += 1

            # 保存前5个样例
            if len(error_types[error_key]['examples']) < 5:
                filing = artifact.filing
                company = filing.company
                error_types[error_key]['examples'].append({
                    'artifact_id': artifact.id,
                    'ticker': company.ticker,
                    'cik': company.cik,
                    'form_type': filing.form_type,
                    'filing_date': filing.filing_date,
                    'url': artifact.url,
                    'error': error_msg[:100]
                })

        for error_key, data in sorted(error_types.items(), key=lambda x: -x[1]['count']):
            print(f"\n{error_key}: {data['count']:,} failures")
            print("  Examples:")
            for ex in data['examples']:
                print(f"    - {ex['ticker']} (CIK:{ex['cik']}) | {ex['form_type']} | {ex['filing_date']}")
                print(f"      URL: {ex['url'][:80]}...")
                print(f"      Error: {ex['error']}")

        # 3. 按Form Type分组
        print("\n" + "-" * 80)
        print("FAILURES BY FORM TYPE")
        print("-" * 80)

        form_type_failures = session.query(
            Filing.form_type,
            func.count(Artifact.id).label('failed_count')
        ).join(Filing).filter(
            Artifact.status == 'failed'
        ).group_by(Filing.form_type).order_by(
            func.count(Artifact.id).desc()
        ).all()

        print(f"\n{'Form Type':<15} {'Failed Artifacts':<20}")
        print("-" * 35)
        for form_type, count in form_type_failures:
            print(f"{form_type:<15} {count:,}")

        # 4. 按公司分组（找出问题公司）
        print("\n" + "-" * 80)
        print("TOP 20 COMPANIES WITH MOST FAILURES")
        print("-" * 80)

        company_failures = session.query(
            Company.ticker,
            Company.cik,
            Company.company_name,
            Company.is_foreign,
            func.count(Artifact.id).label('failed_count')
        ).join(Filing).join(Artifact).filter(
            Artifact.status == 'failed'
        ).group_by(
            Company.id, Company.ticker, Company.cik, Company.company_name, Company.is_foreign
        ).order_by(
            func.count(Artifact.id).desc()
        ).limit(20).all()

        print(f"\n{'Ticker':<10} {'CIK':<12} {'Foreign':<10} {'Failures':<10} {'Company Name':<40}")
        print("-" * 82)
        for ticker, cik, name, is_foreign, count in company_failures:
            foreign_flag = 'Yes' if is_foreign else 'No'
            print(f"{ticker:<10} {cik:<12} {foreign_flag:<10} {count:<10} {name[:38] if name else 'N/A':<40}")

        # 5. 检查未来日期问题
        print("\n" + "-" * 80)
        print("FUTURE-DATED FILINGS (2025+)")
        print("-" * 80)

        today = datetime.now().date()
        future_filings = session.query(
            Filing.form_type,
            func.count(Filing.id).label('count')
        ).join(Artifact).filter(
            Artifact.status == 'failed',
            Filing.filing_date > today
        ).group_by(Filing.form_type).all()

        if future_filings:
            print(f"\n{'Form Type':<15} {'Future Filings':<20}")
            print("-" * 35)
            for form_type, count in future_filings:
                print(f"{form_type:<15} {count}")
        else:
            print("\nNo future-dated filings found.")

        # 6. 检查特定公司的CIK问题（SPOT案例）
        print("\n" + "-" * 80)
        print("CIK VERIFICATION FOR PROBLEM COMPANIES")
        print("-" * 80)

        problem_tickers = ['SPOT', 'TTE', 'TD']  # 从报告中提到的

        for ticker in problem_tickers:
            companies = session.query(Company).filter(
                Company.ticker == ticker
            ).all()

            print(f"\n{ticker}:")
            if len(companies) == 0:
                print("  Not found in database")
            else:
                for company in companies:
                    print(f"  CIK: {company.cik} | Exchange: {company.exchange} | Foreign: {company.is_foreign}")

                    # 查找该公司的失败artifacts
                    failed_count = session.query(func.count(Artifact.id)).join(Filing).filter(
                        Filing.company_id == company.id,
                        Artifact.status == 'failed'
                    ).scalar()

                    print(f"  Failed Artifacts: {failed_count}")

        # 7. 生成安全清理建议
        print("\n" + "="*80)
        print("SAFE CLEANUP RECOMMENDATIONS")
        print("="*80 + "\n")

        # 统计可安全删除的类别
        safe_delete_404 = session.query(func.count(Artifact.id)).filter(
            Artifact.status == 'failed',
            Artifact.retry_count >= 3,
            Artifact.error_message.like('%404%')
        ).scalar()

        safe_delete_future = session.query(func.count(Artifact.id)).join(Filing).filter(
            Artifact.status == 'failed',
            Filing.filing_date > today
        ).scalar()

        print(f"1. 404 Errors (after 3+ retries): {safe_delete_404:,} artifacts")
        print(f"   These URLs are permanently invalid and safe to remove.\n")

        print(f"2. Future-dated Filings: {safe_delete_future:,} artifacts")
        print(f"   These filings don't exist yet and safe to remove.\n")

        print(f"3. Rate Limited (429): Keep and retry with slower settings")
        print(f"   These are temporary failures.\n")

        # 8. 导出详细CSV报告
        print("\n" + "-" * 80)
        print("EXPORT OPTIONS")
        print("-" * 80)
        print("\nTo export detailed failure data to CSV:")
        print("  python export_failed_artifacts.py")
        print("\nTo verify specific CIKs against SEC:")
        print("  python verify_cik_mappings.py --ticker SPOT,TTE,TD")

        print("\n" + "="*80 + "\n")


if __name__ == '__main__':
    analyze_failed_artifacts()
