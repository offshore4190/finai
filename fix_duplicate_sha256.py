"""
修复artifacts表中的重复SHA256值
保留最新的记录，删除旧的重复记录
"""
import sys
from sqlalchemy import create_engine, text
from config.settings import settings

def fix_duplicate_sha256(dry_run=True):
    """
    修复重复的SHA256值
    
    Args:
        dry_run: 如果为True，只显示将要删除的记录，不实际删除
    """
    engine = create_engine(settings.database_url)
    
    print("=" * 80)
    print(f"修复artifacts表中的重复SHA256值 ({'预览模式' if dry_run else '实际执行'})")
    print("=" * 80)
    
    try:
        with engine.begin() as conn:
            # 1. 查找重复的SHA256
            print("\n1. 查找重复的SHA256值...")
            result = conn.execute(text("""
                SELECT sha256, COUNT(*) as count
                FROM artifacts
                WHERE sha256 IS NOT NULL
                GROUP BY sha256
                HAVING COUNT(*) > 1
                ORDER BY count DESC;
            """))
            duplicates = list(result)
            
            if not duplicates:
                print("   ✅ 没有发现重复的SHA256值！")
                return
            
            print(f"   发现 {len(duplicates)} 个重复的SHA256值")
            
            # 显示前5个
            print("\n   前5个重复SHA256:")
            for sha256, count in duplicates[:5]:
                print(f"   - {sha256[:32]}... (重复 {count} 次)")
            
            # 2. 计算需要删除的记录数
            total_to_delete = sum(count - 1 for _, count in duplicates)
            print(f"\n2. 需要删除 {total_to_delete} 条重复记录")
            
            if dry_run:
                print("\n   【预览模式】显示将要删除的记录示例:")
                result = conn.execute(text("""
                    WITH ranked_artifacts AS (
                        SELECT 
                            id,
                            sha256,
                            created_at,
                            status,
                            ROW_NUMBER() OVER (
                                PARTITION BY sha256 
                                ORDER BY created_at DESC, id DESC
                            ) as rn
                        FROM artifacts
                        WHERE sha256 IS NOT NULL
                    )
                    SELECT id, sha256, created_at, status
                    FROM ranked_artifacts
                    WHERE rn > 1
                    LIMIT 10;
                """))
                
                print(f"\n   {'ID':>10} | {'SHA256':32s} | {'创建时间':20s} | {'状态':15s}")
                print("   " + "-" * 85)
                for row in result:
                    sha256_short = row[1][:32] if row[1] else 'NULL'
                    created_at = str(row[2])[:19] if row[2] else 'NULL'
                    print(f"   {row[0]:>10} | {sha256_short} | {created_at:20s} | {row[3]:15s}")
                
                print(f"\n   ⚠️  这是预览模式。要实际删除，请运行：")
                print(f"   python fix_duplicate_sha256.py --execute")
                
            else:
                print("\n3. 开始删除重复记录...")
                print("   保留策略：对于每个重复的SHA256，保留最新的一条记录（按created_at DESC, id DESC）")
                
                # 使用CTE删除重复记录，保留最新的
                result = conn.execute(text("""
                    WITH ranked_artifacts AS (
                        SELECT 
                            id,
                            ROW_NUMBER() OVER (
                                PARTITION BY sha256 
                                ORDER BY created_at DESC, id DESC
                            ) as rn
                        FROM artifacts
                        WHERE sha256 IS NOT NULL
                    )
                    DELETE FROM artifacts
                    WHERE id IN (
                        SELECT id 
                        FROM ranked_artifacts 
                        WHERE rn > 1
                    )
                    RETURNING id;
                """))
                
                deleted_count = result.rowcount
                print(f"   ✅ 成功删除 {deleted_count} 条重复记录")
                
                # 4. 验证
                print("\n4. 验证结果...")
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
                remaining_duplicates = result.scalar()
                
                if remaining_duplicates == 0:
                    print("   ✅ 所有重复SHA256已清理完成！")
                else:
                    print(f"   ⚠️  仍有 {remaining_duplicates} 个重复SHA256")
            
            print("\n" + "=" * 80)
            
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='修复artifacts表中的重复SHA256值')
    parser.add_argument('--execute', action='store_true', 
                        help='实际执行删除（默认只预览）')
    args = parser.parse_args()
    
    if args.execute:
        confirm = input("\n⚠️  确定要删除重复记录吗？这个操作不可恢复！输入 'yes' 确认: ")
        if confirm.lower() != 'yes':
            print("操作已取消")
            sys.exit(0)
    
    fix_duplicate_sha256(dry_run=not args.execute)

