"""
CV Information Extractor

Uses LLM to extract structured information from CV/resume and cover letters.
Auto-fills user profile template with extracted data.

Usage:
    python scripts/extract_from_cv.py --cv data/cv_library/resume.pdf
    python scripts/extract_from_cv.py --cv resume.pdf --cover-letters data/writing_samples/*.md
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.logging import configure_logging, get_logger
from agents.common.gemini_client import GeminiClient, GeminiConfig

configure_logging()
logger = get_logger(__name__)


class CVExtractor:
    """Extracts structured information from CV and cover letters."""
    
    EXTRACTION_PROMPT = """You are an expert HR assistant extracting structured information from a CV/resume.

Extract the following information from the provided CV text:

**Personal Information:**
- First name
- Last name  
- Full name (if different from first + last)
- Email address
- Phone number
- LinkedIn profile URL
- GitHub profile URL
- Portfolio/personal website URL
- Current city
- Current country

**Professional Information:**
- Total years of professional experience (as a number)
- Current company name
- Current job title
- Education (degree, institution, graduation year)

**Work Eligibility:**
- Any mentions of work authorization or visa status
- Locations where authorized to work

**Additional:**
- Any salary expectations mentioned
- Any availability/start date mentions

Return ONLY valid JSON in this exact format (use null for missing fields):

```json
{{
  "personal": {{
    "first_name": "...",
    "last_name": "...",
    "full_name": "...",
    "email": "...",
    "phone": "..."
  }},
  "contact": {{
    "linkedin": "...",
    "github": "...",
    "portfolio": "...",
    "city": "...",
    "country": "..."
  }},
  "professional": {{
    "years_experience": 5,
    "current_company": "...",
    "current_title": "...",
    "education": "..."
  }},
  "work_eligibility": {{
    "work_authorization": "...",
    "authorized_locations": []
  }},
  "preferences": {{
    "salary_expectations": "...",
    "start_date": "..."
  }}
}}
```

CV Text:
{cv_text}

Remember: Return ONLY the JSON, no additional text."""

    COVER_LETTER_PROMPT = """You are analyzing cover letters to extract additional profile information.

From the provided cover letter text, extract:

1. **Why they're interested in roles** (common themes, motivations)
2. **Key strengths they emphasize** (skills, achievements)
3. **Career goals mentioned**
4. **Any work authorization mentions**
5. **Salary expectations if mentioned**

Return ONLY valid JSON:

```json
{{
  "motivations": ["..."],
  "key_strengths": ["..."],
  "career_goals": "...",
  "work_eligibility_notes": "...",
  "salary_notes": "..."
}}
```

