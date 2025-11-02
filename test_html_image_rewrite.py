"""
测试HTML文件内容，验证图片链接重写
检查所有 <img> 标签的 src 属性是否已从原始 URL 重写为本地相对路径

使用方法：
  python test_html_image_rewrite.py                      # 测试所有HTML文件
  python test_html_image_rewrite.py --sample 50          # 随机抽样50个文件测试
  python test_html_image_rewrite.py --exchange NASDAQ    # 只测试NASDAQ
  python test_html_image_rewrite.py --company AAPL       # 只测试特定公司
  python test_html_image_rewrite.py --verbose            # 显示详细信息
"""

import argparse
import re
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple
import random

from bs4 import BeautifulSoup
from config.settings import settings


class HTMLImageRewriteTester:
    """HTML图片链接重写测试器"""
    
    def __init__(self, verbose: bool = False):
        self.storage_root = Path(settings.storage_root)
        self.verbose = verbose
        
        # 统计数据
        self.stats = {
            'total_files': 0,
            'files_with_images': 0,
            'total_img_tags': 0,
            'rewritten_correctly': 0,
            'not_rewritten': 0,
            'invalid_format': 0,
            'errors': 0
        }
        
        # 问题记录
        self.issues = defaultdict(list)
        
    def is_sec_url(self, url: str) -> bool:
        """检查是否是SEC的URL"""
        if not url:
            return False
        return 'sec.gov' in url.lower() or url.startswith('http://') or url.startswith('https://')
    
    def is_local_relative_path(self, path: str) -> bool:
        """检查是否是本地相对路径"""
        if not path:
            return False
        # 应该是 ./imageXX.png 或 imageXX.png 格式
        return (path.startswith('./') or not path.startswith(('http://', 'https://', '/'))) and \
               ('image' in path.lower() or path.endswith(('.png', '.jpg', '.jpeg', '.gif')))
    
    def check_html_file(self, html_path: Path) -> Dict:
        """检查单个HTML文件"""
        result = {
            'path': str(html_path.relative_to(self.storage_root)),
            'img_count': 0,
            'rewritten': 0,
            'not_rewritten': 0,
            'sec_urls': [],
            'local_paths': [],
            'other_urls': []
        }
        
        try:
            with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # 使用 BeautifulSoup 解析
            soup = BeautifulSoup(content, 'html.parser')
            img_tags = soup.find_all('img')
            
            result['img_count'] = len(img_tags)
            
            for img in img_tags:
                src = img.get('src', '')
                
                if not src:
                    continue
                
                if self.is_sec_url(src):
                    # 未重写，仍然是SEC URL
                    result['not_rewritten'] += 1
                    result['sec_urls'].append(src)
                    self.stats['not_rewritten'] += 1
                elif self.is_local_relative_path(src):
                    # 已重写为本地相对路径
                    result['rewritten'] += 1
                    result['local_paths'].append(src)
                    self.stats['rewritten_correctly'] += 1
                else:
                    # 其他格式（可能是data:, 或其他）
                    result['other_urls'].append(src)
            
            self.stats['total_img_tags'] += result['img_count']
            if result['img_count'] > 0:
                self.stats['files_with_images'] += 1
            
            return result
            
        except Exception as e:
            result['error'] = str(e)
            self.stats['errors'] += 1
            return result
    
    def scan_html_files(self, exchange: str = None, company: str = None, sample_size: int = None) -> List[Path]:
        """扫描HTML文件"""
        print(f"📁 扫描HTML文件...")
        
        if not self.storage_root.exists():
            print(f"⚠️  存储目录不存在: {self.storage_root}")
            return []
        
        html_files = []
        
        # 遍历目录结构
        for exchange_dir in self.storage_root.iterdir():
            if not exchange_dir.is_dir():
                continue
            
            # 如果指定了交易所，跳过其他交易所
            if exchange and exchange_dir.name != exchange:
                continue
            
            for company_dir in exchange_dir.iterdir():
                if not company_dir.is_dir():
                    continue
                
                # 如果指定了公司，跳过其他公司
                if company and company_dir.name.upper() != company.upper():
                    continue
                
                # 查找所有HTML文件
                for html_file in company_dir.rglob('*.html'):
                    html_files.append(html_file)
                for htm_file in company_dir.rglob('*.htm'):
                    html_files.append(htm_file)
        
        # 如果指定了抽样大小
        if sample_size and len(html_files) > sample_size:
            html_files = random.sample(html_files, sample_size)
        
        print(f"✅ 找到 {len(html_files)} 个HTML文件")
        return html_files
    
    def run_test(self, exchange: str = None, company: str = None, sample_size: int = None):
        """运行测试"""
        print("\n" + "=" * 100)
        print("🧪 HTML图片链接重写测试")
        print("=" * 100 + "\n")
        
        # 扫描HTML文件
        html_files = self.scan_html_files(exchange, company, sample_size)
        
        if not html_files:
            print("❌ 没有找到HTML文件")
            return
        
        self.stats['total_files'] = len(html_files)
        
        print(f"\n开始检查 {len(html_files)} 个HTML文件...\n")
        
        # 检查每个文件
        problem_files = []
        
        for i, html_path in enumerate(html_files, 1):
            if i % 100 == 0 or self.verbose:
                print(f"  进度: {i}/{len(html_files)}")
            
            result = self.check_html_file(html_path)
            
            # 记录有问题的文件
            if result['not_rewritten'] > 0:
                problem_files.append(result)
                self.issues['not_rewritten'].append(result)
            
            if 'error' in result:
                self.issues['errors'].append(result)
            
            # 如果是verbose模式，显示详细信息
            if self.verbose and result['img_count'] > 0:
                print(f"\n文件: {result['path']}")
                print(f"  图片总数: {result['img_count']}")
                print(f"  已重写: {result['rewritten']}")
                print(f"  未重写: {result['not_rewritten']}")
                
                if result['sec_urls']:
                    print(f"  未重写的SEC URL示例:")
                    for url in result['sec_urls'][:3]:
                        print(f"    - {url}")
        
        # 打印测试报告
        self.print_report(problem_files)
    
    def print_report(self, problem_files: List[Dict]):
        """打印测试报告"""
        print("\n" + "=" * 100)
        print("📊 测试报告")
        print("=" * 100 + "\n")
        
        print("【总体统计】")
        print(f"  测试文件数: {self.stats['total_files']:,}")
        print(f"  包含图片的文件: {self.stats['files_with_images']:,}")
        print(f"  图片标签总数: {self.stats['total_img_tags']:,}")
        print(f"  已正确重写: {self.stats['rewritten_correctly']:,}")
        print(f"  未重写（仍是SEC URL）: {self.stats['not_rewritten']:,}")
        print(f"  处理错误: {self.stats['errors']:,}")
        
        # 计算重写率
        if self.stats['total_img_tags'] > 0:
            rewrite_rate = (self.stats['rewritten_correctly'] / self.stats['total_img_tags']) * 100
            print(f"\n  ✨ 重写率: {rewrite_rate:.2f}%")
        
        print("\n" + "-" * 100)
        
        # 如果有问题文件，显示详情
        if problem_files:
            print(f"\n⚠️  发现 {len(problem_files)} 个文件存在未重写的图片链接\n")
            
            print("【问题文件列表】（前20个）")
            for i, result in enumerate(problem_files[:20], 1):
                print(f"\n{i}. 文件: {result['path']}")
                print(f"   图片总数: {result['img_count']}, 未重写: {result['not_rewritten']}")
                
                if result['sec_urls']:
                    print(f"   未重写的URL示例:")
                    for url in result['sec_urls'][:2]:
                        print(f"     - {url}")
            
            if len(problem_files) > 20:
                print(f"\n... 还有 {len(problem_files) - 20} 个问题文件未列出")
        else:
            print("\n✅ 所有HTML文件的图片链接都已正确重写为本地相对路径！")
        
        # 如果有错误
        if self.stats['errors'] > 0:
            print(f"\n⚠️  处理过程中发生 {self.stats['errors']} 个错误")
            print("【错误文件】（前10个）")
            for i, result in enumerate(self.issues['errors'][:10], 1):
                print(f"{i}. {result['path']}: {result.get('error', 'Unknown error')}")
        
        print("\n" + "=" * 100)
        
        # 给出结论
        if self.stats['not_rewritten'] == 0 and self.stats['errors'] == 0:
            print("🎉 测试通过！所有图片链接都已正确重写。")
        elif self.stats['not_rewritten'] > 0:
            print(f"❌ 测试失败：发现 {self.stats['not_rewritten']} 个未重写的图片链接。")
        else:
            print(f"⚠️  测试完成，但有 {self.stats['errors']} 个文件处理错误。")
        
        print("=" * 100 + "\n")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='测试HTML文件中的图片链接重写',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 测试所有HTML文件
  python test_html_image_rewrite.py
  
  # 随机抽样50个文件测试
  python test_html_image_rewrite.py --sample 50
  
  # 只测试NASDAQ交易所
  python test_html_image_rewrite.py --exchange NASDAQ
  
  # 只测试特定公司
  python test_html_image_rewrite.py --company AAPL
  
  # 详细模式
  python test_html_image_rewrite.py --sample 10 --verbose
        """
    )
    
    parser.add_argument(
        '--exchange',
        type=str,
        help='指定交易所（如：NASDAQ, NYSE）'
    )
    
    parser.add_argument(
        '--company',
        type=str,
        help='指定公司ticker（如：AAPL, TSLA）'
    )
    
    parser.add_argument(
        '--sample',
        type=int,
        help='随机抽样的文件数量'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='显示详细信息'
    )
    
    args = parser.parse_args()
    
    # 检查BeautifulSoup是否可用
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("❌ 错误：需要安装 beautifulsoup4")
        print("   运行: pip install beautifulsoup4")
        return 1
    
    # 运行测试
    tester = HTMLImageRewriteTester(verbose=args.verbose)
    tester.run_test(
        exchange=args.exchange,
        company=args.company,
        sample_size=args.sample
    )
    
    # 根据结果返回退出码
    if tester.stats['not_rewritten'] > 0:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

