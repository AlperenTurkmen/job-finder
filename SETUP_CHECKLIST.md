# Job Finder Web App - Setup Checklist

Use this checklist to get the web application running.

## Prerequisites
- [ ] Python 3.9+ installed (`python3 --version`)
- [ ] PostgreSQL installed (`psql --version`)
- [ ] Git installed (to clone/pull latest code)

## Installation Steps

### 1. Navigate to Project
```bash
cd /Users/alperenturkmen/Documents/GitHub/job-finder
```

### 2. Install Python Dependencies
```bash
pip install -r requirements.txt
```
Expected: ~12 packages installed including Flask, Playwright, asyncpg

### 3. Install Playwright Browser
```bash
playwright install chromium
```
Expected: ~150MB download, browser installed

### 4. Set Up Database
```bash
# Create database (one time only)
createdb jobfinder

# Load schema
psql -d jobfinder -f database/schema.sql

# Verify
psql -d jobfinder -c "\dt"
```
Expected: See `companies` and `jobs` tables

### 5. Configure Environment
```bash
# Copy template
cp .env.example .env

# Edit .env file
nano .env  # or use your favorite editor
```

Required settings in `.env`:
- [ ] `DATABASE_URL=postgresql://youruser:yourpass@localhost/jobfinder`
- [ ] `GEMINI_API_KEY=your_api_key_from_google`
- [ ] `FLASK_SECRET_KEY=random_secret_key`

**Get Gemini API key**: https://makersuite.google.com/app/apikey
**Generate secret key**: `python -c "import secrets; print(secrets.token_hex(32))"`

### 6. Verify Installation
```bash
./verify_setup.sh
```
Expected: All checks pass ✅

### 7. Start the Application
```bash
./start_web.sh
```
Expected: See "Starting Flask application on http://localhost:5000"

### 8. Test in Browser
- [ ] Open http://localhost:5000
- [ ] See the landing page
- [ ] Click "Get Started"
- [ ] Fill out preferences form
- [ ] Submit and see scraping progress
- [ ] View matched job results

## Quick Test Run

Once everything is set up, test with:

1. **Select**: Netflix only
2. **Job Titles**: "Software Engineer"
3. **Skills**: "Python, AWS, Docker"
4. **Location**: Leave empty
5. **Submit**: Wait 30-60 seconds
6. **Verify**: See Netflix jobs with match scores

## Troubleshooting

### "DATABASE_URL not set"
→ Edit `.env` and add: `DATABASE_URL=postgresql://user:pass@localhost/jobfinder`

### "Cannot connect to database"
→ Start PostgreSQL: `brew services start postgresql` (macOS)
→ Or: `sudo service postgresql start` (Linux)

### "No module named 'flask'"
→ Run: `pip install -r requirements.txt`

### "Playwright not installed"
→ Run: `playwright install chromium`

### "No jobs found"
→ Check the terminal logs for scraping errors
→ Try a different company
→ Verify GEMINI_API_KEY is set

## File Locations

- **Main app**: `web/app.py`
- **Templates**: `web/templates/`
- **Database**: `utils/db_client.py`
- **Scrapers**: `tools/scrapers/`
- **Config**: `.env` (you create this)

## What's Next?

After successful setup:
1. ✅ Try different company combinations
2. ✅ Experiment with different skills
3. ✅ Customize match scoring in `web/job_matcher.py`
4. ✅ Add new company scrapers
5. ✅ Integrate with automation pipeline

## Need Help?

- **Setup issues**: See `QUICKSTART.md`
- **Web app docs**: See `web/README.md`
- **Implementation**: See `WEB_APP_SUMMARY.md`
- **Architecture**: See `.github/copilot-instructions.md`

---

**Time to complete**: ~15-20 minutes for first-time setup
**Time to test**: ~2 minutes per company scrape

Happy job hunting! 🎯
