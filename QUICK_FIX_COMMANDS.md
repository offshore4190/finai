# 快速修复命令参考

## 🎯 一键命令

### 最简单的方式（推荐新手）

```bash
cd /Users/hao/Desktop/FINAI/files/filings-etl

# 1️⃣ 预览NASDAQ（查看将要修复什么，完全安全）
make fix-nasdaq-preview

# 2️⃣ 修复NASDAQ
make fix-nasdaq

# 3️⃣ 验证效果
make test-html-links
```

### 修复NYSE

```bash
# 预览
make fix-nyse-preview

# 修复
make fix-nyse

# 验证
make test-html-links
```

### 一键修复所有交易所

```bash
make fix-all-exchanges
```

## 📋 完整命令列表

| 命令 | 功能 | 安全性 |
|------|------|--------|
| `make fix-nasdaq-preview` | 预览NASDAQ | ✅ 安全 |
| `make fix-nasdaq` | 修复NASDAQ | ✅ 有备份 |
| `make fix-nyse-preview` | 预览NYSE | ✅ 安全 |
| `make fix-nyse` | 修复NYSE | ✅ 有备份 |
| `make fix-all-exchanges` | 修复所有 | ✅ 有备份 |
| `make test-html-links` | 测试状态 | ✅ 安全 |

## 🚀 推荐流程

### 新手流程（分步验证）

```bash
# Step 1: 预览NASDAQ
make fix-nasdaq-preview

# Step 2: 看起来没问题？修复！
make fix-nasdaq

# Step 3: 测试验证
make test-html-links

# Step 4: 满意？继续NYSE
make fix-nyse

# Step 5: 最终测试
make test-html-links
```

### 高级用户流程（快速）

```bash
# 一次修复所有
make fix-all-exchanges

# 验证
make test-html-links
```

## 🔍 查看详细信息

```bash
# 查看所有可用命令
make help

# 查看完整指南
cat BATCH_FIX_GUIDE.md

# 查看RPID测试报告
cat RPID_FIX_REPORT.md
```

## ⚡ 直接使用Python脚本

### 预览模式

```bash
source venv/bin/activate

# NASDAQ预览（详细）
python batch_fix_html_by_exchange.py --exchange NASDAQ --dry-run --verbose

# NYSE预览
python batch_fix_html_by_exchange.py --exchange NYSE --dry-run --verbose
```

### 实际修复

```bash
# 修复NASDAQ
python batch_fix_html_by_exchange.py --exchange NASDAQ

# 修复NYSE  
python batch_fix_html_by_exchange.py --exchange NYSE

# 修复所有
python batch_fix_html_by_exchange.py --all
```

## 🔄 恢复原文件

如果需要撤销修复：

```bash
# 恢复单个文件
cd /private/tmp/filings/NASDAQ/AAPL/2023
mv file.html.bak file.html

# 批量恢复NASDAQ所有文件
find /private/tmp/filings/NASDAQ -name "*.bak" -exec bash -c 'mv "$0" "${0%.bak}"' {} \;

# 批量恢复NYSE所有文件
find /private/tmp/filings/NYSE -name "*.bak" -exec bash -c 'mv "$0" "${0%.bak}"' {} \;
```

## 📊 预期结果

### 成功的输出示例

```
✅ 修复完成！
   ✅ 共修复 456 个文件，678 个图片链接
   ⏱️  总耗时: 45.23秒
   💾 原文件已备份为 .bak
```

### 修复前后对比

**修复前** ❌:
```html
<img src="rmb-20250331_g1.jpg">
```

**修复后** ✅:
```html
<img src="./RPID_2025_Q1_09-05-2025_image-001.jpg">
```

## 🎉 下一步

修复完成后：

1. **浏览器测试**: 打开HTML文件查看图片是否正常显示
2. **运行测试**: `make test-html-links`
3. **查看报告**: 检查修复率是否达到100%

---

**快速开始**: `make fix-nasdaq-preview`  
**完整文档**: `BATCH_FIX_GUIDE.md`  
**帮助命令**: `make help`

