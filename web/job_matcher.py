"""
Job Matcher

LLM-powered job scoring using the existing For-Me and For-Them agents.
Provides dual-perspective scoring:
- For-Me Score: How good is this job for the candidate?
- For-Them Score: How good is the candidate for this job?
"""

from typing import Dict, List, Any, Optional
from pathlib import Path
import asyncio
from concurrent.futures import ThreadPoolExecutor

from agents.scoring.for_me_score_agent import ForMeScoreAgent
from agents.scoring.for_them_score_agent import ForThemScoreAgent
from agents.scoring.role_validation_agent import RoleValidationAgent
from utils.logging import get_logger

logger = get_logger(__name__)


class JobMatcher:
    """LLM-powered job matcher using existing scoring agents."""
    
    def __init__(self, preferences: Optional[Dict[str, Any]] = None):
        """Initialize scoring agents.
        
        Args:
            preferences: User preferences (optional, not used by LLM agents)
        """
        self.preferences = preferences or {}
        base_path = Path(__file__).parent.parent
        
        # Initialize the existing scoring agents
        self.validator = RoleValidationAgent(base_path)
        self.for_me_agent = ForMeScoreAgent(base_path)
        self.for_them_agent = ForThemScoreAgent(base_path)
        
        # Thread pool for running synchronous LLM calls
        self.executor = ThreadPoolExecutor(max_workers=3)
    
    async def match_jobs(self, jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Score jobs using LLM-based For-Me and For-Them agents.
        
        Args:
            jobs: List of job dictionaries from database
        
        Returns:
            List of jobs with for_me_score, for_them_score, and reasoning added
        """
        logger.info(f"Scoring {len(jobs)} jobs using LLM agents...")
        
        # Score jobs in parallel
        scored_jobs = await asyncio.gather(*[
            self._score_job(job) for job in jobs
        ])
        
        # Filter out None results (validation failures)
        valid_jobs = [j for j in scored_jobs if j is not None]
        
        logger.info(f"Successfully scored {len(valid_jobs)} jobs")
        return valid_jobs
    
    async def _score_job(self, job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Score a single job using LLM agents.
        
        Args:
            job: Job dictionary
        
        Returns:
            Job with scores added, or None if validation fails
        """
        try:
            # Run validation and scoring in thread pool (they're sync functions)
            loop = asyncio.get_event_loop()
            
            # Validate job has required fields
            validation = await loop.run_in_executor(
                self.executor,
                self.validator.evaluate,
                job
            )
            
            if not validation.is_valid:
                logger.debug(f"Skipping invalid job: {job.get('title')} - {validation.blocking_gaps}")
                return None
            
            # Get For-Me score
            for_me_result = await loop.run_in_executor(
                self.executor,
                self._get_for_me_score,
                job
            )
            
            # Get For-Them score
            for_them_result = await loop.run_in_executor(
                self.executor,
                self._get_for_them_score,
                job
            )
            
            # Create enhanced job dict
            job_copy = job.copy()
            job_copy["for_me_score"] = round(for_me_result.for_me_score, 1)
            job_copy["for_them_score"] = round(for_them_result.for_them_score, 1)
            job_copy["for_me_reasoning"] = for_me_result.reasoning
            job_copy["for_them_reasoning"] = for_them_result.reasoning
            job_copy["for_me_dimensions"] = for_me_result.dimension_scores
            job_copy["for_them_dimensions"] = for_them_result.dimension_scores
            
            # Calculate combined score (average of both)
            job_copy["match_score"] = round((for_me_result.for_me_score + for_them_result.for_them_score) / 2, 1)
            
            # Generate match reasons from both perspectives
            job_copy["match_reasons"] = self._build_match_reasons(for_me_result, for_them_result)
            
            return job_copy
            
        except Exception as e:
            logger.error(f"Error scoring job {job.get('title')}: {e}", exc_info=True)
            return None
    
    def _get_for_me_score(self, job: Dict[str, Any]):
        """Get For-Me score (runs in thread pool)."""
        return self.for_me_agent.evaluate(
            job_title=job.get("title", ""),
            job_description=self._build_job_description(job),
            company=job.get("company", "Unknown"),
            location=job.get("location")
        )
    
    def _get_for_them_score(self, job: Dict[str, Any]):
        """Get For-Them score (runs in thread pool)."""
        return self.for_them_agent.evaluate(
            job_title=job.get("title", ""),
            job_description=self._build_job_description(job),
            company=job.get("company", "Unknown"),
            location=job.get("location")
        )
    
    def _build_job_description(self, job: Dict[str, Any]) -> str:
        """Build a job description from available fields."""
        parts = []
        
        if job.get("department"):
            parts.append(f"Department: {job['department']}")
        
        if job.get("work_type"):
            parts.append(f"Work Type: {job['work_type']}")
        
        if job.get("description"):
            parts.append(f"\n{job['description']}")
        elif job.get("responsibilities"):
            parts.append(f"\nResponsibilities: {job['responsibilities']}")
        
        if job.get("tech_stack"):
            parts.append(f"\nTech Stack: {job['tech_stack']}")
        
        if job.get("other_locations"):
            parts.append(f"\nOther Locations: {', '.join(job['other_locations'])}")
        
        return "\n".join(parts) if parts else "No description available"
    
    def _build_match_reasons(self, for_me_result, for_them_result) -> List[str]:
        """Build match reasons from both scoring perspectives."""
        reasons = []
        
        # Extract key points from For-Me reasoning
        for_me_text = for_me_result.reasoning[:150] + "..." if len(for_me_result.reasoning) > 150 else for_me_result.reasoning
        reasons.append(f"🎯 For You: {for_me_text}")
        
        # Extract key points from For-Them reasoning
        for_them_text = for_them_result.reasoning[:150] + "..." if len(for_them_result.reasoning) > 150 else for_them_result.reasoning
        reasons.append(f"💼 For Employer: {for_them_text}")
        
        return reasons


def filter_jobs_by_threshold(
    jobs: List[Dict[str, Any]], 
    threshold: int = 50
) -> List[Dict[str, Any]]:
    """Filter jobs by minimum match score.
    
    Args:
        jobs: List of jobs with match_score
        threshold: Minimum match score (0-100)
    
    Returns:
        Filtered list of jobs
    """
    filtered = [job for job in jobs if job.get("match_score", 0) >= threshold]
    logger.info(f"Filtered to {len(filtered)} jobs with score >= {threshold}")
    return filtered
