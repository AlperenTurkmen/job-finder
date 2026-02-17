"""
Question Discovery Service

Extracts application questions from job postings without applying.
Stores discovered questions for user profile completion.
"""

import asyncio
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict

from agents.auto_apply.orchestrator import AutoApplyOrchestrator
from agents.auto_apply.playwright_client import PlaywrightSession
from agents.auto_apply.context import AutoApplyContext, FieldDescriptor
from utils.logging import get_logger

logger = get_logger(__name__)


class QuestionDiscoveryService:
    """Service for discovering and managing job application questions."""
    
    def __init__(self, base_path: Optional[Path] = None):
        """Initialize discovery service.
        
        Args:
            base_path: Base path for the project (defaults to parent of web/)
        """
        self.base_path = base_path or Path(__file__).parent.parent
        self.questions_dir = self.base_path / "data" / "application_questions"
        self.questions_dir.mkdir(parents=True, exist_ok=True)
        
        # Profile and CV paths (required by orchestrator but not used for discovery)
        self.profile_path = self.base_path / "data" / "profile.json"
        self.cv_path = self.base_path / "data" / "cv_library" / "resume.pdf"
        
        self.orchestrator = AutoApplyOrchestrator(self.base_path)
    
    async def discover_questions(
        self, 
        job_url: str, 
        company_name: str,
        job_title: str
    ) -> Dict[str, Any]:
        """Discover application questions for a specific job.
        
        This navigates to the job application page and extracts all form fields
        without actually submitting the application.
        
        Args:
            job_url: URL of the job posting
            company_name: Name of the company
            job_title: Title of the job position
        
        Returns:
            Dictionary containing discovered questions and metadata
        """
        logger.info(f"Discovering questions for {company_name} - {job_title}")
        
        try:
            # Create a minimal context for navigation
            # AutoApplyContext requires all these paths even for discovery
            context = AutoApplyContext(
                job_url=job_url,
                cover_letter="",  # Not needed for discovery
                profile_path=self.profile_path,
                cv_path=self.cv_path,
                cover_letter_path=self.base_path / "data" / "cover_letter.md",
                knowledge_store_dir=self.base_path / "memory" / "profile_store",
                answers_dir=self.base_path / "answers"
            )
            context.job_name = f"{company_name}_{job_title}"
            
            # Navigate and extract fields using the navigator agent
            async with PlaywrightSession() as session:
                navigator_result = await self.orchestrator.navigator.run_async(
                    context, 
                    session
                )
                
                if not navigator_result.has_apply_flow:
                    logger.warning(f"No apply flow found for {job_url}")
                    return {
                        "success": False,
                        "error": "No application form detected",
                        "job_url": job_url,
                    }
                
                # Extract question information from fields
                questions = self._extract_questions_from_fields(
                    navigator_result.fields,
                    company_name,
                    job_title
                )
                
                # Save to file
                questions_file = self._save_questions(
                    company_name, 
                    job_title,
                    questions,
                    job_url
                )
                
                logger.info(f"Discovered {len(questions)} questions, saved to {questions_file}")
                
                return {
                    "success": True,
                    "job_url": job_url,
                    "company": company_name,
                    "job_title": job_title,
                    "questions_count": len(questions),
                    "questions": questions,
                    "questions_file": str(questions_file),
                    "apply_methods": [
                        {"label": am.label, "selector": am.selector}
                        for am in navigator_result.apply_methods
                    ]
                }
                
        except Exception as e:
            logger.error(f"Failed to discover questions: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "job_url": job_url,
            }
    
    def _extract_questions_from_fields(
        self, 
        fields: List[FieldDescriptor],
        company_name: str,
        job_title: str
    ) -> List[Dict[str, Any]]:
        """Extract structured question data from field descriptors.
        
        Args:
            fields: List of field descriptors from navigator
            company_name: Company name
            job_title: Job title
        
        Returns:
            List of question dictionaries
        """
        questions = []
        
        for field in fields:
            question = {
                "field_id": field.field_id,
                "label": field.label,
                "question": field.question,
                "type": field.input_type,  # FieldDescriptor uses input_type, not field_type
                "required": field.required,
                "step_index": field.step_index,
                "selector": field.selector,
                "placeholder": field.placeholder,
                "options": field.options or [],
                "source": {
                    "company": company_name,
                    "job_title": job_title,
                }
            }
            
            # Determine the best display text for the question
            if field.question:
                question["display_text"] = field.question
            elif field.label:
                question["display_text"] = field.label
            else:
                question["display_text"] = field.field_id
            
            questions.append(question)
        
        return questions
    
    def _save_questions(
        self,
        company_name: str,
        job_title: str,
        questions: List[Dict[str, Any]],
        job_url: str
    ) -> Path:
        """Save discovered questions to a JSON file.
        
        Args:
            company_name: Company name
            job_title: Job title
            questions: List of question dictionaries
            job_url: Job URL
        
        Returns:
            Path to saved file
        """
        # Create filename from company and job title
        safe_company = company_name.lower().replace(" ", "_").replace("/", "_")
        safe_title = job_title.lower().replace(" ", "_").replace("/", "_")[:50]
        
        filename = f"{safe_company}_{safe_title}.json"
        filepath = self.questions_dir / filename
        
        data = {
            "company": company_name,
            "job_title": job_title,
            "job_url": job_url,
            "discovered_at": None,  # Will be set by JSON serialization
            "questions_count": len(questions),
            "questions": questions
        }
        
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        
        return filepath
    
    def get_all_questions(self) -> List[Dict[str, Any]]:
        """Get all discovered questions from all files.
        
        Returns:
            List of all question files with metadata
        """
        all_files = []
        
        for filepath in self.questions_dir.glob("*.json"):
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                    all_files.append({
                        "filename": filepath.name,
                        "company": data.get("company"),
                        "job_title": data.get("job_title"),
                        "questions_count": data.get("questions_count", 0),
                        "job_url": data.get("job_url"),
                    })
            except Exception as e:
                logger.error(f"Failed to read {filepath}: {e}")
        
        return all_files
    
    def get_unique_questions(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get all unique questions across all discovered applications.
        
        Groups similar questions together for user profile filling.
        
        Returns:
            Dictionary mapping question keys to list of question instances
        """
        unique_questions = defaultdict(list)
        
        for filepath in self.questions_dir.glob("*.json"):
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                    
                    for question in data.get("questions", []):
                        # Create a normalized key for grouping similar questions
                        key = self._normalize_question_key(
                            question.get("display_text", ""),
                            question.get("type", "")
                        )
                        
                        unique_questions[key].append({
                            "company": data.get("company"),
                            "job_title": data.get("job_title"),
                            "question": question.get("display_text"),
                            "type": question.get("type"),
                            "required": question.get("required", False),
                            "field_id": question.get("field_id"),
                            "options": question.get("options", []),
                        })
            except Exception as e:
                logger.error(f"Failed to read {filepath}: {e}")
        
        # Convert defaultdict to regular dict
        return dict(unique_questions)
    
    def _normalize_question_key(self, text: str, field_type: str) -> str:
        """Normalize question text to create a grouping key.
        
        Args:
            text: Question text
            field_type: Field type
        
        Returns:
            Normalized key for grouping
        """
        # Remove common variations and normalize
        normalized = text.lower().strip()
        
        # Remove punctuation
        normalized = normalized.replace("?", "").replace(":", "").replace("*", "")
        
        # Common field patterns
        if "first name" in normalized:
            return "first_name"
        if "last name" in normalized or "surname" in normalized:
            return "last_name"
        if "email" in normalized:
            return "email"
        if "phone" in normalized or "telephone" in normalized:
            return "phone"
        if "linkedin" in normalized:
            return "linkedin"
        if "github" in normalized:
            return "github"
        if "portfolio" in normalized or "website" in normalized:
            return "portfolio"
        if "cover letter" in normalized:
            return "cover_letter"
        if "resume" in normalized or "cv" in normalized:
            return "resume"
        if "work authorization" in normalized or "authorized to work" in normalized:
            return "work_authorization"
        if "sponsorship" in normalized or "visa" in normalized:
            return "visa_sponsorship"
        if "salary" in normalized or "compensation" in normalized:
            return "salary_expectations"
        if "start date" in normalized or "availability" in normalized:
            return "start_date"
        if "years of experience" in normalized:
            return "years_experience"
        
        # For custom questions, use the text itself
        return normalized.replace(" ", "_")[:50]
    
    def generate_profile_template(self) -> Dict[str, Any]:
        """Generate a profile template with all discovered questions.
        
        Returns:
            Dictionary containing profile template structure
        """
        unique_questions = self.get_unique_questions()
        
        template = {
            "personal_info": {},
            "professional": {},
            "custom_questions": {}
        }
        
        # Categorize questions
        personal_fields = [
            "first_name", "last_name", "email", "phone", 
            "linkedin", "github", "portfolio"
        ]
        
        professional_fields = [
            "work_authorization", "visa_sponsorship", "salary_expectations",
            "start_date", "years_experience"
        ]
        
        for key, instances in unique_questions.items():
            # Get first instance as representative
            question = instances[0]
            
            field_data = {
                "question": question["question"],
                "type": question["type"],
                "required": question["required"],
                "answer": "",  # User will fill this
                "options": question.get("options", []),
                "appears_in": [
                    f"{inst['company']} - {inst['job_title']}"
                    for inst in instances
                ]
            }
            
            # Categorize
            if key in personal_fields:
                template["personal_info"][key] = field_data
            elif key in professional_fields:
                template["professional"][key] = field_data
            else:
                template["custom_questions"][key] = field_data
        
        return template
