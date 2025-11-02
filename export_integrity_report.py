"""
导出文件完整性报告为Markdown格式
Professional report generation with detailed analysis
"""

import os
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from typing import Dict, List

from sqlalchemy import create_engine, text
from config.settings import settings


class IntegrityReportExporter:
    """完整性报告导出器"""
    
    def __init__(self):
        self.storage_root = Path(settings.storage_root)
        self.engine = create_engine(settings.database_url)
        self.report_lines = []
        
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
            'by_type': defaultdict(int),
            'by_status': defaultdict(int)
        }
    
    def add_line(self, line: str = ""):
        """添加一行到报告"""
        self.report_lines.append(line)
    
    def format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"
    
    def scan_filesystem(self) -> Dict:
        """扫描文件系统"""
        print("📁 扫描文件系统...")
        
        if not self.storage_root.exists():
            print(f"⚠️  存储目录不存在: {self.storage_root}")
            return {'files': [], 'file_paths': set(), 'file_paths_by_type': defaultdict(set), 'file_paths_by_exchange_type': defaultdict(lambda: defaultdict(set))}
        
        all_files = []
        file_paths_set = set()
        file_paths_by_type = defaultdict(set)  # 按类型分组的路径
        file_paths_by_exchange_type = defaultdict(lambda: defaultdict(set))  # 按交易所和类型分组
        
        for exchange_dir in self.storage_root.iterdir():
            if not exchange_dir.is_dir():
                continue
            
            exchange = exchange_dir.name
            
            for company_dir in exchange_dir.iterdir():
                if not company_dir.is_dir():
                    continue
                
                ticker = company_dir.name
                
                for year_dir in company_dir.iterdir():
                    if not year_dir.is_dir():
                        continue
                    
                    try:
                        year = int(year_dir.name)
                    except ValueError:
                        continue
                    
                    for file_path in year_dir.rglob('*'):
                        if file_path.is_file() and not file_path.name.startswith('.'):
                            try:
                                file_size = file_path.stat().st_size
                                
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
                                relative_path = str(file_path.relative_to(self.storage_root))
                                file_paths_set.add(relative_path)
                                file_paths_by_type[file_type].add(relative_path)
                                file_paths_by_exchange_type[exchange][file_type].add(relative_path)
                                
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
                                pass
        
        print(f"✅ 找到 {len(all_files)} 个文件")
        return {
            'files': all_files,
            'file_paths': file_paths_set,
            'file_paths_by_type': file_paths_by_type,
            'file_paths_by_exchange_type': file_paths_by_exchange_type
        }
    
    def query_database_records(self) -> Dict:
        """查询数据库记录"""
        print("🗄️  查询数据库...")
        
        with self.engine.connect() as conn:
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
            db_paths_by_type = defaultdict(set)  # 按类型分组的路径
            db_paths_by_exchange_type = defaultdict(lambda: defaultdict(set))  # 按交易所和类型分组
            
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
                    db_paths_by_type[artifact_type].add(local_path)
                    db_paths_by_exchange_type[exchange][artifact_type].add(local_path)
                
                self.db_records['total'] += 1
                if status == 'downloaded':
                    self.db_records['downloaded'] += 1
                self.db_records['by_exchange'][exchange] += 1
                self.db_records['by_type'][artifact_type] += 1
                self.db_records['by_status'][status] += 1
            
            print(f"✅ 查询到 {len(db_files)} 条记录")
            return {
                'records': db_files,
                'db_paths': db_paths_set,
                'db_paths_by_type': db_paths_by_type,
                'db_paths_by_exchange_type': db_paths_by_exchange_type
            }
    
    def generate_markdown_report(self, fs_data: Dict, db_data: Dict):
        """生成Markdown报告"""
        print("📝 生成Markdown报告...")
        
        fs_paths = fs_data.get('file_paths', set())
        db_paths = db_data.get('db_paths', set())
        
        missing_in_fs = db_paths - fs_paths
        extra_in_fs = fs_paths - db_paths
        matched = fs_paths & db_paths
        
        # 开始生成报告
        self.add_line("# 📊 SEC报告数据完整性检查报告")
        self.add_line()
        self.add_line(f"**生成时间：** {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}")
        self.add_line(f"**存储位置：** `{self.storage_root}`")
        self.add_line(f"**检查范围：** 2023-2025年 NASDAQ & NYSE 上市公司年报/季报")
        self.add_line()
        self.add_line("---")
        self.add_line()
        
        # 执行摘要
        self.add_line("## 📋 执行摘要")
        self.add_line()
        
        match_rate = (len(matched) / len(db_paths) * 100) if db_paths else 0
        score = self._calculate_score(len(matched), len(db_paths), len(missing_in_fs), len(extra_in_fs), len(fs_paths))
        
        # 计算按类型的匹配率（用于执行摘要）
        fs_paths_by_type = fs_data.get('file_paths_by_type', {})
        db_paths_by_type = db_data.get('db_paths_by_type', {})
        
        html_fs = fs_paths_by_type.get('html', set())
        html_db = db_paths_by_type.get('html', set())
        html_matched = html_fs & html_db
        html_match_rate = (len(html_matched) / len(html_db) * 100) if len(html_db) > 0 else 0
        
        image_fs = fs_paths_by_type.get('image', set())
        image_db = db_paths_by_type.get('image', set())
        image_matched = image_fs & image_db
        image_match_rate = (len(image_matched) / len(image_db) * 100) if len(image_db) > 0 else 0
        
        self.add_line("| 指标 | 数值 | 说明 |")
        self.add_line("|------|------|------|")
        self.add_line(f"| **完整性评分** | **{score:.1f}/100** | {self._get_rating(score)} |")
        self.add_line(f"| 实际文件总数 | {self.file_stats['total_files']:,} | 本地存储的文件数量 |")
        self.add_line(f"| 文件总大小 | {self.format_size(self.file_stats['total_size'])} | 实际占用存储空间 |")
        self.add_line(f"| 数据库记录数 | {self.db_records['total']:,} | 应下载的文件记录 |")
        self.add_line(f"| **总体匹配率** | **{match_rate:.2f}%** | 文件系统与数据库一致性 |")
        self.add_line(f"| └─ HTML匹配率 | {html_match_rate:.2f}% | HTML文件匹配率 ({len(html_matched):,}/{len(html_db):,}) |")
        self.add_line(f"| └─ IMAGE匹配率 | {image_match_rate:.2f}% | 图片文件匹配率 ({len(image_matched):,}/{len(image_db):,}) |")
        self.add_line(f"| 覆盖公司数 | {len(self.file_stats['by_company']):,} | 有文件的公司数量 |")
        self.add_line()
        
        # 数据完整性状态
        if score >= 90:
            self.add_line("### ✅ 数据质量评估：优秀")
            self.add_line()
            self.add_line("数据完整性良好，文件匹配率高，可以放心使用进行分析。")
        elif score >= 80:
            self.add_line("### ⚠️ 数据质量评估：良好")
            self.add_line()
            self.add_line("数据完整性较好，存在少量问题，建议review后使用。")
        else:
            self.add_line("### ❌ 数据质量评估：需要改进")
            self.add_line()
            self.add_line("数据完整性存在较多问题，建议先修复后再使用。")
        
        self.add_line()
        self.add_line("---")
        self.add_line()
        
        # 1. 文件系统概览
        self.add_line("## 📁 文件系统概览")
        self.add_line()
        
        self.add_line("### 按交易所统计")
        self.add_line()
        self.add_line("| 交易所 | 文件数 | 总大小 | 数据库记录 | 完整率 |")
        self.add_line("|--------|--------|--------|-----------|--------|")
        
        for exchange in sorted(self.file_stats['by_exchange'].keys()):
            fs_stats = self.file_stats['by_exchange'][exchange]
            db_count = self.db_records['by_exchange'].get(exchange, 0)
            completeness = (fs_stats['count'] / db_count * 100) if db_count > 0 else 0
            
            self.add_line(f"| {exchange} | {fs_stats['count']:,} | "
                         f"{self.format_size(fs_stats['size'])} | {db_count:,} | {completeness:.1f}% |")
        
        self.add_line()
        
        # 按文件类型统计
        self.add_line("### 按文件类型统计")
        self.add_line()
        self.add_line("| 文件类型 | 文件数 | 总大小 | 占比（数量） | 占比（大小） |")
        self.add_line("|---------|--------|--------|------------|------------|")
        
        total_count = self.file_stats['total_files']
        total_size = self.file_stats['total_size']
        
        for file_type in sorted(self.file_stats['by_type'].keys()):
            stats = self.file_stats['by_type'][file_type]
            count_pct = (stats['count'] / total_count * 100) if total_count > 0 else 0
            size_pct = (stats['size'] / total_size * 100) if total_size > 0 else 0
            
            self.add_line(f"| {file_type} | {stats['count']:,} | "
                         f"{self.format_size(stats['size'])} | {count_pct:.1f}% | {size_pct:.1f}% |")
        
        self.add_line()
        
        # 按年份统计
        self.add_line("### 按年份统计")
        self.add_line()
        self.add_line("| 年份 | 文件数 | 总大小 | 占比 |")
        self.add_line("|------|--------|--------|------|")
        
        for year in sorted(self.file_stats['by_year'].keys(), reverse=True):
            stats = self.file_stats['by_year'][year]
            pct = (stats['count'] / total_count * 100) if total_count > 0 else 0
            
            self.add_line(f"| {year} | {stats['count']:,} | "
                         f"{self.format_size(stats['size'])} | {pct:.1f}% |")
        
        self.add_line()
        self.add_line("---")
        self.add_line()
        
        # 2. 数据库记录分析
        self.add_line("## 🗄️ 数据库记录分析")
        self.add_line()
        
        self.add_line("### 下载状态分布")
        self.add_line()
        self.add_line("| 状态 | 数量 | 占比 |")
        self.add_line("|------|------|------|")
        
        for status in sorted(self.db_records['by_status'].keys()):
            count = self.db_records['by_status'][status]
            pct = (count / self.db_records['total'] * 100) if self.db_records['total'] > 0 else 0
            
            status_icon = "✅" if status == 'downloaded' else "⏭️"
            self.add_line(f"| {status_icon} {status} | {count:,} | {pct:.2f}% |")
        
        self.add_line()
        self.add_line("---")
        self.add_line()
        
        # 3. 按类型统计的完整性（统一口径）
        self.add_line("## 📐 按类型统计的完整性（统一口径）")
        self.add_line()
        self.add_line("### 全局匹配率（按类型）")
        self.add_line()
        
        fs_paths_by_type = fs_data.get('file_paths_by_type', {})
        db_paths_by_type = db_data.get('db_paths_by_type', {})
        
        # 计算每种类型的匹配率
        type_stats = {}
        for artifact_type in set(list(fs_paths_by_type.keys()) + list(db_paths_by_type.keys())):
            fs_paths_type = fs_paths_by_type.get(artifact_type, set())
            db_paths_type = db_paths_by_type.get(artifact_type, set())
            matched_type = fs_paths_type & db_paths_type
            
            type_stats[artifact_type] = {
                'db_count': len(db_paths_type),
                'fs_count': len(fs_paths_type),
                'matched': len(matched_type),
                'match_rate': (len(matched_type) / len(db_paths_type) * 100) if len(db_paths_type) > 0 else 0
            }
        
        self.add_line("| 文件类型 | 数据库记录数 | 文件系统文件数 | 匹配数 | 匹配率 |")
        self.add_line("|---------|------------|--------------|--------|--------|")
        
        total_db_weighted = 0
        total_matched_weighted = 0
        
        for artifact_type in sorted(type_stats.keys()):
            stats = type_stats[artifact_type]
            self.add_line(f"| **{artifact_type}** | {stats['db_count']:,} | {stats['fs_count']:,} | "
                         f"{stats['matched']:,} | **{stats['match_rate']:.2f}%** |")
            total_db_weighted += stats['db_count']
            total_matched_weighted += stats['matched']
        
        # 加权总分
        overall_match_rate = (total_matched_weighted / total_db_weighted * 100) if total_db_weighted > 0 else 0
        self.add_line(f"| **Overall (加权)** | {total_db_weighted:,} | {len(fs_paths):,} | "
                     f"{total_matched_weighted:,} | **{overall_match_rate:.2f}%** |")
        
        self.add_line()
        
        # 按交易所和类型统计
        self.add_line("### 按交易所和类型统计的完整率")
        self.add_line()
        
        fs_by_exchange_type = fs_data.get('file_paths_by_exchange_type', {})
        db_by_exchange_type = db_data.get('db_paths_by_exchange_type', {})
        
        all_exchanges = sorted(set(list(fs_by_exchange_type.keys()) + list(db_by_exchange_type.keys())))
        
        for exchange in all_exchanges:
            self.add_line(f"#### {exchange}")
            self.add_line()
            self.add_line("| 文件类型 | 数据库记录数 | 文件系统文件数 | 匹配数 | 匹配率 |")
            self.add_line("|---------|------------|--------------|--------|--------|")
            
            fs_exchange = fs_by_exchange_type.get(exchange, {})
            db_exchange = db_by_exchange_type.get(exchange, {})
            
            all_types = sorted(set(list(fs_exchange.keys()) + list(db_exchange.keys())))
            
            exchange_total_db = 0
            exchange_total_matched = 0
            
            for artifact_type in all_types:
                fs_paths_ex_type = fs_exchange.get(artifact_type, set())
                db_paths_ex_type = db_exchange.get(artifact_type, set())
                matched_ex_type = fs_paths_ex_type & db_paths_ex_type
                
                db_count = len(db_paths_ex_type)
                fs_count = len(fs_paths_ex_type)
                matched_count = len(matched_ex_type)
                match_rate = (matched_count / db_count * 100) if db_count > 0 else 0
                
                self.add_line(f"| {artifact_type} | {db_count:,} | {fs_count:,} | "
                             f"{matched_count:,} | {match_rate:.2f}% |")
                
                exchange_total_db += db_count
                exchange_total_matched += matched_count
            
            # 交易所加权总分
            exchange_overall = (exchange_total_matched / exchange_total_db * 100) if exchange_total_db > 0 else 0
            self.add_line(f"| **小计 (加权)** | {exchange_total_db:,} | - | "
                         f"{exchange_total_matched:,} | **{exchange_overall:.2f}%** |")
            self.add_line()
        
        self.add_line("---")
        self.add_line()
        
        # 4. 完整性分析
        self.add_line("## 🔍 完整性分析（总体）")
        self.add_line()
        
        self.add_line(f"- **匹配文件数：** {len(matched):,}")
        self.add_line(f"- **匹配率：** {match_rate:.2f}%")
        self.add_line(f"- **缺失文件数：** {len(missing_in_fs):,}")
        self.add_line(f"- **多余文件数：** {len(extra_in_fs):,}")
        self.add_line()
        
        if missing_in_fs:
            self.add_line("### ⚠️ 缺失文件列表（前50个）")
            self.add_line()
            self.add_line("以下文件在数据库中有记录，但在文件系统中缺失：")
            self.add_line()
            for i, path in enumerate(list(missing_in_fs)[:50], 1):
                self.add_line(f"{i}. `{path}`")
            
            if len(missing_in_fs) > 50:
                self.add_line(f"\n... 还有 {len(missing_in_fs) - 50} 个文件未列出")
            self.add_line()
        
        if extra_in_fs:
            self.add_line("### ℹ️ 多余文件列表（前50个）")
            self.add_line()
            self.add_line("以下文件存在于文件系统中，但数据库中没有记录：")
            self.add_line()
            for i, path in enumerate(list(extra_in_fs)[:50], 1):
                self.add_line(f"{i}. `{path}`")
            
            if len(extra_in_fs) > 50:
                self.add_line(f"\n... 还有 {len(extra_in_fs) - 50} 个文件未列出")
            self.add_line()
        
        if not missing_in_fs and not extra_in_fs:
            self.add_line("### ✅ 完美匹配")
            self.add_line()
            self.add_line("所有文件都完美匹配，没有缺失或多余的文件。")
            self.add_line()
        
        self.add_line("---")
        self.add_line()
        
        # 4. 公司覆盖率分析
        self.add_line("## 🏢 公司覆盖率分析")
        self.add_line()
        
        self.add_line(f"**总覆盖公司数：** {len(self.file_stats['by_company']):,} 家")
        self.add_line()
        
        self.add_line("### Top 30 公司（按文件数排序）")
        self.add_line()
        self.add_line("| 排名 | 公司 (交易所/代码) | 文件数 |")
        self.add_line("|------|------------------|--------|")
        
        top_companies = sorted(
            self.file_stats['by_company'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:30]
        
        for rank, (company, count) in enumerate(top_companies, 1):
            self.add_line(f"| {rank} | `{company}` | {count:,} |")
        
        self.add_line()
        self.add_line("---")
        self.add_line()
        
        # 5. 数据质量指标
        self.add_line("## 📊 数据质量指标")
        self.add_line()
        
        missing_rate = (len(missing_in_fs) / len(db_paths) * 100) if db_paths else 0
        extra_rate = (len(extra_in_fs) / len(fs_paths) * 100) if fs_paths else 0
        
        self.add_line("| 指标 | 数值 | 目标 | 状态 |")
        self.add_line("|------|------|------|------|")
        self.add_line(f"| 文件匹配率 | {match_rate:.2f}% | ≥99% | {self._status_icon(match_rate >= 99)} |")
        self.add_line(f"| 缺失率 | {missing_rate:.2f}% | ≤1% | {self._status_icon(missing_rate <= 1)} |")
        self.add_line(f"| 多余文件率 | {extra_rate:.2f}% | ≤1% | {self._status_icon(extra_rate <= 1)} |")
        
        avg_files_per_company = self.file_stats['total_files'] / len(self.file_stats['by_company']) if self.file_stats['by_company'] else 0
        self.add_line(f"| 平均文件数/公司 | {avg_files_per_company:.1f} | ≥15 | {self._status_icon(avg_files_per_company >= 15)} |")
        
        self.add_line()
        self.add_line("---")
        self.add_line()
        
        # 6. 建议和后续行动
        self.add_line("## 💡 建议和后续行动")
        self.add_line()
        
        if score >= 95:
            self.add_line("### ✅ 数据质量优秀")
            self.add_line()
            self.add_line("1. 数据完整性非常好，可以直接用于生产分析")
            self.add_line("2. 建议定期运行完整性检查，确保持续质量")
            self.add_line("3. 考虑设置自动化的数据备份流程")
        elif score >= 80:
            self.add_line("### ⚠️ 需要关注的问题")
            self.add_line()
            if missing_in_fs:
                self.add_line(f"1. 有 {len(missing_in_fs)} 个文件缺失，建议重新下载")
            if extra_in_fs:
                self.add_line(f"2. 有 {len(extra_in_fs)} 个多余文件，建议review并清理")
            self.add_line("3. 建议运行增量更新补齐缺失数据")
        else:
            self.add_line("### ❌ 需要立即处理")
            self.add_line()
            self.add_line("1. **优先级1：** 修复缺失的文件")
            self.add_line("2. **优先级2：** 清理多余的文件")
            self.add_line("3. **优先级3：** 验证数据库记录的准确性")
        
        self.add_line()
        
        self.add_line("### 推荐命令")
        self.add_line()
        self.add_line("```bash")
        self.add_line("# 运行增量更新")
        self.add_line("python main.py incremental")
        self.add_line()
        self.add_line("# 重新检查完整性")
        self.add_line("python export_integrity_report.py")
        self.add_line()
        self.add_line("# 查看数据库状态")
        self.add_line("python query_db_summary.py")
        self.add_line("```")
        self.add_line()
        self.add_line("---")
        self.add_line()
        
        # 附录
        self.add_line("## 📎 附录")
        self.add_line()
        
        self.add_line("### 技术规格")
        self.add_line()
        self.add_line(f"- **存储根目录：** `{self.storage_root}`")
        self.add_line(f"- **数据库：** PostgreSQL")
        self.add_line(f"- **扫描时间：** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.add_line(f"- **Python版本：** {sys.version.split()[0]}")
        self.add_line()
        
        self.add_line("### 评分标准")
        self.add_line()
        self.add_line("完整性评分计算方式：")
        self.add_line()
        self.add_line("- **文件匹配率（50分）：** 匹配文件数 / 数据库记录数 × 50")
        self.add_line("- **缺失率得分（25分）：** max(0, 25 - 缺失率 × 100)")
        self.add_line("- **多余文件得分（25分）：** max(0, 25 - 多余率 × 100)")
        self.add_line()
        
        self.add_line("### 评级说明")
        self.add_line()
        self.add_line("| 分数范围 | 评级 | 说明 |")
        self.add_line("|---------|------|------|")
        self.add_line("| 90-100 | ⭐⭐⭐⭐⭐ 优秀 | 数据质量极佳 |")
        self.add_line("| 80-89 | ⭐⭐⭐⭐ 良好 | 数据质量较好 |")
        self.add_line("| 70-79 | ⭐⭐⭐ 中等 | 需要关注 |")
        self.add_line("| 60-69 | ⭐⭐ 及格 | 需要改进 |")
        self.add_line("| <60 | ⭐ 不及格 | 需要立即处理 |")
        self.add_line()
        
        self.add_line("---")
        self.add_line()
        self.add_line(f"*报告生成于 {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')} by 文件完整性检查工具*")
        
        print("✅ Markdown报告生成完成")
    
    def _calculate_score(self, matched: int, total_db: int, missing: int, extra: int, total_fs: int) -> float:
        """计算完整性评分"""
        score = 0
        
        # 匹配率 (50分)
        if total_db > 0:
            score += (matched / total_db) * 50
        
        # 缺失率 (25分)
        if total_db > 0:
            missing_rate = missing / total_db
            score += max(0, 25 - missing_rate * 100)
        
        # 多余文件率 (25分)
        if total_fs > 0:
            extra_rate = extra / total_fs
            score += max(0, 25 - extra_rate * 100)
        
        return score
    
    def _get_rating(self, score: float) -> str:
        """获取评级"""
        if score >= 90:
            return "⭐⭐⭐⭐⭐ 优秀"
        elif score >= 80:
            return "⭐⭐⭐⭐ 良好"
        elif score >= 70:
            return "⭐⭐⭐ 中等"
        elif score >= 60:
            return "⭐⭐ 及格"
        else:
            return "⭐ 不及格"
    
    def _status_icon(self, condition: bool) -> str:
        """状态图标"""
        return "✅" if condition else "⚠️"
    
    def save_report(self, output_file: str = None):
        """保存报告到文件"""
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"integrity_report_{timestamp}.md"
        
        output_path = Path(output_file)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(self.report_lines))
        
        print(f"\n✅ 报告已保存到: {output_path.absolute()}")
        print(f"   文件大小: {output_path.stat().st_size:,} 字节")
        
        return output_path
    
    def run(self, output_file: str = None):
        """运行完整流程"""
        print("\n" + "=" * 100)
        print("📊 生成Markdown格式完整性报告")
        print("=" * 100 + "\n")
        
        try:
            # 1. 扫描文件系统
            fs_data = self.scan_filesystem()
            
            # 2. 查询数据库
            db_data = self.query_database_records()
            
            # 3. 生成Markdown报告
            self.generate_markdown_report(fs_data, db_data)
            
            # 4. 保存报告
            report_path = self.save_report(output_file)
            
            print("\n" + "=" * 100)
            print("✅ 报告生成成功！")
            print("=" * 100)
            
            return report_path
            
        except Exception as e:
            print(f"\n❌ 生成报告时出错: {e}")
            import traceback
            traceback.print_exc()
            return None


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='导出文件完整性报告为Markdown格式')
    parser.add_argument('-o', '--output', type=str, help='输出文件名（默认：integrity_report_YYYYMMDD_HHMMSS.md）')
    args = parser.parse_args()
    
    exporter = IntegrityReportExporter()
    report_path = exporter.run(args.output)
    
    if report_path:
        print(f"\n📄 可以使用以下命令查看报告：")
        print(f"   cat {report_path}")
        print(f"   或在IDE中打开查看")
    
    sys.exit(0 if report_path else 1)


if __name__ == '__main__':
    main()

