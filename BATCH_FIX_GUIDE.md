# 批量修复HTML图片链接指南

## 🎯 功能说明

批量修复工具可以按交易所分组处理HTML文件，支持：
- ✅ **NASDAQ** - 纳斯达克
- ✅ **NYSE** - 纽约证券交易所
- ✅ **NYSE American** - 纽交所美国交易所
- ✅ **NYSE Arca** - 纽交所Arca交易所

## 🚀 快速开始

### 方法1：使用Makefile（推荐）

```bash
cd /Users/hao/Desktop/FINAI/files/filings-etl

# 1. 预览NASDAQ的修复（安全）
make fix-nasdaq-preview

# 2. 修复NASDAQ
make fix-nasdaq

# 3. 预览NYSE的修复
make fix-nyse-preview

# 4. 修复NYSE
make fix-nyse

# 5. 修复所有交易所（需要确认）
make fix-all-exchanges
```

### 方法2：直接使用Python脚本

```bash
cd /Users/hao/Desktop/FINAI/files/filings-etl
source venv/bin/activate

# 预览模式（安全）
python batch_fix_html_by_exchange.py --exchange NASDAQ --dry-run --verbose
python batch_fix_html_by_exchange.py --exchange NYSE --dry-run --verbose

# 实际修复
python batch_fix_html_by_exchange.py --exchange NASDAQ
python batch_fix_html_by_exchange.py --exchange NYSE

# 修复所有交易所
python batch_fix_html_by_exchange.py --all
```

### 方法3：使用Shell脚本（一键修复所有）

```bash
cd /Users/hao/Desktop/FINAI/files/filings-etl
./batch_fix_all_exchanges.sh
```

## 📊 命令详解

### Makefile命令

| 命令 | 功能 | 是否安全 | 修改文件 |
|------|------|---------|---------|
| `make fix-nasdaq-preview` | 预览NASDAQ修复 | ✅ 完全安全 | ❌ 不修改 |
| `make fix-nasdaq` | 修复NASDAQ | ✅ 创建备份 | ✅ 修改 |
| `make fix-nyse-preview` | 预览NYSE修复 | ✅ 完全安全 | ❌ 不修改 |
| `make fix-nyse` | 修复NYSE | ✅ 创建备份 | ✅ 修改 |
| `make fix-all-exchanges` | 修复所有交易所 | ✅ 创建备份 | ✅ 修改 |
| `make test-html-links` | 测试修复效果 | ✅ 完全安全 | ❌ 不修改 |

### Python脚本参数

```bash
python batch_fix_html_by_exchange.py [选项]

选项：
  --exchange EXCHANGE    指定交易所: NASDAQ, NYSE, NYSE American, NYSE Arca
  --all                  处理所有交易所
  --dry-run              预览模式，不实际修改文件
  --verbose              显示详细信息
  -h, --help             显示帮助信息
```

## 📈 预期输出示例

### NASDAQ修复示例

```
================================================================================
📊 处理交易所: NASDAQ
================================================================================
找到 1,234 个HTML文件
  进度: 100/1234 (8.1%)
  进度: 200/1234 (16.2%)
  ...

【NASDAQ 统计】
  处理文件: 1,234
  修复文件: 456
  修复链接: 678
  错误数量: 0
  处理时间: 45.23秒
```

### 总体报告示例

```
================================================================================
📊 总体修复报告
================================================================================

【按交易所统计】

交易所          处理文件      修复文件      修复链接      错误      时间      
--------------------------------------------------------------------------------
NASDAQ          1,234        456          678          0        45.23s
NYSE            987          345          567          0        38.56s
NYSE American   123          45           67           0        5.12s
NYSE Arca       89           23           34           0        3.89s
--------------------------------------------------------------------------------
总计            2,433        869          1,346        0        92.80s

修复率: 35.69% (869/2,433)

================================================================================
🎉 修复完成！
   ✅ 共修复 869 个文件，1,346 个图片链接
   ⏱️  总耗时: 92.80秒
   💾 原文件已备份为 .bak
================================================================================
```

## 🔍 修复逻辑

### 文件查找规则

对于每个交易所目录（如 `/private/tmp/filings/NASDAQ/`）：
1. 递归查找所有 `.html` 和 `.htm` 文件
2. 跳过 `.bak` 备份文件
3. 按公司和年份组织

### 图片链接修复规则

对于每个HTML文件：
1. 查找同目录下的图片文件（`.jpg`, `.png`, `.gif`, `.svg`）
2. 匹配规则：图片文件名以HTML文件名开头
3. 修改 `<img src="...">` 为相对路径 `./文件名.jpg`

### 示例

```
HTML文件: NASDAQ/AAPL/2023/AAPL_2023_Q1_01-01-2023.html
图片文件: NASDAQ/AAPL/2023/AAPL_2023_Q1_01-01-2023_image-001.jpg

修复前:
  <img src="aapl-20230101_g1.jpg" ...>

修复后:
  <img src="./AAPL_2023_Q1_01-01-2023_image-001.jpg" ...>
```

