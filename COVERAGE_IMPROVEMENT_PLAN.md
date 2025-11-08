# Coverage Improvement Plan
提升覆盖率从73.95%到90%+的完整方案

## 📊 当前状态分析

### 总体数据
```
目标公司总数:     5,911
有filings公司:    4,371 (73.95%)
缺失公司:         1,540 (26.05%) ← 改进目标
```

### 按交易所分解
| 交易所 | 总公司数 | 有数据 | 覆盖率 | 缺失 |
|--------|---------|--------|--------|------|
| NASDAQ | 3,347 | 2,715 | 81.12% | 632 |
| NYSE | 2,244 | 1,606 | 71.57% | 638 |
| NYSE American | 262 | 39 | 14.89% | 223 |
| NYSE Arca | 58 | 11 | 18.97% | 47 |

### 待处理任务
- ✅ Pending downloads: 195个HTML文件
- ⚠️ 缺失公司: 1,540家需要分析

---

## 🎯 改进目标

### 目标1: 短期目标（1-2天）
- **处理pending downloads**: 195 → 0
- **覆盖率提升**: 73.95% → 75-76%
- **预期增加**: ~100家公司

### 目标2: 中期目标（1周）
- **识别并处理海外公司**: 估计300-500家
- **修复CIK错误**: 估计50-100家
- **覆盖率提升**: 75% → 85%
- **预期增加**: ~600-800家公司

### 目标3: 长期目标（2周）
- **处理特殊交易所**: NYSE American/Arca
- **处理Recent IPOs**: 调整日期范围
- **覆盖率提升**: 85% → 90%+
- **预期增加**: ~300-400家公司

**最终目标**: 覆盖率 > 90% (5,320+ / 5,911)

---

## 📋 执行计划（分5个阶段）

---

## 阶段1: 处理Pending Downloads（1-2小时）

### 任务1.1: 下载195个pending artifacts

```bash
# 保守策略下载
python safe_download_pending.py \
  --batch-size 10 \
  --batch-delay 2.0 \
  --download-delay 0.15 \
  --limit 200

# 监控进度
tail -f logs/*.log | grep -i "download"
```

**预期结果**:
- 下载成功: ~180-195个
- 失败: < 15个
- 新增公司数据: ~50-100家

### 任务1.2: 验证结果

```bash
# 检查pending状态
psql -d filings_db -c "
SELECT status, COUNT(*)
FROM artifacts
GROUP BY status;
"

# 检查新增公司
psql -d filings_db -c "
SELECT exchange, COUNT(DISTINCT company_id) as companies_with_data
FROM filings
JOIN companies ON filings.company_id = companies.id
WHERE companies.status = 'active'
GROUP BY exchange;
"
```

**完成标准**:
- ✅ Pending artifacts < 10
- ✅ 覆盖率提升至75%+

---

## 阶段2: 诊断缺失公司（2-3小时）

### 任务2.1: 运行诊断工具

```bash
# 采样100家公司分析原因
python diagnose_missing_coverage.py --sample-size 100

# 查看报告
less diagnose_missing_coverage_report.txt
```

**诊断内容**:
- 有多少是海外公司（只有20-F/6-K）
- 有多少是Recent IPOs（2023+上市）
- 有多少是CIK错误
- 有多少是真正无数据（已退市等）

### 任务2.2: 分析结果

预期发现（基于26%缺失）:

| 原因 | 估计数量 | 占比 | 可改进 |
|------|---------|------|--------|
| 海外公司未标记 | 300-500 | 20-32% | ✅ 可修复 |
| Recent IPOs | 200-300 | 13-19% | ✅ 可调整 |
| CIK错误 | 50-100 | 3-6% | ✅ 可修复 |
| NYSE American特殊 | 150-200 | 10-13% | ✅ 需研究 |
| 真正无数据 | 300-400 | 19-26% | ❌ 无法修复 |

