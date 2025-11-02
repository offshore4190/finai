"""
数据库现状汇总查询（简化版，处理NULL值）
"""
from sqlalchemy import create_engine, text
from config.settings import settings
from datetime import datetime

def query_db_summary():
    """查询数据库现状汇总"""
    engine = create_engine(settings.database_url)
    
    print("\n" + "=" * 100)
    print(f"数据库现状汇总报告 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)
    
    with engine.connect() as conn:
        
        # ========== 1. 总体概览 ==========
        print("\n【1. 总体数据概览】")
        print("-" * 100)
        
        # 公司总数
        result = conn.execute(text("SELECT COUNT(*) FROM companies"))
        total_companies = result.scalar()
        print(f"  公司总数: {total_companies:,}")
        
        # 目标公司数
        result = conn.execute(text("""
            SELECT COUNT(*) FROM companies
            WHERE exchange IN ('NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca')
              AND status = 'active' AND is_active = true
        """))
        target_companies = result.scalar()
        print(f"  目标公司（NASDAQ/NYSE活跃）: {target_companies:,}")
        
        # 报告总数
        result = conn.execute(text("SELECT COUNT(*) FROM filings"))
        total_filings = result.scalar()
        print(f"  报告总数: {total_filings:,}")
        
        # 文件总数
        result = conn.execute(text("SELECT COUNT(*) FROM artifacts"))
        total_artifacts = result.scalar()
        print(f"  文件总数: {total_artifacts:,}")
        
        # ========== 2. 公司按交易所分布 ==========
        print("\n【2. 公司按交易所分布】")
        print("-" * 100)
        result = conn.execute(text("""
            SELECT 
                COALESCE(exchange, 'NULL') as exchange,
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'active' AND is_active = true THEN 1 END) as active
            FROM companies
            GROUP BY exchange
            ORDER BY total DESC;
        """))
        print(f"  {'交易所':20s} | {'总数':>10s} | {'活跃':>10s}")
        print("  " + "-" * 48)
        for row in result:
            print(f"  {row[0]:20s} | {row[1]:>10,} | {row[2]:>10,}")
        
        # ========== 3. 报告统计 ==========
        print("\n【3. 报告类型统计】")
        print("-" * 100)
        result = conn.execute(text("""
            SELECT 
                form_type,
                COUNT(*) as count,
                SUM(CASE WHEN is_amendment THEN 1 ELSE 0 END) as amendments
            FROM filings
            GROUP BY form_type
            ORDER BY count DESC;
        """))
        print(f"  {'报告类型':15s} | {'总数':>10s} | {'修正':>8s}")
        print("  " + "-" * 40)
        for row in result:
            print(f"  {row[0]:15s} | {row[1]:>10,} | {row[2]:>8,}")
        
        # 按年份统计
        print("\n【4. 按年份统计】")
        print("-" * 100)
        result = conn.execute(text("""
            SELECT 
                fiscal_year,
                COUNT(*) as reports,
                COUNT(DISTINCT company_id) as companies
            FROM filings
            WHERE fiscal_year IS NOT NULL
            GROUP BY fiscal_year
            ORDER BY fiscal_year DESC;
        """))
        print(f"  {'年份':8s} | {'报告数':>10s} | {'公司数':>10s}")
        print("  " + "-" * 35)
        for row in result:
            print(f"  {row[0]:8} | {row[1]:>10,} | {row[2]:>10,}")
        
        # ========== 5. 文件下载状态 ==========
        print("\n【5. 文件下载状态】")
        print("-" * 100)
        result = conn.execute(text("""
            SELECT 
                COALESCE(status, 'NULL') as status,
                COUNT(*) as count,
                ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as pct
            FROM artifacts
            GROUP BY status
            ORDER BY count DESC;
        """))
        print(f"  {'状态':20s} | {'数量':>15s} | {'百分比':>10s}")
        print("  " + "-" * 52)
        for row in result:
            print(f"  {row[0]:20s} | {row[1]:>15,} | {row[2]:>9.2f}%")
        
        # ========== 6. 文件类型统计 ==========
        print("\n【6. 文件类型统计】")
        print("-" * 100)
        result = conn.execute(text("""
            SELECT 
                artifact_type,
                COUNT(*) as total,
                SUM(CASE WHEN status = 'downloaded' THEN 1 ELSE 0 END) as downloaded,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'pending_download' THEN 1 ELSE 0 END) as pending
            FROM artifacts
            GROUP BY artifact_type
            ORDER BY total DESC;
        """))
        print(f"  {'文件类型':15s} | {'总数':>12s} | {'已下载':>12s} | {'失败':>8s} | {'待下载':>10s}")
        print("  " + "-" * 70)
        for row in result:
            print(f"  {row[0]:15s} | {row[1]:>12,} | {row[2]:>12,} | {row[3]:>8,} | {row[4]:>10,}")
        
        # ========== 7. SHA256重复情况 ==========
        print("\n【7. SHA256重复情况分析】")
        print("-" * 100)
        result = conn.execute(text("""
            SELECT 
                COUNT(*) as total_with_sha256,
                COUNT(DISTINCT sha256) as unique_sha256
            FROM artifacts
            WHERE sha256 IS NOT NULL;
        """))
        row = result.fetchone()
        total_sha = row[0]
        unique_sha = row[1]
        print(f"  有SHA256的文件总数: {total_sha:,}")
        print(f"  唯一SHA256数量: {unique_sha:,}")
        print(f"  重复文件数: {total_sha - unique_sha:,}")
        
        # 重复SHA256的数量
        result = conn.execute(text("""
            SELECT COUNT(*)
            FROM (
                SELECT sha256
                FROM artifacts
                WHERE sha256 IS NOT NULL
                GROUP BY sha256
                HAVING COUNT(*) > 1
            ) t;
        """))
        dup_sha_count = result.scalar()
        print(f"  重复的SHA256值数量: {dup_sha_count:,}")
        
        # 最重复的SHA256
        result = conn.execute(text("""
            SELECT sha256, COUNT(*) as dup_count
            FROM artifacts
            WHERE sha256 IS NOT NULL
            GROUP BY sha256
            HAVING COUNT(*) > 1
            ORDER BY dup_count DESC
            LIMIT 3;
        """))
        rows = list(result)
        if rows:
            print(f"\n  重复最多的SHA256（前3个）:")
            for sha256, count in rows:
                print(f"    {sha256[:40]}... : 重复 {count} 次")
        
        # ========== 8. 失败文件 ==========
        print("\n【8. 失败文件统计】")
        print("-" * 100)
        result = conn.execute(text("""
            SELECT 
                retry_count,
                COUNT(*) as count
            FROM artifacts
            WHERE status = 'failed'
            GROUP BY retry_count
            ORDER BY retry_count;
        """))
        rows = list(result)
        if rows:
            print(f"  {'重试次数':12s} | {'失败数':>10s}")
            print("  " + "-" * 28)
            for row in rows:
                print(f"  {row[0]:12} | {row[1]:>10,}")
        else:
            print("  ✅ 没有失败的文件")
        
        # ========== 9. 覆盖率分析 ==========
        print("\n【9. 目标公司报告覆盖率（2023-2025）】")
        print("-" * 100)
        result = conn.execute(text("""
            SELECT 
                c.exchange,
                COUNT(DISTINCT c.id) as total_cos,
                COUNT(DISTINCT CASE WHEN f.id IS NOT NULL THEN c.id END) as cos_with_filings,
                ROUND(COUNT(DISTINCT CASE WHEN f.id IS NOT NULL THEN c.id END) * 100.0 / 
                      NULLIF(COUNT(DISTINCT c.id), 0), 2) as coverage_pct
            FROM companies c
            LEFT JOIN filings f ON c.id = f.company_id 
                AND f.filing_date >= '2023-01-01' 
                AND f.filing_date <= '2025-12-31'
            WHERE c.exchange IN ('NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca')
              AND c.status = 'active'
              AND c.is_active = true
            GROUP BY c.exchange
            ORDER BY total_cos DESC;
        """))
        print(f"  {'交易所':20s} | {'公司数':>10s} | {'有报告':>10s} | {'覆盖率':>10s}")
        print("  " + "-" * 58)
        total_cos = 0
        total_with_filings = 0
        for row in result:
            print(f"  {row[0]:20s} | {row[1]:>10,} | {row[2]:>10,} | {row[3]:>9.2f}%")
            total_cos += row[1]
            total_with_filings += row[2]
        if total_cos > 0:
            overall_pct = (total_with_filings / total_cos) * 100
            print("  " + "-" * 58)
            print(f"  {'总计':20s} | {total_cos:>10,} | {total_with_filings:>10,} | {overall_pct:>9.2f}%")
        
        # ========== 10. 执行历史 ==========
        print("\n【10. 最近执行历史（最近5次）】")
        print("-" * 100)
        result = conn.execute(text("""
            SELECT 
                run_type,
                status,
                started_at,
                duration_seconds,
                filings_discovered,
                artifacts_succeeded
            FROM execution_runs
            ORDER BY started_at DESC
            LIMIT 5;
        """))
        rows = list(result)
        if rows:
            print(f"  {'类型':15s} | {'状态':10s} | {'开始时间':20s} | {'耗时(秒)':>10s} | {'报告':>6s} | {'成功':>8s}")
            print("  " + "-" * 88)
            for row in rows:
                started = str(row[2])[:19] if row[2] else 'N/A'
                duration = row[3] if row[3] else 0
                filings = row[4] if row[4] else 0
                succeeded = row[5] if row[5] else 0
                print(f"  {row[0]:15s} | {row[1]:10s} | {started:20s} | {duration:>10,} | {filings:>6,} | {succeeded:>8,}")
        else:
            print("  暂无执行历史")
        
        # ========== 11. 数据库存储 ==========
        print("\n【11. 数据库存储大小（前5个表）】")
        print("-" * 100)
        result = conn.execute(text("""
            SELECT 
                tablename,
                pg_size_pretty(pg_total_relation_size('public.' || tablename)) AS total_size
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY pg_total_relation_size('public.' || tablename) DESC
            LIMIT 5;
        """))
        print(f"  {'表名':30s} | {'总大小':>15s}")
        print("  " + "-" * 50)
        for row in result:
            print(f"  {row[0]:30s} | {row[1]:>15s}")
        
        # 数据库总大小
        result = conn.execute(text("SELECT pg_size_pretty(pg_database_size(current_database()))"))
        db_size = result.scalar()
        print(f"\n  数据库总大小: {db_size}")
        
        print("\n" + "=" * 100)
        print("查询完成！")
        print("=" * 100 + "\n")

if __name__ == '__main__':
    query_db_summary()

