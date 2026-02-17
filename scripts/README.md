# Automation Scripts

This directory contains scripts for automated job scraping, question discovery, profile building, and batch auto-applying.

## Complete Workflow

```
1. Scrape Jobs → 2. Discover Questions → 3. Merge Questions → 4. Extract from CV → 5. Auto-Apply
```

## Scripts Overview

### 1. Job Scraping

#### `quick_scrape.py`
All-in-one scraper for single companies with optional question discovery.

```bash
# Basic scraping
python scripts/quick_scrape.py netflix --limit 10

# With question discovery
python scripts/quick_scrape.py meta --limit 5 --discover-questions

# Save to database + JSON
python scripts/quick_scrape.py google --limit 20
```

**Output:**
- `data/scraped_jobs/all_jobs_YYYYMMDD_HHMMSS.json`
- Database entries (if PostgreSQL available)

#### `scrape_to_json.py`
Multi-company scraper from CSV (database-free).

```bash
# Scrape companies from CSV
python scripts/scrape_to_json.py data/companies/target_companies.csv --limit 10

# Specific companies only
python scripts/scrape_to_json.py data/companies/all.csv --companies netflix,meta,google
```

**Output:** `data/scraped_jobs/all_jobs_YYYYMMDD_HHMMSS.json`

---

### 2. Question Discovery

#### `discover_all_questions.py`
Discovers application questions from job pages. **Now works without database!**

```bash
# From latest scraped JSON (recommended, no database needed)
python scripts/discover_all_questions.py --latest-json --limit 20

# From specific JSON file
python scripts/discover_all_questions.py --json data/scraped_jobs/all_jobs_*.json --limit 10

# From database (if PostgreSQL running)
python scripts/discover_all_questions.py --all --limit 50
python scripts/discover_all_questions.py --company netflix --limit 10

# Skip questions already discovered
python scripts/discover_all_questions.py --latest-json --no-skip-existing
```

**How it works:**
1. Loads jobs from JSON or database
2. Navigates to each job application page using Playwright
3. Extracts all form fields (name, email, work authorization, etc.)
4. Saves questions per company: `data/application_questions/{company}_questions.json`

**Example output:**
```
[1/20] Discovering questions for: Netflix - Senior Engineer
  ✓ Discovered 15 questions
[2/20] Discovering questions for: Meta - Product Manager
  ✓ Discovered 18 questions
...
```

**Output Files:**
- `data/application_questions/netflix_questions.json`
- `data/application_questions/meta_questions.json`
- etc.

---

### 3. Profile Building

#### `merge_all_questions.py`
**NEW!** Creates a universal profile template by merging questions from all companies.

```bash
python scripts/merge_all_questions.py

# Custom output paths
python scripts/merge_all_questions.py \
  --output data/my_questions.json \
  --template-output data/my_template.json
```

**What it does:**
1. Loads all question files from `data/application_questions/*.json`
2. Normalizes field names:
   - "First Name", "first name", "Given Name" → `first_name`
   - "E-mail", "Email Address" → `email`
3. Identifies common questions across companies
4. Categorizes into logical groups:
   - Essential: name, email, phone
   - Contact: LinkedIn, GitHub, portfolio, address
   - Work Eligibility: authorization, visa sponsorship
   - Professional: experience, current role, education
   - Preferences: salary expectations
5. Generates unified template

**Output:**
- `data/master_questions.json` - All questions with company mappings
- `data/user_profile_template.json` - Empty template ready to fill

**Example output:**
```
Step 1: Loading all question files...
Loaded netflix_questions.json: 15 questions
Loaded meta_questions.json: 18 questions
Loaded google_questions.json: 16 questions

Step 2: Merging and normalizing questions...
Processed 49 total questions
Identified 28 unique fields

Step 3: Categorizing questions...
  essential: 3 fields
  contact_info: 7 fields
  work_eligibility: 3 fields
  professional: 5 fields

✅ Saved merged questions to: data/master_questions.json
✅ Saved user template to: data/user_profile_template.json
```

#### `extract_from_cv.py`
**NEW!** Uses LLM to extract information from CV and auto-fill profile template.