### 任务2.3: 导出修复列表

```bash
# 导出需要标记为foreign的公司
python diagnose_missing_coverage.py --export-foreign

# 生成 mark_foreign_companies.sql
```

**完成标准**:
- ✅ 明确1,540家公司的缺失原因分布
- ✅ 生成修复SQL脚本
- ✅ 确定可提升的公司数量

---

## 阶段3: 标记和下载海外公司（2-3天）

### 任务3.1: 批量标记海外公司

```bash
# 审查SQL（重要！）
cat mark_foreign_companies.sql

# 执行标记
psql -d filings_db -f mark_foreign_companies.sql

# 验证
psql -d filings_db -c "
SELECT exchange, is_foreign, COUNT(*)
FROM companies
WHERE status = 'active'
GROUP BY exchange, is_foreign
ORDER BY exchange, is_foreign;
"
```

**预期结果**:
- 标记海外公司: 300-500家
- is_foreign=TRUE 的公司: 从1,300增至1,600-1,800

### 任务3.2: Backfill海外公司数据

```bash
# 使用改进版backfill（带验证）
python -m jobs.backfill_foreign_improved --limit 10  # 测试

# 全量运行（分批）
python -m jobs.backfill_foreign_improved --exchange NASDAQ 2>&1 | tee logs/foreign_nasdaq.log

# 第二天: NYSE
python -m jobs.backfill_foreign_improved --exchange NYSE 2>&1 | tee logs/foreign_nyse.log
```

**预期结果**:
- 新增filings: 3,000-6,000个（20-F + 6-K）
- 新增artifacts: 3,000-6,000个
- 覆盖率提升: 75% → 82-85%

### 任务3.3: 下载artifacts

```bash
# 下载新创建的artifacts（分批）
python safe_download_pending.py \
  --form-types 20-F,6-K \
  --batch-size 10 \
  --batch-delay 2.0 \
  --limit 500

# 每天处理500-1000个
```

**完成标准**:
- ✅ 海外公司覆盖率 > 80%
- ✅ 总体覆盖率 > 82%
- ✅ 新增400-600家公司数据

---

## 阶段4: 修复CIK错误和Recent IPOs（1-2天）

### 任务4.1: 批量验证和修复CIK

```bash
# 验证失败公司的CIK
python verify_cik_mappings.py --batch --limit 200 > cik_fixes.sql

# 审查SQL
cat cik_fixes.sql | grep "UPDATE"

# 执行修复
psql -d filings_db -f cik_fixes.sql
```

**预期结果**:
- 修复CIK错误: 50-100家公司
- 删除无效公司记录（已退市等）

### 任务4.2: 处理Recent IPOs

创建专门的backfill脚本处理2023年后上市的公司:

```bash
# 创建 backfill_recent_ipos.py
python backfill_recent_ipos.py --start-date 2023-01-01
```

这些公司可能只有1-2年数据，调整期望。

**预期结果**:
- 新增200-300家公司数据
- 覆盖率提升: 82% → 86-87%

---

## 阶段5: 处理特殊交易所（2-3天）

### 问题分析: 为什么NYSE American/Arca覆盖率低？

可能原因:
1. **表格类型不同**: 可能不提交10-K/10-Q
2. **ETF占比高**: 虽然应该被过滤，但可能有漏网
3. **CIK映射问题**: listings_ref数据不完整
4. **已退市**: 这些交易所公司流动性差

### 任务5.1: 诊断NYSE American/Arca

```bash
# 专门分析这两个交易所
python diagnose_nyse_american_arca.py
```

创建专门脚本:
```python
# 查询这些公司的特征
SELECT c.ticker, c.cik, c.company_name, c.is_foreign, lr.is_etf
FROM companies c
LEFT JOIN listings_ref lr ON c.ticker = lr.symbol
WHERE c.exchange IN ('NYSE American', 'NYSE Arca')
  AND c.status = 'active'
  AND NOT EXISTS (SELECT 1 FROM filings WHERE company_id = c.id)
ORDER BY c.ticker;
```

