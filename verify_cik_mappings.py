"""
CIK Verification Tool
验证数据库中的CIK号码是否与SEC官方数据匹配
"""
import argparse
import time
import structlog
from typing import Dict, Optional
import httpx

from config.db import get_db_session
from models import Company
from services.sec_api import SECAPIClient

logger = structlog.get_logger()


class CIKVerifier:
    """CIK验证器"""

    def __init__(self):
        self.sec_client = SECAPIClient()
        self.correct_ciks = {}  # ticker -> correct_cik

    def fetch_official_cik(self, ticker: str) -> Optional[str]:
        """
        从SEC官方API获取正确的CIK

        Args:
            ticker: 股票代码

        Returns:
            正确的CIK（10位，带前导零）或None
        """
        try:
            # SEC company tickers API
            company_tickers = self.sec_client.fetch_company_tickers()

            # 遍历查找匹配的ticker
            for key, data in company_tickers.items():
                if data.get('ticker', '').upper() == ticker.upper():
                    cik_int = data.get('cik_str')
                    if cik_int is not None:
                        # 转换为10位字符串
                        return str(cik_int).zfill(10)

            logger.warning("ticker_not_found_in_sec", ticker=ticker)
            return None

        except Exception as e:
            logger.error("cik_fetch_failed", ticker=ticker, error=str(e))
            return None

    def verify_company_cik(self, company: Company) -> Dict:
        """
        验证单个公司的CIK

        Returns:
            {
                'ticker': str,
                'db_cik': str,
                'official_cik': str,
                'match': bool,
                'recommendation': str
            }
        """
        ticker = company.ticker
        db_cik = company.cik.zfill(10)  # 确保10位

        logger.info("verifying_cik", ticker=ticker, db_cik=db_cik)

        # 从SEC获取官方CIK
        official_cik = self.fetch_official_cik(ticker)

        if official_cik is None:
            return {
                'ticker': ticker,
                'db_cik': db_cik,
                'official_cik': 'NOT_FOUND',
                'match': False,
                'recommendation': f'Ticker {ticker} not found in SEC database - may be delisted or wrong ticker'
            }

        match = (db_cik == official_cik)

        if match:
            recommendation = 'CIK is correct'
        else:
            recommendation = f'UPDATE CIK: {db_cik} → {official_cik}'
            self.correct_ciks[ticker] = official_cik

        return {
            'ticker': ticker,
            'db_cik': db_cik,
            'official_cik': official_cik,
            'match': match,
            'recommendation': recommendation
        }

    def verify_multiple_companies(self, tickers: list) -> list:
        """
        验证多个公司

        Args:
            tickers: ticker列表

        Returns:
            验证结果列表
        """
        results = []

        with get_db_session() as session:
            for ticker in tickers:
                # 从数据库查找公司
                companies = session.query(Company).filter(
                    Company.ticker == ticker.upper()
                ).all()

                if not companies:
                    logger.warning("ticker_not_in_db", ticker=ticker)
                    results.append({
                        'ticker': ticker,
                        'db_cik': 'NOT_IN_DB',
                        'official_cik': 'N/A',
                        'match': False,
                        'recommendation': f'Ticker {ticker} not found in local database'
                    })
                    continue

                # 如果有多条记录，全部验证
                for company in companies:
                    result = self.verify_company_cik(company)
                    result['company_id'] = company.id
                    result['exchange'] = company.exchange
                    result['is_foreign'] = company.is_foreign
                    results.append(result)

                # Rate limiting
                time.sleep(0.1)

        return results

    def print_results(self, results: list):
        """打印验证结果"""
        print("\n" + "="*100)
        print("CIK VERIFICATION RESULTS")
        print("="*100 + "\n")

        print(f"{'Ticker':<10} {'DB CIK':<12} {'Official CIK':<14} {'Match':<8} {'Recommendation':<40}")
        print("-"*100)

        mismatches = []

        for result in results:
            match_str = '✓' if result['match'] else '✗'
            print(f"{result['ticker']:<10} {result['db_cik']:<12} {result['official_cik']:<14} {match_str:<8} {result['recommendation']:<40}")

            if not result['match'] and result['official_cik'] != 'NOT_FOUND':
                mismatches.append(result)

        print("\n" + "="*100)
        print(f"SUMMARY: {len([r for r in results if r['match']])} matches, {len(mismatches)} mismatches")
        print("="*100 + "\n")

        if mismatches:
            print("\n" + "-"*100)
            print("SQL UPDATE STATEMENTS (Review before executing!)")
            print("-"*100 + "\n")

            for m in mismatches:
                if 'company_id' in m:
                    print(f"-- {m['ticker']}: {m['db_cik']} → {m['official_cik']}")
                    print(f"UPDATE companies SET cik = '{m['official_cik']}', updated_at = NOW() WHERE id = {m['company_id']};")
                    print()

    def batch_verify_failed_companies(self, limit: int = 50):
        """
        批量验证失败artifacts最多的公司

        Args:
            limit: 验证公司数量上限
        """
        with get_db_session() as session:
            from sqlalchemy import func
            from models import Artifact, Filing

            # 找出失败artifacts最多的公司
            problem_companies = session.query(
                Company.ticker,
                func.count(Artifact.id).label('failed_count')
            ).join(Filing).join(Artifact).filter(
                Artifact.status == 'failed'
            ).group_by(Company.ticker).order_by(
                func.count(Artifact.id).desc()
            ).limit(limit).all()

            tickers = [ticker for ticker, _ in problem_companies]

            logger.info("verifying_problem_companies", count=len(tickers))

            results = self.verify_multiple_companies(tickers)
            self.print_results(results)

            return results


def main():
    parser = argparse.ArgumentParser(description='Verify CIK mappings against SEC official data')
    parser.add_argument(
        '--ticker',
        type=str,
        help='Comma-separated list of tickers to verify (e.g., SPOT,TTE,TD)'
    )
    parser.add_argument(
        '--batch',
        action='store_true',
        help='Verify top companies with most failed artifacts'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=50,
        help='Limit for batch verification (default: 50)'
    )

    args = parser.parse_args()

    verifier = CIKVerifier()

    if args.batch:
        print("Running batch verification for companies with most failures...\n")
        verifier.batch_verify_failed_companies(limit=args.limit)
    elif args.ticker:
        tickers = [t.strip().upper() for t in args.ticker.split(',')]
        results = verifier.verify_multiple_companies(tickers)
        verifier.print_results(results)
    else:
        print("Error: Please specify --ticker or --batch")
        parser.print_help()


if __name__ == '__main__':
    main()
