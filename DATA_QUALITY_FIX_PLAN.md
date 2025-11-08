# 数据质量修复完整方案

## 📊 当前状态总结

```
总Artifacts:        117,508
✓ 已下载:           95,238  (81.05%)
◯ 已跳过(去重):     11,311  ( 9.63%)
✗ 失败:             10,747  ( 9.15%) ← 问题焦点
⧗ 待下载:              195  ( 0.17%)
⟳ 下载中:               17  ( 0.01%)
```

## 🔍 问题根因分析

### 问题1: SEC 429限流 (2,435失败)
**原因**: 下载速度过快，触发SEC保护机制
- SEC限制: 10 requests/second
- 实际峰值: 可能达到15-20 req/s
- 影响: 所有pending downloads暂停

### 问题2: 数据质量问题 (10,747失败)
**根本原因**:
1. **错误的CIK映射** (例: SPOT)
   - 数据库CIK: 1140361
   - 正确CIK: 1639920
   - 影响: 所有该公司的URLs无效

2. **未来日期filings** (2025年)
   - 原因: 日期范围设置错误
   - 影响: 下载不存在的文件

3. **6-K表格特殊性**
   - 10,436个6-K filings
   - 6-K不是标准季报
   - 可能不是所有6-K都包含HTML

### 问题3: 0.6%成功率
- 尝试重试: 10,747个artifacts
- 成功: 30个 (0.6%)
- **结论**: 数据源头有问题，重试无效

---

## 🛠️ 修复方案（5步走）

### ✅ Step 1: 诊断当前状态（30分钟）

```bash
# 1.1 运行完整诊断
python diagnose_failed_artifacts.py > reports/failed_artifacts_report.txt

# 1.2 验证CIK映射
python verify_cik_mappings.py --batch --limit 50 > reports/cik_verification_report.txt

# 1.3 查看报告
cat reports/failed_artifacts_report.txt
cat reports/cik_verification_report.txt
```

**预期输出**:
- 按错误类型分组统计
- Top 20问题公司列表
- CIK错误映射清单
- 未来日期filings统计

---

### ✅ Step 2: 安全备份（15分钟）

```bash
# 2.1 备份失败的artifacts到CSV
python safe_cleanup_failed_artifacts.py --backup

# 验证备份
ls -lh failed_artifacts_backup.csv
wc -l failed_artifacts_backup.csv  # 应该是10,747 + 1(header)

# 2.2 数据库备份（可选但推荐）
pg_dump -h localhost -U postgres -d filings_db \
  -t artifacts -t filings -t companies \
  > backups/db_backup_$(date +%Y%m%d_%H%M%S).sql
```

---

### ✅ Step 3: 修复CIK映射（1-2小时）

#### 3.1 生成CIK更新SQL

```bash
# 运行CIK验证，获取UPDATE语句
python verify_cik_mappings.py --batch --limit 100 > cik_fix.sql

# 编辑cik_fix.sql，只保留UPDATE语句部分
```

#### 3.2 人工审查并执行

```bash
# 审查SQL（确保安全）
cat cik_fix.sql

# 执行更新
psql -d filings_db -f cik_fix.sql

# 验证更新
psql -d filings_db -c "
SELECT ticker, cik, updated_at
FROM companies
WHERE ticker IN ('SPOT', 'TTE', 'TD')
ORDER BY ticker;
"
```

#### 3.3 删除错误CIK的失败artifacts

```sql
-- 在psql中执行（示例：SPOT的旧CIK）
BEGIN;

-- 找出错误CIK的公司ID
WITH wrong_cik_companies AS (
  SELECT id FROM companies
  WHERE ticker = 'SPOT' AND cik = '1140361'
)
-- 删除该公司的失败artifacts
DELETE FROM artifacts
WHERE filing_id IN (
  SELECT id FROM filings
  WHERE company_id IN (SELECT id FROM wrong_cik_companies)
)
AND status = 'failed';

COMMIT;
```

---

### ✅ Step 4: 清理无效数据（30分钟）

#### 4.1 预览清理计划