### 任务5.2: 针对性处理

根据诊断结果:

**情况A: 主要是ETF**
```sql
-- 排除ETF（如果listings_ref有数据）
UPDATE companies
SET is_active = FALSE, status = 'etf_excluded'
WHERE id IN (
  SELECT c.id FROM companies c
  JOIN listings_ref lr ON c.ticker = lr.symbol
  WHERE lr.is_etf = TRUE
    AND c.exchange IN ('NYSE American', 'NYSE Arca')
);
```

**情况B: 是真实公司但无数据**
- 可能已退市或停止交易
- 考虑从目标公司中排除

**情况C: 数据存在但未下载**
- 运行针对性backfill
- 可能需要不同的表格类型

### 任务5.3: 重新评估目标

```bash
# 重新计算目标公司数（排除ETF和无效公司后）
psql -d filings_db -c "
SELECT exchange, COUNT(*) as target_companies
FROM companies
WHERE status = 'active' AND is_active = TRUE
GROUP BY exchange;
"
```

**预期结果**:
- 目标公司数: 5,911 → 5,500-5,700（排除ETF等）
- 覆盖率: 因分母减少而提升

---

## 🎯 预期最终结果

### 覆盖率提升路径

| 阶段 | 操作 | 覆盖率 | 新增公司 |
|------|------|--------|----------|
| 当前 | - | 73.95% | - |
| 阶段1 | Pending downloads | 75% | +100 |
| 阶段3 | 海外公司 | 82-85% | +400-600 |
| 阶段4 | CIK修复+IPOs | 86-87% | +200-300 |
| 阶段5 | 特殊交易所 | 88-90% | +100-200 |
| **最终** | **总计** | **90%+** | **+800-1,200** |

### 按交易所的预期改善

| 交易所 | 当前覆盖 | 目标覆盖 | 改善 |
|--------|---------|---------|------|
| NASDAQ | 81.12% | 90%+ | +9% |
| NYSE | 71.57% | 88%+ | +16% |
| NYSE American | 14.89% | 40-50% | +25-35% |
| NYSE Arca | 18.97% | 40-50% | +21-31% |

**注**: NYSE American/Arca可能需要调整目标（排除ETF后）

---

## 🛠️ 所需工具清单

### 已创建工具 ✅
1. `safe_download_pending.py` - 安全下载pending artifacts
2. `diagnose_missing_coverage.py` - 诊断缺失原因
3. `verify_cik_mappings.py` - CIK验证和修复
4. `jobs/backfill_foreign_improved.py` - 海外公司backfill

### 需要创建工具 📝
5. `backfill_recent_ipos.py` - 处理Recent IPOs
6. `diagnose_nyse_american_arca.py` - NYSE American/Arca专项诊断
7. `batch_mark_foreign.py` - 批量标记海外公司（自动化）
8. `coverage_progress_tracker.py` - 覆盖率进度追踪

---

## 📊 监控和验证

### 每日检查命令

```bash
# 1. 总体覆盖率
psql -d filings_db -c "
SELECT
  COUNT(DISTINCT c.id) as companies_with_data,
  (SELECT COUNT(*) FROM companies WHERE status='active') as total_companies,
  ROUND(100.0 * COUNT(DISTINCT c.id) /
    (SELECT COUNT(*) FROM companies WHERE status='active'), 2) as coverage_pct
FROM companies c
JOIN filings f ON f.company_id = c.id
WHERE c.status = 'active';
"

# 2. 按交易所覆盖率
psql -d filings_db -c "
SELECT
  c.exchange,
  COUNT(DISTINCT CASE WHEN f.id IS NOT NULL THEN c.id END) as with_filings,
  COUNT(DISTINCT c.id) as total,
  ROUND(100.0 * COUNT(DISTINCT CASE WHEN f.id IS NOT NULL THEN c.id END) /
    COUNT(DISTINCT c.id), 2) as coverage_pct
FROM companies c
LEFT JOIN filings f ON f.company_id = c.id
WHERE c.status = 'active'
GROUP BY c.exchange
ORDER BY total DESC;
"

# 3. Artifacts状态
psql -d filings_db -c "
SELECT status, COUNT(*), ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as pct
FROM artifacts
GROUP BY status
ORDER BY COUNT(*) DESC;
"
```

