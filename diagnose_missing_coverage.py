"""
Missing Coverage Diagnostic Tool
诊断为什么1,540家公司没有filings数据
"""
import structlog
from datetime import datetime
from collections import defaultdict
from sqlalchemy import func, and_, or_

from config.db import get_db_session
from models import Company, Filing, Artifact
from services.sec_api import SECAPIClient

logger = structlog.get_logger()


class MissingCoverageDiagnostic:
    """诊断缺失覆盖的原因"""

    def __init__(self):
        self.sec_client = SECAPIClient()
        self.results = {
            'no_sec_data': [],        # SEC返回空数据
            'only_foreign_forms': [],  # 只有20-F/6-K等海外表格
            'only_other_forms': [],    # 有其他表格但无10-K/10-Q
            'recent_ipos': [],         # 2023年后上市的新公司
            'delisted': [],            # 可能已退市
            'etf_marked': [],          # 标记为ETF
            'cik_error': [],           # CIK无效
        }

    def check_company_sec_data(self, company: Company) -> dict:
        """
        检查单个公司在SEC的数据情况

        Returns:
            {
                'has_data': bool,
                'form_types': list,
                'filing_count': int,
                'earliest_filing': date,
                'reason': str
            }
        """
        try:
            # 获取SEC submissions
            submissions = self.sec_client.fetch_company_submissions(company.cik)

            if not submissions or 'filings' not in submissions:
                return {
                    'has_data': False,
                    'form_types': [],
                    'filing_count': 0,
                    'reason': 'NO_SEC_DATA'
                }

            recent_filings = submissions.get('filings', {}).get('recent', {})

            if not recent_filings or not recent_filings.get('form'):
                return {
                    'has_data': False,
                    'form_types': [],
                    'filing_count': 0,
                    'reason': 'EMPTY_FILINGS'
                }

            # 分析表格类型
            form_types = recent_filings.get('form', [])
            filing_dates = recent_filings.get('filingDate', [])

            # 统计表格类型
            form_type_counts = defaultdict(int)
            for form in form_types:
                form_type_counts[form] += 1

            # 检查是否有10-K/10-Q
            has_domestic_forms = any(
                form in form_types
                for form in ['10-K', '10-K/A', '10-Q', '10-Q/A']
            )

            # 检查是否有20-F/6-K
            has_foreign_forms = any(
                form in form_types
                for form in ['20-F', '20-F/A', '6-K', '6-K/A', '40-F', '40-F/A']
            )

            # 找到最早的filing日期
            earliest_filing = None
            if filing_dates:
                try:
                    dates = [datetime.strptime(d, '%Y-%m-%d').date() for d in filing_dates if d]
                    earliest_filing = min(dates) if dates else None
                except:
                    pass

            # 判断原因
            reason = 'UNKNOWN'
            if has_foreign_forms and not has_domestic_forms:
                reason = 'ONLY_FOREIGN_FORMS'
            elif not has_domestic_forms and len(form_type_counts) > 0:
                reason = 'ONLY_OTHER_FORMS'
            elif earliest_filing and earliest_filing.year >= 2023:
                reason = 'RECENT_IPO'
            elif len(form_types) == 0:
                reason = 'NO_FILINGS'

            return {
                'has_data': True,
                'form_types': list(form_type_counts.keys()),
                'form_type_counts': dict(form_type_counts),
                'filing_count': len(form_types),
                'earliest_filing': earliest_filing,
                'has_domestic_forms': has_domestic_forms,
                'has_foreign_forms': has_foreign_forms,
                'reason': reason
            }

        except Exception as e:
            error_str = str(e)

            # 判断错误类型
            if '404' in error_str:
                reason = 'CIK_NOT_FOUND'
            elif '403' in error_str:
                reason = 'CIK_FORBIDDEN'
            else:
                reason = 'API_ERROR'

            logger.error(
                "sec_check_failed",
                ticker=company.ticker,
                cik=company.cik,
                error=error_str
            )

            return {
                'has_data': False,
                'form_types': [],
                'filing_count': 0,
                'reason': reason,
                'error': error_str
            }

    def analyze_missing_companies(self, limit: int = None, sample_size: int = 100):
        """
        分析没有filings的公司

        Args:
            limit: 限制检查的公司数量
            sample_size: 采样数量（如果total > limit）
        """
        with get_db_session() as session:
            # 找出没有filings的公司
            companies_without_filings = session.query(Company).outerjoin(Filing).filter(
                Company.status == 'active',
                Company.is_active == True,
                Company.exchange.in_(['NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca']),
                Filing.id == None  # 没有关联的filings
            ).all()

            total_missing = len(companies_without_filings)

            print("\n" + "="*80)
            print("MISSING COVERAGE DIAGNOSTIC")
            print("="*80)
            print(f"\nTotal companies without filings: {total_missing:,}\n")

            # 按交易所分组
            by_exchange = defaultdict(int)
            for company in companies_without_filings:
                by_exchange[company.exchange] += 1

            print("By Exchange:")
            print("-"*40)
            for exchange, count in sorted(by_exchange.items(), key=lambda x: -x[1]):
                print(f"  {exchange:<20} {count:,}")

            # 采样检查
            if limit and total_missing > limit:
                print(f"\nSampling {limit} companies for detailed analysis...")
                import random
                sampled_companies = random.sample(companies_without_filings, limit)
            else:
                sampled_companies = companies_without_filings[:sample_size]

            print(f"\nAnalyzing {len(sampled_companies)} companies (this may take a few minutes)...\n")

            # 逐个检查
            reason_counts = defaultdict(int)
            company_details = []

            for i, company in enumerate(sampled_companies, 1):
                if i % 10 == 0:
                    print(f"  Progress: {i}/{len(sampled_companies)}...")

                result = self.check_company_sec_data(company)
                reason = result['reason']
                reason_counts[reason] += 1

                company_details.append({
                    'ticker': company.ticker,
                    'cik': company.cik,
                    'exchange': company.exchange,
                    'is_foreign': company.is_foreign,
                    **result
                })

                # 分类存储
                if reason == 'NO_SEC_DATA' or reason == 'EMPTY_FILINGS':
                    self.results['no_sec_data'].append(company)
                elif reason == 'ONLY_FOREIGN_FORMS':
                    self.results['only_foreign_forms'].append(company)
                elif reason == 'ONLY_OTHER_FORMS':
                    self.results['only_other_forms'].append(company)
                elif reason == 'RECENT_IPO':
                    self.results['recent_ipos'].append(company)
                elif reason == 'CIK_NOT_FOUND' or reason == 'CIK_FORBIDDEN':
                    self.results['cik_error'].append(company)

            # 打印结果
            print("\n" + "="*80)
            print("DIAGNOSTIC RESULTS (Sample Analysis)")
            print("="*80 + "\n")

            print(f"{'Reason':<30} {'Count':<10} {'%':<10} {'Estimated Total'}")
            print("-"*70)

            for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
                pct = (count / len(sampled_companies)) * 100
                estimated_total = int((count / len(sampled_companies)) * total_missing)
                print(f"{reason:<30} {count:<10} {pct:>5.1f}%    ~{estimated_total:,}")

            # 打印样例
            print("\n" + "="*80)
            print("SAMPLE COMPANIES BY REASON")
            print("="*80 + "\n")

            # 只有海外表格的公司
            if self.results['only_foreign_forms']:
                print("🌐 ONLY FOREIGN FORMS (20-F/6-K) - Should be marked as is_foreign:")
                print("-"*70)
                for company in self.results['only_foreign_forms'][:10]:
                    print(f"  {company.ticker:<10} CIK:{company.cik:<12} {company.exchange:<15} is_foreign={company.is_foreign}")
                print()

            # 新上市的公司
            if self.results['recent_ipos']:
                print("🆕 RECENT IPOs (2023+) - May not have 3 years of data:")
                print("-"*70)
                for company in self.results['recent_ipos'][:10]:
                    print(f"  {company.ticker:<10} CIK:{company.cik:<12} {company.exchange}")
                print()

            # 只有其他表格的公司
            if self.results['only_other_forms']:
                print("📋 OTHER FORMS ONLY (no 10-K/10-Q) - e.g., S-1, 8-K only:")
                print("-"*70)
                for company in self.results['only_other_forms'][:10]:
                    print(f"  {company.ticker:<10} CIK:{company.cik:<12} {company.exchange}")
                print()

            # CIK错误
            if self.results['cik_error']:
                print("❌ CIK ERRORS (404/403) - Invalid CIK:")
                print("-"*70)
                for company in self.results['cik_error'][:10]:
                    print(f"  {company.ticker:<10} CIK:{company.cik:<12} {company.exchange}")
                print()

            # 无SEC数据
            if self.results['no_sec_data']:
                print("⚠️  NO SEC DATA - Empty submissions:")
                print("-"*70)
                for company in self.results['no_sec_data'][:10]:
                    print(f"  {company.ticker:<10} CIK:{company.cik:<12} {company.exchange}")
                print()

            # 生成推荐
            print("\n" + "="*80)
            print("RECOMMENDATIONS")
            print("="*80 + "\n")

            total_foreign = len(self.results['only_foreign_forms'])
            if total_foreign > 0:
                estimated_foreign = int((total_foreign / len(sampled_companies)) * total_missing)
                print(f"1. Mark ~{estimated_foreign:,} companies as is_foreign=TRUE")
                print(f"   Then run: python main.py foreign-backfill")
                print(f"   Estimated improvement: +{estimated_foreign:,} companies\n")

            total_recent = len(self.results['recent_ipos'])
            if total_recent > 0:
                estimated_recent = int((total_recent / len(sampled_companies)) * total_missing)
                print(f"2. Recent IPOs (~{estimated_recent:,} companies)")
                print(f"   These may not have full 2023-2025 data yet")
                print(f"   Consider extending date range to 2024-2025 only\n")

            total_cik_errors = len(self.results['cik_error'])
            if total_cik_errors > 0:
                estimated_cik = int((total_cik_errors / len(sampled_companies)) * total_missing)
                print(f"3. Fix CIK errors (~{estimated_cik:,} companies)")
                print(f"   Run: python verify_cik_mappings.py --batch --limit 200\n")

            total_other = len(self.results['only_other_forms'])
            if total_other > 0:
                estimated_other = int((total_other / len(sampled_companies)) * total_missing)
                print(f"4. Other forms only (~{estimated_other:,} companies)")
                print(f"   These companies may not file 10-K/10-Q (e.g., SPACs, shells)")
                print(f"   Consider excluding from target coverage\n")

            # 导出详细列表
            print("\n" + "="*80)
            print("EXPORT OPTIONS")
            print("="*80 + "\n")
            print("To export full list of foreign companies for batch update:")
            print("  python diagnose_missing_coverage.py --export-foreign")
            print("\nTo export all missing companies with details:")
            print("  python diagnose_missing_coverage.py --export-all")

    def export_foreign_companies_sql(self):
        """导出需要标记为is_foreign的公司的SQL"""
        if not self.results['only_foreign_forms']:
            print("No foreign companies found in current analysis.")
            return

        output_file = 'mark_foreign_companies.sql'

        with open(output_file, 'w') as f:
            f.write("-- Mark companies with only foreign forms as is_foreign=TRUE\n")
            f.write("-- Generated on: {}\n\n".format(datetime.now()))

            f.write("BEGIN;\n\n")

            for company in self.results['only_foreign_forms']:
                f.write(f"-- {company.ticker} ({company.exchange})\n")
                f.write(f"UPDATE companies SET is_foreign = TRUE, updated_at = NOW() ")
                f.write(f"WHERE ticker = '{company.ticker}' AND cik = '{company.cik}';\n\n")

            f.write("COMMIT;\n")

            f.write(f"\n-- Total companies to mark: {len(self.results['only_foreign_forms'])}\n")

        print(f"\n✅ Exported SQL to: {output_file}")
        print(f"   Companies to mark: {len(self.results['only_foreign_forms']):,}")
        print(f"\n⚠️  Review the SQL file before executing:")
        print(f"   psql -d filings_db -f {output_file}")


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='Diagnose why companies are missing from coverage',
        epilog="""
Examples:
  # Analyze 100 sample companies
  python diagnose_missing_coverage.py

  # Analyze all missing companies
  python diagnose_missing_coverage.py --sample-size 1000

  # Export SQL to mark foreign companies
  python diagnose_missing_coverage.py --export-foreign
        """
    )
    parser.add_argument(
        '--sample-size',
        type=int,
        default=100,
        help='Number of companies to analyze (default: 100)'
    )
    parser.add_argument(
        '--export-foreign',
        action='store_true',
        help='Export SQL to mark foreign companies'
    )

    args = parser.parse_args()

    diagnostic = MissingCoverageDiagnostic()
    diagnostic.analyze_missing_companies(sample_size=args.sample_size)

    if args.export_foreign:
        diagnostic.export_foreign_companies_sql()


if __name__ == '__main__':
    main()
