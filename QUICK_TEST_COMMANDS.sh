#!/bin/bash
# HTML图片链接重写测试 - 快速命令参考
# 运行前请确保已激活虚拟环境: source venv/bin/activate

echo "======================================"
echo "HTML图片链接重写测试 - 快速命令"
echo "======================================"
echo ""

# 进入项目目录
cd /Users/hao/Desktop/FINAI/files/filings-etl

# 激活虚拟环境
source venv/bin/activate

# ==========================================
# 基础测试命令
# ==========================================

echo "1️⃣  快速测试（推荐）- 抽样50个文件"
echo "   命令: python test_html_image_rewrite.py --sample 50"
echo ""
python test_html_image_rewrite.py --sample 50

echo ""
echo "=========================================="
echo ""

# ==========================================
# 其他可用命令
# ==========================================

echo "📚 其他可用命令："
echo ""
echo "2️⃣  详细测试 - 查看每个文件的详情"
echo "   python test_html_image_rewrite.py --sample 20 --verbose"
echo ""

echo "3️⃣  按交易所测试"
echo "   python test_html_image_rewrite.py --exchange NASDAQ"
echo "   python test_html_image_rewrite.py --exchange NYSE"
echo ""

echo "4️⃣  测试特定公司"
echo "   python test_html_image_rewrite.py --company AAPL"
echo "   python test_html_image_rewrite.py --company TSLA"
echo ""

echo "5️⃣  小规模快速测试"
echo "   python test_html_image_rewrite.py --sample 10"
echo ""

echo "6️⃣  中等规模测试"
echo "   python test_html_image_rewrite.py --sample 100"
echo ""

echo "7️⃣  全量测试（耗时较长）"
echo "   python test_html_image_rewrite.py"
echo ""

echo "=========================================="
echo "✅ 测试完成！"
echo "=========================================="

