# User Onboarding & Auto-Apply Workflow

Complete guide for onboarding users and building a universal profile for auto-applying to jobs.

## Overview

This system discovers application questions from **all companies**, creates a **unified profile template**, extracts information from your **CV and cover letters** automatically, and uses that profile to **auto-fill and submit applications**.

## Architecture

```
┌─────────────────┐
│ 1. Scrape Jobs  │ ──> JSON files (no database needed)
└────────┬────────┘
         │
         ▼
┌────────────────────────┐
│ 2. Discover Questions  │ ──> Collect all application questions
└────────┬───────────────┘
         │
         ▼
┌─────────────────────┐
│ 3. Merge Questions  │ ──> Unified template (name, email, etc.)
└────────┬────────────┘
         │
         ▼
┌──────────────────────┐
│ 4. Extract from CV   │ ──> Auto-fill what you can
└────────┬─────────────┘
         │
         ▼
┌─────────────────────┐
│ 5. Manual Fill      │ ──> User fills remaining fields
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ 6. Auto-Apply ✨    │ ──> Automated application submission
└─────────────────────┘
```

## Step-by-Step Workflow

### Step 1: Scrape Jobs from Companies

Scrape jobs from all companies you're interested in:

```bash
# Scrape from multiple companies
python scripts/quick_scrape.py netflix --limit 10
python scripts/quick_scrape.py meta --limit 10
python scripts/quick_scrape.py google --limit 10

# Or scrape from all companies in a CSV
python scripts/scrape_to_json.py data/companies/target_companies.csv --limit 10
```

**Output:** `data/scraped_jobs/all_jobs_YYYYMMDD_HHMMSS.json`

### Step 2: Discover Application Questions

Visit each job application page and collect all the questions asked:

```bash
# From latest scraped jobs (no database needed!)
python scripts/discover_all_questions.py --latest-json --limit 20

# Or from specific company
python scripts/discover_all_questions.py --company netflix --latest-json --limit 5
```

This will:
- Navigate to each job application page
- Extract all form fields (name, email, work authorization, etc.)
- Save questions for each company to `data/application_questions/{company}_questions.json`

**Example output:**
```
[1/20] Discovering questions for: Netflix - Senior Engineer
  ✓ Discovered 15 questions
[2/20] Discovering questions for: Meta - Product Manager
  ✓ Discovered 18 questions
...

Question Discovery Complete
  Successful: 20
  Failed: 0
  Total processed: 20
```

### Step 3: Merge All Questions into Universal Template

Combine questions from all companies and identify common fields:

```bash
python scripts/merge_all_questions.py
```

This will:
- Load all discovered questions from `data/application_questions/*.json`
- Normalize field names (e.g., "First Name", "first name", "Given Name" → `first_name`)
- Categorize questions into logical groups:
  - **Essential:** name, email, phone
  - **Contact:** LinkedIn, GitHub, portfolio, address
  - **Work Eligibility:** work authorization, visa sponsorship
  - **Professional:** experience, current role, education
  - **Preferences:** salary expectations
  - **Custom:** company-specific questions
- Generate unified template: `data/user_profile_template.json`
- Show statistics: which questions appear in most companies

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
  application_specific: 4 fields
  preferences: 2 fields
  other: 4 fields

Total unique fields identified: 28
Essential fields: 3
Can extract from CV: 12

✅ Saved merged questions to: data/master_questions.json
✅ Saved user template to: data/user_profile_template.json
```

**Template structure:**
```json
{
  "personal": {
    "first_name": {
      "question": "First Name",
      "field_type": "text",
      "required_by": "8 companies",
      "appears_in": ["Netflix", "Meta", "Google", ...],
      "answer": "",
      "can_extract_from_cv": true
    },
    "email": { ... }
  },
  "contact": {
    "linkedin": { ... },
    "github": { ... }
  },
  "professional": {
    "years_experience": { ... },
    "current_company": { ... }
  },
  "work_eligibility": {
    "work_authorization": { ... },
    "visa_sponsorship": { ... }
  }
}
```

### Step 4: Extract Information from CV

Use LLM to automatically extract information from your CV and cover letters:

```bash
# Basic: just CV
python scripts/extract_from_cv.py --cv data/cv_library/my_resume.pdf