## 🛡️ 安全保障

### 1. 自动备份
每个修改的HTML文件都会自动备份为 `.bak`：
```
原文件: AAPL_2023_Q1_01-01-2023.html
备份:   AAPL_2023_Q1_01-01-2023.html.bak
```

### 2. 预览模式
使用 `--dry-run` 可以预览将要修复的内容，不会实际修改文件：
```bash
make fix-nasdaq-preview
make fix-nyse-preview
```

### 3. 错误处理
- 遇到错误不会中断整个流程
- 错误会被记录并在最后报告
- 失败的文件不会被修改

## 📝 使用流程

### 推荐的完整流程

```bash
# 1. 预览NASDAQ（查看将要修复什么）
make fix-nasdaq-preview

# 2. 修复NASDAQ
make fix-nasdaq

# 3. 验证NASDAQ修复效果
python test_html_image_rewrite.py --exchange NASDAQ --sample 50

# 4. 如果满意，继续修复NYSE
make fix-nyse-preview
make fix-nyse

# 5. 验证NYSE
python test_html_image_rewrite.py --exchange NYSE --sample 50

# 6. 最终验证所有交易所
make test-html-links
```

### 一键修复所有（高级用户）

```bash
# 直接修复所有交易所
make fix-all-exchanges

# 或使用shell脚本
./batch_fix_all_exchanges.sh
```

## 🔧 故障排除

### 问题1：修复后图片仍然无法显示

**检查步骤**:
```bash
# 1. 确认图片文件存在
ls -la /private/tmp/filings/NASDAQ/AAPL/2023/*.jpg

# 2. 检查HTML中的链接
grep "img src" /private/tmp/filings/NASDAQ/AAPL/2023/*.html | head -5

# 3. 清除浏览器缓存后重新打开
```

### 问题2：进度很慢

**原因**: 大量文件需要处理

**解决方案**: 分批处理
```bash
# 先处理NASDAQ
make fix-nasdaq

# 等待完成后再处理NYSE
make fix-nyse
```

### 问题3：想要恢复原文件

```bash
# 恢复单个文件
cd /private/tmp/filings/NASDAQ/AAPL/2023
mv AAPL_2023_Q1_01-01-2023.html.bak AAPL_2023_Q1_01-01-2023.html

# 批量恢复NASDAQ
find /private/tmp/filings/NASDAQ -name "*.html.bak" -exec bash -c 'mv "$0" "${0%.bak}"' {} \;

# 批量恢复NYSE
find /private/tmp/filings/NYSE -name "*.html.bak" -exec bash -c 'mv "$0" "${0%.bak}"' {} \;
```

## 📊 性能参考

基于实际测试的预估处理时间：

| 交易所 | 文件数量 | 预计时间 |
|--------|---------|---------|
| NASDAQ | ~1,000 | ~30秒 |
| NYSE | ~800 | ~25秒 |
| NYSE American | ~100 | ~5秒 |
| NYSE Arca | ~80 | ~4秒 |
| **总计** | ~2,000 | ~1分钟 |

*实际时间取决于文件数量和系统性能*

## 🎯 最佳实践

### 1. 分步验证
```bash
# 每修复一个交易所就验证一次
make fix-nasdaq
make test-html-links

make fix-nyse
make test-html-links
```

### 2. 保留备份
```bash
# 备份文件保留7天后再删除
find /private/tmp/filings -name "*.html.bak" -mtime +7 -delete
```

### 3. 定期检查
```bash
# 每周运行一次检查
make test-html-links > weekly_check.log
```

## 🔗 相关命令

```bash
# 查看所有命令
make help

# HTML修复相关
make fix-html-preview      # 预览（20文件）
make fix-html-test         # 测试（50文件）
make fix-nasdaq-preview    # 预览NASDAQ
make fix-nasdaq            # 修复NASDAQ
make fix-nyse-preview      # 预览NYSE
make fix-nyse              # 修复NYSE
make fix-all-exchanges     # 修复所有
make test-html-links       # 测试状态
```

## 📞 相关文件

- `batch_fix_html_by_exchange.py` - 批量修复Python脚本
- `batch_fix_all_exchanges.sh` - 一键修复所有交易所
- `fix_html_image_links_simple.py` - 简化版修复脚本
- `test_html_image_rewrite.py` - 测试脚本
- `Makefile` - 命令定义
- `RPID_FIX_REPORT.md` - RPID测试报告
- `HTML_IMAGE_LINK_SOLUTION.md` - 完整解决方案

---

**创建时间**: 2025-11-01  
**状态**: ✅ 工具就绪，RPID已测试通过  
**建议**: 从NASDAQ开始分步修复