### 覆盖率可视化

```bash
# 生成每日报告
python coverage_progress_tracker.py --report daily

# 输出示例:
# Date: 2025-11-09
# Coverage: 75.23% (+1.28% from yesterday)
# Companies: 4,446 / 5,911
# Artifacts downloaded: 97,234 (91.2%)
```

---

## ⚠️ 注意事项

### 1. 海外公司识别准确性
- `diagnose_missing_coverage.py` 基于采样
- 建议采样200-300家以提高准确性
- 人工审查前10-20家确认逻辑正确

### 2. 下载速度控制
- 继续使用保守策略避免429
- 每天下载上限: 1,000-2,000 artifacts
- 优先级: Pending > 国内公司 > 海外公司

### 3. NYSE American/Arca特殊性
- 这两个交易所可能主要是ETF和小盘股
- 考虑调整目标覆盖率（60-70%可能更现实）
- 或从目标公司中排除（重新定义scope）

### 4. 数据质量 vs 覆盖率
- 不要为了覆盖率而降低数据质量
- 某些公司可能确实没有10-K/10-Q（如SPAC、shell公司）
- 接受80-90%的覆盖率，剩余10-20%可能是不可避免的

---

## 🚀 立即开始

### Day 1: 处理Pending + 诊断

```bash
# 上午: 下载pending
python safe_download_pending.py --batch-size 10 --batch-delay 2.0

# 下午: 诊断缺失
python diagnose_missing_coverage.py --sample-size 200

# 晚上: 审查报告，制定详细计划
cat diagnose_missing_coverage_report.txt
```

### Day 2: 标记海外公司

```bash
# 上午: 导出SQL
python diagnose_missing_coverage.py --export-foreign

# 下午: 审查并执行
cat mark_foreign_companies.sql
psql -d filings_db -f mark_foreign_companies.sql

# 晚上: 验证标记结果
psql -d filings_db -c "SELECT is_foreign, COUNT(*) FROM companies GROUP BY is_foreign;"
```

### Day 3-5: Backfill海外公司

```bash
# 每天处理一个交易所
python -m jobs.backfill_foreign_improved --exchange NASDAQ
# 第二天
python -m jobs.backfill_foreign_improved --exchange NYSE
# 第三天
python safe_download_pending.py --form-types 20-F,6-K --limit 1000
```

---

## 📝 成功标准

### 必须达成（Critical）
- [x] 总体覆盖率 > 85%
- [x] NASDAQ覆盖率 > 88%
- [x] NYSE覆盖率 > 85%
- [x] Failed artifacts < 1%
- [x] 无429错误

### 应该达成（High Priority）
- [ ] 总体覆盖率 > 90%
- [ ] NASDAQ覆盖率 > 92%
- [ ] NYSE覆盖率 > 90%
- [ ] 海外公司准确标记

### 可以达成（Nice to Have）
- [ ] NYSE American覆盖率 > 50%
- [ ] NYSE Arca覆盖率 > 50%
- [ ] 所有pending artifacts < 10

---

## 📞 需要帮助？

遇到问题时参考:
- `EXECUTIVE_SUMMARY.md` - 数据质量问题
- `DATA_QUALITY_FIX_PLAN.md` - 清理和修复
- 每个工具的 `--help` - 具体用法

**现在开始**: `python safe_download_pending.py --batch-size 10 --batch-delay 2.0`