# Advanced: CV + cover letters for better insights
python scripts/extract_from_cv.py \
  --cv data/cv_library/my_resume.txt \
  --cover-letters data/writing_samples/*.md
```

**Note:** Currently supports `.txt` and `.md` files. For PDF:
```bash
# Convert PDF to text first
pdftotext my_resume.pdf my_resume.txt

# Or use online converters
```

This will:
- Read your CV text
- Use Gemini LLM to extract structured fields (name, email, experience, etc.)
- Optionally analyze cover letters for motivations and strengths
- Auto-fill the template with extracted data
- Save to `data/profile_filled.json`

**Example output:**
```
Step 1: Reading CV from data/cv_library/resume.txt...
✅ Read 3,456 characters from CV

Step 2: Extracting information from CV using LLM...
✅ Extracted 15 fields

Step 3: Extracting insights from 2 cover letters...
✅ Extracted insights from 2 cover letters

Step 4: Loading user profile template...
✅ Loaded template

Step 5: Merging extracted data with template...
✅ Saved filled profile to: data/profile_filled.json

Extraction Summary
==================
Fields auto-filled: 15
Fields needing manual input: 13
Completion: 53.6%

Next Steps:
  1. Review: cat data/profile_filled.json
  2. Fill remaining empty fields manually
  3. Copy to profile.json
```

### Step 5: Manually Fill Remaining Fields

Open `data/profile_filled.json` and fill in any empty fields:

```json
{
  "personal": {
    "first_name": {
      "answer": "Alex",  // ✅ Extracted from CV
      "source": "cv"
    },
    "phone": {
      "answer": "",  // ❌ FILL THIS
      "can_extract_from_cv": true
    }
  },
  "work_eligibility": {
    "work_authorization": {
      "answer": "",  // ❌ FILL THIS
      "appears_in": ["Netflix", "Meta", "Google", ...]
    },
    "visa_sponsorship": {
      "answer": "",  // ❌ FILL THIS
      "required_by": "7 companies"
    }
  },
  "preferences": {
    "salary_expectations": {
      "answer": "",  // ❌ OPTIONAL
      "required_by": "3 companies"
    }
  }
}
```

**Tips:**
- Focus on fields where `required_by` is high (needed by many companies)
- Check `appears_in` to see which companies ask each question
- Some fields are optional but good to fill for completeness

Once complete, save as your active profile:

```bash
cp data/profile_filled.json data/profile.json
```

### Step 6: Auto-Apply to Jobs! 🚀

Now you're ready to auto-apply. The system will:
1. Navigate to job application page
2. Fill all form fields using your profile
3. Upload CV if required
4. Review before submitting (optional)
5. Submit application

**Option A: Command Line**

```bash
# Apply to specific job
python agents/auto_apply/run_auto_apply.py \
  --url "https://jobs.netflix.com/jobs/123456" \
  --profile data/profile.json \
  --cv data/cv_library/resume.pdf

# Batch apply to all scraped jobs
python scripts/batch_auto_apply.py --latest-json --profile data/profile.json
```

**Option B: Web Interface**

```bash
# Start web app
python web/app.py

# Visit http://localhost:8080
# Browse jobs → Click "Auto-Apply" → Confirm
```

**Safety Features:**
- Always asks for confirmation before submitting
- Shows you exactly what will be filled
- Logs all actions for review
- Can run in "dry-run" mode (fill but don't submit)

## File Structure

```
data/
├── scraped_jobs/               # Step 1: Scraped jobs
│   └── all_jobs_*.json
├── application_questions/      # Step 2: Discovered questions
│   ├── netflix_questions.json
│   ├── meta_questions.json
│   └── google_questions.json
├── master_questions.json       # Step 3: Merged questions
├── user_profile_template.json  # Step 3: Empty template
├── profile_filled.json         # Step 4: Auto-filled profile
├── profile.json                # Step 5: Final user profile
└── cv_library/                 # Your CV files
    ├── resume.pdf
    └── resume.txt
```

## Advanced Usage

### Updating Your Profile

As you apply to more companies, you might discover new questions:

```bash
# Discover questions from new companies
python scripts/discover_all_questions.py --latest-json --limit 10

# Re-merge to get new fields
python scripts/merge_all_questions.py

# Manually add new answers to your profile.json
```

### Customizing Applications

Each company might want slightly different answers:

```json
{
  "custom_answers": {
    "why_interested": {
      "answer": "Default answer for most companies",
      "company_specific": {
        "Netflix": "Specific answer for Netflix culture fit",
        "Meta": "Specific answer for Meta's mission"
      }
    }
  }
}
```

### Dry-Run Mode

Test auto-apply without actually submitting:

```bash
python agents/auto_apply/run_auto_apply.py \
  --url "https://jobs.example.com/apply" \
  --profile data/profile.json \
  --dry-run
```

This will:
- Fill all form fields
- Take screenshots
- Log all actions
- Stop before clicking "Submit"

## Troubleshooting

### "No jobs with URLs found"

The scraper didn't extract job URLs. Check:
```bash
# View scraped data
cat data/scraped_jobs/all_jobs_*.json | jq '.jobs_by_company.netflix[0]'

# If job_url is empty, scraper needs fixing or manual URL addition
```

**Solution:** Manually add URLs to the JSON, or fix the company scraper regex.

### "Failed to extract from CV"

The LLM couldn't parse your CV. Try:
- Convert PDF to text: `pdftotext cv.pdf cv.txt`
- Simplify formatting (remove tables, fancy layouts)
- Ensure CV has clear sections (Experience, Education, Contact)

### "Question discovery failed"

Application page might require login or have anti-bot protection:
- Check if you need to be logged in first
- Try with `--headless false` to see browser
- Some companies block automation (check their ToS)

### "Field not in template"

A company asks a unique question not in your template:
- Add field manually to `profile.json`
- Or add to `custom_answers` section
- Next time you run merge, it will be included

## Best Practices

1. **Start Small:** Scrape 5-10 jobs first, test the full workflow
2. **Review Questions:** Check `master_questions.json` to understand what companies ask
3. **Keep CV Updated:** Re-extract when you update your CV
4. **Company-Specific:** For your top choices, customize answers in profile
5. **Dry-Run First:** Test auto-apply in dry-run mode before going live
6. **Regular Updates:** Re-scrape and re-discover questions monthly

## Privacy & Ethics

⚠️ **Important Considerations:**

- **Terms of Service:** Some companies prohibit automated applications. Check ToS before using.
- **Data Privacy:** Your profile stays local. Never upload to third parties.
- **Honesty:** Auto-fill should use your real information, not fabricated data.
- **Review:** Always review what will be submitted, especially for top-choice companies.
- **Rate Limiting:** Add delays between applications to avoid overwhelming servers.

## Quick Reference

```bash
# 1. Scrape jobs
python scripts/quick_scrape.py <company> --limit 10

# 2. Discover questions (no database needed)
python scripts/discover_all_questions.py --latest-json --limit 20

# 3. Create universal template
python scripts/merge_all_questions.py

# 4. Extract from CV
python scripts/extract_from_cv.py --cv resume.txt --cover-letters writing_samples/*.md

# 5. Fill remaining fields manually
# Edit data/profile_filled.json, save as data/profile.json

# 6. Auto-apply!
python agents/auto_apply/run_auto_apply.py --url <job_url> --profile data/profile.json
```

## Getting Help

- Check logs: `tail -f logs/job_finder.log`
- Verbose mode: `export LOG_LEVEL=DEBUG`
- Issues: Review `answers/not_applied/` for failed applications
- Screenshots: Check `output/dom_snapshots/` for visual debugging

---

**Happy Job Hunting! 🎯**
