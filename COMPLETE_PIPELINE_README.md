# Complete Job Scraping Pipeline

## Overview

This is the **complete end-to-end pipeline** that automates the entire process from company names to structured JSON job data:

```
Companies CSV → Job URLs → Scraped Content → Normalized JSON
```

## Pipeline Steps

### Step 1: Extract Job URLs from Careers Pages
- Reads company names and careers page URLs from CSV
- Uses Playwright to visit each careers page
- Extracts all links from the page
- Uses Gemini LLM to identify actual job posting URLs
- Appends URLs to `sample_urls.csv`

### Step 2: Scrape Job Postings
- Reads job URLs from `sample_urls.csv`
- Uses Playwright to scrape each job page (handles JavaScript)
- Uses Gemini LLM to clean content (removes navigation/headers)
- Saves raw text to intermediate CSV

### Step 3: Normalize to Structured JSON
- Reads scraped content from intermediate CSV
- Uses Gemini LLM to extract structured information
- Generates JSON files with schema:
  - Job details (title, company, location, seniority)
  - Responsibilities, requirements (must-have/nice-to-have)
  - Skills with importance ratings
  - Tech stack, years of experience, etc.

## Quick Start

### 1. Prepare Companies CSV

Create `data/companies/example_companies.csv` with company names and their careers page URLs:

```csv
Nike,https://careers.nike.com/jobs
Apple,https://jobs.apple.com/en-gb/search
Google,https://careers.google.com/jobs/results/
```

**Note**: No headers required, but you can add them if you want.

### 2. Run the Complete Pipeline

```bash
python pipeline/run_complete_pipeline.py
```

This will:
1. Extract job URLs from all companies in `data/companies/example_companies.csv`
2. Scrape and clean job content from those URLs
3. Generate structured JSON files in `data/roles/`

## Command-Line Options

```bash
python pipeline/run_complete_pipeline.py [OPTIONS]
```

### Input/Output Options
- `--companies-csv PATH`: Companies CSV file (default: `data/companies/example_companies.csv`)
- `--job-urls-csv PATH`: Intermediate job URLs CSV (default: `data/job_urls/sample_urls.csv`)
- `--output-dir PATH`: Output directory for JSON files (default: `data/roles/`)

### URL Extraction Options
- `--url-extraction-model MODEL`: Gemini model for URL filtering (default: `gemini-2.0-flash-exp`)
- `--url-extraction-timeout MS`: Page load timeout in milliseconds (default: 60000)
- `--max-companies N`: Limit companies to process (for testing)

### Scraping Options
- `--scrape-timeout SECONDS`: Timeout per job page scrape (default: 60.0)
- `--no-clean`: Disable LLM content cleaning (faster but noisier)
- `--max-urls N`: Limit job URLs to scrape (for testing)

### Normalization Options
- `--normalization-model MODEL`: Gemini model for normalization (default: `gemini-2.0-flash-exp`)
- `--temperature FLOAT`: LLM temperature (default: 0.0)
- `--prompt-file PATH`: Custom prompt template
- `--example-json PATH`: Example JSON for few-shot learning
- `--overwrite`: Overwrite existing JSON files

## Examples

### Test with Single Company
```bash
# Process only first company, scrape 5 URLs
python pipeline/run_complete_pipeline.py \
    --max-companies 1 \
    --max-urls 5
```

### Process Specific Companies File
```bash
# Use custom companies list
python pipeline/run_complete_pipeline.py \
    --companies-csv data/companies/tech_companies.csv \
    --output-dir data/tech_roles
```

### Disable LLM Cleaning (Faster)
```bash
# Skip LLM cleaning step (useful if pages are already clean)
python pipeline/run_complete_pipeline.py \
    --no-clean \
    --max-companies 3
```

### Full Production Run
```bash
# Process all companies with all URLs
python pipeline/run_complete_pipeline.py \
    --companies-csv data/companies/all_companies.csv \
    --output-dir data/production_roles \
    --overwrite
```

## End-to-End Apply Pipeline

Use `pipeline/run_apply_pipeline.py` to chain **every** stage automatically: careers pages → job URLs → scraping + normalization → role scoring → cover letter generation → auto-apply. This command wires the output of each step into the next one and only applies to roles whose For-Me and For-Them scores both meet the chosen threshold (default: 60).

```bash
python pipeline/run_apply_pipeline.py \
  --companies-csv data/companies/example_companies.csv \
  --job-urls-csv data/job_urls/example_run.csv \
  --output-dir data/roles \
  --apply-threshold 65 \
  --profile-json job-application-engine/input/profile.json \
  --cv-pdf job-application-engine/input/user_uploaded_cv.pdf
```

What happens:

