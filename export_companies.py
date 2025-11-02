"""
导出公司信息到CSV文件
按交易所分组，保存到 交易所名称/company.csv

使用方法：
  python export_companies.py --all                    # 导出所有交易所
  python export_companies.py --exchange NASDAQ        # 导出指定交易所
  python export_companies.py --exchange NYSE          # 导出NYSE
  python export_companies.py --output-dir ./output    # 指定输出目录
"""
import argparse
import csv
import os
from pathlib import Path
from sqlalchemy import create_engine, text
from config.settings import settings
import structlog

logger = structlog.get_logger()


def export_companies_to_csv(exchange_filter=None, output_base_dir='data/companies'):
    """
    导出公司信息到CSV文件
    
    Args:
        exchange_filter: 指定交易所，None表示导出所有
        output_base_dir: 输出基础目录
    """
    engine = create_engine(settings.database_url)
    
    # 确保输出目录存在
    Path(output_base_dir).mkdir(parents=True, exist_ok=True)
    
    with engine.connect() as conn:
        # 查询公司信息，包含最早的filing_date作为上市时间近似值
        query = """
        SELECT 
            c.ticker AS 股票代码,
            c.company_name AS 公司名称,
            c.exchange AS 交易所,
            MIN(f.filing_date) AS 上市时间
        FROM companies c
        LEFT JOIN filings f ON c.id = f.company_id
        WHERE c.is_active = true
        """
        
        params = {}
        if exchange_filter:
            query += " AND c.exchange = :exchange"
            params['exchange'] = exchange_filter
        
        query += """
        GROUP BY c.ticker, c.company_name, c.exchange
        ORDER BY c.exchange, c.ticker
        """
        
        result = conn.execute(text(query), params)
        rows = result.fetchall()
        
        if not rows:
            logger.warning("no_companies_found", exchange=exchange_filter)
            print(f"未找到任何公司记录")
            return
        
        # 按交易所分组
        companies_by_exchange = {}
        for row in rows:
            ticker, company_name, exchange, listing_date = row
            if exchange not in companies_by_exchange:
                companies_by_exchange[exchange] = []
            
            companies_by_exchange[exchange].append({
                '股票代码': ticker,
                '公司名称': company_name,
                '上市时间': str(listing_date) if listing_date else 'N/A'
            })
        
        # 为每个交易所创建CSV文件
        total_exported = 0
        for exchange, companies in companies_by_exchange.items():
            # 创建交易所目录
            exchange_dir = os.path.join(output_base_dir, exchange)
            Path(exchange_dir).mkdir(parents=True, exist_ok=True)
            
            # 写入CSV文件
            csv_path = os.path.join(exchange_dir, 'company.csv')
            with open(csv_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
                fieldnames = ['股票代码', '公司名称', '上市时间']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                writer.writerows(companies)
            
            logger.info(
                "export_completed",
                exchange=exchange,
                count=len(companies),
                path=csv_path
            )
            print(f"✓ {exchange}: 导出 {len(companies)} 家公司 -> {csv_path}")
            total_exported += len(companies)
        
        print(f"\n总计导出 {total_exported} 家公司到 {len(companies_by_exchange)} 个交易所")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='导出公司信息到CSV文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 导出所有交易所的公司
  python export_companies.py --all
  
  # 导出指定交易所
  python export_companies.py --exchange NASDAQ
  python export_companies.py --exchange NYSE
  python export_companies.py --exchange "NYSE American"
  
  # 指定输出目录
  python export_companies.py --all --output-dir ./output/companies
  
输出格式:
  - 文件路径: {output_dir}/{交易所名称}/company.csv
  - CSV字段: 股票代码,公司名称,上市时间
  - 编码: UTF-8 with BOM (Excel兼容)
        """
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--all',
        action='store_true',
        help='导出所有交易所'
    )
    group.add_argument(
        '--exchange',
        type=str,
        help='指定交易所名称（如：NASDAQ, NYSE, NYSE American）'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='data/companies',
        help='输出目录（默认: data/companies）'
    )
    
    args = parser.parse_args()
    
    try:
        if args.all:
            logger.info("exporting_all_exchanges", output_dir=args.output_dir)
            print(f"开始导出所有交易所的公司信息到: {args.output_dir}\n")
            export_companies_to_csv(exchange_filter=None, output_base_dir=args.output_dir)
        else:
            logger.info(
                "exporting_single_exchange",
                exchange=args.exchange,
                output_dir=args.output_dir
            )
            print(f"开始导出 {args.exchange} 交易所的公司信息到: {args.output_dir}\n")
            export_companies_to_csv(
                exchange_filter=args.exchange,
                output_base_dir=args.output_dir
            )
        
        print("\n✓ 导出完成!")
        
    except Exception as e:
        logger.error("export_failed", error=str(e), exc_info=True)
        print(f"\n✗ 导出失败: {str(e)}")
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())

