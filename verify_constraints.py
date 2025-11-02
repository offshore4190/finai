"""
验证数据库约束和索引
"""
from sqlalchemy import create_engine, text
from config.settings import settings

def verify_constraints():
    """验证artifacts表的约束和索引"""
    engine = create_engine(settings.database_url)
    
    print("=" * 100)
    print("验证数据库约束和索引")
    print("=" * 100)
    
    with engine.connect() as conn:
        # 1. 查看artifacts表的所有索引
        print("\n【1. artifacts表的索引】")
        result = conn.execute(text("""
            SELECT 
                indexname,
                indexdef
            FROM pg_indexes
            WHERE tablename = 'artifacts'
            ORDER BY indexname;
        """))
        
        print(f"\n{'索引名称':50s} | 定义")
        print("-" * 100)
        for row in result:
            print(f"{row[0]:50s}")
            print(f"  └─ {row[1]}")
            print()
        
        # 2. 查看artifacts表的约束
        print("\n【2. artifacts表的约束】")
        result = conn.execute(text("""
            SELECT 
                conname as constraint_name,
                contype as constraint_type,
                pg_get_constraintdef(oid) as definition
            FROM pg_constraint
            WHERE conrelid = 'artifacts'::regclass
            ORDER BY conname;
        """))
        
        rows = list(result)
        if rows:
            print(f"\n{'约束名称':40s} | {'类型':6s} | 定义")
            print("-" * 100)
            for row in rows:
                constraint_type = {
                    'p': 'PRIMARY',
                    'u': 'UNIQUE',
                    'f': 'FOREIGN',
                    'c': 'CHECK'
                }.get(row[1], row[1])
                print(f"{row[0]:40s} | {constraint_type:6s} | {row[2]}")
        else:
            print("  未找到约束")
        
        # 3. 检查特定索引是否存在
        print("\n【3. 关键索引状态检查】")
        
        indexes_to_check = [
            ('idx_artifacts_sha256_unique', '旧的SHA256唯一索引（应该不存在）'),
            ('idx_artifacts_sha256', '新的SHA256普通索引（应该存在）'),
            ('idx_artifacts_filing_url_unique', 'filing_id+url唯一索引（应该存在）')
        ]
        
        for idx_name, description in indexes_to_check:
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 
                    FROM pg_indexes 
                    WHERE indexname = :idx_name
                );
            """), {"idx_name": idx_name})
            exists = result.scalar()
            status = "✅ 存在" if exists else "❌ 不存在"
            print(f"  {idx_name:50s} - {status}")
            print(f"    描述: {description}")
        
        print("\n" + "=" * 100)

if __name__ == '__main__':
    verify_constraints()