1. **Job URL extraction** – reuses `agents/job_url_extractor_agent` to expand every careers page into individual postings (results appended to `--job-urls-csv`).
2. **Scrape + normalize** – runs `pipeline/scrape_and_normalize.py`, saving raw text to `data/roles_for_llm/*.csv` and structured JSON to `--output-dir`.
3. **Role scoring** – writes the normalized roles into `job-application-engine/input/all_jobs.json` and invokes the multi-agent `RoleEvaluationEngine` (For-Me + For-Them + insight) until every role is scored.
4. **Cover letter + auto-apply** – for any role whose scores are ≥ threshold, the script:
   - Updates `job-application-engine/input/role.json` with that role’s payload.
   - Calls `OrchestratorAgent` to produce a fresh cover letter at `job-application-engine/output/final_cover_letter.md`.
   - Executes `AutoApplyOrchestrator` with the generated letter, `profile.json`, and the latest CV PDF. The agent blocks for human input unless you pass `--no-wait-for-user`.

Outputs & artifacts:

- `results.json`: high-level summary (job URLs found, scrape counts, scoring stats, application outcomes).
- `job-application-engine/output/final_cover_letter.md`: last cover letter produced (per role as it runs).
- `job-application-engine/answers/{applied,not_applied}/a_*.json`: same audit artifacts created by the standalone auto-apply workflow.

Useful flags:

- `--apply-threshold` – adjust the min score per dimension.
- `--max-applications` – cap how many roles to auto-apply in one run.
- `--answers-json` – reuse a debug answers file for auto-apply (bypasses profile heuristics).
- `--no-wait-for-user` – fail fast if manual answers are required instead of pausing.

> **Prereqs**: Playwright browsers must be installed (`playwright install chromium`), BrowserMCP env vars must be configured for scraping, and Gemini API keys must be set for both the scraping and job-application-engine agents.

### Offline Mock Mode

Need a deterministic test bed with zero live network calls? Use the assets under `mock_site/` and `mock_data/`:

1. **Serve the mock careers site**

  ```bash
  cd mock_site
  python -m http.server 8000
  ```

  Leave this terminal running so `http://localhost:8000/careers.html` stays reachable.

2. **Point the pipeline at the mock CSV** and feed the canned LLM answers:

  ```bash
  export MOCK_LLM_RESPONSES=$(pwd)/mock_data/mock_llm_responses.json
  python pipeline/run_apply_pipeline.py \
    --companies-csv data/companies/mock_companies.csv \
    --job-urls-csv data/job_urls/mock_urls.csv \
    --intermediate-csv data/roles_for_llm/mock_scraped.csv \
    --output-dir data/roles_mock \
    --mock-normalized-json mock_data/normalized_roles.json \
    --mock-llm-responses mock_data/mock_llm_responses.json \
    --apply-threshold 60 \
    --profile-json job-application-engine/input/profile.json \
    --cv-pdf job-application-engine/input/user_uploaded_cv.pdf
  ```

  - The scraper pulls pages from the local HTTP server.
  - `mock_data/normalized_roles.json` supplies the structured JSON payloads, bypassing the normalization LLM.
  - Every Gemini-powered agent (scoring, cover letters, HR simulation, answer validity, etc.) consumes the canned responses in `mock_data/mock_llm_responses.json`.
  - The auto-apply workflow interacts with the inline form embedded in `mock_site/jobs/mockcorp-data-scientist.html`, so you get a full Playwright run without hitting a real ATS.

You can duplicate the HTML/JSON samples to model other scenarios—just add additional entries keyed by `job_url`, `role`, or `field_id` inside `mock_llm_responses.json`.

## Individual Components

You can also run each step independently:

### Step 1: Extract Job URLs Only
```bash
python agents/job_url_extractor_agent.py \
    data/companies/example_companies.csv \
    --output data/job_urls/my_urls.csv
```

### Step 2+3: Scrape and Normalize (if you already have URLs)
```bash
python pipeline/scrape_and_normalize.py \
    data/job_urls/my_urls.csv \
    --output-dir data/my_roles
```

### Step 3: Normalize Only (if you already have scraped content)
```bash
python agents/role_normaliser_agent.py \
    data/roles_for_llm/scraped.csv \
    --output-dir data/roles
```

## Output Structure

```
data/
├── companies/
│   └── example_companies.csv          # Input: Company names + careers URLs
├── job_urls/
│   └── sample_urls.csv                # Step 1 output: Individual job URLs
├── roles_for_llm/
│   └── sample_urls_scraped.csv        # Step 2 output: Scraped raw text
└── roles/
    ├── nike-software-engineer.json    # Step 3 output: Structured JSON
    ├── apple-ml-engineer.json
    └── google-swe.json
```

### JSON Schema Example

