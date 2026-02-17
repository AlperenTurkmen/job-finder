#!/bin/bash

# Installation Verification Script for Job Finder Web App

echo "🔍 Verifying Job Finder Web App Installation..."
echo ""

ERRORS=0

# Check Python version
echo "1. Checking Python version..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo "   ✅ $PYTHON_VERSION"
else
    echo "   ❌ Python 3 not found"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# Check if in correct directory
echo "2. Checking working directory..."
if [ -f "web/app.py" ]; then
    echo "   ✅ In correct directory"
else
    echo "   ❌ Not in job-finder root directory"
    echo "      Please cd to /Users/alperenturkmen/Documents/GitHub/job-finder"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# Check .env file
echo "3. Checking .env file..."
if [ -f ".env" ]; then
    echo "   ✅ .env file exists"
    
    # Check required variables
    if grep -q "DATABASE_URL" .env && [ -n "$(grep DATABASE_URL .env | cut -d'=' -f2)" ]; then
        echo "   ✅ DATABASE_URL is set"
    else
        echo "   ⚠️  DATABASE_URL not set in .env"
        ERRORS=$((ERRORS + 1))
    fi
    
    if grep -q "GEMINI_API_KEY" .env && [ -n "$(grep GEMINI_API_KEY .env | cut -d'=' -f2)" ]; then
        echo "   ✅ GEMINI_API_KEY is set"
    else
        echo "   ⚠️  GEMINI_API_KEY not set in .env"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "   ❌ .env file not found"
    echo "      Run: cp .env.example .env"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# Check Python packages
echo "4. Checking Python packages..."
REQUIRED_PACKAGES=("flask" "playwright" "asyncpg" "beautifulsoup4")
for package in "${REQUIRED_PACKAGES[@]}"; do
    if python3 -c "import $package" 2>/dev/null; then
        echo "   ✅ $package installed"
    else
        echo "   ❌ $package not installed"
        ERRORS=$((ERRORS + 1))
    fi
done
echo ""

# Check Playwright browsers
echo "5. Checking Playwright browsers..."
if python3 -c "from playwright.sync_api import sync_playwright; sync_playwright()" 2>/dev/null; then
    echo "   ✅ Playwright configured"
else
    echo "   ⚠️  Playwright may need browser installation"
    echo "      Run: playwright install chromium"
fi
echo ""

# Check PostgreSQL
echo "6. Checking PostgreSQL..."
if command -v psql &> /dev/null; then
    echo "   ✅ psql command found"
    
    if [ -f ".env" ] && grep -q "DATABASE_URL" .env; then
        DB_URL=$(grep DATABASE_URL .env | cut -d'=' -f2)
        if [ -n "$DB_URL" ]; then
            if psql "$DB_URL" -c "SELECT 1" > /dev/null 2>&1; then
                echo "   ✅ Database connection successful"
                
                # Check if schema is loaded
                TABLE_COUNT=$(psql "$DB_URL" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('companies', 'jobs')" 2>/dev/null | tr -d '[:space:]')
                if [ "$TABLE_COUNT" = "2" ]; then
                    echo "   ✅ Database schema loaded"
                else
                    echo "   ⚠️  Database schema not found"
                    echo "      Run: psql -d jobfinder -f database/schema.sql"
                fi
            else
                echo "   ⚠️  Cannot connect to database"
                echo "      Check your DATABASE_URL in .env"
            fi
        fi
    fi
else
    echo "   ⚠️  PostgreSQL not found"
    echo "      Install PostgreSQL to use the web app"
fi
echo ""

# Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $ERRORS -eq 0 ]; then
    echo "✅ All checks passed!"
    echo ""
    echo "🚀 You're ready to start the web app:"
    echo "   ./start_web.sh"
    echo ""
    echo "   Or run directly:"
    echo "   python web/app.py"
else
    echo "⚠️  Found $ERRORS issue(s)"
    echo ""
    echo "📖 See QUICKSTART.md for setup instructions"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
