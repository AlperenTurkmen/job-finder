"""
Universal Question Merger

Discovers questions from all companies and creates a unified master template.
Identifies common questions, company-specific questions, and field types.

Usage:
    python scripts/merge_all_questions.py
    python scripts/merge_all_questions.py --output data/master_questions.json
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Any

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


class QuestionMerger:
    """Merges questions from all companies into a unified template."""
    
    def __init__(self, questions_dir: Path = None):
        """Initialize merger.
        
        Args:
            questions_dir: Directory containing question JSON files
        """
        self.questions_dir = questions_dir or (PROJECT_ROOT / "data" / "application_questions")
        self.questions_dir.mkdir(parents=True, exist_ok=True)
        
        # Common field patterns for normalization
        self.field_patterns = {
            "first_name": ["first name", "first", "given name", "forename"],
            "last_name": ["last name", "last", "surname", "family name", "lastname"],
            "full_name": ["full name", "name", "your name"],
            "email": ["email", "e-mail", "email address"],
            "phone": ["phone", "telephone", "mobile", "phone number", "contact number"],
            "linkedin": ["linkedin", "linkedin profile", "linkedin url"],
            "github": ["github", "github profile", "github username"],
            "portfolio": ["portfolio", "website", "personal website", "portfolio url"],
            "city": ["city", "current city", "location city"],
            "country": ["country", "current country"],
            "address": ["address", "street address", "full address"],
            "postal_code": ["postal code", "zip code", "postcode", "zip"],
            "work_authorization": ["work authorization", "authorized to work", "right to work", "work permit"],
            "visa_sponsorship": ["visa sponsorship", "require sponsorship", "visa", "sponsorship needed"],
            "years_experience": ["years of experience", "years experience", "total experience", "experience years"],
            "current_company": ["current company", "current employer", "present company"],
            "current_title": ["current title", "current position", "current role", "job title"],
            "salary_expectations": ["salary expectations", "desired salary", "expected salary", "salary requirement"],
            "start_date": ["start date", "availability", "available to start", "notice period", "when can you start"],
            "education": ["education", "degree", "university", "college"],
            "cv_upload": ["cv", "resume", "curriculum vitae", "upload cv", "upload resume"],
            "cover_letter": ["cover letter", "covering letter", "motivation letter"],
            "why_interested": ["why interested", "why this role", "why us", "motivation", "why apply"],
            "referral": ["referral", "how did you hear", "referred by", "reference"],
        }
    
    def normalize_field_name(self, question_text: str, field_type: str) -> str:
        """Normalize a field name based on question text.
        
        Args:
            question_text: The question text
            field_type: Field type
            
        Returns:
            Normalized field name
        """
        text_lower = question_text.lower().strip()
        
        # Check patterns
        for normalized_name, patterns in self.field_patterns.items():
            for pattern in patterns:
                if pattern in text_lower:
                    return normalized_name
        
        # Fallback: create simple name from text
        simple_name = (
            text_lower
            .replace("?", "")
            .replace(":", "")
            .replace("*", "")
            .replace(" ", "_")
            .replace("-", "_")
        )
        
        # Limit length
        return simple_name[:50]
    
    def load_all_questions(self) -> List[Dict[str, Any]]:
        """Load all question files from directory.
        
        Returns:
            List of all question file data
        """
        all_files = []
        
        for filepath in self.questions_dir.glob("*.json"):
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                    all_files.append(data)
                    logger.info(f"Loaded {filepath.name}: {data.get('questions_count', 0)} questions")
            except Exception as e:
                logger.error(f"Failed to load {filepath}: {e}")
        
        return all_files
    
    def merge_questions(self, all_files: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge questions from all files into unified structure.
        
        Args:
            all_files: List of question file data
            
        Returns:
            Merged question structure
        """
        # Track each unique question
        merged = defaultdict(lambda: {
            "normalized_name": "",
            "common_labels": [],
            "field_type": "",
            "required_count": 0,
            "optional_count": 0,
            "companies": set(),
            "options": set(),
            "examples": []
        })
        
        total_questions = 0
        
        for file_data in all_files:
            company = file_data.get("company", "Unknown")
            
            for question in file_data.get("questions", []):
                total_questions += 1
                
                # Normalize the field
                display_text = question.get("display_text") or question.get("question") or question.get("label", "")
                field_type = question.get("type", "text")
                normalized_name = self.normalize_field_name(display_text, field_type)
                
                # Add to merged data
                merged[normalized_name]["normalized_name"] = normalized_name
                merged[normalized_name]["common_labels"].append(display_text)
                merged[normalized_name]["field_type"] = field_type
                merged[normalized_name]["companies"].add(company)
                
                if question.get("required"):
                    merged[normalized_name]["required_count"] += 1
                else:
                    merged[normalized_name]["optional_count"] += 1
                
                # Add options if any
                if question.get("options"):
                    for opt in question["options"]:
                        merged[normalized_name]["options"].add(opt)
                
                # Add example
                merged[normalized_name]["examples"].append({
                    "company": company,
                    "label": display_text,
                    "required": question.get("required", False),
                    "type": field_type
                })
        
        logger.info(f"Processed {total_questions} total questions")
        logger.info(f"Identified {len(merged)} unique fields")
        
        # Convert sets to lists for JSON serialization
        result = {}
        for name, data in merged.items():
            result[name] = {
                "normalized_name": data["normalized_name"],
                "common_labels": list(set(data["common_labels"]))[:10],  # Limit to 10 unique labels
                "field_type": data["field_type"],
                "appears_in_companies": sorted(list(data["companies"])),
                "companies_count": len(data["companies"]),
                "required_in": data["required_count"],
                "optional_in": data["optional_count"],
                "options": sorted(list(data["options"])) if data["options"] else [],
                "examples": data["examples"][:5]  # Keep first 5 examples
            }
        
        return result
    
    def categorize_questions(self, merged: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Categorize questions into logical groups.
        
        Args:
            merged: Merged questions dictionary
            
        Returns:
            Categorized questions
        """
        categories = {
            "essential": {},  # Name, email, phone - always needed
            "contact_info": {},  # LinkedIn, GitHub, portfolio, address
            "work_eligibility": {},  # Work authorization, visa, start date
            "professional": {},  # Experience, current role, education
            "application_specific": {},  # Cover letter, why interested, referral
            "preferences": {},  # Salary, location preferences
            "uploads": {},  # CV, resume uploads
            "other": {}  # Everything else
        }
        
        essential_fields = ["first_name", "last_name", "full_name", "email", "phone"]
        contact_fields = ["linkedin", "github", "portfolio", "address", "city", "country", "postal_code"]
        eligibility_fields = ["work_authorization", "visa_sponsorship", "start_date"]
        professional_fields = ["years_experience", "current_company", "current_title", "education"]
        application_fields = ["why_interested", "cover_letter", "referral"]
        preference_fields = ["salary_expectations"]
        upload_fields = ["cv_upload"]
        
        for name, data in merged.items():
            if name in essential_fields:
                categories["essential"][name] = data
            elif name in contact_fields:
                categories["contact_info"][name] = data
            elif name in eligibility_fields:
                categories["work_eligibility"][name] = data
            elif name in professional_fields:
                categories["professional"][name] = data
            elif name in application_fields:
                categories["application_specific"][name] = data
            elif name in preference_fields:
                categories["preferences"][name] = data
            elif name in upload_fields:
                categories["uploads"][name] = data
            else:
                categories["other"][name] = data
        
        return categories
    
    def generate_user_template(self, categorized: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Generate a user profile template.
        
        Args:
            categorized: Categorized questions
            
        Returns:
            User profile template
        """
        template = {
            "personal": {},
            "contact": {},
            "professional": {},
            "work_eligibility": {},
            "preferences": {},
            "custom_answers": {}
        }
        
        # Map categories to template sections
        category_mapping = {
            "essential": "personal",
            "contact_info": "contact",
            "professional": "professional",
            "work_eligibility": "work_eligibility",
            "preferences": "preferences",
            "application_specific": "custom_answers",
            "other": "custom_answers"
        }
        
        for category, questions in categorized.items():
            if category == "uploads":
                continue  # Skip uploads, handled separately
            
            template_section = category_mapping.get(category, "custom_answers")
            
            for name, data in questions.items():
                template[template_section][name] = {
                    "question": data["common_labels"][0] if data["common_labels"] else name,
                    "field_type": data["field_type"],
                    "required_by": f"{data['required_in']} companies",
                    "appears_in": data["appears_in_companies"],
                    "options": data["options"] if data["options"] else None,
                    "answer": "",  # User fills this
                    "can_extract_from_cv": name in [
                        "first_name", "last_name", "full_name", "email", "phone",
                        "city", "country", "linkedin", "github", "years_experience",
                        "current_company", "current_title", "education"
                    ]
                }
        
        return template


def main():
    """Main execution."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Merge questions from all companies")
    parser.add_argument(
        "--output",
        type=str,
        default="data/master_questions.json",
        help="Output file for merged questions"
    )
    parser.add_argument(
        "--template-output",
        type=str,
        default="data/user_profile_template.json",
        help="Output file for user profile template"
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("Question Merger - Creating Universal Template")
    logger.info("=" * 60)
    
    merger = QuestionMerger()
    
    # Load all questions
    logger.info("\nStep 1: Loading all question files...")
    all_files = merger.load_all_questions()
    
    if not all_files:
        logger.error("No question files found! Run discovery first:")
        logger.error("  python scripts/discover_all_questions.py --all --limit 5")
        return 1
    
    logger.info(f"Loaded {len(all_files)} question files")
    
    # Merge questions
    logger.info("\nStep 2: Merging and normalizing questions...")
    merged = merger.merge_questions(all_files)
    
    # Categorize
    logger.info("\nStep 3: Categorizing questions...")
    categorized = merger.categorize_questions(merged)
    
    for category, questions in categorized.items():
        if questions:
            logger.info(f"  {category}: {len(questions)} fields")
    
    # Generate template
    logger.info("\nStep 4: Generating user profile template...")
    template = merger.generate_user_template(categorized)
    
    # Save outputs
    output_path = PROJECT_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump({
            "generated_at": "2026-02-17",
            "total_unique_fields": len(merged),
            "total_companies": len(set(
                company
                for data in merged.values()
                for company in data["appears_in_companies"]
            )),
            "merged_questions": merged,
            "categorized": {k: list(v.keys()) for k, v in categorized.items()},
            "full_categorized": categorized
        }, f, indent=2)
    
    logger.info(f"✅ Saved merged questions to: {output_path}")
    
    # Save template
    template_path = PROJECT_ROOT / args.template_output
    with open(template_path, "w") as f:
        json.dump(template, f, indent=2)
    
    logger.info(f"✅ Saved user template to: {template_path}")
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Summary")
    logger.info("=" * 60)
    logger.info(f"Total unique fields identified: {len(merged)}")
    logger.info(f"Essential fields: {len(categorized['essential'])}")
    logger.info(f"Can extract from CV: {sum(1 for section in template.values() for field in section.values() if isinstance(field, dict) and field.get('can_extract_from_cv'))}")
    
    logger.info("\n📋 Next Steps:")
    logger.info("  1. Review: cat data/user_profile_template.json")
    logger.info("  2. Extract from CV: python scripts/extract_from_cv.py --cv your_cv.pdf")
    logger.info("  3. Fill remaining fields manually")
    logger.info("  4. Start auto-applying!")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