Each JSON file contains:
```json
{
  "job_id": "nike_software_engineer_portland",
  "company_name": "Nike",
  "role_name": "Software Engineer III",
  "location_names": ["Portland, OR"],
  "country": "US",
  "seniority": "Mid-level",
  "job_type": ["Full-time"],
  "remote": false,
  "responsibilities": [
    "Design and implement scalable microservices",
    "Collaborate with cross-functional teams"
  ],
  "must_have_requirements": [
    "5+ years software development experience",
    "Strong knowledge of Python and Java"
  ],
  "nice_to_have_requirements": [
    "Experience with Kubernetes",
    "ML/AI background"
  ],
  "skills": [
    {
      "name": "Python",
      "importance": 9,
      "years_of_experience": 5
    },
    {
      "name": "Kubernetes",
      "importance": 6,
      "years_of_experience": 2
    }
  ],
  "tech_stack": ["Python", "Java", "AWS", "Kubernetes"],
  "years_of_experience_required": 5,
  "raw_text": "Full unedited job posting text..."
}
```

## Performance & Cost Estimates

### For 5 Companies, ~50 Job URLs

**Time**: ~10-15 minutes
- URL extraction: ~1 min per company (5 min)
- Scraping: ~5-10 sec per URL (5-8 min)
- Normalization: ~5-30 sec per job (5-25 min)

**Cost** (using `gemini-2.0-flash-exp`):
- Currently: **FREE** (preview model)
- Future production: **~$0.50** for 50 jobs

### For 100 Companies, ~1000 Job URLs

**Time**: ~3-6 hours
**Cost**: **~$10** (future production pricing)

### Scaling to 10,000 Jobs

**Time**: ~30-60 hours (can parallelize)
**Cost**: **~$100** (future production pricing)

## Error Handling

The pipeline is resilient:
- **URL extraction failures**: Logs error, continues with other companies
- **Scraping timeouts**: Marks URL as failed in CSV, continues
- **LLM errors**: Logs error, attempts retry with exponential backoff
- **Partial completion**: All intermediate results are saved

To retry failed URLs:
1. Check `data/roles_for_llm/sample_urls_scraped.csv` for `status` column
2. Extract failed URLs to new CSV
3. Re-run pipeline with just those URLs

## Tips for Large Batches

### 1. Test First
```bash
# Validate with 1 company, 5 URLs
python pipeline/run_complete_pipeline.py --max-companies 1 --max-urls 5
```

### 2. Process in Batches
Split your companies CSV into smaller batches:
```bash
# Batch 1: Companies 1-20
python pipeline/run_complete_pipeline.py \
    --companies-csv data/companies/batch1.csv \
    --output-dir data/roles_batch1

# Batch 2: Companies 21-40
python pipeline/run_complete_pipeline.py \
    --companies-csv data/companies/batch2.csv \
    --output-dir data/roles_batch2
```

### 3. Monitor Progress
```bash
# Run with output piped to log file
python pipeline/run_complete_pipeline.py 2>&1 | tee pipeline.log
```

### 4. Resume After Failure
URLs are appended to `sample_urls.csv`, so re-running the same companies won't create duplicates.

## Troubleshooting

### "No links found on careers page"
- Check if the URL is correct
- Some sites may block headless browsers (try different user-agent)
- Page might require JavaScript - Playwright should handle this

### "LLM identified 0 job posting URLs"
- The LLM couldn't identify job-specific links
- Try manually checking the careers page structure
- May need to adjust the filtering prompt

### "Timeout loading page"
- Increase timeout: `--url-extraction-timeout 120000` (120 seconds)
- `--scrape-timeout 120`

### "API Key not found"
- Ensure `.env` file exists with `GEMINI_API_KEY=your_key`
- Or set environment variable: `export GEMINI_API_KEY=your_key`

### Rate Limiting
- Pipeline includes 2-second delays between companies
- For large batches, consider longer delays or split into multiple runs

## Integration with Existing Pipeline

This complete pipeline integrates with your existing system:

```
OLD: run_all.py (company search → careers page → role extraction)
NEW: run_complete_pipeline.py (companies CSV → job URLs → scrape → normalize)
```

Both can coexist:
- Use `run_all.py` when you want to search for companies and extract from feeds/APIs
- Use `run_complete_pipeline.py` when you already have companies/URLs and want to scrape individual job pages

## Related Files

- `agents/job_url_extractor_agent.py`: Step 1 - URL extraction logic
- `pipeline/scrape_and_normalize.py`: Steps 2+3 - Scraping and normalization
- `job_scraper_agent.py`: Core scraping functionality
- `agents/role_normaliser_agent.py`: Normalization logic
- `content_cleaner.py`: LLM-based content cleaning
