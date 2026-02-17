# Job Finder - Complete System Architecture

## Web Application Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│                          USER JOURNEY                                 │
└──────────────────────────────────────────────────────────────────────┘

1. Landing Page (/)
   ↓
2. Preferences Form (/preferences)
   - Select companies (Netflix, Meta, Google, etc.)
   - Enter job titles (Software Engineer, etc.)
   - Add skills (Python, AWS, etc.)
   - Set location & remote preference
   ↓
3. Scraping Progress (/scrape)
   - Shows real-time scraping status
   - AJAX call to /api/scrape
   ↓
4. Job Results (/results)
   - Jobs ranked by match score (0-100%)
   - Shows why each job matches
   - Links to job detail pages
   ↓
5. Job Detail (/job/<id>)
   - Full job information
   - Apply link to company website


┌──────────────────────────────────────────────────────────────────────┐
│                     TECHNICAL ARCHITECTURE                            │
└──────────────────────────────────────────────────────────────────────┘

                         ┌──────────────┐
                         │   Browser    │
                         └───────┬──────┘
                                 │ HTTP
                                 ↓
                    ┌────────────────────────┐
                    │   Flask Application    │
                    │     (web/app.py)       │
                    └───────┬────────────────┘
                            │
                ┌───────────┼───────────┐
                │           │           │
                ↓           ↓           ↓
        ┌──────────┐  ┌─────────┐  ┌────────────┐
        │ Templates│  │ Session │  │   Routes   │
        │  (HTML)  │  │  Store  │  │ & API      │
        └──────────┘  └─────────┘  └─────┬──────┘
                                          │
                          ┌───────────────┼──────────────┐
                          │               │              │
                          ↓               ↓              ↓
                  ┌──────────────┐  ┌──────────┐  ┌──────────┐
                  │  Scraper     │  │   Job    │  │ Database │
                  │ Orchestrator │  │ Matcher  │  │  Client  │
                  └───────┬──────┘  └────┬─────┘  └─────┬────┘
                          │              │              │
                          ↓              │              ↓
              ┌────────────────────┐     │      ┌──────────────┐
              │ Company Scrapers   │     │      │ PostgreSQL   │
              │ (tools/scrapers/)  │     │      │   Database   │
              │                    │     │      │              │
              │ - netflix.py       │     │      │ - companies  │
              │ - meta.py          │     │      │ - jobs       │
              │ - google.py        │     │      └──────────────┘
              │ - etc.             │     │
              └────────┬───────────┘     │
                       │                 │
                       ↓                 │
              ┌────────────────────┐     │
              │   Playwright       │     │
              │  (Web Scraping)    │     │
              └────────┬───────────┘     │
                       │                 │
                       ↓                 │
              ┌────────────────────┐     │
              │  Job Normalizer    │     │
              │ (standardize data) │     │
              └────────┬───────────┘     │
                       │                 │
                       └────────┬────────┘
                                │
                                ↓
                        ┌───────────────┐
                        │ Normalized    │
                        │ Jobs (dicts)  │
                        └───────┬───────┘
                                │
                ┌───────────────┴───────────────┐
                │                               │
                ↓                               ↓
        ┌──────────────┐              ┌──────────────┐
        │  Database    │              │ Job Matcher  │
        │   Storage    │              │  (Scoring)   │
        └──────────────┘              └──────┬───────┘
                                             │
                                             ↓
                                    ┌─────────────────┐
                                    │ Ranked Results  │
                                    │ (with scores)   │
                                    └─────────────────┘


┌──────────────────────────────────────────────────────────────────────┐
│                      DATA FLOW DIAGRAM                                │
└──────────────────────────────────────────────────────────────────────┘

User Input                  Scraping                    Matching
─────────────              ─────────────               ──────────────

Companies: [Netflix]  →  Scraper Orchestrator    →   Job Matcher
Skills: [Python]      →  ↓                        →   ↓
Location: Amsterdam   →  Netflix Scraper         →   For each job:
Remote: Yes           →  ↓                        →   - Title match
                         Playwright              →   - Skills match
                         ↓                        →   - Location match
                         HTML → Parse            →   - Remote match
                         ↓                        →   ↓
                         Normalize               →   Score: 85%
                         ↓                        →   Reasons:
                         {                       →   - Title matches
                           title: "...",         →   - 3 skills match
                           location: "...",      →   - Remote role
                           company: "Netflix"    →   
                         }                       →   
                         ↓                        →   
                         PostgreSQL              →   
                                                 →   
                                                 →   Display results
                                                     sorted by score


