#!/bin/bash

# Production Configuration Check for Job Finder
# Run this before deploying to production

set -e

echo "🔒 Job Finder - Production Readiness Check"
echo "=========================================="
echo ""

ERRORS=0
WARNINGS=0

# Check .env exists
echo "1. Checking environment configuration..."
if [ ! -f ".env" ]; then
    echo "   ❌ .env file missing"
    ERRORS=$((ERRORS + 1))
else
    echo "   ✅ .env file exists"
    
    # Check critical variables
    if ! grep -q "FLASK_SECRET_KEY" .env || [ "$(grep FLASK_SECRET_KEY .env | cut -d'=' -f2)" == "dev-secret-key-change-in-production" ]; then
        echo "   ❌ FLASK_SECRET_KEY not set or using default"
        ERRORS=$((ERRORS + 1))
    else
        echo "   ✅ FLASK_SECRET_KEY configured"
    fi
    
    if ! grep -q "DATABASE_URL" .env; then
        echo "   ❌ DATABASE_URL not set"
        ERRORS=$((ERRORS + 1))
    else
        echo "   ✅ DATABASE_URL configured"
    fi
    
    if ! grep -q "GEMINI_API_KEY" .env; then
        echo "   ⚠️  GEMINI_API_KEY not set (required for AI features)"
        WARNINGS=$((WARNINGS + 1))
    else
        echo "   ✅ GEMINI_API_KEY configured"
    fi
    
    # Check debug mode
    if grep -q "FLASK_DEBUG=true" .env; then
        echo "   ⚠️  FLASK_DEBUG is enabled (disable for production)"
        WARNINGS=$((WARNINGS + 1))
    fi
fi
echo ""

# Check database connection
echo "2. Checking database connection..."
if [ -n "$DATABASE_URL" ] || ([ -f ".env" ] && grep -q "DATABASE_URL" .env); then
    export $(grep DATABASE_URL .env | xargs) 2>/dev/null || true
    if psql "$DATABASE_URL" -c "SELECT 1" > /dev/null 2>&1; then
        echo "   ✅ Database connection successful"
        
        # Check tables exist
        TABLE_COUNT=$(psql "$DATABASE_URL" -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" 2>/dev/null || echo "0")
        if [ "$TABLE_COUNT" -gt 0 ]; then
            echo "   ✅ Database schema loaded ($TABLE_COUNT tables)"
        else
            echo "   ⚠️  Database has no tables - run: psql -d jobfinder -f database/schema.sql"
            WARNINGS=$((WARNINGS + 1))
        fi
    else
        echo "   ❌ Cannot connect to database"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "   ❌ DATABASE_URL not configured"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# Check Python packages
echo "3. Checking Python dependencies..."
REQUIRED_PACKAGES=("flask" "playwright" "asyncpg" "google.generativeai")
ALL_PACKAGES_OK=true
for package in "${REQUIRED_PACKAGES[@]}"; do
    IMPORT_NAME=$(echo $package | cut -d'.' -f1)
    if python3 -c "import $IMPORT_NAME" 2>/dev/null; then
        echo "   ✅ $package installed"
    else
        echo "   ❌ $package missing"
        ALL_PACKAGES_OK=false
        ERRORS=$((ERRORS + 1))
    fi
done
echo ""

# Check Playwright browsers
echo "4. Checking Playwright browsers..."
if python3 -c "from playwright.sync_api import sync_playwright; sync_playwright()" 2>/dev/null; then
    echo "   ✅ Playwright browsers installed"
else
    echo "   ❌ Playwright browsers not installed - run: playwright install chromium"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# Check directory structure
echo "5. Checking directory structure..."
REQUIRED_DIRS=("agents" "web" "database" "utils" "tools" "data")
for dir in "${REQUIRED_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        echo "   ✅ $dir/ exists"
    else
        echo "   ❌ $dir/ missing"
        ERRORS=$((ERRORS + 1))
    fi
done
echo ""

# Security checks
echo "6. Security checks..."
if [ -f "data/profile.json" ]; then
    echo "   ⚠️  data/profile.json exists (contains personal data)"
    WARNINGS=$((WARNINGS + 1))
fi

if [ -f "data/user_answers.json" ]; then
    echo "   ⚠️  data/user_answers.json exists (contains personal data)"
    WARNINGS=$((WARNINGS + 1))
fi

if [ -d ".git" ]; then
    if git check-ignore .env > /dev/null 2>&1; then
        echo "   ✅ .env is gitignored"
    else
        echo "   ❌ .env is NOT gitignored - add to .gitignore!"
        ERRORS=$((ERRORS + 1))
    fi
fi
echo ""

# Summary
echo "=========================================="
echo "Summary:"
echo "  Errors: $ERRORS"
echo "  Warnings: $WARNINGS"
echo ""

if [ $ERRORS -eq 0 ]; then
    if [ $WARNINGS -eq 0 ]; then
        echo "✅ Production ready! No issues found."
        exit 0
    else
        echo "⚠️  Production ready with warnings. Review warnings above."
        exit 0
    fi
else
    echo "❌ NOT production ready. Fix errors above before deploying."
    exit 1
fi
