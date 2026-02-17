# Job Finder

A **multi-agent job application automation system** with a web interface for finding and applying to relevant jobs automatically.

> 🚀 **New to Job Finder?** Check out [GET_STARTED.md](GET_STARTED.md) for a quick 3-step setup!

## Features

- 🌐 **Web Interface** - User-friendly app for job discovery and matching
- 🤖 **AI-Powered** - LLM-based scraping, scoring, and cover letter generation
- 🎯 **Smart Matching** - Intelligent job matching based on your profile
- 🏢 **Multi-Company** - Support for Netflix, Meta, Google, IBM, and more
- 📝 **Auto-Apply** - Automated form filling and job application submission
- 💾 **Database** - PostgreSQL storage for persistent job data

## Quick Start

### 5-Minute Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Set up PostgreSQL database
createdb jobfinder
psql -d jobfinder -f database/schema.sql

# 3. Configure environment
cp .env.example .env
# Edit .env and add:
#   DATABASE_URL=postgresql://user:password@localhost/jobfinder
#   GEMINI_API_KEY=your_api_key_here
#   FLASK_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")

# 4. Start the web application
./start_web.sh
```

Visit **http://localhost:5000** and start finding jobs!

### Alternative: Command-Line Usage

```bash
# Run the full pipeline
python pipeline/run_apply_pipeline.py \
  --companies-csv data/companies/example_companies.csv \
  --max-companies 1 \
  --max-urls 3
```

## Supported Companies

- Netflix
- Meta (Facebook)
- Google
- IBM
- Samsung
- Vodafone
- Rockstar Games
- Rebellion
- Miniclip

## How It Works

1. **Select Companies** - Choose companies you want to apply to
2. **Enter Preferences** - Your skills, location, job titles
3. **AI Scraping** - Real-time job extraction from career pages
4. **Smart Matching** - AI scores each job based on fit
5. **Auto-Apply** - Automated application submission (optional)

## Documentation

- [QUICKSTART.md](QUICKSTART.md) - Detailed setup guide
- [docs/DATABASE_SETUP.md](docs/DATABASE_SETUP.md) - Database configuration
- [docs/AUTO_APPLY_GUIDE.md](docs/AUTO_APPLY_GUIDE.md) - Auto-apply feature guide
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - System architecture
- [web/README.md](web/README.md) - Web app documentation

## Configuration

Create a `.env` file with these variables:

```bash
DATABASE_URL=postgresql://user:password@localhost/jobfinder
GEMINI_API_KEY=your_gemini_api_key
FLASK_SECRET_KEY=generate_random_32_byte_hex
PORT=5000  # optional
LOG_LEVEL=INFO  # optional
```

## Project Structure

```
job-finder/
├── web/                       # Flask web application
│   ├── app.py                 # Main web server
│   ├── scraper_orchestrator.py
│   ├── job_matcher.py
│   └── templates/             # HTML templates
├── agents/                    # Multi-agent system
│   ├── discovery/             # Job scraping and extraction
│   ├── scoring/               # Job evaluation
│   ├── cover_letter/          # Cover letter generation
│   ├── auto_apply/            # Form filling automation
│   └── common/                # Shared utilities
├── pipeline/                  # Command-line pipelines
├── tools/                     # Search and scraper utilities
│   └── scrapers/              # Company-specific scrapers
├── database/                  # PostgreSQL schema
├── data/                      # Input/output data
├── config/                    # Prompts and workflows
└── docs/                      # Documentation
```

## Requirements

- Python 3.9+
- PostgreSQL 12+
- Chromium (installed via Playwright)
- Gemini API key (get from [Google AI Studio](https://makersuite.google.com/app/apikey))

## Development

```bash
# Run tests
pytest tests/

# Check database connection
python scripts/check_database.py

# Scrape specific company
python scripts/quick_scrape.py --company netflix

# Score existing jobs
python scripts/score_jobs.py

# Generate cover letter
python scripts/generate_cover_letter.py
```

## Troubleshooting

### Database Connection Issues
```bash
# Verify PostgreSQL is running
pg_isready

# Check database exists
psql -l | grep jobfinder

# Verify schema
psql -d jobfinder -c "\dt"
```

### Playwright Issues
```bash
# Reinstall browsers
playwright install --force chromium
```

### API Key Issues
```bash
# Test Gemini API key
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print('✅ API key loaded' if os.getenv('GEMINI_API_KEY') else '❌ API key missing')"
```

## Contributing

This project uses:
- **Flask** for web framework
- **Playwright** for web scraping
- **Gemini LLM** for AI features
- **PostgreSQL** for data storage
- **asyncio** for async operations

## License

MIT License - See LICENSE file for details

## Support

For detailed guides, see the [docs/](docs/) directory:
- Setup & Installation: [QUICKSTART.md](QUICKSTART.md)
- Auto-Apply: [docs/AUTO_APPLY_GUIDE.md](docs/AUTO_APPLY_GUIDE.md)
- Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Database: [docs/DATABASE_SETUP.md](docs/DATABASE_SETUP.md)
- `data/output/final_cover_letter.md` - Generated cover letter
- `data/output/results.json` - Pipeline summary