```bash
# 预览所有将被删除的数据
python safe_cleanup_failed_artifacts.py --preview-all
```

**审查输出**:
- 404错误: ~X,XXX artifacts
- 未来日期: ~X,XXX artifacts
- 总计: ~X,XXX artifacts

#### 4.2 执行清理

```bash
# 执行清理（需要输入DELETE确认）
python safe_cleanup_failed_artifacts.py --execute --clean-404 --clean-future

# 验证结果
psql -d filings_db -c "
SELECT status, COUNT(*)
FROM artifacts
GROUP BY status
ORDER BY COUNT(*) DESC;
"
```

**预期结果**:
- Failed artifacts: 从10,747降至~2,000-3,000
- 剩余的失败主要是429错误（可重试）

---

### ✅ Step 5: 安全重新下载（分批进行，2-4天）

#### 5.1 保守策略测试

```bash
# 小批量测试（50个artifacts）
python safe_download_pending.py \
  --batch-size 5 \
  --batch-delay 3.0 \
  --download-delay 0.2 \
  --limit 50

# 监控日志，检查是否有429错误
tail -f logs/download.log | grep -i "429\|rate"
```

#### 5.2 逐步扩大规模

```bash
# 如果测试成功，增加到200个
python safe_download_pending.py \
  --batch-size 10 \
  --batch-delay 2.0 \
  --limit 200

# 继续监控
tail -f logs/download.log
```

#### 5.3 分交易所下载

```bash
# NASDAQ (分天进行)
nohup python safe_download_pending.py \
  --exchange NASDAQ \
  --batch-size 10 \
  --batch-delay 2.0 \
  --limit 1000 \
  > logs/nasdaq_download_$(date +%Y%m%d).log 2>&1 &

# 第二天：NYSE
nohup python safe_download_pending.py \
  --exchange NYSE \
  --batch-size 10 \
  --batch-delay 2.0 \
  --limit 1000 \
  > logs/nyse_download_$(date +%Y%m%d).log 2>&1 &
```

#### 5.4 处理429错误的artifacts

```bash
# 等待24小时后，重试之前429错误的artifacts
python safe_download_pending.py \
  --no-skip-429 \
  --batch-size 5 \
  --batch-delay 5.0 \
  --download-delay 0.3 \
  --limit 500
```

---

## 📈 监控与验证

### 每日检查清单

```bash
# 1. 检查artifacts状态分布
psql -d filings_db -c "
SELECT status, COUNT(*) as count,
       ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as pct
FROM artifacts
GROUP BY status
ORDER BY count DESC;
"

# 2. 检查429错误数量
psql -d filings_db -c "
SELECT COUNT(*) as rate_limit_errors
FROM artifacts
WHERE status = 'failed'
  AND error_message LIKE '%429%';
"

# 3. 检查覆盖率
python diagnose_coverage.py
```

### 下载速度建议

| 场景 | batch_size | batch_delay | download_delay | 预期速度 |
|------|------------|-------------|----------------|----------|
| 保守（推荐） | 5 | 3.0s | 0.2s | ~150/小时 |
| 适中 | 10 | 2.0s | 0.15s | ~250/小时 |
| 激进（有风险） | 20 | 1.0s | 0.1s | ~450/小时 |

**计算方法**:
- 每批时间 = batch_size × download_delay + batch_delay
- 每小时批次 = 3600 / 每批时间
- 每小时artifacts = 每小时批次 × batch_size

---

## 🚨 风险缓解

### Risk 1: 误删有效数据
**缓解措施**:
- ✅ 强制备份（CSV + SQL）
- ✅ 预览机制（--preview-all）
- ✅ 确认机制（需输入DELETE）
- ✅ 只删除retry_count >= 3的404错误

### Risk 2: 继续触发429
**缓解措施**:
- ✅ 保守的默认参数
- ✅ 自动增加延迟（检测到429后）
- ✅ 批次限制（每次最多处理有限数量）
- ✅ skip_429选项（默认跳过之前429错误）