```bash
# Basic: Just CV
python scripts/extract_from_cv.py --cv data/cv_library/resume.txt

# Advanced: CV + cover letters for better insights
python scripts/extract_from_cv.py \
  --cv data/cv_library/resume.txt \
  --cover-letters data/writing_samples/*.md

# Custom paths
python scripts/extract_from_cv.py \
  --cv my_resume.txt \
  --template data/user_profile_template.json \
  --output data/my_profile.json
```

**Supported formats:**
- `.txt` and `.md` files (direct support)
- `.pdf` files (convert first: `pdftotext resume.pdf resume.txt`)

**What it extracts:**
- Personal: name, email, phone
- Contact: LinkedIn, GitHub, portfolio, city, country  
- Professional: years of experience, current company/title, education
- Work eligibility: authorization mentions
- From cover letters: motivations, key strengths, career goals

**Example output:**
```
Step 1: Reading CV...
✅ Read 3,456 characters from CV

Step 2: Extracting information using LLM...
✅ Extracted 15 fields

Step 3: Extracting insights from 2 cover letters...
✅ Extracted insights from 2 cover letters

Step 4: Loading template...
✅ Loaded template

Step 5: Merging...
✅ Saved filled profile to: data/profile_filled.json

Extraction Summary
==================
Fields auto-filled: 15
Fields needing manual input: 13
Completion: 53.6%
```

**Next step:** Edit `data/profile_filled.json` to fill remaining fields, then save as `data/profile.json`

---

### 4. Auto-Apply

#### `batch_auto_apply.py`
**NEW!** Batch auto-apply to multiple jobs using your unified profile.

```bash
# Apply to all jobs in latest scrape
python scripts/batch_auto_apply.py \
  --latest-json \
  --profile data/profile.json \
  --cv data/cv_library/resume.pdf

# Apply to specific company only
python scripts/batch_auto_apply.py \
  --latest-json \
  --company netflix \
  --profile data/profile.json \
  --limit 5

# Dry-run mode (test without submitting)
python scripts/batch_auto_apply.py \
  --latest-json \
  --profile data/profile.json \
  --dry-run

# Custom delay between applications (default: 10 seconds)
python scripts/batch_auto_apply.py \
  --latest-json \
  --profile data/profile.json \
  --delay 30
```

**Safety features:**
- Asks for confirmation before submitting (unless dry-run)
- Delays between applications to avoid rate limiting
- Saves results to JSON for review
- Logs all actions

**Example output:**
```
Ready to Apply
==============
Jobs to apply: 15
Mode: LIVE (will submit applications)
Delay between applications: 10 seconds

⚠️  WARNING: This will submit real job applications!
Type 'yes' to proceed: yes

[1/15] Applying to: Netflix - Senior Engineer
✅ Successfully applied

[2/15] Applying to: Meta - Product Manager
✅ Successfully applied
...

Batch Application Complete
==========================
✅ Successful: 12
❌ Failed: 2
⏭️  Skipped: 1
```

**Output:** `data/batch_apply_results.json`

---

## Complete Workflow Example

Here's a full end-to-end example:

```bash
# 1. Scrape jobs from companies (no database needed!)
python scripts/quick_scrape.py netflix --limit 10
python scripts/quick_scrape.py meta --limit 10
python scripts/quick_scrape.py google --limit 10

# 2. Discover application questions from all scraped jobs
python scripts/discover_all_questions.py --latest-json --limit 30

# 3. Merge all questions into unified template
python scripts/merge_all_questions.py

# 4. Extract info from your CV to auto-fill template
python scripts/extract_from_cv.py \
  --cv data/cv_library/resume.txt \
  --cover-letters data/writing_samples/*.md

# 5. Manually fill remaining empty fields
# Edit data/profile_filled.json, save as data/profile.json

# 6. Test with dry-run
python scripts/batch_auto_apply.py \
  --latest-json \
  --profile data/profile.json \
  --dry-run \
  --limit 3

# 7. Apply for real!
python scripts/batch_auto_apply.py \
  --latest-json \
  --profile data/profile.json \
  --cv data/cv_library/resume.pdf \
  --limit 10
```

---

## File Outputs

