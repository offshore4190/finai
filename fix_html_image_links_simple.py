"""
修复HTML文件中的图片链接（简化版，不依赖数据库）
将绝对路径或SEC URL重写为相对路径

使用方法：
  python fix_html_image_links_simple.py                   # 修复所有HTML文件
  python fix_html_image_links_simple.py --sample 50       # 随机抽样50个文件
  python fix_html_image_links_simple.py --dry-run         # 预览模式，不实际修改
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List
import random

from bs4 import BeautifulSoup
from config.settings import settings


class HTMLImageLinkFixerSimple:
    """HTML图片链接修复器（简化版）"""
    
    def __init__(self, dry_run: bool = False, verbose: bool = False):
        self.storage_root = Path(settings.storage_root)
        self.dry_run = dry_run
        self.verbose = verbose
        
        # 统计数据
        self.stats = {
            'total_files': 0,
            'files_fixed': 0,
            'links_fixed': 0,
            'errors': 0
        }
    
    def find_local_images(self, html_path: Path) -> Dict[str, str]:
        """
        找到与HTML文件相关的本地图片
        基于文件命名规则，不依赖数据库
        
        HTML: NYSE/AB/2024/ab-20231231.html
        Images: NYSE/AB/2024/ab-20231231_image-001.jpg
                NYSE/AB/2024/ab-20231231_image-002.png
        """
        html_dir = html_path.parent
        html_stem = html_path.stem  # 文件名不含扩展名
        
        # 查找同目录下符合命名规则的图片
        mapping = {}
        
        for img_file in html_dir.iterdir():
            if not img_file.is_file():
                continue
            
            # 检查是否是图片文件
            if img_file.suffix.lower() not in ['.jpg', '.jpeg', '.png', '.gif', '.svg']:
                continue
            
            # 检查是否与HTML文件相关
            # 图片名应该以HTML文件名开头
            if img_file.stem.startswith(html_stem):
                # 相对路径
                relative_path = f"./{img_file.name}"
                
                # 尝试匹配可能的原始文件名
                # 从 ab-20231231_image-001.jpg 提取 可能的原始名称
                # 原始名称可能是 ab-20231231_g1.jpg, g1.jpg 等
                
                # 添加映射：原始文件名 -> 相对路径
                mapping[img_file.name] = relative_path
                
                # 如果有_image-XXX模式，尝试推断原始名称
                match = re.search(r'_image-(\d+)', img_file.stem)
                if match:
                    seq = int(match.group(1))
                    # 可能的原始名称模式
                    possible_names = [
                        f"g{seq}{img_file.suffix}",  # g1.jpg
                        f"{html_stem}_g{seq}{img_file.suffix}",  # ab-20231231_g1.jpg
                        f"image{seq:02d}{img_file.suffix}",  # image01.jpg
                        f"img{seq}{img_file.suffix}",  # img1.jpg
                    ]
                    for name in possible_names:
                        mapping[name] = relative_path
        
        return mapping
    
    def fix_html_file(self, html_path: Path) -> Dict:
        """修复单个HTML文件"""
        result = {
            'path': str(html_path.relative_to(self.storage_root)),
            'fixed': False,
            'links_fixed': 0,
            'changes': []
        }
        
        try:
            # 读取HTML文件
            with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
                original_content = f.read()
            
            # 获取本地图片映射
            image_mapping = self.find_local_images(html_path)
            
            if not image_mapping:
                if self.verbose:
                    print(f"  ℹ️  {result['path']}: 没有找到关联的图片文件")
                return result
            
            if self.verbose:
                print(f"  📝 {result['path']}: 找到 {len(image_mapping)} 个可能的图片映射")
            
            # 解析HTML
            soup = BeautifulSoup(original_content, 'lxml')
            img_tags = soup.find_all('img')
            
            if not img_tags:
                return result
            
            modified = False
            
            for img in img_tags:
                src = img.get('src', '')
                
                if not src:
                    continue
                
                # 如果已经是正确的相对路径，跳过
                if src.startswith('./') and src[2:] in [v[2:] for v in image_mapping.values()]:
                    continue
                
                # 提取文件名
                src_filename = Path(src).name
                
                # 尝试在映射中查找
                new_src = image_mapping.get(src_filename)
                
                # 如果找不到，尝试模糊匹配
                if not new_src:
                    for key, value in image_mapping.items():
                        if src_filename in key or key in src_filename:
                            new_src = value
                            break
                
                # 如果找到了新的相对路径，并且与原来不同
                if new_src and new_src != src:
                    old_src = src[:100] + '...' if len(src) > 100 else src
                    img['src'] = new_src
                    modified = True
                    result['links_fixed'] += 1
                    result['changes'].append({
                        'old': old_src,
                        'new': new_src
                    })
            
            if modified:
                if not self.dry_run:
                    # 保存修改后的HTML
                    new_content = str(soup)
                    
                    # 备份原文件
                    backup_path = html_path.with_suffix(html_path.suffix + '.bak')
                    if not backup_path.exists():
                        with open(backup_path, 'w', encoding='utf-8') as f:
                            f.write(original_content)
                    
                    # 写入新内容
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    
                    if self.verbose:
                        print(f"  ✅ {result['path']}: 修复了 {result['links_fixed']} 个链接")
                
                result['fixed'] = True
                self.stats['files_fixed'] += 1
                self.stats['links_fixed'] += result['links_fixed']
            
            return result
            
        except Exception as e:
            result['error'] = str(e)
            self.stats['errors'] += 1
            if self.verbose:
                print(f"  ❌ {result['path']}: 错误 - {str(e)}")
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
                    if '.bak' not in html_file.name:
                        html_files.append(html_file)
                for htm_file in company_dir.rglob('*.htm'):
                    if '.bak' not in htm_file.name:
                        html_files.append(htm_file)
        
        if sample_size and len(html_files) > sample_size:
            html_files = random.sample(html_files, sample_size)
        
        print(f"✅ 找到 {len(html_files)} 个HTML文件\n")
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
        
        print(f"开始处理 {len(html_files)} 个HTML文件...\n")
        
        fixed_files = []
        
        for i, html_path in enumerate(html_files, 1):
            if not self.verbose and i % 50 == 0:
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
                
                if result['changes']:
                    print(f"   示例:")
                    for change in result['changes'][:2]:
                        print(f"     {change['old']}")
                        print(f"     → {change['new']}")
            
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
            print("   原文件已备份为 .html.bak 或 .htm.bak")
        else:
            print("✅ 所有文件都正常，无需修复。")
        
        print("=" * 100 + "\n")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='修复HTML文件中的图片链接（简化版）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 预览模式（不实际修改）
  python fix_html_image_links_simple.py --dry-run --sample 10 --verbose
  
  # 修复所有HTML文件
  python fix_html_image_links_simple.py
  
  # 修复指定交易所
  python fix_html_image_links_simple.py --exchange NASDAQ
  
  # 修复抽样文件（推荐）
  python fix_html_image_links_simple.py --sample 50
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
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='显示详细信息'
    )
    
    args = parser.parse_args()
    
    # 运行修复
    fixer = HTMLImageLinkFixerSimple(dry_run=args.dry_run, verbose=args.verbose)
    fixer.run(
        exchange=args.exchange,
        sample_size=args.sample
    )
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