┌──────────────────────────────────────────────────────────────────────┐
│                    COMPONENT RESPONSIBILITIES                         │
└──────────────────────────────────────────────────────────────────────┘

web/app.py
├─ Route handlers (/, /preferences, /results, etc.)
├─ Session management (user preferences)
├─ Coordinate scraping and matching
└─ Render templates

web/scraper_orchestrator.py
├─ Import company scrapers dynamically
├─ Run scrapers in parallel
├─ Normalize results
└─ Handle scraping errors

web/job_matcher.py
├─ Calculate match scores (0-100)
├─ Compare skills, titles, locations
├─ Generate match reasons
└─ Rank jobs by score

web/templates/
├─ base.html - Common layout and styling
├─ index.html - Landing page
├─ preferences.html - User input form
├─ scraping.html - Progress indicator
├─ results.html - Job listings
└─ job_detail.html - Single job view

utils/db_client.py
├─ PostgreSQL connection pooling
├─ CRUD operations for companies
├─ CRUD operations for jobs
└─ Bulk insert/update helpers

tools/scrapers/
├─ Company-specific scraping logic
├─ job_listing_normalizer.py - Data standardization
└─ Each scraper returns consistent format


┌──────────────────────────────────────────────────────────────────────┐
│                       DATABASE SCHEMA                                 │
└──────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────┐
│        companies            │
├─────────────────────────────┤
│ id (PK)                     │
│ name (UNIQUE)               │
│ domain                      │
│ careers_url                 │
│ location                    │
│ industry                    │
│ created_at                  │
│ updated_at                  │
└─────────────┬───────────────┘
              │ 1
              │
              │ N
┌─────────────▼───────────────┐
│           jobs              │
├─────────────────────────────┤
│ id (PK)                     │
│ company_id (FK)             │
│ title                       │
│ job_url (UNIQUE)            │
│ location                    │
│ other_locations (array)     │
│ department                  │
│ work_type                   │
│ job_id                      │
│ description                 │
│ for_me_score                │
│ for_them_score              │
│ status                      │
│ applied_at                  │
│ created_at                  │
│ updated_at                  │
└─────────────────────────────┘


┌──────────────────────────────────────────────────────────────────────┐
│                    MATCHING ALGORITHM                                 │
└──────────────────────────────────────────────────────────────────────┘

Input: User Preferences + Job Listing

Step 1: Title Match (30 points max)
  - Exact match in job title → 30 points
  - 2+ word match → 20 points
  - 1 word match → 10 points

Step 2: Skills Match (40 points max)
  - Count matching skills in job text
  - Score = (matched / total) * 40

Step 3: Location Match (15 points max)
  - User location in job location → 15 points
  - No match → 0 points

Step 4: Remote Preference (15 points max)
  - Exact match (remote/hybrid/onsite) → 15 points
  - Partial match (wanted remote, got hybrid) → 10 points
  - No match → 0 points

Final Score: Sum of all components (0-100)

Output: 
  - match_score: 85
  - match_reasons: [
      "Title matches 'software engineer'",
      "Matches your skills: Python, AWS, Docker",
      "Work type is remote"
    ]


┌──────────────────────────────────────────────────────────────────────┐
│                      DEPLOYMENT OPTIONS                               │
└──────────────────────────────────────────────────────────────────────┘

Local Development:
  ./start_web.sh
  → Runs on http://localhost:5000
  → Debug mode enabled
  → Auto-reload on changes

Production (Option 1 - Gunicorn):
  gunicorn -w 4 -b 0.0.0.0:8000 web.app:app
  → 4 worker processes
  → Production WSGI server
  → Behind nginx reverse proxy

Production (Option 2 - Docker):
  docker build -t job-finder-web .
  docker run -p 8000:8000 job-finder-web
  → Containerized deployment
  → Easy scaling
  → Environment isolation

Cloud (Option 3 - Heroku/Railway):
  git push heroku main
  → Automatic deployment
  → Managed PostgreSQL
  → HTTPS included
```