```
data/
├── scraped_jobs/               # Step 1: Scraped job data
│   └── all_jobs_20260217_124734.json
├── application_questions/      # Step 2: Discovered questions per company
│   ├── netflix_questions.json
│   ├── meta_questions.json
│   └── google_questions.json
├── master_questions.json       # Step 3: Merged questions with mappings
├── user_profile_template.json  # Step 3: Empty template
├── profile_filled.json         # Step 4: Auto-filled from CV
├── profile.json                # Step 5: Final user profile (manual edits)
└── batch_apply_results.json    # Step 6: Application results
```

---

## Command Reference

### Scraping
```bash
quick_scrape.py <company> [--limit N] [--discover-questions]
scrape_to_json.py <csv_file> [--limit N] [--companies netflix,meta]
```

### Question Discovery
```bash
discover_all_questions.py --latest-json [--limit N] [--company NAME]
discover_all_questions.py --json <file> [--limit N]
discover_all_questions.py --all [--company NAME]  # Database mode
```

### Profile Building
```bash
merge_all_questions.py [--output <file>] [--template-output <file>]
extract_from_cv.py --cv <file> [--cover-letters <files>] [--output <file>]
```

### Auto-Apply
```bash
batch_auto_apply.py --latest-json --profile <file> [--cv <file>] [--limit N] [--dry-run]
batch_auto_apply.py --json <file> --profile <file> [--company NAME] [--delay N]
```

---

## Troubleshooting

### No Jobs with URLs
```bash
# Check if URLs were extracted
cat data/scraped_jobs/all_jobs_*.json | jq '.jobs_by_company.netflix[0].job_url'

# If empty, scraper needs fixing or manual URL addition
```

### Profile Fields Missing
```bash
# Check what was extracted
cat data/profile_filled.json | jq '.personal'

# Manually fill missing fields
vi data/profile_filled.json

# Save as active profile
cp data/profile_filled.json data/profile.json
```

### Failed Auto-Apply
```bash
# Check failure logs
tail -f logs/job_finder.log

# Review failed applications
cat answers/not_applied/*.json

# Try with dry-run to debug
python scripts/batch_auto_apply.py ... --dry-run --limit 1
```

---

## Best Practices

1. **Start small:** Test with `--limit 3` first
2. **Use dry-run:** Always test with `--dry-run` before going live
3. **Database optional:** All scripts work with JSON files only
4. **Regular updates:** Re-scrape and re-discover questions monthly
5. **Review profile:** Keep `data/profile.json` up to date
6. **Rate limiting:** Use `--delay` to avoid overwhelming servers
7. **Check ToS:** Some companies prohibit automated applications

---

## Environment Variables

```bash
# Required for LLM features (CV extraction, question parsing)
export GEMINI_API_KEY="your_api_key_here"

# Optional: Logging level
export LOG_LEVEL="DEBUG"

# Optional: Mock mode for testing
export MOCK_LLM_RESPONSES="path/to/mock_responses.json"
```

---

For complete workflow guide, see: [USER_ONBOARDING_GUIDE.md](../USER_ONBOARDING_GUIDE.md)
For auto-apply details, see: [AUTO_APPLY_GUIDE.md](../AUTO_APPLY_GUIDE.md)


Scripts for automating job scraping and question discovery.

## Quick Start

### Option 1: All-in-One Scrape & Discover

Scrape jobs and automatically discover application questions:

```bash
# Scrape from one company
python scripts/quick_scrape.py netflix --limit 5

# Scrape from multiple companies
python scripts/quick_scrape.py netflix meta google --limit 10

# Scrape from all companies
python scripts/quick_scrape.py --all-companies --limit 5

# See available companies
python scripts/quick_scrape.py --list-companies
```

This will:
1. ✅ Scrape jobs from selected companies
2. ✅ Save jobs to database
3. ✅ Automatically discover application questions
4. ✅ Save questions to `data/application_questions/`

### Option 2: Discover Questions for Existing Jobs

If you already have jobs in the database and just want to discover questions:

```bash
# Discover questions for all Netflix jobs
python scripts/discover_all_questions.py --company Netflix

# Discover questions for all jobs (up to 10)
python scripts/discover_all_questions.py --all --limit 10

# Discover for all jobs, skip already processed
python scripts/discover_all_questions.py --all
```

## Available Scripts

### `quick_scrape.py`

One-step solution for scraping and question discovery.

