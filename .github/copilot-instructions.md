# Copilot Instructions for job-finder

## Project Overview

A **multi-agent job application automation system** built on Gemini LLMs and Playwright. It scrapes company careers pages, normalizes job postings into structured JSON, scores roles against a user profile, generates tailored cover letters, and auto-applies via browser automation.

## Architecture

```
Companies CSV → Job URL Extraction → Scrape & Normalize → Role Scoring → Cover Letter → Auto-Apply
```

### Directory Structure

```
job-finder/
├── agents/                        # All agents in unified structure
│   ├── discovery/                 # Find careers pages and extract jobs
│   │   ├── careers_page_finder_agent.py
│   │   ├── job_url_extractor_agent.py
│   │   └── role_normaliser_agent.py
│   ├── scoring/                   # Evaluate roles for fit
│   │   ├── for_me_score_agent.py
│   │   ├── for_them_score_agent.py
│   │   ├── role_evaluation_engine.py
│   │   └── role_validation_agent.py
│   ├── cover_letter/              # Generate and refine cover letters
│   │   ├── cover_letter_generator_agent.py
│   │   ├── hr_simulation_agent.py
│   │   └── style_extractor_agent.py
│   ├── common/                    # Shared utilities
│   │   ├── gemini_client.py
│   │   ├── profile_agent.py
│   │   ├── orchestrator_agent.py
│   │   ├── insight_generator_agent.py
│   │   ├── role_analysis_agent.py
│   │   └── csv_writer_agent.py
│   └── auto_apply/                # Playwright-based form filling
│       ├── orchestrator.py
│       ├── playwright_client.py
│       ├── application_navigator_agent.py
│       └── ...
├── pipeline/                      # Orchestrators (2 files)
│   ├── run_apply_pipeline.py      # Main entry point - full pipeline
│   └── scrape_and_normalize.py    # Scraping step (Playwright)
├── utils/                         # Shared utilities (3 files)
│   ├── logging.py                 # Logging configuration
│   ├── content_cleaner.py         # LLM-based content cleaning
│   └── mock_llm.py                # Mock responses for offline testing
├── tools/                         # Search utilities
│   ├── google_search.py           # Google search API
│   ├── duckduckgo_search.py       # DuckDuckGo search
│   ├── html_parser.py             # HTML anchor extraction
│   └── import_roles.py            # Merge roles into all_jobs.json
├── config/
│   ├── prompts/                   # LLM prompt templates
│   └── workflows/                 # ADK workflow YAML files
├── data/                          # Input/output data
│   ├── companies/                 # Input company CSVs
│   ├── profile.json               # User profile for scoring
│   ├── roles/                     # Normalized role JSONs
│   └── output/                    # Pipeline results (results.json, all_jobs.json)
├── tests/                         # Pytest tests
├── mock_site/                     # Offline testing HTML
└── mock_data/                     # Mock LLM responses
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Set API key in .env
echo "GEMINI_API_KEY=your_key_here" > .env

# Run pipeline
python pipeline/run_apply_pipeline.py \
  --companies-csv data/companies/example_companies.csv \
  --max-companies 1 --max-urls 3 --apply-threshold 50
```

## Key Patterns

### Agent Structure
All agents follow this pattern (see [agents/discovery/job_url_extractor_agent.py](agents/discovery/job_url_extractor_agent.py)):
```python
from utils.logging import get_logger
logger = get_logger(__name__)

@dataclass(slots=True)
class ResultClass:
    ...

async def main_function(...):
    # Playwright for scraping, Gemini for intelligence
    async with async_playwright() as p:
        ...

if __name__ == "__main__":
    asyncio.run(main())
```

### Web Scraping
All scraping uses **Playwright** directly (no external browser services):
```python
from playwright.async_api import async_playwright

async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page()
    await page.goto(url, wait_until="networkidle")
    content = await page.inner_text("body")
```

### Mock Mode for Testing
```bash
export MOCK_LLM_RESPONSES=$(pwd)/mock_data/mock_llm_responses.json
python pipeline/run_apply_pipeline.py --mock-normalized-json mock_data/normalized_roles.json
```

### Data Contracts
Normalized roles require: `company`, `role`, `location`, `responsibilities`, `tech_stack`, `job_type`, `job_url`

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Required for LLM calls |
| `MOCK_LLM_RESPONSES` | Path to mock JSON for offline runs |
| `LOG_LEVEL` | Logging verbosity (default: INFO) |

## Adding New Agents

1. Place in appropriate `agents/` subpackage:
   - `agents/discovery/` - Job discovery and scraping
   - `agents/scoring/` - Role evaluation
   - `agents/cover_letter/` - Cover letter generation
   - `agents/common/` - Shared utilities
   - `agents/auto_apply/` - Form filling automation
2. Use `utils.logging.get_logger(__name__)` for logging
3. Use Playwright for web interaction, Gemini for intelligence
4. Support mock mode via `utils.mock_llm.mock_enabled()` / `get_mock_response(bucket)`
5. Expose primary functionality as an async function for orchestrator integration
