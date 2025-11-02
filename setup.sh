#!/bin/bash
# Quick setup script for US-Listed Filings ETL

set -e

echo "🚀 Setting up US-Listed Filings ETL..."

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Found Python $python_version"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Setup .env if not exists
if [ ! -f ".env" ]; then
    echo "⚙️  Creating .env file..."
    cp .env.example .env
    echo ""
    echo "⚠️  IMPORTANT: Edit .env and set SEC_USER_AGENT before running!"
    echo "   Example: SEC_USER_AGENT='YourCompany contact@yourcompany.com'"
    echo ""
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env and set SEC_USER_AGENT (REQUIRED)"
echo "2. Start PostgreSQL: docker-compose up -d postgres"
echo "3. Initialize database: python main.py init-db"
echo "4. Build listings: python main.py listings"
echo "5. Run backfill: python main.py backfill --limit 10"
echo ""
echo "For full documentation, see README.md"
