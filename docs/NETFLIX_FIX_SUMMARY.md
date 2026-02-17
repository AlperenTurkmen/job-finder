# Netflix Scraper Fix - Job URL Extraction

## Problem
Netflix scraper was falling back to DOM parsing mode, which didn't extract job URLs. This left `job_url` fields empty in the scraped data, blocking question discovery.

## Root Cause
The original regex pattern was too strict:
- Required exact field ordering in embedded JSON
- Required exact spacing and formatting  
- Failed when Netflix's page structure varied slightly

## Solution

### 1. Improved Primary Regex (Lines 191-254)
**Old pattern (too strict):**
```python
job_pattern = r'\{"id":\s*(\d+),\s*"name":\s*"([^"]+)",\s*"location":\s*"([^"]*)",\s*"locations":\s*\[([^\]]*)\][^}]*"department":\s*"([^"]*)"...'
```

**New pattern (flexible):**
```python
job_objects_pattern = r'\{"id":\s*(\d+)[^}]{50,800}?"name":\s*"([^"]+)"[^}]{0,800}?\}'
```

**Key improvements:**
- Matches `id` and `name` fields with flexible spacing
- Allows 50-800 characters between id and name (handles field reordering)
- Uses separate extraction for additional fields (location, department, etc.)
- More resilient to HTML structure changes

### 2. Enhanced Fallback DOM Parsing (Lines 255-302)
When regex fails, fallback now:
- Extracts job IDs from any embedded JSON snippets
- Matches DOM titles with extracted IDs
- Builds job URLs even in fallback mode

**Before:**
```python
job_url=""  # Always empty in fallback
```

**After:**
```python
# Match titles with extracted job IDs
if title in job_ids_by_title:
    job_id = job_ids_by_title[title]
    job_url = f"https://explore.jobs.netflix.net/careers/job/{job_id}"
```

## Testing

### Test 1: Direct Scraper Test
```bash
python test_netflix_urls.py
```

Expected output:
```
Scraped 3 jobs

1. Associate, Production Finance UK Prep/Wrap - 12 month FTC
   Location: London, United Kingdom
   URL: https://explore.jobs.netflix.net/careers/job/790313667445
   Job ID: 790313667445

2. Senior Client Partner (Real Money Gaming)
   URL: https://explore.jobs.netflix.net/careers/job/790318451233
   ...

✅ 3/3 jobs have URLs
✅ URL extraction working!
```

### Test 2: Full Pipeline Test
```bash
python scripts/quick_scrape.py netflix --limit 3
```

Then check the output:
```bash
# Find latest scraped file
ls -t data/scraped_jobs/ | head -1

# Check if URLs are present
python -c "
import json
with open('data/scraped_jobs/all_jobs_LATEST.json') as f:
    data = json.load(f)
    job = data['jobs_by_company']['netflix'][0]
    print('Title:', job['title'])
    print('URL:', job.get('job_url', 'MISSING'))
"
```

Expected:
```
Title: Associate, Production Finance UK Prep/Wrap - 12 month FTC
URL: https://explore.jobs.netflix.net/careers/job/790313667445
```

### Test 3: Question Discovery
Once URLs are confirmed:
```bash
# Discover questions from scraped jobs
python scripts/discover_all_questions.py --latest-json --limit 3

# This should now work since jobs have URLs!
```

## Files Changed

1. **tools/scrapers/netflix.py** (Lines 185-302)
   - Improved regex pattern for JSON extraction
   - Enhanced fallback to extract URLs from DOM + embedded JSON snippets
   - More resilient to page structure changes

2. **test_netflix_urls.py** (New)
   - Simple test script to verify URL extraction
   - Runs scraper with 3 jobs and checks if URLs are present

3. **test_netflix_structure.py** (New)
   - Debugging tool to examine Netflix page structure
   - Helps understand why URLs weren't being extracted
   - Opens browser for manual inspection

## Verification Checklist

- [ ] Netflix scraper imports without errors: `python -c "from tools.scrapers.netflix import scrape_netflix_jobs; print('OK')"`
- [ ] Scraper extracts job URLs: Run `python test_netflix_urls.py`
- [ ] Jobs saved to JSON have URLs: Check `job_url` field in latest `data/scraped_jobs/*.json`
- [ ] Question discovery works: Run `python scripts/discover_all_questions.py --latest-json --limit 1`
- [ ] Full workflow succeeds: Scrape → Discover → Merge → Extract → Apply

## Next Steps

Once verified working:

1. **Scrape jobs from all companies:**
   ```bash
   python scripts/quick_scrape.py netflix --limit 10
   python scripts/quick_scrape.py meta --limit 10
   python scripts/quick_scrape.py google --limit 10
   ```

2. **Discover application questions:**
   ```bash
   python scripts/discover_all_questions.py --latest-json --limit 30
   ```

3. **Create unified profile:**
   ```bash
   python scripts/merge_all_questions.py
   python scripts/extract_from_cv.py --cv data/cv_library/resume.txt
   ```

4. **Start auto-applying!**
   ```bash
   python scripts/batch_auto_apply.py --latest-json --profile data/profile.json --dry-run
   ```

## Technical Details

**Why the old regex failed:**
- Netflix's page embeds job data as JSON in `<script>` tags or inline
- JSON objects have fields in various orders (not always id→name→location)
- Whitespace and formatting vary between page loads
- Old pattern required exact field sequence and spacing

**Why the new regex works:**
- Only requires `id` and `name` fields (minimum needed for URL)
- Flexible character matching between fields (`[^}]{50,800}?`)
- Extracts additional fields separately (not in one giant regex)
- Falls back gracefully if regex fails

**Job URL format:**
```
https://explore.jobs.netflix.net/careers/job/{JOB_ID}
```

Where `JOB_ID` is the numeric ID from the embedded JSON (e.g., `790313667445`).

## Troubleshooting

**If URLs still empty:**
1. Check page source: `python test_netflix_structure.py` (opens browser for 30s)
2. Look for embedded JSON manually: View page source, search for `"id":`
3. Check regex: Does the JSON structure match the pattern?

**If regex needs further adjustment:**
- The pattern is in `tools/scrapers/netflix.py` line 191
- Test regex at https://regex101.com/ with Netflix page source
- Key parts: `\{"id":\s*(\d+)` matches start, `"name":\s*"([^"]+)"` matches title

**If fallback also fails:**
- Check if position cards exist: Search for class `position-card` in page source
- Verify titles match between DOM and JSON: Run `test_netflix_structure.py`
- May need to add alternative selectors for title/location elements

---

**Status:** ✅ Fix implemented and ready for testing
**Date:** 2026-02-17
**Files Modified:** 1 (netflix.py)
**Files Added:** 2 (test scripts)
