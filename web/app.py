"""
Flask Web Application for Job Finder

Provides a web interface for users to:
1. Select companies they're interested in
2. Enter their job search preferences
3. View scraped jobs matched to their profile
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from datetime import datetime
import json
import asyncio
from typing import Optional
from functools import wraps

from utils.db_client import DatabaseClient
from utils.logging import get_logger

logger = get_logger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-in-production")

# Available scrapers
AVAILABLE_COMPANIES = [
    {"id": "netflix", "name": "Netflix"},
    {"id": "meta", "name": "Meta"},
    {"id": "samsung", "name": "Samsung"},
    {"id": "vodafone", "name": "Vodafone"},
    {"id": "rockstar", "name": "Rockstar Games"},
    {"id": "rebellion", "name": "Rebellion"},
    {"id": "miniclip", "name": "Miniclip"},
    {"id": "google", "name": "Google"},
    {"id": "ibm", "name": "IBM"},
]


def async_route(f):
    """Decorator to handle async route functions."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapped


@app.route("/")
def index():
    """Landing page."""
    return render_template("index.html", companies=AVAILABLE_COMPANIES)


@app.route("/preferences", methods=["GET", "POST"])
def preferences():
    """User preferences form."""
    if request.method == "POST":
        # Store preferences in session
        preferences = {
            "companies": request.form.getlist("companies"),
            "skills": request.form.get("skills", "").split(","),
            "location": request.form.get("location", ""),
            "remote_preference": request.form.get("remote_preference", ""),
            "job_titles": request.form.get("job_titles", "").split(","),
            "experience_level": request.form.get("experience_level", ""),
            "min_salary": request.form.get("min_salary", ""),
        }
        
        # Clean up empty strings
        preferences["skills"] = [s.strip() for s in preferences["skills"] if s.strip()]
        preferences["job_titles"] = [t.strip() for t in preferences["job_titles"] if t.strip()]
        
        session["preferences"] = preferences
        
        logger.info(f"User preferences saved: {len(preferences['companies'])} companies selected")
        
        return redirect(url_for("scrape"))
    
    return render_template("preferences.html", companies=AVAILABLE_COMPANIES)


@app.route("/scrape")
def scrape():
    """Trigger scraping for selected companies."""
    preferences = session.get("preferences")
    if not preferences:
        return redirect(url_for("preferences"))
    
    return render_template("scraping.html", companies=preferences["companies"])


@app.route("/api/scrape", methods=["POST"])
@async_route
async def api_scrape():
    """API endpoint to trigger scraping."""
    preferences = session.get("preferences")
    if not preferences:
        return jsonify({"error": "No preferences found"}), 400
    
    try:
        from web.scraper_orchestrator import ScraperOrchestrator
        
        orchestrator = ScraperOrchestrator()
        results = await orchestrator.scrape_companies(preferences["companies"])
        
        # Store in database
        db = DatabaseClient()
        await db.initialize()
        
        job_count = 0
        for company_results in results.values():
            for job in company_results:
                await db.insert_job(job)
                job_count += 1
        
        await db.close()
        
        logger.info(f"Scraped and stored {job_count} jobs")
        
        return jsonify({
            "success": True,
            "job_count": job_count,
            "results": {k: len(v) for k, v in results.items()}
        })
    
    except Exception as e:
        logger.error(f"Scraping failed: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/results")
@async_route
async def results():
    """Display matched job results."""
    preferences = session.get("preferences")
    if not preferences:
        return redirect(url_for("preferences"))
    
    try:
        from web.job_matcher import JobMatcher
        
        db = DatabaseClient()
        await db.initialize()
        
        # Get jobs from database
        company_ids = preferences["companies"]
        # Map company IDs to display names
        company_names = [c["name"] for c in AVAILABLE_COMPANIES if c["id"] in company_ids]
        jobs = await db.get_jobs_by_companies(company_names)
        
        # Match jobs to user profile using LLM scoring
        matcher = JobMatcher(preferences)
        matched_jobs = await matcher.match_jobs(jobs)
        
        # Update database with scores
        for job in matched_jobs:
            if job.get("job_url"):
                await db._db.update_job_scores(
                    job_url=job["job_url"],
                    for_me_score=int(job.get("for_me_score", 0)),
                    for_them_score=int(job.get("for_them_score", 0))
                )
        
        await db.close()
        
        # Sort by match score (average of both)
        matched_jobs.sort(key=lambda x: x.get("match_score", 0), reverse=True)
        
        return render_template(
            "results.html",
            jobs=matched_jobs,
            preferences=preferences,
            total_jobs=len(jobs)
        )
    
    except Exception as e:
        logger.error(f"Failed to load results: {e}", exc_info=True)
        return render_template("error.html", error=str(e))


@app.route("/job/<int:job_id>")
@async_route
async def job_detail(job_id: int):
    """Display detailed job information."""
    try:
        db = DatabaseClient()
        await db.initialize()
        
        job = await db.get_job_by_id(job_id)
        
        await db.close()
        
        if not job:
            return render_template("error.html", error="Job not found"), 404
        
        preferences = session.get("preferences", {})
        
        # Calculate scores if not already present
        for_me_score = job.get("for_me_score")
        for_them_score = job.get("for_them_score")
        match_score = None
        
        if for_me_score and for_them_score:
            match_score = round((for_me_score + for_them_score) / 2, 1)
        elif preferences:
            # Score this job on demand
            from web.job_matcher import JobMatcher
            matcher = JobMatcher(preferences)
            scored = await matcher.match_jobs([job])
            if scored:
                job = scored[0]
                for_me_score = job.get("for_me_score")
                for_them_score = job.get("for_them_score")
                match_score = job.get("match_score")
        
        return render_template(
            "job_detail.html", 
            job=job, 
            match_score=match_score,
            for_me_score=for_me_score,
            for_them_score=for_them_score
        )
    
    except Exception as e:
        logger.error(f"Failed to load job detail: {e}", exc_info=True)
        return render_template("error.html", error=str(e))


@app.route("/api/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    
    logger.info(f"Starting Job Finder web application on port {port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
