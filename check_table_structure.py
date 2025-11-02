"""
查看表结构
"""
from sqlalchemy import create_engine, text
from config.settings import settings

def check_table_structure():
    """查看所有表的结构"""
    engine = create_engine(settings.database_url)
    
    with engine.connect() as conn:
        # 获取所有表
        result = conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """))
        tables = [row[0] for row in result]
        
        print("=" * 100)
        print("数据库表结构")
        print("=" * 100)
        
        for table in tables:
            print(f"\n【表: {table}】")
            result = conn.execute(text(f"""
                SELECT 
                    column_name, 
                    data_type, 
                    character_maximum_length,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' 
                  AND table_name = '{table}'
                ORDER BY ordinal_position;
            """))
            
            print(f"{'列名':25s} | {'类型':20s} | {'长度':>8s} | {'可空':6s} | {'默认值':30s}")
            print("-" * 100)
            for row in result:
                col_name = row[0]
                col_type = row[1]
                max_len = str(row[2]) if row[2] else '-'
                nullable = row[3]
                default = (row[4][:27] + '...') if row[4] and len(row[4]) > 30 else (row[4] or '-')
                print(f"{col_name:25s} | {col_type:20s} | {max_len:>8s} | {nullable:6s} | {default:30s}")

if __name__ == '__main__':
    check_table_structure()

