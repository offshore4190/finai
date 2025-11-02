"""
检查数据库当前状态和重复数据
"""
import sys
from sqlalchemy import create_engine, text
from config.settings import settings

def check_database_status():
    """检查数据库状态"""
    engine = create_engine(settings.database_url)
    
    print("=" * 80)
    print("数据库状态检查")
    print("=" * 80)
    
    try:
        with engine.connect() as conn:
            # 1. 检查表是否存在
            print("\n1. 检查数据库表:")
            result = conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name;
            """))
            tables = [row[0] for row in result]
            print(f"   找到 {len(tables)} 个表:")
            for table in tables:
                print(f"   - {table}")
            
            if not tables:
                print("\n   ❌ 数据库为空，需要初始化")
                return
            
            # 2. 检查各表的记录数
            print("\n2. 各表记录数:")
            for table in tables:
                try:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    count = result.scalar()
                    print(f"   {table:30s}: {count:>10,} 条记录")
                except Exception as e:
                    print(f"   {table:30s}: 错误 - {e}")
            
            # 3. 检查artifacts表中的重复sha256
            if 'artifacts' in tables:
                print("\n3. 检查artifacts表的SHA256重复情况:")
                result = conn.execute(text("""
                    SELECT sha256, COUNT(*) as count
                    FROM artifacts
                    WHERE sha256 IS NOT NULL
                    GROUP BY sha256
                    HAVING COUNT(*) > 1
                    ORDER BY count DESC
                    LIMIT 10;
                """))
                duplicates = list(result)
                
                if duplicates:
                    print(f"   ⚠️  发现 {len(duplicates)} 个重复的SHA256值:")
                    for sha256, count in duplicates[:5]:
                        print(f"   - {sha256[:16]}... (重复 {count} 次)")
                    
                    # 显示总重复数
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
                    total_dup_hashes = result.scalar()
                    
                    result = conn.execute(text("""
                        SELECT SUM(count - 1)
                        FROM (
                            SELECT COUNT(*) as count
                            FROM artifacts
                            WHERE sha256 IS NOT NULL
                            GROUP BY sha256
                            HAVING COUNT(*) > 1
                        ) t;
                    """))
                    total_dup_records = result.scalar()
                    
                    print(f"\n   共有 {total_dup_hashes} 个SHA256值重复")
                    print(f"   需要清理 {total_dup_records} 条重复记录")
                else:
                    print("   ✅ 没有发现重复的SHA256值")
            
            # 4. 检查companies表
            if 'companies' in tables:
                print("\n4. 公司数据统计:")
                result = conn.execute(text("""
                    SELECT exchange, COUNT(*) as count
                    FROM companies
                    GROUP BY exchange
                    ORDER BY count DESC;
                """))
                for exchange, count in result:
                    print(f"   {exchange or 'NULL':20s}: {count:>6,} 家公司")
            
            # 5. 检查filings表
            if 'filings' in tables:
                print("\n5. 报告数据统计:")
                result = conn.execute(text("""
                    SELECT form_type, COUNT(*) as count
                    FROM filings
                    GROUP BY form_type
                    ORDER BY count DESC
                    LIMIT 5;
                """))
                for form_type, count in result:
                    print(f"   {form_type:20s}: {count:>6,} 份报告")
            
            # 6. 检查artifacts状态
            if 'artifacts' in tables:
                print("\n6. 文件下载状态:")
                result = conn.execute(text("""
                    SELECT status, COUNT(*) as count
                    FROM artifacts
                    GROUP BY status
                    ORDER BY count DESC;
                """))
                for status, count in result:
                    print(f"   {status or 'NULL':20s}: {count:>6,} 个文件")
            
            print("\n" + "=" * 80)
            
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    check_database_status()

