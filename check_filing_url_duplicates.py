"""
检查是否存在 (filing_id, url) 的重复
"""
from sqlalchemy import create_engine, text
from config.settings import settings

def check_filing_url_duplicates():
    """检查filing_id和url的重复情况"""
    engine = create_engine(settings.database_url)
    
    print("=" * 100)
    print("检查 (filing_id, url) 重复情况")
    print("=" * 100)
    
    with engine.connect() as conn:
        # 检查重复
        print("\n1. 查找重复的 (filing_id, url) 组合...")
        result = conn.execute(text("""
            SELECT filing_id, url, COUNT(*) as count
            FROM artifacts
            GROUP BY filing_id, url
            HAVING COUNT(*) > 1
            ORDER BY count DESC
            LIMIT 10;
        """))
        duplicates = list(result)
        
        if duplicates:
            print(f"   ⚠️  发现 {len(duplicates)} 个重复的 (filing_id, url) 组合")
            print(f"\n   前10个重复:")
            print(f"   {'Filing ID':>12s} | {'URL':60s} | {'重复次数':>8s}")
            print("   " + "-" * 88)
            for filing_id, url, count in duplicates:
                url_short = (url[:57] + '...') if len(url) > 60 else url
                print(f"   {filing_id:>12} | {url_short:60s} | {count:>8}")
            
            # 统计总数
            result = conn.execute(text("""
                SELECT COUNT(*) 
                FROM (
                    SELECT filing_id, url
                    FROM artifacts
                    GROUP BY filing_id, url
                    HAVING COUNT(*) > 1
                ) t;
            """))
            total_dup = result.scalar()
            print(f"\n   共有 {total_dup} 个重复的 (filing_id, url) 组合")
            
            # 计算需要删除的记录数
            result = conn.execute(text("""
                SELECT SUM(count - 1)
                FROM (
                    SELECT COUNT(*) as count
                    FROM artifacts
                    GROUP BY filing_id, url
                    HAVING COUNT(*) > 1
                ) t;
            """))
            records_to_delete = result.scalar()
            print(f"   需要清理 {records_to_delete} 条重复记录")
            
        else:
            print("   ✅ 没有发现重复的 (filing_id, url) 组合")
            print("   可以安全地创建 UNIQUE(filing_id, url) 约束")
        
        # 检查url字段是否有NULL
        print("\n2. 检查URL字段的NULL值...")
        result = conn.execute(text("""
            SELECT COUNT(*) 
            FROM artifacts 
            WHERE url IS NULL;
        """))
        null_urls = result.scalar()
        if null_urls > 0:
            print(f"   ⚠️  发现 {null_urls} 条记录的URL为NULL")
        else:
            print("   ✅ 没有NULL值的URL")
        
        print("\n" + "=" * 100)

if __name__ == '__main__':
    check_filing_url_duplicates()

