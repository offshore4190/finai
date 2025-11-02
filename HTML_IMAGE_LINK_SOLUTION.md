# HTML图片链接问题解决方案

## 🔍 问题描述

在浏览器中打开HTML文件时，图片无法显示，链接显示为：
```
file:///private/tmp/filings/NYSE/AB/2024/ab-20231231_g2.jpg
```

这是因为HTML文件中的图片链接是**绝对路径**或**SEC URL**，而不是**相对路径**。

## 📊 问题分析

### 根本原因

下载器服务（`services/downloader.py`）在下载HTML文件后，**没有重写图片链接**：

1. ✅ 图片文件已正确下载到本地
2. ❌ HTML文件中的`<img src=...>`没有被重写为相对路径
3. ❌ 浏览器尝试使用绝对路径或远程URL加载图片失败

### 预期行为

HTML文件中的图片链接应该是：
```html
<img src="./image01.jpg">
<img src="./image02.png">
```

而不是：
```html
<img src="file:///private/tmp/filings/...">
<img src="https://www.sec.gov/Archives/...">
```

## 🛠️ 解决方案

### 方案一：修复现有HTML文件（推荐）

使用 `fix_html_image_links_simple.py` 脚本修复已下载的HTML文件。

#### 步骤1：预览修复（安全）

```bash
cd /Users/hao/Desktop/FINAI/files/filings-etl
source venv/bin/activate

# 预览模式，查看将要修复什么
python fix_html_image_links_simple.py --dry-run --sample 20 --verbose
```

#### 步骤2：小规模测试

```bash
# 先修复少量文件测试
python fix_html_image_links_simple.py --sample 50
```

#### 步骤3：全量修复

```bash
# 修复所有HTML文件
python fix_html_image_links_simple.py

# 或按交易所分批修复
python fix_html_image_links_simple.py --exchange NASDAQ
python fix_html_image_links_simple.py --exchange NYSE
```

#### 特点

- ✅ 不依赖数据库
- ✅ 基于文件系统和命名规则
- ✅ 自动备份原文件（.bak）
- ✅ 支持预览模式
- ✅ 支持抽样测试

### 方案二：修复下载器（长期解决）

修改 `services/downloader.py`，在下载HTML时自动重写图片链接。

#### 需要添加的功能

在 `download_artifact` 方法中，处理HTML时：

```python
# 在保存HTML之前重写图片链接
if artifact.artifact_type == 'html':
    # 解析HTML
    soup = BeautifulSoup(content, 'lxml')
    img_tags = soup.find_all('img')
    
    # 重写每个图片链接
    for seq, img in enumerate(img_tags, 1):
        src = img.get('src', '')
        if src:
            # 构造本地相对路径
            ext = Path(src).suffix or '.jpg'
            local_image_name = f"{html_stem}_image-{seq:03d}{ext}"
            img['src'] = f"./{local_image_name}"
    
    # 保存重写后的HTML
    content = str(soup).encode('utf-8')
```

## 📝 使用示例

### 示例1：快速修复

```bash
# 最简单的使用方式
cd /Users/hao/Desktop/FINAI/files/filings-etl
source venv/bin/activate
python fix_html_image_links_simple.py --sample 100
```

预期输出：
```
====================================================================================================
📊 修复报告
====================================================================================================

【总体统计】
  处理文件数: 100
  修复的文件: 45
  修复的链接: 123
  处理错误: 0

✅ 成功修复 45 个文件
🎉 修复完成！已修复 45 个文件。
   原文件已备份为 .html.bak 或 .htm.bak
====================================================================================================
```

### 示例2：修复特定公司

```bash
# 进入公司目录
cd /private/tmp/filings/NYSE/AB/2024

# 查看HTML文件中的图片链接（修复前）
grep -n "img src" *.html | head -5
```

输出示例：
```
ab-20231231.html:123:<img src="file:///private/tmp/filings/NYSE/AB/2024/ab-20231231_g2.jpg">
```

```bash
# 修复
cd /Users/hao/Desktop/FINAI/files/filings-etl
source venv/bin/activate
python fix_html_image_links_simple.py --exchange NYSE
```

```bash
# 查看修复后的链接
cd /private/tmp/filings/NYSE/AB/2024
grep -n "img src" *.html | head -5
```

