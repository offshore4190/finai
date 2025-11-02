"""
详细查询数据库现状
不做任何修改，只读取和展示信息
"""
from sqlalchemy import create_engine, text
from config.settings import settings
from datetime import datetime

def query_database_detailed():
    """详细查询数据库现状"""
    engine = create_engine(settings.database_url)
    
    print("=" * 100)
    print("数据库详细状态报告")
    print(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)
    
    with engine.connect() as conn:
        
        # ============ 1. 公司数据详情 ============
        print("\n" + "="*100)
        print("1. 公司数据详细统计")
        print("="*100)
        
        # 1.1 按交易所分组
        print("\n【按交易所分组】")
        result = conn.execute(text("""
            SELECT 
                exchange,
                COUNT(*) as company_count,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active_count,
                COUNT(CASE WHEN is_active = true THEN 1 END) as is_active_count
            FROM companies
            GROUP BY exchange
            ORDER BY company_count DESC;
        """))
        print(f"{'交易所':20s} | {'公司总数':>10s} | {'status=active':>15s} | {'is_active=true':>15s}")
        print("-" * 70)
        for row in result:
            exchange = row[0] or 'NULL'
            print(f"{exchange:20s} | {row[1]:>10,} | {row[2]:>15,} | {row[3]:>15,}")
        
        # 1.2 目标公司（NASDAQ/NYSE）详情
        print("\n【目标公司（NASDAQ/NYSE系列）详情】")
        result = conn.execute(text("""
            SELECT exchange, COUNT(*) as count
            FROM companies
            WHERE exchange IN ('NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca')
              AND status = 'active'
              AND is_active = true
            GROUP BY exchange
            ORDER BY count DESC;
        """))
        total_target = 0
        for row in result:
            print(f"  {row[0]:20s}: {row[1]:>6,} 家")
            total_target += row[1]
        print(f"  {'总计':20s}: {total_target:>6,} 家目标公司")
        
        # 1.3 示例公司
        print("\n【示例公司（前10家NASDAQ公司）】")
        result = conn.execute(text("""
            SELECT ticker, company_name, cik, exchange, status
            FROM companies
            WHERE exchange = 'NASDAQ'
            ORDER BY ticker
            LIMIT 10;
        """))
        print(f"{'股票代码':10s} | {'公司名称':50s} | {'CIK':12s} | {'状态':10s}")
        print("-" * 90)
        for row in result:
            name = (row[1][:47] + '...') if row[1] and len(row[1]) > 50 else (row[1] or 'N/A')
            print(f"{row[0]:10s} | {name:50s} | {row[2]:12s} | {row[4]:10s}")
        
        # ============ 2. 报告数据详情 ============
        print("\n" + "="*100)
        print("2. 报告（Filings）数据详细统计")
        print("="*100)
        
        # 2.1 按表单类型统计
        print("\n【按报告类型统计】")
        result = conn.execute(text("""
            SELECT 
                form_type,
                COUNT(*) as count,
                COUNT(CASE WHEN is_amendment = true THEN 1 END) as amendments
            FROM filings
            GROUP BY form_type
            ORDER BY count DESC;
        """))
        print(f"{'报告类型':15s} | {'总数':>10s} | {'修正报告':>12s}")
        print("-" * 45)
        for row in result:
            print(f"{row[0]:15s} | {row[1]:>10,} | {row[2]:>12,}")
        
        # 2.2 按年份统计
        print("\n【按报告年份统计】")
        result = conn.execute(text("""
            SELECT 
                fiscal_year,
                COUNT(*) as count,
                COUNT(DISTINCT company_id) as companies
            FROM filings
            WHERE fiscal_year IS NOT NULL
            GROUP BY fiscal_year
            ORDER BY fiscal_year DESC;
        """))
        print(f"{'年份':10s} | {'报告数':>10s} | {'公司数':>10s}")
        print("-" * 35)
        for row in result:
            print(f"{row[0]:10} | {row[1]:>10,} | {row[2]:>10,}")
        
        # 2.3 按季度统计
        print("\n【按财报周期统计】")
        result = conn.execute(text("""
            SELECT 
                fiscal_period,
                COUNT(*) as count
            FROM filings
            WHERE fiscal_period IS NOT NULL
            GROUP BY fiscal_period
            ORDER BY 
                CASE fiscal_period
                    WHEN 'FY' THEN 1
                    WHEN 'Q1' THEN 2
                    WHEN 'Q2' THEN 3
                    WHEN 'Q3' THEN 4
                    WHEN 'Q4' THEN 5
                    ELSE 6
                END;
        """))
        print(f"{'周期':10s} | {'报告数':>10s}")
        print("-" * 25)
        for row in result:
            print(f"{row[0]:10s} | {row[1]:>10,}")
        
        # 2.4 最近的报告
        print("\n【最新报告（最近10份）】")
        result = conn.execute(text("""
            SELECT 
                c.ticker,
                f.form_type,
                f.fiscal_year,
                f.fiscal_period,
                f.filing_date,
                f.is_amendment
            FROM filings f
            JOIN companies c ON f.company_id = c.id
            ORDER BY f.filing_date DESC
            LIMIT 10;
        """))
        print(f"{'股票代码':10s} | {'类型':10s} | {'年份':6s} | {'周期':6s} | {'报告日期':12s} | {'修正':4s}")
        print("-" * 70)
        for row in result:
            amendment = '是' if row[5] else '否'
            print(f"{row[0]:10s} | {row[1]:10s} | {row[2]:6} | {row[3]:6s} | {str(row[4]):12s} | {amendment:4s}")
        
        # ============ 3. 文件（Artifacts）详情 ============
        print("\n" + "="*100)
        print("3. 文件（Artifacts）数据详细统计")
        print("="*100)
        
        # 3.1 按状态统计
        print("\n【按下载状态统计】")
        result = conn.execute(text("""
            SELECT 
                status,
                COUNT(*) as count,
                ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as percentage
            FROM artifacts
            GROUP BY status
            ORDER BY count DESC;
        """))
        print(f"{'状态':20s} | {'数量':>12s} | {'百分比':>10s}")
        print("-" * 50)
        for row in result:
            status = row[0] or 'NULL'
            print(f"{status:20s} | {row[1]:>12,} | {row[2]:>9.2f}%")
        
        # 3.2 按文件类型统计
        print("\n【按文件类型统计】")
        result = conn.execute(text("""
            SELECT 
                artifact_type,
                COUNT(*) as count,
                COUNT(CASE WHEN status = 'downloaded' THEN 1 END) as downloaded,
                COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed
            FROM artifacts
            GROUP BY artifact_type
            ORDER BY count DESC;
        """))
        print(f"{'文件类型':15s} | {'总数':>10s} | {'已下载':>10s} | {'失败':>8s}")
        print("-" * 55)
        for row in result:
            print(f"{row[0]:15s} | {row[1]:>10,} | {row[2]:>10,} | {row[3]:>8,}")
        
        # 3.3 重试情况
        print("\n【重试统计】")
        result = conn.execute(text("""
            SELECT 
                retry_count,
                COUNT(*) as count
            FROM artifacts
            GROUP BY retry_count
            ORDER BY retry_count;
        """))
        print(f"{'重试次数':12s} | {'数量':>10s}")
        print("-" * 28)
        for row in result:
            print(f"{row[0]:12} | {row[1]:>10,}")
        
        # 3.4 失败的文件详情
        print("\n【失败文件详情（前10个）】")
        result = conn.execute(text("""
            SELECT 
                c.ticker,
                f.form_type,
                a.artifact_type,
                a.retry_count,
                a.error_message
            FROM artifacts a
            JOIN filings f ON a.filing_id = f.id
            JOIN companies c ON f.company_id = c.id
            WHERE a.status = 'failed'
            ORDER BY a.retry_count DESC, a.updated_at DESC
            LIMIT 10;
        """))
        rows = list(result)
        if rows:
            print(f"{'股票代码':10s} | {'报告类型':10s} | {'文件类型':10s} | {'重试':4s} | {'错误信息':40s}")
            print("-" * 85)
            for row in rows:
                error = (row[4][:37] + '...') if row[4] and len(row[4]) > 40 else (row[4] or 'N/A')
                print(f"{row[0]:10s} | {row[1]:10s} | {row[2]:10s} | {row[3]:4} | {error:40s}")
        else:
            print("  ✅ 没有失败的文件")
        
        # 3.5 SHA256重复情况详细分析
        print("\n【SHA256重复情况详细分析】")
        result = conn.execute(text("""
            SELECT 
                COUNT(DISTINCT sha256) as unique_sha256,
                COUNT(*) as total_with_sha256
            FROM artifacts
            WHERE sha256 IS NOT NULL;
        """))
        row = result.fetchone()
        print(f"  有SHA256的文件总数: {row[1]:,}")
        print(f"  唯一SHA256数量: {row[0]:,}")
        print(f"  平均每个SHA256: {row[1]/row[0]:.2f} 个文件")
        
        result = conn.execute(text("""
            SELECT sha256, COUNT(*) as dup_count
            FROM artifacts
            WHERE sha256 IS NOT NULL
            GROUP BY sha256
            HAVING COUNT(*) > 1
            ORDER BY dup_count DESC
            LIMIT 5;
        """))
        rows = list(result)
        if rows:
            print(f"\n  重复最多的SHA256（前5个）:")
            for sha256, count in rows:
                print(f"    {sha256[:40]}... : {count} 次重复")
        
        # ============ 4. 执行历史 ============
        print("\n" + "="*100)
        print("4. 执行历史（Execution Runs）")
        print("="*100)
        
        result = conn.execute(text("""
            SELECT 
                run_type,
                status,
                started_at,
                completed_at,
                duration_seconds,
                filings_discovered,
                artifacts_attempted,
                artifacts_succeeded,
                artifacts_failed
            FROM execution_runs
            ORDER BY started_at DESC
            LIMIT 10;
        """))
        print(f"\n{'类型':15s} | {'状态':10s} | {'开始时间':20s} | {'耗时(秒)':>10s} | {'报告':>6s} | {'成功':>6s}")
        print("-" * 90)
        for row in result:
            started = str(row[2])[:19] if row[2] else 'N/A'
            duration = row[4] if row[4] else 0
            filings = row[5] if row[5] else 0
            succeeded = row[7] if row[7] else 0
            print(f"{row[0]:15s} | {row[1]:10s} | {started:20s} | {duration:>10,} | {filings:>6,} | {succeeded:>6,}")
        
        # ============ 5. 错误日志 ============
        print("\n" + "="*100)
        print("5. 错误日志统计")
        print("="*100)
        
        # 按错误类型统计
        print("\n【按错误类型统计】")
        result = conn.execute(text("""
            SELECT 
                error_type,
                COUNT(*) as count
            FROM error_logs
            GROUP BY error_type
            ORDER BY count DESC
            LIMIT 10;
        """))
        rows = list(result)
        if rows:
            print(f"{'错误类型':40s} | {'次数':>10s}")
            print("-" * 55)
            for row in rows:
                error_type = (row[0][:37] + '...') if row[0] and len(row[0]) > 40 else (row[0] or 'N/A')
                print(f"{error_type:40s} | {row[1]:>10,}")
        else:
            print("  ✅ 没有错误日志")
        
        # ============ 6. 覆盖率分析 ============
        print("\n" + "="*100)
        print("6. 数据覆盖率分析（2023-2025）")
        print("="*100)
        
        print("\n【目标公司的报告覆盖率】")
        result = conn.execute(text("""
            SELECT 
                c.exchange,
                COUNT(DISTINCT c.id) as total_companies,
                COUNT(DISTINCT CASE WHEN f.id IS NOT NULL THEN c.id END) as companies_with_filings,
                ROUND(COUNT(DISTINCT CASE WHEN f.id IS NOT NULL THEN c.id END) * 100.0 / COUNT(DISTINCT c.id), 2) as coverage_pct
            FROM companies c
            LEFT JOIN filings f ON c.id = f.company_id 
                AND f.filing_date >= '2023-01-01' 
                AND f.filing_date <= '2025-12-31'
            WHERE c.exchange IN ('NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca')
              AND c.status = 'active'
              AND c.is_active = true
            GROUP BY c.exchange
            ORDER BY total_companies DESC;
        """))
        print(f"{'交易所':20s} | {'公司总数':>10s} | {'有报告':>10s} | {'覆盖率':>10s}")
        print("-" * 60)
        for row in result:
            print(f"{row[0]:20s} | {row[1]:>10,} | {row[2]:>10,} | {row[3]:>9.2f}%")
        
        # ============ 7. 存储空间估算 ============
        print("\n" + "="*100)
        print("7. 数据库存储统计")
        print("="*100)
        
        result = conn.execute(text("""
            SELECT 
                schemaname,
                tablename,
                pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size,
                pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) AS table_size,
                pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) AS index_size
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
        """))
        print(f"\n{'表名':25s} | {'总大小':>12s} | {'表大小':>12s} | {'索引大小':>12s}")
        print("-" * 70)
        for row in result:
            print(f"{row[1]:25s} | {row[2]:>12s} | {row[3]:>12s} | {row[4]:>12s}")
        
        # 数据库总大小
        result = conn.execute(text("""
            SELECT pg_size_pretty(pg_database_size(current_database()));
        """))
        db_size = result.scalar()
        print(f"\n数据库总大小: {db_size}")
        
        print("\n" + "="*100)
        print("查询完成！")
        print("="*100)

if __name__ == '__main__':
    query_database_detailed()

