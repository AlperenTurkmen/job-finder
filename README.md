# job-finder

A **multi-agent job application automation system** built on Gemini LLMs and Playwright.

## What it does

```
Companies CSV → Job URL Extraction → Scrape & Normalize → Role Scoring → Cover Letter → Auto-Apply
```

1. **Extracts job URLs** from company careers pages using Playwright + LLM filtering
2. **Scrapes & normalizes** job postings into structured JSON
3. **Scores roles** against your profile (For-Me / For-Them scores)
4. **Generates cover letters** tailored to each role
5. **Auto-applies** via Playwright browser automation

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

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
├── agents/                    # All agents in unified structure
│   ├── discovery/             # Find careers pages and extract jobs
│   ├── scoring/               # Evaluate roles for fit
│   ├── cover_letter/          # Generate and refine cover letters
│   ├── common/                # Shared utilities (Gemini client, profile)
│   └── auto_apply/            # Playwright-based form filling
├── pipeline/                  # Main entry points
│   ├── run_apply_pipeline.py  # Full pipeline orchestrator
│   └── scrape_and_normalize.py
├── utils/                     # Shared utilities (logging, mock_llm)
├── tools/                     # Search utilities (Google, DuckDuckGo)
├── config/
│   ├── prompts/               # LLM prompt templates
│   └── workflows/             # ADK workflow YAML files
├── data/                      # Input/output data
│   ├── companies/             # Input company CSVs
│   ├── roles/                 # Normalized role JSONs
│   └── output/                # Pipeline results
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