### Risk 3: CIK更新影响现有数据
**缓解措施**:
- ✅ 只更新companies表
- ✅ 保留原有filings和artifacts
- ✅ 可以通过updated_at字段追踪变更
- ✅ 数据库备份可恢复

---

## 📝 执行时间线（建议）

### Day 1: 诊断与备份
- [x] 运行诊断脚本（30分钟）
- [x] 备份数据（15分钟）
- [ ] 审查报告，制定详细计划（1小时）

### Day 2: 修复CIK
- [ ] 验证CIK映射（1小时）
- [ ] 生成并审查UPDATE SQL（30分钟）
- [ ] 执行CIK更新（15分钟）
- [ ] 删除错误CIK的artifacts（15分钟）

### Day 3: 清理无效数据
- [ ] 预览清理计划（15分钟）
- [ ] 执行清理（15分钟）
- [ ] 验证结果（30分钟）

### Day 4-7: 分批下载
- [ ] Day 4: 测试下载（50-200 artifacts）
- [ ] Day 5: NASDAQ下载（~1,000）
- [ ] Day 6: NYSE下载（~1,000）
- [ ] Day 7: 处理剩余和429错误

### Day 8: 最终验证
- [ ] 运行完整诊断
- [ ] 生成覆盖率报告
- [ ] 文档更新

---

## ✅ 成功标准

完成后应该达到:

1. **失败率 < 2%**
   ```sql
   SELECT
     ROUND(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as fail_rate
   FROM artifacts;
   ```
   目标: < 2.0%

2. **429错误 = 0**
   ```sql
   SELECT COUNT(*) FROM artifacts WHERE error_message LIKE '%429%';
   ```
   目标: 0

3. **覆盖率 > 90%**
   ```sql
   SELECT
     COUNT(DISTINCT c.id) as companies_with_filings,
     (SELECT COUNT(*) FROM companies WHERE status='active') as total_companies
   FROM companies c
   JOIN filings f ON f.company_id = c.id
   WHERE c.status = 'active';
   ```
   目标: > 90%

---

## 🔧 工具清单

所有工具已创建并可用:

1. ✅ `diagnose_failed_artifacts.py` - 失败artifacts诊断
2. ✅ `verify_cik_mappings.py` - CIK验证工具
3. ✅ `safe_cleanup_failed_artifacts.py` - 安全清理工具
4. ✅ `safe_download_pending.py` - 安全下载工具

---

## 📞 支持与问题排查

### 常见问题

**Q: 清理后发现误删了有效数据怎么办？**
A: 从CSV备份恢复：
```python
# 创建恢复脚本
import csv
from config.db import get_db_session
from models import Artifact

with open('failed_artifacts_backup.csv') as f:
    reader = csv.DictReader(f)
    # ... 恢复逻辑
```

**Q: 429错误仍然频繁出现怎么办？**
A: 进一步降低速度：
```bash
python safe_download_pending.py \
  --batch-size 3 \
  --batch-delay 5.0 \
  --download-delay 0.5
```

**Q: 如何验证CIK是否正确？**
A: 手动访问SEC网站：
```
https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={CIK}&type=&dateb=&owner=exclude&count=40
```

---

## 📊 预期最终状态

```
总Artifacts:        ~107,000 (清理后)
✓ 已下载:           ~95,000 (88.8%)
◯ 已跳过(去重):     ~11,000 (10.3%)
✗ 失败:             ~1,000  ( 0.9%) ← 可接受范围
⧗ 待下载:               0   ( 0.0%)
```

成功率: **~99%** (vs 当前 81%)

---

## 🎯 立即行动

**现在就可以开始**:

```bash
# Step 1: 诊断
python diagnose_failed_artifacts.py

# Step 2: 备份
python safe_cleanup_failed_artifacts.py --backup

# Step 3: 验证CIK（查看问题公司）
python verify_cik_mappings.py --ticker SPOT,TTE,TD

# 等待人工审查报告后，继续执行后续步骤
```

---

**重要**: 每个步骤执行前请仔细审查输出，确保理解将要执行的操作。有疑问随时停止并咨询。