Cover Letter Text:
{cover_letter_text}"""

    def __init__(self):
        """Initialize extractor."""
        config = GeminiConfig(
            model="gemini-2.5-flash",
            temperature=0.0,
            json_mode=True
        )
        self.client = GeminiClient(config)
    
    def extract_from_text(self, cv_text: str) -> Dict[str, Any]:
        """Extract information from CV text using LLM.
        
        Args:
            cv_text: CV text content
            
        Returns:
            Extracted information dictionary
        """
        try:
            prompt = self.EXTRACTION_PROMPT.format(cv_text=cv_text)
            
            # Use generate_json for direct JSON response
            extracted = self.client.generate_json(prompt)
            logger.info("✅ Successfully extracted information from CV")
            return extracted
            
        except ValueError as e:
            # This is the JSON parsing error
            logger.error(f"Failed to extract from CV - JSON parse error: {e}")
            logger.error("Check if the prompt is too complex or  the response is truncated")
            return {}
        except Exception as e:
            logger.error(f"Failed to extract from CV: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {}
    
    def extract_from_cover_letters(self, cover_letter_texts: List[str]) -> Dict[str, Any]:
        """Extract insights from cover letters.
        
        Args:
            cover_letter_texts: List of cover letter texts
            
        Returns:
            Extracted insights
        """
        all_insights = {
            "motivations": [],
            "key_strengths": [],
            "career_goals": [],
            "work_eligibility_notes": [],
            "salary_notes": []
        }
        
        for i, text in enumerate(cover_letter_texts):
            try:
                prompt = self.COVER_LETTER_PROMPT.format(cover_letter_text=text)
                
                # Use generate_json for direct JSON response
                insights = self.client.generate_json(prompt)
                
                # Merge insights
                if insights.get("motivations"):
                    all_insights["motivations"].extend(insights["motivations"])
                if insights.get("key_strengths"):
                    all_insights["key_strengths"].extend(insights["key_strengths"])
                if insights.get("career_goals"):
                    all_insights["career_goals"].append(insights["career_goals"])
                if insights.get("work_eligibility_notes"):
                    all_insights["work_eligibility_notes"].append(insights["work_eligibility_notes"])
                if insights.get("salary_notes"):
                    all_insights["salary_notes"].append(insights["salary_notes"])
                
                logger.info(f"✅ Extracted insights from cover letter {i+1}")
                
            except Exception as e:
                logger.error(f"Failed to extract from cover letter {i+1}: {e}")
        
        # Deduplicate and limit
        all_insights["motivations"] = list(set(all_insights["motivations"]))[:10]
        all_insights["key_strengths"] = list(set(all_insights["key_strengths"]))[:10]
        
        return all_insights
    
    def read_cv_file(self, filepath: Path) -> str:
        """Read CV file content.
        
        Args:
            filepath: Path to CV file
            
        Returns:
            CV text content
        """
        if not filepath.exists():
            raise FileNotFoundError(f"CV file not found: {filepath}")
        
        # For now, only support text-based formats
        # In production, you'd use PyPDF2, python-docx, etc.
        if filepath.suffix.lower() in [".txt", ".md"]:
            return filepath.read_text(encoding="utf-8")
        elif filepath.suffix.lower() == ".pdf":
            logger.warning("PDF parsing not implemented yet. Please convert to .txt or .md")
            logger.warning("You can use: pdftotext resume.pdf resume.txt")
            raise NotImplementedError("PDF parsing requires PyPDF2 or pdfplumber")
        else:
            raise ValueError(f"Unsupported file format: {filepath.suffix}")
    
    def merge_with_template(
        self,
        extracted: Dict[str, Any],
        template: Dict[str, Any],
        cover_letter_insights: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Merge extracted data with user profile template.
        
        Args:
            extracted: Extracted CV data
            template: User profile template
            cover_letter_insights: Insights from cover letters
            
        Returns:
            Merged profile
        """
        merged = json.loads(json.dumps(template))  # Deep copy
        
        # Merge CV data
        for section_name, section_data in extracted.items():
            if section_name in merged and isinstance(section_data, dict):
                for field_name, value in section_data.items():
                    if field_name in merged[section_name]:
                        if isinstance(merged[section_name][field_name], dict):
                            # Template has metadata structure
                            merged[section_name][field_name]["answer"] = value
                            merged[section_name][field_name]["source"] = "cv"
                        else:
                            # Simple structure
                            merged[section_name][field_name] = value
        
        # Add cover letter insights
        if cover_letter_insights:
            merged["cover_letter_insights"] = cover_letter_insights
            
            # Pre-fill "why_interested" in custom_answers if available
            if "custom_answers" in merged and "why_interested" in merged["custom_answers"]:
                motivations = cover_letter_insights.get("motivations", [])
                if motivations:
                    if isinstance(merged["custom_answers"]["why_interested"], dict):
                        merged["custom_answers"]["why_interested"]["answer"] = " ".join(motivations[:3])
                        merged["custom_answers"]["why_interested"]["source"] = "cover_letters"
        
        return merged


