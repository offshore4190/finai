"""
批量修复HTML图片链接 - 按交易所分组处理
支持 NYSE 和 NASDAQ 独立处理

使用方法：
  python batch_fix_html_by_exchange.py --exchange NASDAQ    # 只修复NASDAQ
  python batch_fix_html_by_exchange.py --exchange NYSE      # 只修复NYSE
  python batch_fix_html_by_exchange.py --all                # 修复所有
  python batch_fix_html_by_exchange.py --dry-run --all      # 预览模式
"""

import argparse
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from typing import Dict, List
import time

from bs4 import BeautifulSoup
from config.settings import settings
import structlog

logger = structlog.get_logger()


class BatchHTMLFixer:
    """批量HTML图片链接修复器"""
    
    def __init__(self, dry_run: bool = False, verbose: bool = False):
        self.storage_root = Path(settings.storage_root)
        self.dry_run = dry_run
        self.verbose = verbose
        
        # 统计数据 - 按交易所分组
        self.stats = {
            'NASDAQ': {'files': 0, 'fixed': 0, 'links': 0, 'errors': 0, 'time': 0},
            'NYSE': {'files': 0, 'fixed': 0, 'links': 0, 'errors': 0, 'time': 0},
            'NYSE American': {'files': 0, 'fixed': 0, 'links': 0, 'errors': 0, 'time': 0},
            'NYSE Arca': {'files': 0, 'fixed': 0, 'links': 0, 'errors': 0, 'time': 0},
        }
        
        self.total_start_time = None
    
    def find_local_images(self, html_path: Path) -> Dict[str, str]:
        """找到与HTML文件相关的本地图片"""
        html_dir = html_path.parent
        html_stem = html_path.stem
        
        mapping = {}
        
        for img_file in html_dir.iterdir():
            if not img_file.is_file():
                continue
            
            if img_file.suffix.lower() not in ['.jpg', '.jpeg', '.png', '.gif', '.svg']:
                continue
            
            if img_file.stem.startswith(html_stem):
                relative_path = f"./{img_file.name}"
                mapping[img_file.name] = relative_path
        
        return mapping
    
    def fix_html_file(self, html_path: Path, exchange: str) -> Dict:
        """修复单个HTML文件"""
        result = {
            'path': str(html_path.relative_to(self.storage_root)),
            'exchange': exchange,
            'fixed': False,
            'links_fixed': 0,
            'changes': []
        }
        
        try:
            # 读取HTML
            with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # 获取本地图片映射
            image_mapping = self.find_local_images(html_path)
            
            if not image_mapping:
                return result
            
            # 解析HTML
            soup = BeautifulSoup(content, 'lxml')
            img_tags = soup.find_all('img')
            
            if not img_tags:
                return result
            
            modified = False
            local_images = sorted(image_mapping.values())
            
            for i, img in enumerate(img_tags):
                src = img.get('src', '')
                
                if not src:
                    continue
                
                # 如果已经是正确的相对路径，跳过
                if src.startswith('./') and src in local_images:
                    continue
                
                # 使用映射查找新路径
                new_src = None
                src_filename = Path(src).name
                
                if src_filename in image_mapping:
                    new_src = image_mapping[src_filename]
                elif i < len(local_images):
                    new_src = local_images[i]
                
                if new_src and new_src != src:
                    img['src'] = new_src
                    modified = True
                    result['links_fixed'] += 1
                    result['changes'].append({
                        'old': src[:80],
                        'new': new_src
                    })
            
            if modified:
                if not self.dry_run:
                    # 备份原文件
                    backup_path = html_path.with_suffix(html_path.suffix + '.bak')
                    if not backup_path.exists():
                        with open(backup_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                    
                    # 保存修改后的HTML
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(str(soup))
                    
                    if self.verbose:
                        logger.info("html_fixed", 
                                  path=result['path'], 
                                  links=result['links_fixed'])
                
                result['fixed'] = True
                self.stats[exchange]['fixed'] += 1
                self.stats[exchange]['links'] += result['links_fixed']
            
            return result
            
        except Exception as e:
            result['error'] = str(e)
            self.stats[exchange]['errors'] += 1
            if self.verbose:
                logger.error("fix_failed", path=result['path'], error=str(e))
            return result
    
    def process_exchange(self, exchange: str) -> List[Dict]:
        """处理单个交易所的所有HTML文件"""
        print(f"\n{'='*80}")
        print(f"📊 处理交易所: {exchange}")
        print(f"{'='*80}")
        
        start_time = time.time()
        
        # 查找该交易所的所有HTML文件
        exchange_dir = self.storage_root / exchange
        
        if not exchange_dir.exists():
            print(f"⚠️  目录不存在: {exchange_dir}")
            return []
        
        html_files = []
        for html_file in exchange_dir.rglob('*.html'):
            if '.bak' not in html_file.name:
                html_files.append(html_file)
        for htm_file in exchange_dir.rglob('*.htm'):
            if '.bak' not in htm_file.name:
                html_files.append(htm_file)
        
        print(f"找到 {len(html_files)} 个HTML文件")
        
        if not html_files:
            return []
        
        self.stats[exchange]['files'] = len(html_files)
        
        # 处理每个文件
        fixed_files = []
        for i, html_path in enumerate(html_files, 1):
            if not self.verbose and i % 100 == 0:
                progress = (i / len(html_files)) * 100
                print(f"  进度: {i}/{len(html_files)} ({progress:.1f}%)")
            
            result = self.fix_html_file(html_path, exchange)
            
            if result['fixed']:
                fixed_files.append(result)
        
        elapsed = time.time() - start_time
        self.stats[exchange]['time'] = elapsed
        
        # 打印该交易所的统计
        print(f"\n【{exchange} 统计】")
        print(f"  处理文件: {self.stats[exchange]['files']:,}")
        print(f"  修复文件: {self.stats[exchange]['fixed']:,}")
        print(f"  修复链接: {self.stats[exchange]['links']:,}")
        print(f"  错误数量: {self.stats[exchange]['errors']:,}")
        print(f"  处理时间: {elapsed:.2f}秒")
        
        if fixed_files and self.verbose:
            print(f"\n  修复的文件示例（前5个）:")
            for result in fixed_files[:5]:
                print(f"    ✅ {result['path']} ({result['links_fixed']}个链接)")
        
        return fixed_files
    
    def run(self, exchanges: List[str]):
        """运行批量修复"""
        self.total_start_time = time.time()
        
        mode_str = "预览模式" if self.dry_run else "修复模式"
        print("\n" + "="*80)
        print(f"🔧 批量修复HTML图片链接 ({mode_str})")
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80)
        
        all_fixed_files = []
        
        # 处理每个交易所
        for exchange in exchanges:
            fixed_files = self.process_exchange(exchange)
            all_fixed_files.extend(fixed_files)
        
        # 打印总体报告
        self.print_summary_report()
    
    def print_summary_report(self):
        """打印总体报告"""
        total_elapsed = time.time() - self.total_start_time
        
        print("\n" + "="*80)
        print("📊 总体修复报告")
        print("="*80)
        
        mode_str = " (预览模式，未实际修改)" if self.dry_run else ""
        
        # 按交易所统计
        print(f"\n【按交易所统计{mode_str}】\n")
        print(f"{'交易所':<15} {'处理文件':<12} {'修复文件':<12} {'修复链接':<12} {'错误':<8} {'时间':<10}")
        print("-"*80)
        
        total_files = 0
        total_fixed = 0
        total_links = 0
        total_errors = 0
        
        for exchange in ['NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca']:
            stats = self.stats[exchange]
            if stats['files'] > 0:
                print(f"{exchange:<15} {stats['files']:<12,} {stats['fixed']:<12,} "
                      f"{stats['links']:<12,} {stats['errors']:<8,} {stats['time']:<10.2f}s")
                
                total_files += stats['files']
                total_fixed += stats['fixed']
                total_links += stats['links']
                total_errors += stats['errors']
        
        print("-"*80)
        print(f"{'总计':<15} {total_files:<12,} {total_fixed:<12,} "
              f"{total_links:<12,} {total_errors:<8,} {total_elapsed:<10.2f}s")
        
        # 修复率
        if total_files > 0:
            fix_rate = (total_fixed / total_files) * 100
            print(f"\n修复率: {fix_rate:.2f}% ({total_fixed:,}/{total_files:,})")
        
        print("\n" + "="*80)
        
        # 结论
        if self.dry_run:
            print("ℹ️  这是预览模式，没有实际修改文件。")
            print("   要实际修复，请去掉 --dry-run 参数。")
        elif total_fixed > 0:
            print(f"🎉 修复完成！")
            print(f"   ✅ 共修复 {total_fixed:,} 个文件，{total_links:,} 个图片链接")
            print(f"   ⏱️  总耗时: {total_elapsed:.2f}秒")
            print(f"   💾 原文件已备份为 .bak")
        else:
            print("✅ 所有文件都正常，无需修复。")
        
        if total_errors > 0:
            print(f"\n⚠️  处理过程中发生 {total_errors:,} 个错误")
        
        print("="*80 + "\n")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='批量修复HTML图片链接（按交易所分组）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 预览NASDAQ的修复
  python batch_fix_html_by_exchange.py --exchange NASDAQ --dry-run
  
  # 修复NASDAQ
  python batch_fix_html_by_exchange.py --exchange NASDAQ
  
  # 修复NYSE
  python batch_fix_html_by_exchange.py --exchange NYSE
  
  # 修复所有交易所
  python batch_fix_html_by_exchange.py --all
  
  # 详细模式
  python batch_fix_html_by_exchange.py --exchange NASDAQ --verbose
        """
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--exchange',
        type=str,
        choices=['NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca'],
        help='指定要处理的交易所'
    )
    group.add_argument(
        '--all',
        action='store_true',
        help='处理所有交易所'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='预览模式，不实际修改文件'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='显示详细信息'
    )
    
    args = parser.parse_args()
    
    # 确定要处理的交易所列表
    if args.all:
        exchanges = ['NASDAQ', 'NYSE', 'NYSE American', 'NYSE Arca']
    else:
        exchanges = [args.exchange]
    
    # 运行修复
    fixer = BatchHTMLFixer(dry_run=args.dry_run, verbose=args.verbose)
    fixer.run(exchanges)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

