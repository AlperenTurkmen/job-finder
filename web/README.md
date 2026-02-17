# Job Finder Web Application

A web interface for finding relevant job opportunities from top tech companies. The application scrapes job listings in real-time, stores them in a database, and uses intelligent matching to find jobs that align with your skills and preferences.

## Features

- 🎯 **Smart Job Matching**: AI-powered matching based on skills, location, and preferences
- 🏢 **Multi-Company Support**: Scrapes jobs from 9 leading tech companies
- 💾 **Database Storage**: PostgreSQL database for persistent job storage
- 🎨 **Modern UI**: Clean, responsive interface
- ⚡ **Real-Time Scraping**: Fetches latest jobs on demand
- 📊 **Match Scoring**: Shows how well each job matches your profile

## Supported Companies

- Netflix
- Meta (Facebook)
- Samsung
- Vodafone
- Rockstar Games
- Rebellion
- Miniclip
- Google
- IBM

## Quick Start

### Prerequisites

1. PostgreSQL database (see [DATABASE_SETUP.md](../DATABASE_SETUP.md))
2. Python 3.9+
3. Chromium (for web scraping)

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Install Playwright browser
playwright install chromium

# Set up environment variables
cp .env.example .env
# Edit .env and add:
# - DATABASE_URL=postgresql://user:pass@localhost/jobfinder
# - GEMINI_API_KEY=your_gemini_key
# - FLASK_SECRET_KEY=your_secret_key
```

### Running the Application

```bash
# Start the web server
python web/app.py

# Or use the startup script
chmod +x start_web.sh
./start_web.sh
```

The application will be available at http://localhost:5000

## How It Works

1. **User Preferences**: Users select companies and enter their job search preferences
   - Companies of interest
   - Desired job titles
   - Skills and experience
   - Location preferences
   - Remote/hybrid/onsite preference

2. **Real-Time Scraping**: The app scrapes selected company career pages using Playwright
   - Extracts job listings
   - Normalizes data into consistent format
   - Stores in PostgreSQL database

3. **Intelligent Matching**: Jobs are scored based on:
   - Job title alignment (30%)
   - Skills match (40%)
   - Location match (15%)
   - Work type preference (15%)

4. **Results Display**: Jobs are ranked by match score
   - See why each job matches your profile
   - Direct links to apply
   - Detailed job information

## API Endpoints

- `GET /` - Landing page
- `GET /preferences` - User preferences form
- `POST /preferences` - Submit preferences
- `GET /scrape` - Scraping status page
- `POST /api/scrape` - Trigger scraping (AJAX)
- `GET /results` - Display matched jobs
- `GET /job/<job_id>` - Job detail page
- `GET /api/health` - Health check

## Architecture

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │
       v
┌─────────────┐      ┌──────────────────┐
│ Flask App   │─────>│ Scraper          │
│ (web/app.py)│      │ Orchestrator     │
└──────┬──────┘      └────────┬─────────┘
       │                      │
       │                      v
       │             ┌─────────────────┐
       │             │ Company Scrapers│
       │             │ (Playwright)    │
       │             └────────┬────────┘
       │                      │
       v                      v
┌─────────────────────────────────┐
│      PostgreSQL Database        │
│  - companies table              │
│  - jobs table                   │
└─────────────────────────────────┘
       │
       v
┌─────────────┐
│ Job Matcher │
│ (scoring)   │
└─────────────┘
```

## Configuration

Environment variables (`.env`):

```bash
# Required
DATABASE_URL=postgresql://user:password@localhost/jobfinder
GEMINI_API_KEY=your_gemini_api_key_here

# Optional
FLASK_SECRET_KEY=random_secret_for_sessions
FLASK_DEBUG=true
PORT=5000
```

## File Structure

```
web/
├── app.py                  # Main Flask application
├── scraper_orchestrator.py # Coordinates scraping
├── job_matcher.py          # Job matching logic
└── templates/              # HTML templates
    ├── base.html           # Base template
    ├── index.html          # Landing page
    ├── preferences.html    # Preferences form
    ├── scraping.html       # Scraping progress
    ├── results.html        # Job results
    ├── job_detail.html     # Job details
    └── error.html          # Error page
```

## Development

### Running Tests

```bash
pytest tests/
```

### Adding a New Scraper

1. Create scraper in `tools/scrapers/new_company.py`
2. Add mapping to `tools/scrapers/job_listing_normalizer.py`
3. Add company to `AVAILABLE_COMPANIES` in `web/app.py`
4. Add scraper to `SCRAPER_MAP` in `web/scraper_orchestrator.py`

### Customizing Match Algorithm

Edit `web/job_matcher.py` to adjust:
- Match scoring weights
- Skill matching logic
- Location matching rules

## Troubleshooting

**Database connection errors:**
- Verify DATABASE_URL is correct
- Ensure PostgreSQL is running
- Run schema: `psql -d jobfinder -f database/schema.sql`

**Scraping fails:**
- Check GEMINI_API_KEY is set
- Ensure Playwright is installed: `playwright install chromium`
- Check company websites are accessible

**No job matches:**
- Try broadening search criteria
- Check selected companies have jobs
- Verify skills are spelled correctly

## License

See main project README
