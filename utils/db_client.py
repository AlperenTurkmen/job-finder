"""PostgreSQL client for job finder database.

This is the ONLY module that should interact with the database.
All scrapers and agents should use this client for all database operations.
"""

from typing import Optional, List, Dict, Any
import os

import asyncpg

from utils.logging import get_logger

logger = get_logger(__name__)


class JobFinderDB:
    """Async PostgreSQL client for job finder database.
    
    This is a singleton database client that handles all CRUD operations.
    Use this for all database interactions from scrapers and agents.
    
    Usage:
        db = JobFinderDB(connection_string)
        await db.connect()
        try:
            company_id = await db.upsert_company("Netflix", "netflix.com")
            job_id = await db.upsert_job(company_id, "Engineer", "https://...")
        finally:
            await db.close()
    """
    
    def __init__(self, connection_string: str):
        """Initialize database client.
        
        Args:
            connection_string: PostgreSQL connection string
                Format: postgresql://user:password@host/database
        """
        self.connection_string = connection_string
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """Create database connection pool."""
        if not self.pool:
            self.pool = await asyncpg.create_pool(self.connection_string)
            logger.debug("Database connection pool created")
    
    async def close(self):
        """Close database connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.debug("Database connection pool closed")
    
    # ==================== COMPANY METHODS ====================
    
    async def upsert_company(
        self,
        name: str,
        domain: Optional[str] = None,
        careers_url: Optional[str] = None,
        location: Optional[str] = None,
        industry: Optional[str] = None,
        notes: Optional[str] = None
    ) -> int:
        """Insert or update a company. Returns company_id.
        
        If company exists (by name), updates its fields.
        If company doesn't exist, creates new entry.
        
        Args:
            name: Company name (unique identifier)
            domain: Company domain (e.g., "netflix.com")
            careers_url: URL to company careers page
            location: Company headquarters location
            industry: Industry/sector
            notes: Additional notes
            
        Returns:
            company_id (int)
        """
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow(
                """
                INSERT INTO companies (name, domain, careers_url, location, industry, notes)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (name) DO UPDATE SET
                    domain = COALESCE(EXCLUDED.domain, companies.domain),
                    careers_url = COALESCE(EXCLUDED.careers_url, companies.careers_url),
                    location = COALESCE(EXCLUDED.location, companies.location),
                    industry = COALESCE(EXCLUDED.industry, companies.industry),
                    notes = COALESCE(EXCLUDED.notes, companies.notes),
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
                """,
                name, domain, careers_url, location, industry, notes
            )
            logger.debug(f"Company '{name}' → ID {result['id']}")
            return result['id']
    
    async def get_company(self, name: str) -> Optional[Dict[str, Any]]:
        """Get company by name.
        
        Args:
            name: Company name
            
        Returns:
            Dict with company data or None if not found
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM companies WHERE name = $1",
                name
            )
            return dict(row) if row else None
    
    async def get_company_by_id(self, company_id: int) -> Optional[Dict[str, Any]]:
        """Get company by ID.
        
        Args:
            company_id: Company ID
            
        Returns:
            Dict with company data or None if not found
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM companies WHERE id = $1",
                company_id
            )
            return dict(row) if row else None
    
    async def delete_company(self, name: str) -> bool:
        """Delete company and all associated jobs (CASCADE).
        
        Args:
            name: Company name
            
        Returns:
            True if deleted, False if not found
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM companies WHERE name = $1",
                name
            )
            deleted = result.split()[-1] != "0"
            if deleted:
                logger.info(f"Deleted company '{name}' and all associated jobs")
            return deleted
    
    # ==================== JOB METHODS ====================
    
    async def upsert_job(
        self,
        company_id: int,
        title: str,
        job_url: str,
        location: Optional[str] = None,
        other_locations: Optional[List[str]] = None,
        department: Optional[str] = None,
        business_unit: Optional[str] = None,
        work_type: Optional[str] = None,
        job_id: Optional[str] = None,
        description: Optional[str] = None,
        salary_range: Optional[str] = None,
        status: str = "new"
    ) -> int:
        """Insert or update a job listing. Returns job_id or -1 if duplicate.
        
        Uses job_url as unique identifier - won't create duplicates.
        If job exists, updates all fields except created_at.
        
        Args:
            company_id: Foreign key to companies table
            title: Job title
            job_url: Unique URL to job posting (used for deduplication)
            location: Primary job location
            other_locations: List of additional locations for multi-location jobs
            department: Department name
            business_unit: Business unit
            work_type: "onsite", "remote", or "hybrid"
            job_id: External ATS job ID
            description: Full job description blob
            salary_range: Salary range string
            status: "new", "applied", "rejected", "interview"
            
        Returns:
            job_id (int) if inserted/updated, -1 if duplicate (no changes made)
        """
        async with self.pool.acquire() as conn:
            try:
                result = await conn.fetchrow(
                    """
                    INSERT INTO jobs (
                        company_id, title, job_url, location, other_locations,
                        department, business_unit, work_type, job_id, 
                        description, salary_range, status
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    ON CONFLICT (job_url) DO UPDATE SET
                        title = EXCLUDED.title,
                        location = EXCLUDED.location,
                        other_locations = EXCLUDED.other_locations,
                        department = EXCLUDED.department,
                        business_unit = EXCLUDED.business_unit,
                        work_type = EXCLUDED.work_type,
                        job_id = EXCLUDED.job_id,
                        description = EXCLUDED.description,
                        salary_range = EXCLUDED.salary_range,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id
                    """,
                    company_id, title, job_url, location, other_locations or [],
                    department, business_unit, work_type, job_id,
                    description, salary_range, status
                )
                logger.debug(f"Upserted job: {title} → ID {result['id']}")
                return result['id']
            except Exception as e:
                logger.error(f"Failed to upsert job '{title}': {e}")
                raise
    
    async def get_job(self, job_url: str) -> Optional[Dict[str, Any]]:
        """Get job by URL.
        
        Args:
            job_url: Job URL (unique identifier)
            
        Returns:
            Dict with job data or None if not found
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM jobs WHERE job_url = $1",
                job_url
            )
            return dict(row) if row else None
    
    async def get_jobs_by_company(
        self,
        company_name: str,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all jobs for a company, optionally filtered by status.
        
        Args:
            company_name: Company name
            status: Optional status filter ("new", "applied", etc.)
            
        Returns:
            List of job dicts
        """
        async with self.pool.acquire() as conn:
            if status:
                rows = await conn.fetch(
                    """
                    SELECT j.* FROM jobs j
                    JOIN companies c ON j.company_id = c.id
                    WHERE c.name = $1 AND j.status = $2
                    ORDER BY j.created_at DESC
                    """,
                    company_name, status
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT j.* FROM jobs j
                    JOIN companies c ON j.company_id = c.id
                    WHERE c.name = $1
                    ORDER BY j.created_at DESC
                    """,
                    company_name
                )
            return [dict(row) for row in rows]
    
    async def update_job_status(
        self,
        job_url: str,
        status: str,
        applied_at: Optional[str] = None
    ) -> bool:
        """Update job application status.
        
        Args:
            job_url: Job URL
            status: New status ("new", "applied", "rejected", "interview")
            applied_at: Optional timestamp for when applied
            
        Returns:
            True if updated, False if not found
        """
        async with self.pool.acquire() as conn:
            if applied_at:
                result = await conn.execute(
                    """
                    UPDATE jobs
                    SET status = $1, applied_at = $2, updated_at = CURRENT_TIMESTAMP
                    WHERE job_url = $3
                    """,
                    status, applied_at, job_url
                )
            else:
                result = await conn.execute(
                    """
                    UPDATE jobs
                    SET status = $1, updated_at = CURRENT_TIMESTAMP
                    WHERE job_url = $2
                    """,
                    status, job_url
                )
            updated = result.split()[-1] != "0"
            if updated:
                logger.info(f"Updated job status: {job_url} → {status}")
            return updated
    
    async def update_job_scores(
        self,
        job_url: str,
        for_me_score: Optional[int] = None,
        for_them_score: Optional[int] = None
    ) -> bool:
        """Update job scoring metrics.
        
        Args:
            job_url: Job URL
            for_me_score: How good this job is for the candidate (0-100)
            for_them_score: How good the candidate is for this job (0-100)
            
        Returns:
            True if updated, False if not found
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE jobs
                SET for_me_score = COALESCE($1, for_me_score),
                    for_them_score = COALESCE($2, for_them_score),
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_url = $3
                """,
                for_me_score, for_them_score, job_url
            )
            updated = result.split()[-1] != "0"
            if updated:
                logger.debug(f"Updated scores for {job_url}")
            return updated
    
    async def delete_job(self, job_url: str) -> bool:
        """Delete a job listing.
        
        Args:
            job_url: Job URL
            
        Returns:
            True if deleted, False if not found
        """
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM jobs WHERE job_url = $1",
                job_url
            )
            deleted = result.split()[-1] != "0"
            if deleted:
                logger.info(f"Deleted job: {job_url}")
            return deleted
    
    async def get_jobs_by_companies(
        self,
        company_names: List[str]
    ) -> List[Dict[str, Any]]:
        """Get all jobs for multiple companies.
        
        Args:
            company_names: List of company names
            
        Returns:
            List of job dicts with company info
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT 
                    j.*,
                    c.name as company
                FROM jobs j
                JOIN companies c ON j.company_id = c.id
                WHERE c.name = ANY($1::text[])
                ORDER BY j.created_at DESC
                """,
                company_names
            )
            return [dict(row) for row in rows]
    
    async def get_job_by_id(self, job_db_id: int) -> Optional[Dict[str, Any]]:
        """Get job by database ID.
        
        Args:
            job_db_id: Database ID (primary key)
            
        Returns:
            Dict with job data or None if not found
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 
                    j.*,
                    c.name as company
                FROM jobs j
                JOIN companies c ON j.company_id = c.id
                WHERE j.id = $1
                """,
                job_db_id
            )
            return dict(row) if row else None
    
    # ==================== BULK OPERATIONS ====================
    
    async def bulk_upsert_jobs(
        self,
        company_name: str,
        jobs: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """Bulk insert/update jobs for a company.
        
        This is the recommended method for scrapers to save jobs.
        Automatically handles company creation and deduplication.
        
        Args:
            company_name: Company name
            jobs: List of job dicts with fields:
                - title (required)
                - job_url (required)
                - location, department, work_type, etc. (optional)
                
        Returns:
            Dict with counts: {"inserted": N, "updated": M, "skipped": K}
        """
        # Get or create company
        company = await self.get_company(company_name)
        if not company:
            logger.error(f"Company '{company_name}' not found. Create it first with upsert_company()")
            return {"inserted": 0, "updated": 0, "skipped": len(jobs)}
        
        company_id = company['id']
        inserted = 0
        updated = 0
        
        for job_data in jobs:
            # Check if job already exists
            existing = await self.get_job(job_data['job_url'])
            
            job_id = await self.upsert_job(
                company_id=company_id,
                title=job_data['title'],
                job_url=job_data['job_url'],
                location=job_data.get('location'),
                department=job_data.get('department'),
                business_unit=job_data.get('business_unit'),
                work_type=job_data.get('work_type'),
                job_id=job_data.get('job_id'),
                description=job_data.get('description'),
                responsibilities=job_data.get('responsibilities'),
                qualifications=job_data.get('qualifications'),
                tech_stack=job_data.get('tech_stack'),
                job_type=job_data.get('job_type'),
                salary_range=job_data.get('salary_range'),
            )
            
            if existing:
                updated += 1
            else:
                inserted += 1
        
        logger.info(f"✅ Bulk upsert: {inserted} inserted, {updated} updated")
        return {"inserted": inserted, "updated": updated, "skipped": 0}


# ==================== SCRAPER HELPER FUNCTIONS ====================

async def save_jobs_to_db(
    company_name: str,
    company_domain: str,
    careers_url: str,
    jobs: List[Dict[str, Any]],
    db_connection_string: str
) -> Dict[str, int]:
    """Save scraped jobs to database (recommended for all scrapers).
    
    This is the primary function scrapers should use to save jobs.
    Handles company creation, deduplication, and bulk insertion.
    
    Args:
        company_name: Company name (e.g., "Netflix")
        company_domain: Company domain (e.g., "netflix.com")
        careers_url: URL to company careers page
        jobs: List of job dicts with at minimum:
            - title (str): Job title
            - job_url (str): Unique job URL
            Plus optional fields: location, department, work_type, etc.
        db_connection_string: PostgreSQL connection string from .env
        
    Returns:
        Dict with counts: {"inserted": N, "updated": M, "skipped": K}
        
    Example:
        >>> from utils.db_client import save_jobs_to_db
        >>> 
        >>> jobs = [
        ...     {"title": "Engineer", "job_url": "https://...", "location": "London"},
        ...     {"title": "Designer", "job_url": "https://...", "location": "Madrid"}
        ... ]
        >>> 
        >>> result = await save_jobs_to_db(
        ...     company_name="Netflix",
        ...     company_domain="netflix.com",
        ...     careers_url="https://explore.jobs.netflix.net/careers",
        ...     jobs=jobs,
        ...     db_connection_string=os.getenv("DATABASE_URL")
        ... )
        >>> print(f"Inserted: {result['inserted']}, Updated: {result['updated']}")
    """
    db = JobFinderDB(db_connection_string)
    await db.connect()
    
    try:
        # Ensure company exists
        company_id = await db.upsert_company(
            name=company_name,
            domain=company_domain,
            careers_url=careers_url
        )
        logger.info(f"Company '{company_name}' → ID {company_id}")
        
        # Bulk insert jobs
        result = await db.bulk_upsert_jobs(company_name, jobs)
        return result
        
    finally:
        await db.close()


# Simple alias for web app convenience
class DatabaseClient:
    """Convenience wrapper for JobFinderDB using environment variables."""
    
    def __init__(self):
        """Initialize with DATABASE_URL from environment."""
        self.connection_string = os.getenv("DATABASE_URL")
        if not self.connection_string:
            raise ValueError("DATABASE_URL environment variable not set")
        self._db = JobFinderDB(self.connection_string)
    
    async def initialize(self):
        """Connect to database."""
        await self._db.connect()
    
    async def close(self):
        """Close database connection."""
        await self._db.close()
    
    async def insert_job(self, job: Dict[str, Any]) -> int:
        """Insert a normalized job dict into database.
        
        Args:
            job: Normalized job dict with fields like:
                - company, title, job_url, location, etc.
        
        Returns:
            Job database ID
        """
        # Get or create company
        company_name = job.get("company", "Unknown")
        company_id = await self._db.upsert_company(name=company_name)
        
        # Insert job
        return await self._db.upsert_job(
            company_id=company_id,
            title=job.get("title", ""),
            job_url=job.get("job_url", ""),
            location=job.get("location"),
            other_locations=job.get("other_locations", []),
            department=job.get("department"),
            work_type=job.get("work_location_option"),
            job_id=job.get("job_id"),
        )
    
    async def get_jobs_by_companies(self, company_names: List[str]) -> List[Dict[str, Any]]:
        """Get jobs for multiple companies."""
        return await self._db.get_jobs_by_companies(company_names)
    
    async def get_job_by_id(self, job_id: int) -> Optional[Dict[str, Any]]:
        """Get job by ID."""
        return await self._db.get_job_by_id(job_id)
