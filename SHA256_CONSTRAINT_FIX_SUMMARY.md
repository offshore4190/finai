# SHA256约束修复总结

## 问题描述

初始化数据库时出现错误：
```
could not create unique index "idx_artifacts_sha256_unique"
DETAIL: Key (sha256)=(c2cee8f67c7c6d1815663f9dfb7288568f53d82522a2966ac7ec07926cc6d351) is duplicated.
```

**根本原因：**
- SHA256被设置为全局唯一约束
- 但实际上不同的报告可能引用相同的图片文件（如公司logo、常见图表等）
- 发现6,325个SHA256值重复，共15,467条记录受影响

## 解决方案

### 设计思路

正确的约束策略应该是：
1. **允许SHA256重复** - 不同报告可以引用相同内容的文件
2. **防止同一报告重复下载** - 使用 `UNIQUE(filing_id, url)` 约束
3. **保留SHA256索引** - 用于内容查找和去重分析，但不强制唯一

### 实施步骤

#### 1. 创建新的Migration (007)

文件：`migrations/007_fix_sha256_constraint.sql`

```sql
-- 1. 删除SHA256的唯一索引
DROP INDEX IF EXISTS idx_artifacts_sha256_unique;

-- 2. 创建普通的SHA256索引（允许重复）
CREATE INDEX IF NOT EXISTS idx_artifacts_sha256 
ON artifacts(sha256) 
WHERE sha256 IS NOT NULL;

-- 3. 添加 filing_id + url 的唯一约束
CREATE UNIQUE INDEX IF NOT EXISTS idx_artifacts_filing_url_unique 
ON artifacts(filing_id, url);

-- 4. 性能优化：复合索引
CREATE INDEX IF NOT EXISTS idx_artifacts_filing_status 
ON artifacts(filing_id, status);
```

#### 2. 更新主Schema

文件：`migrations/schema.sql`

修改第72-75行，从：
```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_artifacts_sha256_unique 
ON artifacts(sha256) WHERE sha256 IS NOT NULL;
```

改为：
```sql
-- SHA256索引用于内容查找和复用，但不强制唯一
CREATE INDEX IF NOT EXISTS idx_artifacts_sha256 
ON artifacts(sha256) WHERE sha256 IS NOT NULL;

-- 唯一约束：同一报告的同一URL只下载一次
CREATE UNIQUE INDEX IF NOT EXISTS idx_artifacts_filing_url_unique 
ON artifacts(filing_id, url);
```

#### 3. 更新main.py

添加migration 007的执行：
```python
# Execute SHA256 constraint fix
migration_path = "migrations/007_fix_sha256_constraint.sql"
execute_schema_file(migration_path)
```

## 验证结果

### ✅ 索引状态

| 索引名称 | 状态 | 说明 |
|---------|------|------|
| `idx_artifacts_sha256_unique` | ❌ 已删除 | 旧的有问题的唯一索引 |
| `idx_artifacts_sha256` | ✅ 已创建 | 新的普通索引，用于内容查找 |
| `idx_artifacts_filing_url_unique` | ✅ 已创建 | filing_id + url 唯一约束 |

### ✅ 最终约束策略（三层防护）

1. **`UNIQUE(filing_id, filename)`** - 同一报告的文件名不重复
2. **`UNIQUE(filing_id, url)`** - 同一报告的源URL不重复（新增）
3. **`INDEX(sha256)`** - 允许重复，用于内容分析（修改）

### ✅ 数据完整性

- **数据保留：** 所有106,313条文件记录完整保留
- **SHA256重复：** 15,467条重复记录现在是合法的
- **无 (filing_id, url) 重复：** 验证通过，可安全创建唯一约束
- **数据库状态：** 正常运行，大小131MB

## 优势分析

### 1. 更合理的数据模型

**修复前：**
- ❌ 强制所有文件SHA256唯一
- ❌ 无法处理多个报告引用相同图片的情况
- ❌ 导致初始化失败

**修复后：**
- ✅ SHA256可以重复（符合实际情况）
- ✅ 防止同一报告重复下载（真正需要的约束）
- ✅ 数据库初始化成功

### 2. 实际应用场景

**允许的场景（SHA256重复）：**
- 公司A和公司B的报告都使用了相同的logo
- 多个报告引用了相同的图表模板
- 标准化的财务报表格式图片

**防止的场景（filing_id + url 唯一）：**
- 同一报告不会重复下载同一个文件
- 防止并发下载导致的重复记录
- 数据一致性保障

### 3. 性能优化

- **查询优化：** 可以通过SHA256快速查找内容相同的文件
- **存储优化：** 未来可基于SHA256实现文件去重存储
- **分析能力：** 可以统计哪些图片被多个报告引用

## 使用示例

### 查找内容相同的文件

```sql
-- 查找被多个报告引用的图片
SELECT 
    sha256,
    COUNT(DISTINCT filing_id) as filing_count,
    COUNT(*) as total_count
FROM artifacts
WHERE sha256 IS NOT NULL
GROUP BY sha256
HAVING COUNT(DISTINCT filing_id) > 1
ORDER BY filing_count DESC
LIMIT 10;
```

### 查找特定报告的所有文件

```sql
-- 确保没有重复URL
SELECT 
    filing_id,
    url,
    COUNT(*) as count
FROM artifacts
WHERE filing_id = 12345
GROUP BY filing_id, url;
```

## 相关脚本

创建的辅助脚本：

1. **check_db_status.py** - 快速查看数据库状态
2. **query_db_summary.py** - 详细的数据库汇总报告
3. **check_table_structure.py** - 查看表结构
4. **check_filing_url_duplicates.py** - 检查 (filing_id, url) 重复
5. **verify_constraints.py** - 验证约束和索引
6. **fix_duplicate_sha256.py** - SHA256去重工具（已不需要）

## 数据库当前状态

### 总体数据
- 公司总数：10,142
- 目标公司：5,911（NASDAQ/NYSE活跃）
- 报告总数：44,188
- 文件总数：106,313

### 下载状态
- ✅ 已下载：94,971 (89.33%)
- ⏭️ 跳过：11,299 (10.63%)
- ⏳ 待下载：22
- 🔄 下载中：17
- ❌ 失败：4

### 覆盖率（2023-2025）
- NASDAQ：77.17% (2,583/3,347)
- NYSE：68.49% (1,537/2,244)
- 总体：70.55% (4,170/5,911)

### SHA256统计（现在是合理的）
- 有SHA256的文件：106,275
- 唯一SHA256：90,808
- 重复文件：15,467（合法，不同报告引用相同内容）
- 重复的SHA256值：6,325

## 总结

✅ **问题已完全解决**

- 删除了不合理的SHA256全局唯一约束
- 添加了正确的 (filing_id, url) 唯一约束
- 保留了SHA256索引用于内容分析
- 所有现有数据完整保留
- 数据库可以正常初始化和运行

**关键要点：**
1. SHA256重复是合理的业务场景，不应强制唯一
2. 真正需要防止的是同一报告重复下载同一文件
3. 三层约束提供了完整的数据完整性保障

---

**日期：** 2025-11-01  
**版本：** Migration 007  
**状态：** ✅ 已完成并验证