def main():
    """Main execution."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Extract information from CV and cover letters")
    parser.add_argument(
        "--cv",
        type=str,
        required=True,
        help="Path to CV file (.txt, .md, or .pdf)"
    )
    parser.add_argument(
        "--cover-letters",
        type=str,
        nargs="*",
        help="Paths to cover letter files"
    )
    parser.add_argument(
        "--template",
        type=str,
        default="data/user_profile_template.json",
        help="User profile template file"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/profile_filled.json",
        help="Output file for filled profile"
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("CV Information Extractor")
    logger.info("=" * 60)
    
    extractor = CVExtractor()
    
    # Read CV
    logger.info(f"\nStep 1: Reading CV from {args.cv}...")
    cv_path = Path(args.cv)
    if not cv_path.is_absolute():
        cv_path = PROJECT_ROOT / cv_path
    
    try:
        cv_text = extractor.read_cv_file(cv_path)
        logger.info(f"✅ Read {len(cv_text)} characters from CV")
    except Exception as e:
        logger.error(f"Failed to read CV: {e}")
        return 1
    
    # Extract from CV
    logger.info("\nStep 2: Extracting information from CV using LLM...")
    extracted = extractor.extract_from_text(cv_text)
    
    if not extracted:
        logger.error("Failed to extract information from CV")
        return 1
    
    logger.info(f"✅ Extracted {sum(len(v) if isinstance(v, dict) else 1 for v in extracted.values())} fields")
    
    # Extract from cover letters if provided
    cover_letter_insights = None
    if args.cover_letters:
        logger.info(f"\nStep 3: Extracting insights from {len(args.cover_letters)} cover letters...")
        cover_letter_texts = []
        
        for cl_path_str in args.cover_letters:
            cl_path = Path(cl_path_str)
            if not cl_path.is_absolute():
                cl_path = PROJECT_ROOT / cl_path
            
            try:
                if cl_path.is_file():
                    cover_letter_texts.append(cl_path.read_text(encoding="utf-8"))
                else:
                    # Glob pattern
                    for matched_file in PROJECT_ROOT.glob(cl_path_str):
                        if matched_file.is_file():
                            cover_letter_texts.append(matched_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Couldn't read {cl_path}: {e}")
        
        if cover_letter_texts:
            cover_letter_insights = extractor.extract_from_cover_letters(cover_letter_texts)
            logger.info(f"✅ Extracted insights from {len(cover_letter_texts)} cover letters")
    
    # Load template
    logger.info("\nStep 4: Loading user profile template...")
    template_path = PROJECT_ROOT / args.template
    
    if not template_path.exists():
        logger.error(f"Template not found: {template_path}")
        logger.error("Run first: python scripts/merge_all_questions.py")
        return 1
    
    with open(template_path, "r") as f:
        template = json.load(f)
    
    logger.info("✅ Loaded template")
    
    # Merge
    logger.info("\nStep 5: Merging extracted data with template...")
    filled_profile = extractor.merge_with_template(extracted, template, cover_letter_insights)
    
    # Save
    output_path = PROJECT_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(filled_profile, f, indent=2)
    
    logger.info(f"✅ Saved filled profile to: {output_path}")
    
    # Count filled vs empty
    def count_filled(data, filled=0, empty=0):
        if isinstance(data, dict):
            for value in data.values():
                if isinstance(value, dict):
                    if "answer" in value:
                        if value["answer"]:
                            filled += 1
                        else:
                            empty += 1
                    else:
                        filled, empty = count_filled(value, filled, empty)
                elif value:
                    filled += 1
                else:
                    empty += 1
        return filled, empty
    
    filled_count, empty_count = count_filled(filled_profile)
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Extraction Summary")
    logger.info("=" * 60)
    logger.info(f"Fields auto-filled: {filled_count}")
    logger.info(f"Fields needing manual input: {empty_count}")
    logger.info(f"Completion: {filled_count / (filled_count + empty_count) * 100:.1f}%")
    
    logger.info("\n📋 Next Steps:")
    logger.info(f"  1. Review: cat {args.output}")
    logger.info("  2. Fill remaining empty fields manually")
    logger.info("  3. Copy to profile.json: cp data/profile_filled.json data/profile.json")
    logger.info("  4. Start auto-applying: python scripts/batch_auto_apply.py")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
