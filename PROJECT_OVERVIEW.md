# SEC Filings ETL 系统 - 完整项目说明

## 📖 目录

1. [项目简介](#项目简介)
2. [系统架构](#系统架构)
3. [核心功能](#核心功能)
4. [安装部署](#安装部署)
5. [使用方法](#使用方法)
6. [数据模型](#数据模型)
7. [API参考](#api参考)
8. [维护指南](#维护指南)
9. [常见问题](#常见问题)

---

## 项目简介

### 什么是 SEC Filings ETL？

这是一个自动化的数据采集和处理系统，用于从美国证券交易委员会(SEC) EDGAR数据库下载和管理上市公司的财务报告。

### 核心价值

- 📊 **自动化数据采集**: 自动下载10-K、10-Q、20-F、40-F等财务报告
- 🗄️ **结构化存储**: PostgreSQL数据库管理元数据，本地文件系统存储HTML文件
- 🔍 **数据质量保证**: 完整性检查、重复检测、错误处理
- 📈 **覆盖率追踪**: 实时监控数据覆盖率和下载进度
- 🌍 **海外公司支持**: 特别优化的海外公司（Foreign Private Issuer）处理

### 适用场景

- 金融数据分析
- 投资研究
- 机器学习训练数据
- 监管合规分析
- 学术研究

---

## 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        SEC EDGAR API                         │
│              https://www.sec.gov/cgi-bin/browse-edgar       │
└─────────────────────────────────────────────────────────────┘
                            ↓ HTTPS
┌─────────────────────────────────────────────────────────────┐
│                     ETL Pipeline (Python)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Listings   │  │   Backfill   │  │  Incremental │      │
│  │     Sync     │→│     Jobs     │→│    Updates   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│         ↓                  ↓                   ↓             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           Rate Limiter (10 req/sec)                  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                ↓                           ↓
    ┌──────────────────┐        ┌──────────────────┐
    │   PostgreSQL DB  │        │  Local Storage   │
    │   (Metadata)     │        │   (/data/filings)│
    │                  │        │                  │
    │ • Companies      │        │ • HTML Files     │
    │ • Filings        │        │ • Images         │
    │ • Artifacts      │        │ • Attachments    │
    └──────────────────┘        └──────────────────┘
```

### 技术栈

| 组件 | 技术 |
|------|------|
| **编程语言** | Python 3.11+ |
| **Web框架** | httpx (HTTP客户端) |
| **数据库** | PostgreSQL 14+ |
| **ORM** | SQLAlchemy 2.0 |
| **数据库迁移** | Alembic |
| **HTML解析** | BeautifulSoup4 + lxml |
| **日志** | structlog |
| **配置管理** | pydantic-settings |
| **容器化** | Docker / Docker Compose |

### 目录结构

```
filings-etl/
├── config/                    # 配置模块
│   ├── db.py                 # 数据库连接
│   └── settings.py           # 环境变量配置
├── models/                    # 数据模型
│   ├── company.py            # 公司模型
│   ├── filing.py             # Filing模型
│   ├── artifact.py           # Artifact模型
│   └── execution_run.py      # 执行记录模型
├── services/                  # 核心服务
│   ├── sec_api.py            # SEC API客户端
│   └── storage.py            # 存储服务
├── jobs/                      # ETL任务
│   ├── backfill.py           # 美国公司backfill
│   ├── backfill_foreign_improved.py  # 海外公司backfill
│   ├── incremental.py        # 增量更新
│   └── listings_build.py     # 公司列表构建
├── utils/                     # 工具函数
│   ├── rate_limiter.py       # 速率限制器
│   └── retry.py              # 重试装饰器
├── migrations/                # 数据库迁移
├── tests/                     # 测试
├── .env                       # 环境变量（需手动创建）
├── requirements.txt           # Python依赖
├── docker-compose.yml         # Docker配置
└── README.md                  # 主文档
```

---

## 核心功能

### 1. 公司列表同步

**功能**: 从SEC获取所有上市公司列表

**命令**:
```bash
python -m jobs.listings_build
```

**输出**:
- 更新`companies`表
- 新增公司自动标记为`is_active=true`
- 退市公司标记为`is_active=false`

**数据来源**:
```
https://www.sec.gov/files/company_tickers.json
```

### 2. Backfill任务

**功能**: 批量下载历史Filing数据

#### 2.1 美国公司 Backfill

```bash
# NASDAQ公司
python nasdaq_full_backfill.py

# NYSE公司
python nyse_full_backfill.py

# 所有交易所
python all_exchanges_backfill.py
```

**处理表格类型**:
- 10-K: 年报
- 10-Q: 季报
- 10-K/A, 10-Q/A: 修订版

**日期范围**: 默认2023-01-01至今

#### 2.2 海外公司 Backfill

```bash
# 海外公司（20-F, 40-F, 6-K）
python -m jobs.backfill_foreign_improved --exchange NASDAQ
```

**处理表格类型**:
- 20-F: 海外公司年报
- 40-F: 加拿大公司年报
- 6-K: 当前报告

**特殊处理**:
- ✅ Primary document自动获取（从index页面解析）
- ✅ CIK验证
- ✅ 日期验证（排除未来日期）

### 3. 增量更新

**功能**: 定期检查新Filing

```bash
python -m jobs.incremental --lookback-days 7
```

**适用场景**:
- 日常维护
- 获取最新Filing
- Cron定时任务

**推荐频率**:
```bash
# 添加到crontab
0 2 * * * cd /path/to/filings-etl && python -m jobs.incremental
```

### 4. 文件下载

**功能**: 下载pending状态的artifacts

```bash
# 安全下载（带速率限制）
python safe_download_pending.py \
  --batch-size 10 \
  --batch-delay 2.0 \
  --download-delay 0.15 \
  --limit 1000
```

**速率控制**:
- SEC限制: 10请求/秒
- 推荐设置: 6-7请求/秒（避免429错误）

### 5. 数据质量检查

```bash
# 检查文件完整性
python check_file_integrity.py

# 诊断失败的artifacts
python diagnose_failed_artifacts.py

# 验证CIK映射
python verify_cik_mappings.py
```

### 6. 覆盖率追踪

```bash
# 查看当前覆盖率
python coverage_progress_tracker.py

# 保存快照并对比
python coverage_progress_tracker.py --save --compare

# 诊断缺失覆盖
python diagnose_missing_coverage.py
```

---

## 安装部署

### 前置要求

- Python 3.11+
- PostgreSQL 14+
- 磁盘空间: 至少100GB（用于存储HTML文件）
- 内存: 至少4GB

### 步骤1: 克隆仓库

```bash
git clone <repository-url>
cd filings-etl
```

### 步骤2: 安装依赖

```bash
# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 步骤3: 配置环境变量

```bash
# 复制示例配置
cp .env.example .env

# 编辑.env文件
nano .env
```

**必需配置项**:

```bash
# 数据库配置
DB_HOST=localhost
DB_PORT=5432
DB_NAME=filings_db
DB_USER=postgres
DB_PASSWORD=your_password

# 存储配置
STORAGE_BACKEND=local
STORAGE_ROOT=/data/filings

# SEC API配置（重要！）
SEC_USER_AGENT=YourCompany contact@yourcompany.com
SEC_RATE_LIMIT=10
```

⚠️ **重要**: SEC要求自定义User-Agent，格式必须包含公司名和联系邮箱

### 步骤4: 初始化数据库

#### 方法A: 使用Docker Compose

```bash
# 启动PostgreSQL
docker-compose up -d

# 等待数据库启动
sleep 5

# 运行迁移
alembic upgrade head
```

#### 方法B: 手动安装PostgreSQL

```bash
# 创建数据库
createdb filings_db

# 运行迁移
alembic upgrade head
```

### 步骤5: 验证安装

```bash
# 检查数据库连接
python check_db_status.py

# 测试SEC API连接
python -c "
from services.sec_api import SECAPIClient
client = SECAPIClient()
data = client.fetch_company_tickers()
print(f'✅ 成功获取 {len(data)} 家公司')
"
```

### 步骤6: 创建存储目录

```bash
# 创建数据目录
sudo mkdir -p /data/filings
sudo chown $USER:$USER /data/filings

# 验证权限
touch /data/filings/test.txt && rm /data/filings/test.txt
```

---

## 使用方法

### 完整工作流程

#### 第一次使用（初始化）

```bash
# 1. 同步公司列表
python -m jobs.listings_build

# 2. 标记海外公司
python batch_mark_foreign.py --exchange NASDAQ
python batch_mark_foreign.py --exchange NYSE

# 3. 运行backfill（美国公司）
python nasdaq_full_backfill.py --limit 100  # 先测试100家

# 4. 运行backfill（海外公司）
python -m jobs.backfill_foreign_improved --limit 10  # 先测试10家

# 5. 下载文件
python safe_download_pending.py --limit 100

# 6. 检查覆盖率
python coverage_progress_tracker.py
```

#### 日常维护（增量更新）

```bash
# 每天运行一次
python -m jobs.incremental --lookback-days 7
python safe_download_pending.py --limit 500
```

#### 数据质量检查（每周）

```bash
# 检查失败的artifacts
python diagnose_failed_artifacts.py

# 修复失败的下载
python repair_failed_artifacts.py

# 生成覆盖率报告
python coverage_progress_tracker.py --save --compare
```

---

## 数据模型

### 1. Companies（公司表）

**字段**:
```python
id              # 主键
ticker          # 股票代码（如 AAPL）
cik             # SEC CIK编号（10位数字）
name            # 公司名称
exchange        # 交易所（NASDAQ/NYSE/etc）
is_active       # 是否活跃
is_foreign      # 是否海外公司
created_at      # 创建时间
updated_at      # 更新时间
```

**索引**:
- `ticker` (UNIQUE)
- `cik` (UNIQUE)
- `exchange`
- `is_foreign`

**示例查询**:
```sql
-- 查看所有NASDAQ海外公司
SELECT ticker, name, cik
FROM companies
WHERE exchange = 'NASDAQ'
  AND is_foreign = true
  AND is_active = true;
```

### 2. Filings（表格表）

**字段**:
```python
id                  # 主键
company_id          # 外键 → companies.id
accession_number    # Accession号（唯一标识）
form_type           # 表格类型（10-K/10-Q/20-F/etc）
filing_date         # 提交日期
report_date         # 报告日期
fiscal_year         # 财年
fiscal_period       # 财务期间（FY/Q1/Q2/Q3/Q4）
is_amendment        # 是否修订版
primary_document    # 主文档文件名
created_at          # 创建时间
```

**索引**:
- `accession_number` (UNIQUE)
- `company_id, form_type, fiscal_year`
- `filing_date`

**示例查询**:
```sql
-- 查看AAPL的所有10-K年报
SELECT f.filing_date, f.fiscal_year, f.accession_number
FROM filings f
JOIN companies c ON f.company_id = c.id
WHERE c.ticker = 'AAPL'
  AND f.form_type = '10-K'
ORDER BY f.filing_date DESC;
```

### 3. Artifacts（文件表）

**字段**:
```python
id              # 主键
filing_id       # 外键 → filings.id
artifact_type   # 文件类型（html/pdf/image）
filename        # 文件名
url             # SEC下载URL
local_path      # 本地存储路径
status          # 状态（pending_download/downloaded/failed）
file_size       # 文件大小（字节）
sha256          # SHA256哈希
error_message   # 错误信息（如果失败）
downloaded_at   # 下载时间
created_at      # 创建时间
```

**状态流转**:
```
pending_download → downloading → downloaded
                              ↓
                            failed
```

**示例查询**:
```sql
-- 查看下载失败的artifacts
SELECT
    c.ticker,
    f.form_type,
    a.filename,
    a.error_message
FROM artifacts a
JOIN filings f ON a.filing_id = f.id
JOIN companies c ON f.company_id = c.id
WHERE a.status = 'failed'
LIMIT 100;
```

### 4. ExecutionRuns（执行记录表）

**字段**:
```python
id                  # 主键
run_type            # 运行类型（backfill/incremental）
started_at          # 开始时间
completed_at        # 完成时间
status              # 状态（running/completed/failed）
duration_seconds    # 执行时长
filings_discovered  # 发现的Filing数量
error_summary       # 错误摘要
meta_data           # 元数据（JSON）
```

**示例查询**:
```sql
-- 查看最近的backfill运行记录
SELECT
    run_type,
    started_at,
    duration_seconds,
    filings_discovered,
    status
FROM execution_runs
WHERE run_type LIKE '%backfill%'
ORDER BY started_at DESC
LIMIT 10;
```

---

## API参考

### SECAPIClient

位置: `services/sec_api.py`

#### 初始化

```python
from services.sec_api import SECAPIClient

client = SECAPIClient()
```

#### 方法

##### fetch_company_tickers()

获取所有公司列表

```python
data = client.fetch_company_tickers()
# 返回: Dict[str, Dict]
# {
#   "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
#   ...
# }
```

##### fetch_company_submissions(cik: str)

获取公司的所有submissions

```python
submissions = client.fetch_company_submissions("0000320193")
# 返回: Dict 包含所有Filing元数据
```

##### parse_filings(submissions_data, form_types, start_date, end_date)

解析Filing数据

```python
from datetime import datetime

filings = client.parse_filings(
    submissions,
    form_types=['10-K', '10-Q'],
    start_date=datetime(2023, 1, 1),
    end_date=datetime.now()
)
# 返回: List[Dict]
```

##### get_primary_document_from_index(cik: str, accession: str)

从index页面获取主文档文件名（海外公司专用）

```python
filename = client.get_primary_document_from_index(
    cik="0001234567",
    accession="0001193125-24-123456"
)
# 返回: str (如 "abevform20f_2023.htm")
```

##### download_file(url: str, output_path: str)

下载文件

```python
size = client.download_file(
    url="https://www.sec.gov/Archives/...",
    output_path="/data/filings/NASDAQ/AAPL/2024/FY_01-11-2024.html"
)
# 返回: int (文件大小)
```

##### construct_document_url(cik, accession, filename)

构造文档URL

```python
url = client.construct_document_url(
    cik="0000320193",
    accession="0001193125-24-012345",
    filename="aapl-20240930.htm"
)
# 返回: "https://www.sec.gov/Archives/edgar/data/320193/0001193125-24-012345/aapl-20240930.htm"
```

### StorageService

位置: `services/storage.py`

#### 初始化

```python
from services.storage import storage_service
```

#### 方法

##### construct_path(exchange, ticker, fiscal_year, fiscal_period, filing_date_str, artifact_type)

构造本地存储路径

```python
path = storage_service.construct_path(
    exchange="NASDAQ",
    ticker="AAPL",
    fiscal_year=2024,
    fiscal_period="FY",
    filing_date_str="01-11-2024",
    artifact_type="html"
)
# 返回: "/data/filings/NASDAQ/AAPL/2024/FY_01-11-2024.html"
```

##### ensure_directory_structure(exchange, ticker, fiscal_year)

确保目录存在

```python
storage_service.ensure_directory_structure(
    exchange="NASDAQ",
    ticker="AAPL",
    fiscal_year=2024
)
# 创建: /data/filings/NASDAQ/AAPL/2024/
```

---

## 维护指南

### 日常监控

#### 1. 检查下载状态

```bash
# 每天运行
python -c "
from config.db import get_db_session
from models import Artifact
from sqlalchemy import func

with get_db_session() as session:
    stats = session.query(
        Artifact.status,
        func.count(Artifact.id)
    ).group_by(Artifact.status).all()

    for status, count in stats:
        print(f'{status}: {count:,}')
"
```

#### 2. 检查失败率

```bash
python diagnose_failed_artifacts.py | grep "Failed artifacts:"
# 如果失败率 >5%，需要调查原因
```

#### 3. 检查磁盘空间

```bash
df -h /data/filings
# 确保剩余空间 >20%
```

### 定期维护任务

#### 每日任务

```bash
#!/bin/bash
# daily_maintenance.sh

# 增量更新
python -m jobs.incremental --lookback-days 7

# 下载新文件
python safe_download_pending.py --limit 500

# 检查失败的下载
python diagnose_failed_artifacts.py > /tmp/failed_check.txt

# 发送报告
mail -s "Daily ETL Report" admin@example.com < /tmp/failed_check.txt
```

#### 每周任务

```bash
#!/bin/bash
# weekly_maintenance.sh

# 修复失败的下载
python repair_failed_artifacts.py

# 清理孤立文件
python -c "
from services.storage import storage_service
storage_service.cleanup_orphaned_files()
"

# 生成覆盖率报告
python coverage_progress_tracker.py --save --compare
```

#### 每月任务

```bash
#!/bin/bash
# monthly_maintenance.sh

# 数据库vacuum
psql -d filings_db -c "VACUUM ANALYZE;"

# 检查数据完整性
python check_file_integrity.py --full

# 备份数据库
pg_dump filings_db | gzip > backup_$(date +%Y%m%d).sql.gz
```

### 故障排查

#### 问题1: 下载速度慢

**症状**: 下载速度<5文件/秒

**可能原因**:
1. 网络延迟高
2. SEC服务器响应慢
3. 速率限制设置过于保守

**解决方案**:
```bash
# 1. 检查网络延迟
ping www.sec.gov

# 2. 调整速率限制（谨慎）
python safe_download_pending.py \
  --download-delay 0.12  # 从0.15减少到0.12
```

#### 问题2: 大量429错误

**症状**: 日志中频繁出现"429 Too Many Requests"

**解决方案**:
```bash
# 增加延迟时间
python safe_download_pending.py \
  --download-delay 0.2   # 增加到0.2秒
  --batch-delay 3.0      # 增加到3秒
```

#### 问题3: 磁盘空间不足

**症状**: 下载失败，错误信息包含"No space left on device"

**解决方案**:
```bash
# 1. 清理旧的日志文件
find logs/ -name "*.log" -mtime +30 -delete

# 2. 压缩旧的HTML文件
find /data/filings -name "*.html" -mtime +365 -exec gzip {} \;

# 3. 考虑迁移到更大的存储
```

#### 问题4: 数据库连接池耗尽

**症状**: 错误信息"QueuePool limit of size X overflow X reached"

**解决方案**:
```python
# 编辑 config/db.py
engine = create_engine(
    settings.database_url,
    pool_size=20,        # 从默认5增加到20
    max_overflow=40,     # 从默认10增加到40
)
```

---

## 常见问题

### Q1: 为什么有些公司没有数据？

**A**: 可能的原因：
1. 公司最近才上市，历史数据不足
2. 公司已退市或被收购
3. CIK映射错误
4. Filing格式不在我们支持的类型中

**解决**:
```bash
# 检查特定公司
python -c "
from config.db import get_db_session
from models import Company
with get_db_session() as session:
    company = session.query(Company).filter_by(ticker='XXXX').first()
    if company:
        print(f'CIK: {company.cik}')
        print(f'Is Active: {company.is_active}')
        print(f'Is Foreign: {company.is_foreign}')
    else:
        print('公司不存在于数据库')
"
```

### Q2: 海外公司的6-K报告很多，都需要下载吗？

**A**: 6-K是当前报告，发布频率高（类似于8-K）。建议：
- 初期：只下载20-F和40-F年报
- 后期：根据需求选择性下载6-K

### Q3: 下载的HTML文件中图片链接失效怎么办？

**A**: 使用图片本地化工具：
```bash
python fix_html_image_links.py --exchange NASDAQ --ticker AAPL
```

### Q4: 如何只更新特定交易所的数据？

**A**:
```bash
# 只更新NASDAQ
python -m jobs.incremental --exchange NASDAQ

# 只更新NYSE
python -m jobs.incremental --exchange NYSE
```

### Q5: 数据可以商业使用吗？

**A**: SEC数据是公开数据，可以商业使用。但请遵守：
1. SEC使用条款
2. 速率限制（10请求/秒）
3. 合理的User-Agent
4. 不要滥用SEC服务器

### Q6: 如何导出数据？

**A**:
```bash
# 导出特定公司的Filing列表
python export_companies.py --ticker AAPL --format csv

# 导出所有海外公司
python export_companies.py --foreign-only --format json
```

### Q7: 系统要求是什么？

**A**:
- **CPU**: 2核以上
- **内存**: 4GB以上（推荐8GB）
- **磁盘**: 100GB以上（5000家公司×每家约20MB）
- **网络**: 稳定的互联网连接

### Q8: 可以在云端部署吗？

**A**: 可以，推荐配置：
- AWS EC2 t3.medium + RDS PostgreSQL
- GCP Compute Engine e2-medium + Cloud SQL
- Azure VM B2s + Azure Database for PostgreSQL

存储可以使用：
- AWS S3
- GCP Cloud Storage
- Azure Blob Storage

修改`STORAGE_BACKEND=s3`并配置相应的bucket即可。

---

## 路线图

### 已完成 ✅

- [x] 美国公司10-K/10-Q下载
- [x] 海外公司20-F/40-F支持
- [x] Primary document自动获取
- [x] CIK验证
- [x] 速率限制
- [x] 覆盖率追踪
- [x] 数据质量检查

### 进行中 🚧

- [ ] 6-K报告处理优化
- [ ] 图片自动下载和本地化
- [ ] HTML链接重写
- [ ] 增量更新自动化

### 计划中 📋

- [ ] Web界面（数据浏览和搜索）
- [ ] RESTful API
- [ ] 数据导出（CSV/JSON/Parquet）
- [ ] 文本提取（从HTML到纯文本）
- [ ] 财务指标提取
- [ ] 机器学习特征工程

---

## 贡献指南

欢迎贡献！请遵循以下步骤：

1. Fork本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启Pull Request

---

## 许可证

MIT License - 详见 LICENSE 文件

---

## 联系方式

- GitHub: [项目仓库地址]
- Email: team@finai-research.com
- 文档: 查看项目根目录的各个.md文件

---

**最后更新**: 2025-11-08
**版本**: 2.0
**维护者**: FinAI Research Team
