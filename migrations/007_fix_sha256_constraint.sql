-- Migration 007: 修复SHA256约束问题
-- 
-- 问题：SHA256被设置为全局唯一，但实际上不同报告可能引用相同的图片（如公司logo）
-- 
-- 解决方案：
-- 1. 删除SHA256的唯一约束
-- 2. 创建普通的SHA256索引用于查找和内容复用
-- 3. 添加 UNIQUE(filing_id, url) 保证同一报告不会重复下载相同URL
--
-- Date: 2025-11-01

-- 1. 删除SHA256的唯一索引（如果存在）
DROP INDEX IF EXISTS idx_artifacts_sha256_unique;

-- 2. 创建普通的SHA256索引用于查找相同内容
-- 这允许不同报告引用相同的文件（如公司logo）
CREATE INDEX IF NOT EXISTS idx_artifacts_sha256 ON artifacts(sha256) WHERE sha256 IS NOT NULL;

-- 3. 添加 filing_id + url 的唯一约束
-- 保证同一个报告的同一个URL只下载一次
-- 注意：使用url而不是filename，因为url是源地址标识符
CREATE UNIQUE INDEX IF NOT EXISTS idx_artifacts_filing_url_unique ON artifacts(filing_id, url);

-- 4. 为了性能，创建复合索引用于常见查询
CREATE INDEX IF NOT EXISTS idx_artifacts_filing_status ON artifacts(filing_id, status);

-- 说明：
-- - sha256可以重复：允许不同报告引用相同内容
-- - (filing_id, url)唯一：同一报告不会重复下载
-- - 已有的(filing_id, filename)约束保持不变，双重保护

