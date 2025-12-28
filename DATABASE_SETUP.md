# Database Setup Complete ✅

## What You Have Now

### 1. Database Structure
- **Database**: `job_finder`
- **Tables**: 
  - `companies` - stores company info
  - `jobs` - stores job listings with scores, status tracking

### 2. Database Client (`utils/db_client.py`)
**This is the ONLY file that talks to the database.**

#### Main Class: `JobFinderDB`

**Company Methods:**
- `upsert_company()` - Add or update company
- `get_company()` - Get company by name
- `delete_company()` - Delete company and all its jobs

**Job Methods:**
- `upsert_job()` - Add or update job (auto-deduplicates by URL)
- `get_job()` - Get job by URL
- `get_jobs_by_company()` - Get all jobs for a company
- `update_job_status()` - Update application status (new/applied/rejected/interview)
- `update_job_scores()` - Update for_me_score and for_them_score
- `delete_job()` - Delete a job
- `bulk_upsert_jobs()` - Batch insert/update jobs

**Helper Function for Scrapers:**
```python
save_jobs_to_db(company_name, company_domain, careers_url, jobs, db_connection_string)
```

### 3. Netflix Scraper Integration

The Netflix scraper (`tools/scrapers/netflix.py`) now supports automatic database saving:

```python
# Option 1: Just scrape (returns jobs)
jobs = await scrape_netflix_jobs(location="United Kingdom")

# Option 2: Scrape AND save to database automatically
jobs = await scrape_netflix_jobs(
    location="United Kingdom",
    save_to_db=True,
    db_connection_string=os.getenv("DATABASE_URL")
)
```

### 4. Key Features

✅ **No Duplicates** - Uses `job_url` as unique identifier
✅ **Auto-Update** - If job exists, updates fields instead of creating duplicate
✅ **Cascading Delete** - Deleting company removes all its jobs
✅ **Status Tracking** - Track application progress (new → applied → interview)
✅ **Scoring** - Store for_me_score and for_them_score for each job
✅ **Safe** - All database operations are async and use connection pooling

## How to Use (For Any Scraper)

### Pattern 1: Simple (Recommended)
```python
from utils.db_client import save_jobs_to_db
import os

# Convert scraped jobs to dicts
job_dicts = [
    {
        "title": job.title,
        "job_url": job.job_url,
        "location": job.location,
        "department": job.department,
        # ... other fields
    }
    for job in scraped_jobs
]

# Save to database
result = await save_jobs_to_db(
    company_name="CompanyName",
    company_domain="company.com",
    careers_url="https://company.com/careers",
    jobs=job_dicts,
    db_connection_string=os.getenv("DATABASE_URL")
)

print(f"Inserted: {result['inserted']}, Updated: {result['updated']}")
```

### Pattern 2: Advanced (Manual Control)
```python
from utils.db_client import JobFinderDB
import os

db = JobFinderDB(os.getenv("DATABASE_URL"))
await db.connect()

try:
    # Create company
    company_id = await db.upsert_company(
        name="CompanyName",
        domain="company.com",
        careers_url="https://company.com/careers"
    )
    
    # Add jobs one by one
    for job in scraped_jobs:
        await db.upsert_job(
            company_id=company_id,
            title=job.title,
            job_url=job.job_url,
            location=job.location,
            # ... other fields
        )
    
    # Update status after applying
    await db.update_job_status(job_url, "applied")
    
    # Update scores after evaluation
    await db.update_job_scores(job_url, for_me_score=85, for_them_score=90)
    
finally:
    await db.close()
```

## Testing

Run database tests:
```bash
python test_db_only.py
```

Check database in DBeaver:
```
Host: localhost
Port: 5432
Database: job_finder
Username: job_finder_user
Password: your_secure_password
```

## Files Created

✅ `database/schema.sql` - Table definitions
✅ `utils/db_client.py` - Database client (ONLY file that touches DB)
✅ `tools/scrapers/netflix.py` - Integrated with database
✅ `scripts/check_database.py` - Utility to view DB contents
✅ `test_db_only.py` - Database tests
✅ `.env` - Contains DATABASE_URL

## Next Steps

1. **Use this pattern for other scrapers** - Copy the Netflix integration pattern
2. **Track applications** - Use `update_job_status()` when you apply
3. **Score jobs** - Use `update_job_scores()` after evaluation agents run
4. **Query in DBeaver** - View and analyze jobs visually

---

**Status: Ready to use! 🚀**
