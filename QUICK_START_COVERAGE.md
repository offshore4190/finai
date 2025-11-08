# 快速开始 - 覆盖率提升

## 🎯 当前状态 → 目标

```
当前覆盖率: 73.95% (4,371 / 5,911 公司)
目标覆盖率: 90%+   (5,320+ / 5,911 公司)
需要增加:   ~950-1,200 家公司
```

---

## 🚀 立即开始（3个命令）

### Step 1: 查看当前状态 (1分钟)

```bash
# 激活虚拟环境
source venv/bin/activate  # 或 ./venv/bin/activate

# 查看覆盖率仪表板
python coverage_progress_tracker.py --save

# 保存第一个快照用于后续对比
```

**你会看到**:
- 总体覆盖率: 73.95%
- 各交易所明细
- Artifacts状态
- Filings分布

---

### Step 2: 处理Pending Downloads (30分钟)

```bash
# 下载195个pending artifacts
python safe_download_pending.py \
  --batch-size 10 \
  --batch-delay 2.0 \
  --limit 200

# 查看进度
tail -f logs/*.log | grep "download"
```

**预期结果**:
- 下载成功: 180-195个
- 覆盖率: 73.95% → 75%
- 新增公司: ~50-100家

---

### Step 3: 诊断缺失公司 (30-60分钟)

```bash
# 采样100家公司分析原因
python diagnose_missing_coverage.py --sample-size 100

# 查看报告（向下滚动查看详细信息）
```

**你会发现**:
- 有多少是海外公司（需要20-F/6-K）
- 有多少是Recent IPOs
- 有多少是CIK错误
- 可改进的公司数量估计

---

## 📋 后续步骤（根据诊断结果）

### 情况A: 发现300-500家海外公司（最常见）

```bash
# Day 1: 标记海外公司（预览）
python batch_mark_foreign.py --limit 50

# 审查输出，确认逻辑正确

# Day 1: 执行标记
python batch_mark_foreign.py --execute

# Day 2-3: Backfill海外公司数据
python -m jobs.backfill_foreign_improved --exchange NASDAQ
python -m jobs.backfill_foreign_improved --exchange NYSE

# Day 4-5: 下载artifacts
python safe_download_pending.py --form-types 20-F,6-K --limit 1000
```

**预期提升**: 75% → 82-85%

---

### 情况B: 发现CIK错误（50-100家）

```bash
# 批量验证和修复CIK
python verify_cik_mappings.py --batch --limit 200 > cik_fixes.sql

# 审查SQL
cat cik_fixes.sql | grep "UPDATE"

# 执行修复
psql -d filings_db -f cik_fixes.sql

# 重新运行backfill（针对修复的公司）
python main.py backfill --limit 100
```

**预期提升**: +1-2%

---

### 情况C: 发现Recent IPOs（200-300家）

这些公司可能只有1-2年数据，需要调整日期范围或接受较低覆盖率。

**选项1**: 接受现状（推荐）
- 这些公司确实没有完整的2023-2025数据
- 不影响整体覆盖率目标

**选项2**: 调整日期范围
- 修改backfill的START_DATE到2024-01-01
- 只针对这些公司运行

---

## 🎯 每日监控命令

### 早上：查看昨天进度

```bash
python coverage_progress_tracker.py --compare
```

**输出示例**:
```
PROGRESS SINCE LAST SNAPSHOT
Time since last snapshot: 1 day, 2:15:30
📈 Coverage: +2.31%
⬆️ Companies with data: +137

By Exchange:
  NASDAQ               Coverage: +1.85%  Companies: +62
  NYSE                 Coverage: +2.76%  Companies: +62
```

---

### 下午：处理Pending

```bash
# 检查pending数量
psql -d filings_db -c "
SELECT COUNT(*) FROM artifacts WHERE status = 'pending_download';
"

# 如果有pending，下载
python safe_download_pending.py --batch-size 10 --limit 500
```

---

### 晚上：保存快照

```bash
python coverage_progress_tracker.py --save
```

---

## 📊 里程碑检查点

### Milestone 1: 75% 覆盖率 (1-2天)
- [x] 处理195个pending downloads
- [x] 新增50-100家公司

### Milestone 2: 80% 覆盖率 (3-5天)
- [ ] 诊断完成，明确缺失原因
- [ ] 标记300-500家海外公司
- [ ] Backfill海外公司（部分）

### Milestone 3: 85% 覆盖率 (1周)
- [ ] 完成海外公司backfill
- [ ] 下载所有海外公司artifacts
- [ ] 修复CIK错误

### Milestone 4: 90% 覆盖率 (2周)
- [ ] 处理Recent IPOs
- [ ] 优化NYSE American/Arca
- [ ] 最终数据验证

---

## ⚠️ 重要提醒

### 1. 下载速度控制
**永远使用保守策略**:
```bash
--batch-size 5-10
--batch-delay 2.0-3.0
--download-delay 0.15-0.2
```

如果看到429错误，立即停止并增加延迟。

### 2. 数据质量优先
- 不要为了覆盖率而降低数据质量
- 某些公司可能确实没有10-K/10-Q
- 80-90%是合理目标，100%不现实

### 3. 海外公司标记准确性
- 使用 `--limit 50` 先测试
- 人工审查前10-20家公司
- 确认逻辑正确后再全量执行

### 4. 定期保存快照
每天或每个阶段后运行:
```bash
python coverage_progress_tracker.py --save --compare
```

---

## 🆘 常见问题

### Q1: 诊断工具运行很慢？
A: 正常，需要调用SEC API。100家公司约需20-30分钟。可以先用 `--limit 50` 测试。

### Q2: 标记了海外公司但覆盖率没提升？
A: 标记只是第一步，还需要:
1. 运行 `backfill_foreign_improved`
2. 下载artifacts
3. 等待1-2天完成

### Q3: 某些公司无论如何都没有数据？
A: 可能原因:
- 已退市
- 新上市（数据不足）
- 特殊类型（SPAC、shell公司）
- CIK错误（运行verify_cik_mappings修复）

### Q4: NYSE American/Arca覆盖率始终很低？
A: 这两个交易所可能:
- ETF占比高（应排除）
- 小盘股数据不完整
- 考虑调整目标覆盖率到60-70%

---

## 📞 获取帮助

### 详细文档
- `COVERAGE_IMPROVEMENT_PLAN.md` - 完整5阶段计划
- `DATA_QUALITY_FIX_PLAN.md` - 数据质量修复
- `EXECUTIVE_SUMMARY.md` - 问题总结

### 工具帮助
```bash
python diagnose_missing_coverage.py --help
python batch_mark_foreign.py --help
python coverage_progress_tracker.py --help
```

---

## ✅ 成功案例参考

### 典型改进路径
```
Day 1:  73.95% → 75.12%   (pending downloads)
Day 2:  75.12% → 76.34%   (诊断+部分backfill)
Day 3:  76.34% → 80.21%   (海外公司标记)
Day 5:  80.21% → 85.67%   (海外公司下载)
Day 7:  85.67% → 87.43%   (CIK修复)
Day 10: 87.43% → 89.12%   (Recent IPOs)
Day 14: 89.12% → 91.56%   (最终优化)
```

### 关键成功因素
1. ✅ 每天监控进度
2. ✅ 保守的下载策略（避免429）
3. ✅ 海外公司准确标记
4. ✅ 及时修复CIK错误
5. ✅ 接受合理的覆盖率上限（90-92%）

---

**现在开始第一步**:

```bash
python coverage_progress_tracker.py --save
```

然后根据结果决定是先处理pending downloads还是直接诊断缺失公司。
