# Job Scraper & Normalizer Pipeline

This pipeline scrapes job postings from URLs and converts them to structured JSON format.

## Overview

The pipeline consists of two main steps:
1. **Scraping**: Extract raw job text from URLs using Playwright + LLM-based content cleaning
2. **Normalization**: Convert raw text to structured JSON using Gemini LLM

## Quick Start

### 1. Create a CSV with Job URLs

Create a CSV file with a `url` column:

```csv
url
https://www.rockstargames.com/careers/openings/position/6673341003
https://sec.wd3.myworkdayjobs.com/en-US/Samsung_Careers/details/Internship-Display_R100686
```

Save it to `data/job_urls/my_jobs.csv`

### 2. Run the Pipeline

```bash
python pipeline/scrape_and_normalize.py data/job_urls/my_jobs.csv
```

This will:
- Scrape each URL and extract clean job content
- Create an intermediate CSV at `data/roles_for_llm/my_jobs_scraped.csv`
- Convert raw text to structured JSON files in `data/roles/`

## Command-Line Options

```bash
python pipeline/scrape_and_normalize.py INPUT_CSV [OPTIONS]
```

### Required Arguments
- `INPUT_CSV`: Path to CSV file with `url` column

### Optional Arguments

#### Output Control
- `--output-dir PATH`: Directory for JSON output (default: `data/roles/`)
- `--intermediate-csv PATH`: Path for intermediate CSV (default: auto-generated)

#### Scraping Options
- `--scrape-timeout SECONDS`: Timeout per URL (default: 60.0)
- `--no-clean`: Disable LLM-based content cleaning (faster but noisier)
- `--max-urls N`: Limit number of URLs to process (for testing)

#### Normalization Options
- `--model MODEL`: Gemini model to use (default: `gemini-2.0-flash-exp`)
- `--temperature FLOAT`: LLM temperature (default: 0.0)
- `--prompt-file PATH`: Custom prompt template file
- `--example-json PATH`: Example JSON for few-shot learning
- `--overwrite`: Overwrite existing JSON files

## Examples

### Basic Usage
```bash
# Process all URLs in the CSV
python pipeline/scrape_and_normalize.py data/job_urls/sample_urls.csv
```

### Test with Limited URLs
```bash
# Process only first 5 URLs
python pipeline/scrape_and_normalize.py data/job_urls/large_list.csv --max-urls 5
```

### Custom Output Directory
```bash
# Save JSON files to custom location
python pipeline/scrape_and_normalize.py data/job_urls/tech_jobs.csv \
    --output-dir data/tech_roles
```

### Disable LLM Cleaning (Faster)
```bash
# Get raw scraped content without LLM filtering
# Useful when job pages are already clean
python pipeline/scrape_and_normalize.py data/job_urls/clean_sites.csv --no-clean
```

### Custom Normalization Prompt
```bash
# Use custom prompt for specialized extraction
python pipeline/scrape_and_normalize.py data/job_urls/academic_jobs.csv \
    --prompt-file config/prompts/academic_roles.txt \
    --example-json config/examples/academic_example.json
```

## Output Files

### Intermediate CSV
Location: `data/roles_for_llm/{input_name}_scraped.csv`

Columns:
- `url`: Original job posting URL
- `raw_text`: Extracted job text (cleaned if `--no-clean` not used)
- `status`: `success` or `failed: ErrorType`

### Structured JSON Files
Location: `data/roles/` (or `--output-dir`)

Each JSON file contains:
```json
{
  "job_id": "company_role_location",
  "company_name": "Company Name",
  "role_name": "Job Title",
  "location_names": ["City, Country"],
  "seniority": "Mid-level",
  "responsibilities": [...],
  "must_have_requirements": [...],
  "nice_to_have_requirements": [...],
  "skills": [
    {
      "name": "Python",
      "importance": 9,
      "years_of_experience": 3
    }
  ],
  "tech_stack": ["Python", "AWS", "PostgreSQL"],
  "raw_text": "Full original job posting text..."
}
```

## Cost Estimation

For scraping **10,000 jobs**:

### Current (Free Preview)
- `gemini-2.0-flash-exp` is **FREE** during preview
- Playwright is open source (free)
- **Total: $0**

### Future Production Pricing
- Scraping: Free (Playwright)
- LLM Cleaning: ~$2.50 (Flash 2.0 rates)
- Normalization: ~$4.91 (Flash 2.0 rates)
- **Total: ~$7.41 for 10,000 jobs**

## Architecture

```
┌─────────────────┐
│  Input CSV      │  (job URLs)
│  url            │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────┐
│  Step 1: Scraping               │
│  - Playwright (headless Chrome) │
│  - JavaScript rendering         │
│  - LLM content cleaning         │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  Intermediate CSV           │  (scraped raw text)
│  url | raw_text | status   │
└────────┬────────────────────┘
         │
         ▼
┌──────────────────────────────┐
│  Step 2: Normalization       │
│  - Gemini LLM extraction     │
│  - Structured JSON schema    │
└────────┬─────────────────────┘
         │
         ▼
┌─────────────────┐
│  JSON Files     │  (structured roles)
│  *.json         │
└─────────────────┘
```

## Error Handling

The pipeline continues processing even if some URLs fail:

- **URLValidationError**: Invalid URL format
- **BrowserMCPTimeoutError**: Page took too long to load
- **BrowserMCPError**: Scraping failed (network, etc.)

Failed URLs are logged with status in the intermediate CSV.

## Tips for Large Batches

### For 500+ Jobs

1. **Test First**: Use `--max-urls 10` to verify your URLs work
2. **Monitor Progress**: Check logs in real-time
3. **Resume Failed**: Re-run with only failed URLs from intermediate CSV
4. **Parallel Processing**: Split CSV and run multiple pipelines in parallel

### Performance

- **Scraping**: ~3-10 seconds per URL (depends on page load time)
- **LLM Cleaning**: ~3-5 seconds per job
- **Normalization**: ~5-30 seconds per job (depends on content length)

**Estimated time for 500 jobs**: 1.5-4 hours

## Troubleshooting

### "No URLs found in input CSV"
- Check your CSV has a `url` column header
- Verify URLs are not empty

### "Playwright browser not found"
```bash
playwright install chromium
```

### "GEMINI_API_KEY not found"
- Create `.env` file with `GEMINI_API_KEY=your_key_here`
- Or set environment variable: `export GEMINI_API_KEY=your_key`

### Timeout Errors
- Increase timeout: `--scrape-timeout 120`
- Check if site blocks headless browsers

### LLM Errors (Rate Limits)
- Add delays between requests
- Use smaller batches with `--max-urls`

## Related Scripts

- `main.py`: Scrape a single URL (quick testing)
- `job_scraper_agent.py`: Core scraping logic
- `agents/role_normaliser_agent.py`: Normalization logic
- `pipeline/run_all.py`: Full company discovery pipeline
