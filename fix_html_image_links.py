"""
修复HTML文件中的图片链接
将绝对路径或SEC URL重写为相对路径

使用方法：
  python fix_html_image_links.py                      # 修复所有HTML文件
  python fix_html_image_links.py --sample 50          # 随机抽样50个文件
  python fix_html_image_links.py --exchange NASDAQ    # 只修复NASDAQ
  python fix_html_image_links.py --dry-run            # 预览模式，不实际修改
"""

import argparse
import re
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List
import random

from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text
from config.settings import settings
import structlog

logger = structlog.get_logger()


class HTMLImageLinkFixer:
    """HTML图片链接修复器"""
    
    def __init__(self, dry_run: bool = False):
        self.storage_root = Path(settings.storage_root)
        self.dry_run = dry_run
        self.engine = create_engine(settings.database_url)
        
        # 统计数据
        self.stats = {
            'total_files': 0,
            'files_fixed': 0,
            'links_fixed': 0,
            'errors': 0
        }
        
    def get_image_mapping(self, html_path: Path) -> Dict[str, str]:
        """
        获取该HTML文件对应的图片映射
        从数据库查询该filing的所有图片，建立URL到本地相对路径的映射
        
        Returns:
            {原始URL: 相对路径}
        """
        # 从HTML路径提取信息
        # 格式: NASDAQ/AAPL/2023/aapl-20230930.htm
        relative_path = str(html_path.relative_to(self.storage_root))
        
        with self.engine.connect() as conn:
            # 查找该HTML文件对应的artifact
            result = conn.execute(text("""
                SELECT a.id, a.filing_id
                FROM artifacts a
                WHERE a.local_path = :html_path
                  AND a.artifact_type = 'html'
                LIMIT 1
            """), {'html_path': relative_path})
            
            row = result.fetchone()
            if not row:
                logger.warning("html_artifact_not_found", path=relative_path)
                return {}
            
            artifact_id, filing_id = row
            
            # 查询该filing的所有图片
            result = conn.execute(text("""
                SELECT url, local_path, filename
                FROM artifacts
                WHERE filing_id = :filing_id
                  AND artifact_type = 'image'
                  AND status IN ('downloaded', 'skipped')
            """), {'filing_id': filing_id})
            
            mapping = {}
            for row in result:
                url, local_path, filename = row
                
                # 计算相对路径
                # HTML在: NYSE/AB/2024/ab-20231231.html
                # 图片在: NYSE/AB/2024/ab-20231231_image-001.jpg
                # 相对路径: ./ab-20231231_image-001.jpg
                if local_path:
                    image_path = Path(local_path)
                    relative_to_html = f"./{image_path.name}"
                    mapping[url] = relative_to_html
            
            logger.debug(
                "image_mapping_built",
                html_path=relative_path,
                filing_id=filing_id,
                image_count=len(mapping)
            )
            
            return mapping
    
    def fix_html_file(self, html_path: Path) -> Dict:
        """修复单个HTML文件"""
        result = {
            'path': str(html_path.relative_to(self.storage_root)),
            'fixed': False,
            'links_fixed': 0,
            'original_links': [],
            'new_links': []
        }
        
        try:
            # 读取HTML文件
            with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
                original_content = f.read()
            
            # 获取图片映射
            image_mapping = self.get_image_mapping(html_path)
            
            if not image_mapping:
                logger.debug("no_images_for_html", path=result['path'])
                return result
            
            # 解析HTML
            soup = BeautifulSoup(original_content, 'lxml')
            img_tags = soup.find_all('img')
            
            modified = False
            
            for img in img_tags:
                src = img.get('src', '')
                
                if not src:
                    continue
                
                # 尝试匹配原始URL
                new_src = None
                
                # 直接匹配
                if src in image_mapping:
                    new_src = image_mapping[src]
                else:
                    # 尝试去掉file:///前缀匹配
                    if src.startswith('file:///'):
                        # file:///private/tmp/filings/NYSE/AB/2024/ab-20231231_g2.jpg
                        # 提取文件名部分
                        filename = Path(src).name
                        
                        # 在映射中查找包含此文件名的URL
                        for url, relative_path in image_mapping.items():
                            if filename in url or filename in relative_path:
                                new_src = relative_path
                                break
                    
                    # 尝试匹配URL中的文件名
                    if not new_src:
                        src_filename = Path(src).name
                        for url, relative_path in image_mapping.items():
                            url_filename = Path(url).name
                            if src_filename == url_filename:
                                new_src = relative_path
                                break
                
                # 如果找到了新的相对路径，进行替换
                if new_src and new_src != src:
                    result['original_links'].append(src)
                    result['new_links'].append(new_src)
                    img['src'] = new_src
                    modified = True
                    result['links_fixed'] += 1
            
            if modified and not self.dry_run:
                # 保存修改后的HTML
                new_content = str(soup)
                
                # 备份原文件
                backup_path = html_path.with_suffix('.html.bak')
                if not backup_path.exists():
                    with open(backup_path, 'w', encoding='utf-8') as f:
                        f.write(original_content)
                
                # 写入新内容
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                
                result['fixed'] = True
                self.stats['files_fixed'] += 1
                self.stats['links_fixed'] += result['links_fixed']
                
                logger.info(
                    "html_fixed",
                    path=result['path'],
                    links_fixed=result['links_fixed']
                )
            elif modified:
                result['fixed'] = True  # Would be fixed
                self.stats['links_fixed'] += result['links_fixed']
            
            return result
            
        except Exception as e:
            result['error'] = str(e)
            self.stats['errors'] += 1
            logger.error("fix_failed", path=result['path'], error=str(e))
            return result
    
    def scan_html_files(self, exchange: str = None, sample_size: int = None) -> List[Path]:
        """扫描HTML文件"""
        print(f"📁 扫描HTML文件...")
        
        if not self.storage_root.exists():
            print(f"⚠️  存储目录不存在: {self.storage_root}")
            return []
        
        html_files = []
        
        for exchange_dir in self.storage_root.iterdir():
            if not exchange_dir.is_dir():
                continue
            
            if exchange and exchange_dir.name != exchange:
                continue
            
            for company_dir in exchange_dir.iterdir():
                if not company_dir.is_dir():
                    continue
                
                for html_file in company_dir.rglob('*.html'):
                    # 跳过备份文件
                    if html_file.suffix == '.bak':
                        continue
                    html_files.append(html_file)
                for htm_file in company_dir.rglob('*.htm'):
                    html_files.append(htm_file)
        
        if sample_size and len(html_files) > sample_size:
            html_files = random.sample(html_files, sample_size)
        
        print(f"✅ 找到 {len(html_files)} 个HTML文件")
        return html_files
    
    def run(self, exchange: str = None, sample_size: int = None):
        """运行修复"""
        mode_str = "预览模式" if self.dry_run else "修复模式"
        print("\n" + "=" * 100)
        print(f"🔧 HTML图片链接修复工具 ({mode_str})")
        print("=" * 100 + "\n")
        
        html_files = self.scan_html_files(exchange, sample_size)
        
        if not html_files:
            print("❌ 没有找到HTML文件")
            return
        
        self.stats['total_files'] = len(html_files)
        
        print(f"\n开始处理 {len(html_files)} 个HTML文件...\n")
        
        fixed_files = []
        
        for i, html_path in enumerate(html_files, 1):
            if i % 100 == 0:
                print(f"  进度: {i}/{len(html_files)}")
            
            result = self.fix_html_file(html_path)
            
            if result['fixed']:
                fixed_files.append(result)
        
        # 打印报告
        self.print_report(fixed_files)
    
    def print_report(self, fixed_files: List[Dict]):
        """打印报告"""
        print("\n" + "=" * 100)
        print("📊 修复报告")
        print("=" * 100 + "\n")
        
        mode_str = " (预览模式，未实际修改)" if self.dry_run else ""
        
        print(f"【总体统计{mode_str}】")
        print(f"  处理文件数: {self.stats['total_files']:,}")
        print(f"  修复的文件: {self.stats['files_fixed']:,}")
        print(f"  修复的链接: {self.stats['links_fixed']:,}")
        print(f"  处理错误: {self.stats['errors']:,}")
        
        if fixed_files:
            print(f"\n✅ 成功修复 {len(fixed_files)} 个文件")
            
            print("\n【修复的文件】（前20个）")
            for i, result in enumerate(fixed_files[:20], 1):
                print(f"\n{i}. 文件: {result['path']}")
                print(f"   修复链接数: {result['links_fixed']}")
                
                if result['original_links'] and result['new_links']:
                    print(f"   示例:")
                    for orig, new in zip(result['original_links'][:2], result['new_links'][:2]):
                        print(f"     {orig[:80]}...")
                        print(f"     → {new}")
            
            if len(fixed_files) > 20:
                print(f"\n... 还有 {len(fixed_files) - 20} 个文件未列出")
        else:
            print("\n✅ 所有HTML文件的图片链接都已经是正确的相对路径！")
        
        if self.stats['errors'] > 0:
            print(f"\n⚠️  处理过程中发生 {self.stats['errors']} 个错误")
        
        print("\n" + "=" * 100)
        
        if self.dry_run:
            print("ℹ️  这是预览模式，没有实际修改文件。")
            print("   要实际修复，请去掉 --dry-run 参数。")
        elif self.stats['files_fixed'] > 0:
            print(f"🎉 修复完成！已修复 {self.stats['files_fixed']} 个文件。")
            print("   原文件已备份为 .html.bak")
        else:
            print("✅ 所有文件都正常，无需修复。")
        
        print("=" * 100 + "\n")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='修复HTML文件中的图片链接',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 预览模式（不实际修改）
  python fix_html_image_links.py --dry-run --sample 10
  
  # 修复所有HTML文件
  python fix_html_image_links.py
  
  # 修复指定交易所
  python fix_html_image_links.py --exchange NASDAQ
  
  # 修复抽样文件
  python fix_html_image_links.py --sample 50
        """
    )
    
    parser.add_argument(
        '--exchange',
        type=str,
        help='指定交易所（如：NASDAQ, NYSE）'
    )
    
    parser.add_argument(
        '--sample',
        type=int,
        help='随机抽样的文件数量'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='预览模式，不实际修改文件'
    )
    
    args = parser.parse_args()
    
    # 运行修复
    fixer = HTMLImageLinkFixer(dry_run=args.dry_run)
    fixer.run(
        exchange=args.exchange,
        sample_size=args.sample
    )
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

