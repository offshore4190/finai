.PHONY: start db-up db-down test logs db-psql db-status

# 1) 启动本地开发环境（主要是启动 DB；venv 需你在当前 shell 手动 source）
start: db-up
	@echo "🔹 Activating virtualenv (tip):"
	@echo "   source .venv/bin/activate"
	@echo "✅ Environment is ready. You can now run: python main.py ..."

# 2) 启动 Postgres（Docker Compose）
db-up:
	@echo "🚀 Starting Postgres via docker compose..."
	docker compose up -d
	@echo "⏳ Waiting for Postgres to become ready..."
	@sleep 2
	@docker exec -it filings_postgres pg_isready -U postgres -d filings_db

# 3) 停止/移除容器（不会删除数据卷）
db-down:
	@echo "🛑 Stopping Postgres..."
	docker compose down

# 4) 查看数据库容器日志
logs:
	docker compose logs -f postgres

# 5) 进入数据库交互（容器内 psql）
db-psql:
	docker exec -it filings_postgres psql -U postgres -d filings_db

# 6) 数据库就绪检查
db-status:
	docker exec -it filings_postgres pg_isready -U postgres -d filings_db

# 7) 运行测试（需你在当前 shell 先手动激活 venv）
test:
	@echo "🧪 Running tests..."
	@source .venv/bin/activate && pytest -q
