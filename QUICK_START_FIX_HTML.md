# 🚀 HTML图片链接修复 - 快速开始

## 问题描述

HTML文件中的图片显示为：`file:///private/tmp/filings/...` 而不是相对路径。

## 一键修复

```bash
cd /Users/hao/Desktop/FINAI/files/filings-etl

# 1️⃣ 预览（安全，不修改文件）
make fix-html-preview

# 2️⃣ 测试修复50个文件
make fix-html-test

# 3️⃣ 验证修复效果
make test-html-links

# 4️⃣ 修复所有文件（需要确认）
make fix-html-all
```

## 详细步骤

### 步骤1：预览将要修复什么

```bash
make fix-html-preview
```

输出示例：
```
✅ 成功修复 2 个文件

1. NYSE/AGO/2025/AGO_2025_Q1_08-08-2025.html
   ago-20250630_g1.jpg → ./AGO_2025_Q1_08-08-2025_image-001.jpg
```

### 步骤2：小规模测试

```bash
make fix-html-test
```

这会修复50个文件，原文件自动备份为 `.bak`

### 步骤3：验证效果

```bash
make test-html-links
```

预期输出：
```
✨ 重写率: 100.00%
🎉 测试通过！所有图片链接都已正确重写。
```

### 步骤4：全量修复

```bash
make fix-html-all
```

系统会要求确认，输入 `y` 继续。

## 命令说明

| 命令 | 作用 | 是否安全 | 修改文件 |
|------|------|---------|---------|
| `make fix-html-preview` | 预览将要修复什么 | ✅ 完全安全 | ❌ 不修改 |
| `make fix-html-test` | 测试修复50个文件 | ✅ 创建备份 | ✅ 修改 |
| `make test-html-links` | 测试链接状态 | ✅ 完全安全 | ❌ 不修改 |
| `make fix-html-all` | 修复所有文件 | ✅ 创建备份 | ✅ 修改 |

## 恢复原文件

如果需要恢复：

```bash
# 查找备份文件
find /private/tmp/filings -name "*.html.bak" | head -10

# 恢复单个文件
cd /private/tmp/filings/NYSE/AB/2024
mv ab-20231231.html.bak ab-20231231.html
```

## 验证修复效果

### 方法1：使用测试工具

```bash
make test-html-links
```

### 方法2：手动检查

```bash
# 查看HTML文件中的图片链接
cd /private/tmp/filings/NYSE/AB/2024
grep "img src" *.html | head -5
```

修复前：
```html
<img src="file:///private/tmp/filings/NYSE/AB/2024/ab-20231231_g2.jpg">
```

修复后：
```html
<img src="./ab-20231231_image-001.jpg">
```

### 方法3：浏览器测试

打开任意HTML文件，检查图片是否正常显示。

## 数据库连接说明

### ✅ 当前状态

PostgreSQL容器正在运行：
```bash
docker ps | grep postgres
# filings_postgres   Up 17 minutes (healthy)
```

### 💡 简化版脚本优势

当前使用的 `fix_html_image_links_simple.py`：
- ✅ **不需要数据库连接**
- ✅ 基于文件系统和命名规则
- ✅ 更快、更简单
- ✅ 已验证可用

### 🔧 如果需要数据库操作

```bash
# 启动数据库（如果未运行）
make docker-up

# 查看所有可用命令
make help

# 运行其他需要数据库的命令
make diagnose
make compliance
```

## 常见问题

### Q1: 修复后图片仍然无法显示？

**A**: 检查：
1. 图片文件是否存在
   ```bash
   ls -la /private/tmp/filings/NYSE/AB/2024/*.jpg
   ```
2. 清除浏览器缓存后重新打开HTML

### Q2: 想要更改修复的文件数量？

**A**: 直接运行Python脚本：
```bash
source venv/bin/activate
python fix_html_image_links_simple.py --sample 100
```

### Q3: 可以只修复特定交易所吗？

**A**: 可以：
```bash
source venv/bin/activate
python fix_html_image_links_simple.py --exchange NASDAQ
python fix_html_image_links_simple.py --exchange NYSE
```

### Q4: 如何查看详细的修复过程？

**A**: 使用详细模式：
```bash
source venv/bin/activate
python fix_html_image_links_simple.py --sample 20 --verbose
```

## 进度追踪

- [x] 问题诊断：HTML图片链接使用绝对路径
- [x] 解决方案：创建修复脚本
- [x] 预览测试：验证修复逻辑
- [ ] 小规模修复：50个文件
- [ ] 验证效果：测试链接状态
- [ ] 全量修复：所有HTML文件

## 下一步

1. **现在就试试**：`make fix-html-preview`
2. **测试修复**：`make fix-html-test`
3. **验证效果**：`make test-html-links`
4. **全量修复**：`make fix-html-all`

---

**创建时间**：2025-11-01  
**状态**：✅ 工具就绪，数据库运行正常  
**建议操作**：立即运行 `make fix-html-preview` 开始修复

