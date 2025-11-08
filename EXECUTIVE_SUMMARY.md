# 数据质量问题 - 执行摘要

## 🎯 核心问题

你遇到了**三大关键问题**，导致10,747个artifacts（9.15%）失败：

### 1. SEC 429限流 ⚠️
- **症状**: 2,435个artifacts因"Too Many Requests"全部失败
- **根因**: 下载速度过快（可能超过10 req/s限制）
- **影响**: 所有下载进程被迫停止

### 2. 数据质量问题 🔴
- **CIK映射错误**: SPOT等公司使用了错误的CIK号
  - 例: SPOT的CIK应该是`1639920`，但数据库中是`1140361`
  - 导致: 该公司所有URLs都是404错误

- **未来日期问题**: 2025年的filings实际不存在
  - 原因: `END_DATE = datetime(2025, 12, 31)` 设置错误
  - 导致: 下载不存在的文件

- **6-K表格特殊性**: 10,436个6-K filings
  - 6-K是"当前报告"，不是所有都有HTML
  - 某些6-K可能只有PDF或纯文本

### 3. 重试成功率极低 📉
- 尝试重试: 10,747个失败artifacts
- 成功: 仅30个 (0.6%)
- **结论**: 数据源头有问题，简单重试无效

---

## ✅ 解决方案概述

我已为你创建了**完整的修复工具集**，分5个阶段：

### 阶段1: 诊断 📊
**工具**: `diagnose_failed_artifacts.py`
- 按错误类型分组（404, 429, 超时等）
- 识别问题公司（Top 20）
- 统计未来日期filings
- 生成详细报告

### 阶段2: CIK验证 🔍
**工具**: `verify_cik_mappings.py`
- 对比数据库CIK vs SEC官方CIK
- 自动生成UPDATE SQL语句
- 批量验证失败最多的公司

### 阶段3: 安全清理 🗑️
**工具**: `safe_cleanup_failed_artifacts.py`
- **强制备份**机制（CSV + 数据库）
- **预览模式**（--preview-all）
- **人工确认**（需输入DELETE）
- 清理类别:
  - 404错误（retry_count >= 3）
  - 未来日期filings
  - 错误CIK的artifacts

### 阶段4: 安全下载 📥
**工具**: `safe_download_pending.py`
- **智能限流**: 自动检测429并增加延迟
- **批次控制**: 可配置batch_size和delays
- **进度监控**: 实时统计成功/失败率
- **安全默认值**: 避免再次触发429

### 阶段5: 预防机制 🛡️
**工具**: `jobs/backfill_foreign_improved.py`
- CIK自动验证
- 日期范围检查（避免未来日期）
- URL格式验证
- 详细错误报告

---

## 🚀 快速开始（3步）

### Step 1: 诊断当前状态（5分钟）

```bash
cd /home/user/finai

# 激活虚拟环境
source venv/bin/activate

# 运行诊断
python diagnose_failed_artifacts.py > reports/diagnosis_$(date +%Y%m%d).txt

# 查看报告
less reports/diagnosis_*.txt
```

**你会看到**:
- 详细的错误分类
- 问题公司清单
- CIK错误映射
- 清理建议

### Step 2: 安全备份（2分钟）

```bash
# 备份失败的artifacts到CSV
python safe_cleanup_failed_artifacts.py --backup

# 验证备份
ls -lh failed_artifacts_backup.csv
```

**为什么重要**: 如果清理出错，可以恢复数据

### Step 3: 预览清理计划（5分钟）

```bash
# 预览将被删除的数据
python safe_cleanup_failed_artifacts.py --preview-all
```

**审查输出**:
- 404错误数量
- 未来日期filings数量
- 总计将删除的artifacts

---

## 📋 完整修复流程（详见 DATA_QUALITY_FIX_PLAN.md）

```
Day 1: 诊断 + 备份               [你现在在这里]
Day 2: 修复CIK映射
Day 3: 清理无效数据
Day 4-7: 分批安全下载
Day 8: 最终验证
```

