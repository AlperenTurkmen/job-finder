# Quick Start Guide - Job Finder Web Application

This guide will help you get the Job Finder web application running in minutes.

## Prerequisites Checklist

- [ ] Python 3.9 or higher installed
- [ ] PostgreSQL installed and running
- [ ] Git (to clone the repository)

## Step-by-Step Setup

### 1. Install Python Dependencies

```bash
cd /Users/alperenturkmen/Documents/GitHub/job-finder
pip install -r requirements.txt
```

### 2. Install Playwright Browser

```bash
playwright install chromium
```

### 3. Set Up PostgreSQL Database

```bash
# Create database
createdb jobfinder

# Run schema
psql -d jobfinder -f database/schema.sql

# Verify it worked
psql -d jobfinder -c "SELECT count(*) FROM companies;"
```

### 4. Configure Environment Variables

```bash
# Copy example environment file
cp .env.example .env

# Edit .env file and add your credentials
# You need to set:
# - DATABASE_URL (e.g., postgresql://youruser:yourpass@localhost/jobfinder)
# - GEMINI_API_KEY (get from https://makersuite.google.com/app/apikey)
# - FLASK_SECRET_KEY (generate with: python -c "import secrets; print(secrets.token_hex(32))")
```

### 5. Start the Application

```bash
# Option 1: Use the startup script (recommended)
./start_web.sh

# Option 2: Run directly
python web/app.py
```

### 6. Open in Browser

Navigate to: **http://localhost:5000**

## First Time Usage

1. **Select Companies**: Choose which companies you want to scrape jobs from
2. **Enter Preferences**: 
   - Job titles you're interested in (e.g., "Software Engineer, Backend Developer")
   - Your skills (e.g., "Python, JavaScript, AWS, Docker")
   - Preferred location (e.g., "Amsterdam, London, Remote")
   - Work type preference (Remote/Hybrid/Onsite)
3. **Wait for Scraping**: The app will scrape job listings in real-time (takes 30-60 seconds)
4. **View Matches**: See jobs ranked by how well they match your profile

## Troubleshooting

### "DATABASE_URL not set"
- Make sure you created `.env` file from `.env.example`
- Verify DATABASE_URL is set correctly in `.env`

### "Cannot connect to database"
- Check if PostgreSQL is running: `pg_isready`
- Verify your database exists: `psql -l | grep jobfinder`
- Test connection: `psql -d jobfinder -c "SELECT 1"`

### "Playwright not found"
- Run: `pip install playwright && playwright install chromium`

### "No jobs found"
- Try selecting different companies
- Check the companies' career pages are accessible
- Look at the terminal/logs for scraping errors

### "GEMINI_API_KEY not set"
- Get API key from: https://makersuite.google.com/app/apikey
- Add to `.env` file: `GEMINI_API_KEY=your_key_here`

## What Each File Does

- `web/app.py` - Main Flask application (routes, endpoints)
- `web/scraper_orchestrator.py` - Coordinates scraping across companies
- `web/job_matcher.py` - Scores jobs against your profile
- `web/templates/` - HTML templates for the UI
- `tools/scrapers/` - Company-specific scraping logic
- `utils/db_client.py` - Database interaction layer

## Next Steps

Once the app is running, you can:

1. **Customize matching logic**: Edit `web/job_matcher.py` to adjust scoring weights
2. **Add more companies**: Create new scrapers in `tools/scrapers/`
3. **Integrate with pipeline**: Use scraped jobs with the automation pipeline
4. **Export results**: Add export functionality for matched jobs

## Getting Help

- Check `web/README.md` for detailed documentation
- Look at existing scrapers in `tools/scrapers/` for examples
- Review database schema in `database/schema.sql`
- See `.github/copilot-instructions.md` for architecture overview

## Common Commands

```bash
# Start web app
./start_web.sh

# Check database
psql -d jobfinder

# View logs (increase verbosity)
export LOG_LEVEL=DEBUG
python web/app.py

# Test a single scraper
cd tools/scrapers
python netflix.py

# Run tests
pytest tests/
```

## Development Mode

For development, enable debug mode in `.env`:

```bash
FLASK_DEBUG=true
```

This enables:
- Auto-reload on code changes
- Detailed error pages
- Debug toolbar

Enjoy finding your dream job! 🎯
