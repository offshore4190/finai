"""
文件完整性检查工具
High-level Python engineer implementation for data integrity verification

功能：
1. 扫描本地文件系统，统计实际下载的文件
2. 与数据库记录对比
3. 识别缺失、多余或损坏的文件
4. 生成详细的完整性报告
"""

import os
import sys
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime
from typing import Dict, List, Tuple, Set
import hashlib

from sqlalchemy import create_engine, text
from config.settings import settings

class FileIntegrityChecker:
    """文件完整性检查器"""
    
    def __init__(self):
        self.storage_root = Path(settings.storage_root)
        self.engine = create_engine(settings.database_url)
        
        # 统计数据
        self.file_stats = {
            'total_files': 0,
            'total_size': 0,
            'by_exchange': defaultdict(lambda: {'count': 0, 'size': 0}),
            'by_type': defaultdict(lambda: {'count': 0, 'size': 0}),
            'by_year': defaultdict(lambda: {'count': 0, 'size': 0}),
            'by_company': defaultdict(int)
        }
        
        self.db_records = {
            'total': 0,
            'downloaded': 0,
            'by_exchange': defaultdict(int),
            'by_type': defaultdict(int)
        }
    
    def scan_filesystem(self) -> Dict[str, any]:
        """扫描文件系统，收集实际文件信息"""
        print("\n" + "=" * 100)
        print("📁 扫描本地文件系统...")
        print("=" * 100)
        
        if not self.storage_root.exists():
            print(f"⚠️  存储目录不存在: {self.storage_root}")
            print(f"   请检查配置: STORAGE_ROOT={settings.storage_root}")
            return {}
        
        print(f"存储根目录: {self.storage_root}")
        print(f"开始扫描...\n")
        
        # 收集所有文件
        all_files = []
        file_paths_set = set()
        
        # 遍历所有交易所目录
        for exchange_dir in self.storage_root.iterdir():
            if not exchange_dir.is_dir():
                continue
                
            exchange = exchange_dir.name
            
            # 遍历所有公司目录
            for company_dir in exchange_dir.iterdir():
                if not company_dir.is_dir():
                    continue
                    
                ticker = company_dir.name
                
                # 遍历所有年份目录
                for year_dir in company_dir.iterdir():
                    if not year_dir.is_dir():
                        continue
                    
                    try:
                        year = int(year_dir.name)
                    except ValueError:
                        continue
                    
                    # 收集该年份下的所有文件
                    for file_path in year_dir.rglob('*'):
                        if file_path.is_file():
                            try:
                                file_size = file_path.stat().st_size
                                
                                # 判断文件类型
                                if file_path.parent.name == 'xbrl':
                                    file_type = 'xbrl'
                                elif file_path.suffix.lower() in ['.html', '.htm']:
                                    file_type = 'html'
                                elif file_path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif']:
                                    file_type = 'image'
                                else:
                                    file_type = 'other'
                                
                                file_info = {
                                    'path': file_path,
                                    'relative_path': file_path.relative_to(self.storage_root),
                                    'exchange': exchange,
                                    'ticker': ticker,
                                    'year': year,
                                    'type': file_type,
                                    'size': file_size,
                                    'name': file_path.name
                                }
                                
                                all_files.append(file_info)
                                file_paths_set.add(str(file_path.relative_to(self.storage_root)))
                                
                                # 更新统计
                                self.file_stats['total_files'] += 1
                                self.file_stats['total_size'] += file_size
                                self.file_stats['by_exchange'][exchange]['count'] += 1
                                self.file_stats['by_exchange'][exchange]['size'] += file_size
                                self.file_stats['by_type'][file_type]['count'] += 1
                                self.file_stats['by_type'][file_type]['size'] += file_size
                                self.file_stats['by_year'][year]['count'] += 1
                                self.file_stats['by_year'][year]['size'] += file_size
                                self.file_stats['by_company'][f"{exchange}/{ticker}"] += 1
                                
                            except Exception as e:
                                print(f"⚠️  处理文件出错: {file_path}: {e}")
        
        print(f"✅ 扫描完成，找到 {len(all_files)} 个文件\n")
        
        return {
            'files': all_files,
            'file_paths': file_paths_set
        }
    
    def query_database_records(self) -> Dict[str, any]:
        """查询数据库中的文件记录"""
        print("\n" + "=" * 100)
        print("🗄️  查询数据库记录...")
        print("=" * 100 + "\n")
        
        with self.engine.connect() as conn:
            # 查询所有应该存在的文件
            result = conn.execute(text("""
                SELECT 
                    a.id,
                    a.local_path,
                    a.artifact_type,
                    a.status,
                    a.file_size,
                    c.exchange,
                    c.ticker,
                    f.fiscal_year
                FROM artifacts a
                JOIN filings f ON a.filing_id = f.id
                JOIN companies c ON f.company_id = c.id
                WHERE a.status IN ('downloaded', 'skipped')
                  AND a.local_path IS NOT NULL;
            """))
            
            db_files = []
            db_paths_set = set()
            
            for row in result:
                artifact_id, local_path, artifact_type, status, file_size, exchange, ticker, year = row
                
                db_files.append({
                    'id': artifact_id,
                    'local_path': local_path,
                    'type': artifact_type,
                    'status': status,
                    'size': file_size,
                    'exchange': exchange,
                    'ticker': ticker,
                    'year': year
                })
                
                if local_path:
                    db_paths_set.add(local_path)
                
                self.db_records['total'] += 1
                if status == 'downloaded':
                    self.db_records['downloaded'] += 1
                self.db_records['by_exchange'][exchange] += 1
                self.db_records['by_type'][artifact_type] += 1
            
            print(f"✅ 查询完成，数据库中有 {len(db_files)} 条记录\n")
            
            return {
                'records': db_files,
                'db_paths': db_paths_set
            }
    
    def compare_and_analyze(self, fs_data: Dict, db_data: Dict) -> Dict:
        """对比文件系统和数据库，分析差异"""
        print("\n" + "=" * 100)
        print("🔍 对比分析...")
        print("=" * 100 + "\n")
        
        fs_paths = fs_data.get('file_paths', set())
        db_paths = db_data.get('db_paths', set())
        
        # 找出差异
        missing_in_fs = db_paths - fs_paths  # 数据库有但文件系统没有
        extra_in_fs = fs_paths - db_paths    # 文件系统有但数据库没有
        matched = fs_paths & db_paths        # 都有的
        
        analysis = {
            'total_db': len(db_paths),
            'total_fs': len(fs_paths),
            'matched': len(matched),
            'missing_in_fs': len(missing_in_fs),
            'extra_in_fs': len(extra_in_fs),
            'missing_files': list(missing_in_fs)[:100],  # 最多显示100个
            'extra_files': list(extra_in_fs)[:100]
        }
        
        return analysis
    
    def format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"
    
    def print_report(self, fs_data: Dict, db_data: Dict, analysis: Dict):
        """打印完整性报告"""
        print("\n" + "=" * 100)
        print("📊 文件完整性报告")
        print(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 100)
        
        # ========== 1. 总体概览 ==========
        print("\n【1. 总体概览】")
        print("-" * 100)
        print(f"  存储根目录: {self.storage_root}")
        print(f"  是否存在: {'✅ 是' if self.storage_root.exists() else '❌ 否'}")
        print(f"\n  实际文件总数: {self.file_stats['total_files']:,}")
        print(f"  实际文件总大小: {self.format_size(self.file_stats['total_size'])}")
        print(f"\n  数据库记录总数: {self.db_records['total']:,}")
        print(f"  数据库中已下载: {self.db_records['downloaded']:,}")
        
        # ========== 2. 完整性分析 ==========
        print("\n【2. 完整性分析】")
        print("-" * 100)
        
        match_rate = (analysis['matched'] / analysis['total_db'] * 100) if analysis['total_db'] > 0 else 0
        print(f"  匹配文件数: {analysis['matched']:,}")
        print(f"  匹配率: {match_rate:.2f}%")
        
        if analysis['missing_in_fs'] > 0:
            print(f"\n  ⚠️  数据库有记录但文件缺失: {analysis['missing_in_fs']:,} 个")
            print(f"     (显示前10个)")
            for path in analysis['missing_files'][:10]:
                print(f"     - {path}")
        else:
            print(f"\n  ✅ 没有缺失的文件")
        
        if analysis['extra_in_fs'] > 0:
            print(f"\n  ⚠️  文件存在但数据库无记录: {analysis['extra_in_fs']:,} 个")
            print(f"     (显示前10个)")
            for path in analysis['extra_files'][:10]:
                print(f"     - {path}")
        else:
            print(f"\n  ✅ 没有多余的文件")
        
        # ========== 3. 按交易所统计 ==========
        print("\n【3. 按交易所统计（文件系统）】")
        print("-" * 100)
        
        if self.file_stats['by_exchange']:
            print(f"  {'交易所':20s} | {'文件数':>12s} | {'总大小':>15s} | {'数据库记录':>12s}")
            print("  " + "-" * 70)
            
            for exchange in sorted(self.file_stats['by_exchange'].keys()):
                fs_stats = self.file_stats['by_exchange'][exchange]
                db_count = self.db_records['by_exchange'].get(exchange, 0)
                print(f"  {exchange:20s} | {fs_stats['count']:>12,} | "
                      f"{self.format_size(fs_stats['size']):>15s} | {db_count:>12,}")
        else:
            print("  暂无数据")
        
        # ========== 4. 按文件类型统计 ==========
        print("\n【4. 按文件类型统计（文件系统）】")
        print("-" * 100)
        
        if self.file_stats['by_type']:
            print(f"  {'文件类型':15s} | {'文件数':>12s} | {'总大小':>15s} | {'数据库记录':>12s}")
            print("  " + "-" * 65)
            
            for file_type in sorted(self.file_stats['by_type'].keys()):
                fs_stats = self.file_stats['by_type'][file_type]
                db_count = self.db_records['by_type'].get(file_type, 0)
                print(f"  {file_type:15s} | {fs_stats['count']:>12,} | "
                      f"{self.format_size(fs_stats['size']):>15s} | {db_count:>12,}")
        else:
            print("  暂无数据")
        
        # ========== 5. 按年份统计 ==========
        print("\n【5. 按年份统计（文件系统）】")
        print("-" * 100)
        
        if self.file_stats['by_year']:
            print(f"  {'年份':8s} | {'文件数':>12s} | {'总大小':>15s}")
            print("  " + "-" * 42)
            
            for year in sorted(self.file_stats['by_year'].keys(), reverse=True):
                stats = self.file_stats['by_year'][year]
                print(f"  {year:8} | {stats['count']:>12,} | {self.format_size(stats['size']):>15s}")
        else:
            print("  暂无数据")
        
        # ========== 6. 公司覆盖率 ==========
        print("\n【6. 公司覆盖率（Top 20）】")
        print("-" * 100)
        
        if self.file_stats['by_company']:
            print(f"  {'公司 (交易所/代码)':30s} | {'文件数':>10s}")
            print("  " + "-" * 45)
            
            top_companies = sorted(
                self.file_stats['by_company'].items(),
                key=lambda x: x[1],
                reverse=True
            )[:20]
            
            for company, count in top_companies:
                print(f"  {company:30s} | {count:>10,}")
            
            total_companies = len(self.file_stats['by_company'])
            print(f"\n  总计: {total_companies:,} 家公司有文件")
        else:
            print("  暂无数据")
        
        # ========== 7. 数据完整性评分 ==========
        print("\n【7. 数据完整性评分】")
        print("-" * 100)
        
        # 计算评分
        score = 0
        max_score = 100
        
        # 匹配率 (50分)
        if analysis['total_db'] > 0:
            match_score = (analysis['matched'] / analysis['total_db']) * 50
            score += match_score
            print(f"  文件匹配率得分: {match_score:.1f}/50")
        
        # 缺失率 (25分)
        if analysis['total_db'] > 0:
            missing_rate = analysis['missing_in_fs'] / analysis['total_db']
            missing_score = max(0, 25 - missing_rate * 100)
            score += missing_score
            print(f"  缺失率得分: {missing_score:.1f}/25 (缺失率: {missing_rate*100:.2f}%)")
        
        # 多余文件率 (25分)
        if analysis['total_fs'] > 0:
            extra_rate = analysis['extra_in_fs'] / analysis['total_fs']
            extra_score = max(0, 25 - extra_rate * 100)
            score += extra_score
            print(f"  多余文件得分: {extra_score:.1f}/25 (多余率: {extra_rate*100:.2f}%)")
        
        print(f"\n  📊 总体完整性评分: {score:.1f}/{max_score}")
        
        if score >= 90:
            print("  评级: ⭐⭐⭐⭐⭐ 优秀")
        elif score >= 80:
            print("  评级: ⭐⭐⭐⭐ 良好")
        elif score >= 70:
            print("  评级: ⭐⭐⭐ 中等")
        elif score >= 60:
            print("  评级: ⭐⭐ 及格")
        else:
            print("  评级: ⭐ 需要改进")
        
        print("\n" + "=" * 100)
        print("报告完成")
        print("=" * 100 + "\n")
    
    def run(self):
        """运行完整性检查"""
        try:
            # 1. 扫描文件系统
            fs_data = self.scan_filesystem()
            
            # 2. 查询数据库
            db_data = self.query_database_records()
            
            # 3. 对比分析
            analysis = self.compare_and_analyze(fs_data, db_data)
            
            # 4. 打印报告
            self.print_report(fs_data, db_data, analysis)
            
            return True
            
        except Exception as e:
            print(f"\n❌ 检查过程出错: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    """主函数"""
    print("\n" + "=" * 100)
    print("🔧 文件完整性检查工具")
    print("High-level Python Engineer Implementation")
    print("=" * 100)
    
    checker = FileIntegrityChecker()
    success = checker.run()
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