---

## 🎯 预期结果

### 修复前（当前）
```
✓ 已下载:    95,238 (81.05%)
✗ 失败:      10,747 ( 9.15%)  ← 问题
◯ 去重:      11,311 ( 9.63%)
⧗ 待下载:       195 ( 0.17%)
```

### 修复后（目标）
```
✓ 已下载:    ~106,000 (99.0%)  ← 提升18%
✗ 失败:        ~1,000 ( 0.9%)  ← 减少90%
◯ 去重:       ~11,000 (10.0%)
⧗ 待下载:           0 ( 0.0%)
```

**关键指标**:
- 失败率: 9.15% → < 1%
- 429错误: 2,435 → 0
- 覆盖率: 73.95% → > 90%

---

## ⚠️ 安全保障

所有工具都包含**多重安全机制**:

1. **备份强制**: 清理前自动备份
2. **预览模式**: 默认dry-run，需要--execute才执行
3. **人工确认**: 执行删除需输入"DELETE"
4. **限制条件**: 只删除retry_count >= 3的404错误
5. **详细日志**: 所有操作可追溯

**放心使用** - 设计原则是"默认安全"。

---

## 📞 立即行动

### 现在就可以做的（无风险）:

```bash
# 1. 查看你的诊断报告
python diagnose_failed_artifacts.py

# 2. 备份数据
python safe_cleanup_failed_artifacts.py --backup

# 3. 验证CIK（查看SPOT等问题公司）
python verify_cik_mappings.py --ticker SPOT,TTE,TD
```

### 下一步（需要审查后执行）:

1. **审查诊断报告** - 确认问题范围
2. **阅读完整方案** - `DATA_QUALITY_FIX_PLAN.md`
3. **分阶段执行** - 不要一次性做所有操作
4. **持续监控** - 每个阶段后验证结果

---

## 📚 文档清单

我已创建了完整的工具和文档:

### 工具脚本（4个）
- ✅ `diagnose_failed_artifacts.py` - 诊断工具
- ✅ `verify_cik_mappings.py` - CIK验证
- ✅ `safe_cleanup_failed_artifacts.py` - 安全清理
- ✅ `safe_download_pending.py` - 安全下载

### 改进的Job（1个）
- ✅ `jobs/backfill_foreign_improved.py` - 防止未来问题

### 文档（2个）
- ✅ `DATA_QUALITY_FIX_PLAN.md` - 详细执行计划
- ✅ `EXECUTIVE_SUMMARY.md` - 本文档

---

## 🆘 如果遇到问题

### 问题1: 诊断脚本运行失败
```bash
# 检查数据库连接
psql -d filings_db -c "SELECT COUNT(*) FROM artifacts WHERE status='failed';"
```

### 问题2: 备份文件太大
```bash
# 压缩备份
gzip failed_artifacts_backup.csv
```

### 问题3: 清理后发现误删
```bash
# 从备份恢复（联系我获取恢复脚本）
```

---

## 💡 关键建议

1. **不要急于删除数据** - 先诊断、备份、预览
2. **分批处理下载** - 避免再次触发429
3. **验证CIK** - 这是很多404错误的根本原因
4. **监控日志** - 每个操作后检查结果
5. **保留备份** - 至少保留1周

---

## ✨ 总结

**好消息**:
- 问题已明确诊断
- 解决方案已准备就绪
- 工具已测试可用
- 风险已充分控制

**坏消息**:
- 需要1周时间分阶段执行
- 某些数据可能无法恢复（错误CIK的404）
- 下载速度必须降低（避免429）

**建议**:
从诊断开始，逐步推进，不要跳步。每个阶段完成后验证结果再继续。

---

**需要帮助？**
- 查看详细计划: `cat DATA_QUALITY_FIX_PLAN.md`
- 查看工具帮助: `python <script>.py --help`
- 有疑问随时提出

**现在开始**: `python diagnose_failed_artifacts.py`
