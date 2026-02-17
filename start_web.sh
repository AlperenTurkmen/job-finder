#!/bin/bash

# Job Finder Web Application Startup Script

set -e

echo "🚀 Starting Job Finder Web Application..."

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found"
    echo "Please create a .env file with:"
    echo "  DATABASE_URL=postgresql://user:pass@localhost/jobfinder"
    echo "  GEMINI_API_KEY=your_api_key"
    echo "  FLASK_SECRET_KEY=your_secret"
    exit 1
fi

# Load environment variables
export $(cat .env | xargs)

# Check DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo "❌ Error: DATABASE_URL not set in .env"
    exit 1
fi

# Check if PostgreSQL is accessible
echo "🔍 Checking database connection..."
if command -v psql &> /dev/null; then
    if psql "$DATABASE_URL" -c "SELECT 1" > /dev/null 2>&1; then
        echo "✅ Database connection successful"
    else
        echo "⚠️  Warning: Cannot connect to database"
        echo "   Make sure PostgreSQL is running and DATABASE_URL is correct"
    fi
else
    echo "⚠️  psql not found, skipping database check"
fi

# Check if Playwright is installed
echo "🔍 Checking Playwright..."
if python -c "from playwright.sync_api import sync_playwright" 2>/dev/null; then
    echo "✅ Playwright installed"
else
    echo "⚠️  Playwright not found. Installing..."
    pip install playwright
    playwright install chromium
fi

# Set defaults if not in .env
export FLASK_DEBUG=${FLASK_DEBUG:-true}
export PORT=${PORT:-5000}

echo ""
echo "📋 Configuration:"
echo "   Port: $PORT"
echo "   Debug: $FLASK_DEBUG"
echo ""

# Start the application
echo "🎯 Starting Flask application on http://localhost:$PORT"
echo ""

cd "$(dirname "$0")/.."
python web/app.py
