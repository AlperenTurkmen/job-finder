# job-finder

A **multi-agent job application automation system** with a web interface for finding and applying to relevant jobs.

## Features

### 🌐 Web Interface (NEW!)
- **User-friendly web app** for finding jobs matched to your profile
- Select companies, enter skills and preferences
- Real-time scraping and intelligent job matching
- See why each job matches your profile

### 🤖 Automation Pipeline
- **Multi-agent system** for automated job applications
- LLM-powered scraping, scoring, and cover letter generation
- Playwright-based form filling

## Quick Start

### Web Interface (Recommended)

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Set up environment (see .env.example)
cp .env.example .env
# Edit .env with your DATABASE_URL, GEMINI_API_KEY, etc.

# Set up database (see DATABASE_SETUP.md)
psql -d jobfinder -f database/schema.sql

# Start the web application
./start_web.sh
# Or: python web/app.py
```

Visit http://localhost:5000 to use the web interface.

See [web/README.md](web/README.md) for detailed documentation.

### Command-Line Pipeline

```bash
# Set API key
echo "GEMINI_API_KEY=your_key_here" > .env

# Run the pipeline
python pipeline/run_apply_pipeline.py \
  --companies-csv data/companies/example_companies.csv \
  --max-companies 1 \
  --max-urls 3 \
  --apply-threshold 50
```

## Project Structure

```
job-finder/
├── web/                       # Web application (NEW!)
│   ├── app.py                 # Flask web server
│   ├── scraper_orchestrator.py
│   ├── job_matcher.py         # Job matching logic
│   └── templates/             # HTML templates
├── agents/                    # All agents in unified structure
│   ├── discovery/             # Find careers pages and extract jobs
│   ├── scoring/               # Evaluate roles for fit
│   ├── cover_letter/          # Generate and refine cover letters
│   ├── common/                # Shared utilities (Gemini client, profile)
│   └── auto_apply/            # Playwright-based form filling
├── pipeline/                  # Command-line entry points
│   ├── run_apply_pipeline.py  # Full pipeline orchestrator
│   └── scrape_and_normalize.py
├── utils/                     # Shared utilities (logging, db_client)
├── tools/                     # Search utilities and scrapers
│   └── scrapers/              # Company-specific scrapers
├── database/                  # Database schema
├── config/                    # Prompts and workflows
├── data/                      # Input/output data
└── tests/                     # Pytest tests
```

## Configuration

| Environment Variable | Purpose |
|---------------------|---------|
| `GEMINI_API_KEY` | Required for LLM calls |
| `MOCK_LLM_RESPONSES` | Path to mock JSON for offline testing |
| `LOG_LEVEL` | Logging verbosity (default: INFO) |

## Input Files

- `data/companies/*.csv` - Company name + careers URL
- `data/profile.json` - Your profile for scoring
- `data/user_uploaded_cv.pdf` - Your CV

## Output Files

- `data/roles/*.json` - Normalized job postings
- `data/output/final_cover_letter.md` - Generated cover letter
- `data/output/results.json` - Pipeline summary