**Usage:**
```bash
python scripts/quick_scrape.py [companies...] [options]

Options:
  --all-companies           Scrape all available companies
  --limit N                 Max jobs per company (default: 100)
  --no-discover-questions   Skip question discovery
  --no-save-db             Don't save to database
  --list-companies         Show available companies
```

**Examples:**
```bash
# Quick test with 3 jobs from Netflix
python scripts/quick_scrape.py netflix --limit 3

# Production run: scrape and discover from multiple companies
python scripts/quick_scrape.py netflix meta samsung --limit 20

# Just scrape, no question discovery
python scripts/quick_scrape.py google --limit 10 --no-discover-questions
```

### `discover_all_questions.py`

Discover questions for jobs already in the database.

**Usage:**
```bash
python scripts/discover_all_questions.py [options]

Options:
  --company NAME           Process only this company
  --all                   Process all companies
  --limit N               Max jobs to process
  --no-skip-existing      Re-process even if questions exist
```

**Examples:**
```bash
# Find questions for all Netflix jobs
python scripts/discover_all_questions.py --company Netflix

# Process first 5 jobs from all companies
python scripts/discover_all_questions.py --all --limit 5

# Re-discover questions (overwrite existing)
python scripts/discover_all_questions.py --company Meta --no-skip-existing
```

## Workflow

### Automated Workflow (Recommended)

```bash
# 1. Scrape jobs and discover questions automatically
python scripts/quick_scrape.py netflix meta google --limit 10

# 2. Check discovered questions
ls -la data/application_questions/

# 3. View in web UI (start web server first)
PORT=8080 python web/app.py
# Visit: http://localhost:8080/questions

# 4. Download profile template from web UI
# Fill out data/user_answers.json

# 5. Auto-apply from web UI!
```

### Manual Workflow

```bash
# 1. Scrape jobs first (without discovery)
python scripts/quick_scrape.py netflix --limit 5 --no-discover-questions

# 2. Later, discover questions
python scripts/discover_all_questions.py --company Netflix

# 3. Continue with steps 3-5 from above
```

## Output

### Scraped Jobs
- **Database**: PostgreSQL (via `utils.db_client`)
- **Table**: `jobs`

### Discovered Questions
- **Location**: `data/application_questions/`
- **Format**: JSON files named `{company}_{job_title}.json`
- **Example**: `data/application_questions/netflix_software_engineer.json`

Each question file contains:
```json
{
  "company": "Netflix",
  "job_title": "Software Engineer",
  "job_url": "https://...",
  "questions_count": 12,
  "questions": [
    {
      "field_id": "first_name",
      "label": "First Name",
      "type": "text",
      "required": true,
      "options": []
    }
  ]
}
```

## Tips

1. **Start Small**: Test with `--limit 3` first
2. **Rate Limiting**: Scripts include 2-second delays between requests
3. **Skip Existing**: By default, already-discovered questions are skipped
4. **Check Logs**: Scripts provide detailed progress logs
5. **Web UI**: Use the web interface to view/manage questions

## Troubleshooting

### "No jobs found in database"
- Run `quick_scrape.py` first to scrape jobs
- Check database connection

### "Failed to discover questions"
- Some job pages may not have detectable forms
- Check the job URL manually
- Try different jobs from same company

### "Address already in use" (web server)
- Use different port: `PORT=8080 python web/app.py`
- Or disable AirPlay Receiver on macOS

### Rate Limiting
- Scripts have built-in delays
- If you get blocked, increase delay in code
- Reduce `--limit` value

## Next Steps

After discovering questions:

1. **View Questions**: Visit `/questions` page in web UI
2. **Download Template**: Click "Download Profile Template"
3. **Fill Answers**: Save as `data/user_answers.json`
4. **Add Your CV**: Place resume at `data/cv_library/resume.pdf`
5. **Auto-Apply**: Use "Auto-Apply" button on job detail pages

## Related Files

- `data/profile.json` - Your profile (already exists)
- `data/user_answers.json` - Your answers to questions (you create)
- `data/cv_library/resume.pdf` - Your CV (you provide)
- `data/application_questions/` - Discovered questions (auto-generated)

For more details, see:
- [AUTO_APPLY_GUIDE.md](../AUTO_APPLY_GUIDE.md) - Complete usage guide
- [AUTO_APPLY_IMPLEMENTATION.md](../AUTO_APPLY_IMPLEMENTATION.md) - Technical details