输出示例：
```
ab-20231231.html:123:<img src="./ab-20231231_image-001.jpg">
```

### 示例3：验证修复效果

```bash
# 修复后运行测试
python test_html_image_rewrite.py --sample 50
```

预期输出：
```
✨ 重写率: 100.00%
🎉 测试通过！所有图片链接都已正确重写。
```

## 🔧 故障排除

### 问题1：仍然无法显示图片

**可能原因**:
1. 图片文件未下载
2. 图片文件名不匹配
3. 浏览器缓存

**解决方法**:
```bash
# 检查图片文件是否存在
ls -la /private/tmp/filings/NYSE/AB/2024/*.jpg
ls -la /private/tmp/filings/NYSE/AB/2024/*.png

# 清除浏览器缓存后重新打开HTML文件
```

### 问题2：修复后链接仍然错误

**可能原因**: 图片文件命名与HTML文件不匹配

**解决方法**:
```bash
# 使用详细模式查看匹配情况
python fix_html_image_links_simple.py --sample 10 --verbose --dry-run
```

### 问题3：想恢复原始文件

**解决方法**:
```bash
# 查找备份文件
find /private/tmp/filings -name "*.bak"

# 恢复单个文件
cd /private/tmp/filings/NYSE/AB/2024
mv ab-20231231.html.bak ab-20231231.html

# 批量恢复（小心使用）
find /private/tmp/filings -name "*.html.bak" -exec bash -c 'mv "$0" "${0%.bak}"' {} \;
```

## 📊 测试工具

### 1. 测试图片链接重写状态

```bash
python test_html_image_rewrite.py --sample 50
```

### 2. 检查特定文件

```bash
# 在Python中快速检查
python3 << EOF
from bs4 import BeautifulSoup
from pathlib import Path

html_file = Path('/private/tmp/filings/NYSE/AB/2024/ab-20231231.html')
with open(html_file) as f:
    soup = BeautifulSoup(f, 'html.parser')
    
for img in soup.find_all('img'):
    print(f"src: {img.get('src', 'N/A')}")
EOF
```

### 3. 批量检查

```bash
# 查找所有包含file://的HTML文件
grep -r "file:///" /private/tmp/filings --include="*.html" | wc -l

# 查找所有包含sec.gov的HTML文件
grep -r "sec.gov" /private/tmp/filings --include="*.html" | wc -l
```

## 💡 最佳实践

### 1. 修复前后对比

```bash
# 修复前：测试当前状态
python test_html_image_rewrite.py --sample 100 > before_fix.txt

# 执行修复
python fix_html_image_links_simple.py --sample 100

# 修复后：再次测试
python test_html_image_rewrite.py --sample 100 > after_fix.txt

# 对比结果
diff before_fix.txt after_fix.txt
```

### 2. 分批处理

```bash
# 按交易所分批处理，更安全
python fix_html_image_links_simple.py --exchange NASDAQ --dry-run
python fix_html_image_links_simple.py --exchange NASDAQ

python fix_html_image_links_simple.py --exchange NYSE --dry-run
python fix_html_image_links_simple.py --exchange NYSE
```

### 3. 定期检查

```bash
# 添加到crontab或定期任务
# 每周检查一次新下载的文件
python fix_html_image_links_simple.py --sample 200
```

## 🎯 快速命令参考

```bash
# 进入项目目录
cd /Users/hao/Desktop/FINAI/files/filings-etl && source venv/bin/activate

# 预览修复（安全）
python fix_html_image_links_simple.py --dry-run --sample 20 --verbose

# 小规模测试
python fix_html_image_links_simple.py --sample 50

# 全量修复
python fix_html_image_links_simple.py

# 验证修复效果
python test_html_image_rewrite.py --sample 50
```

## 📞 相关文件

- `fix_html_image_links_simple.py` - 修复脚本（简化版，推荐）
- `fix_html_image_links.py` - 修复脚本（数据库版）
- `test_html_image_rewrite.py` - 测试脚本
- `TEST_HTML_IMAGE_REWRITE_GUIDE.md` - 测试指南
- `services/downloader.py` - 下载器服务（需要改进）

---

**最后更新**: 2025-11-01  
**问题追踪**: HTML图片链接使用绝对路径导致浏览器无法显示  
**解决状态**: ✅ 已提供修复脚本和长期解决方案

