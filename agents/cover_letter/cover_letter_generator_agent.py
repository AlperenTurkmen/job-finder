"""Cover Letter Generator Agent with Gemini-powered drafting."""
from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent
from typing import Dict, Optional

try:
    from agents.common.gemini_client import GeminiClient, GeminiConfig
except ImportError:  # pragma: no cover - script execution fallback
    from ..common.gemini_client import GeminiClient, GeminiConfig


class CoverLetterGeneratorAgent:
    """Generates cover letters using raw job description and profile."""

    REASONING_MODEL = "gemini-2.5-pro"
    STYLE_MODEL = "gemini-2.5-flash"

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or Path(__file__).resolve().parents[2]
        self.output_dir = self.base_path / "data" / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.profile_file = self.base_path / "data" / "profile.md"
        self.generator_client = GeminiClient(
            GeminiConfig(
                model=self.REASONING_MODEL,
                system_instruction="Write outstanding cover letters that mirror the candidate's style.",
                temperature=0.35,
                mock_bucket="cover_letter_generate",
            )
        )
        self.revision_client = GeminiClient(
            GeminiConfig(
                model=self.STYLE_MODEL,
                system_instruction="Revise cover letters according to HR feedback without losing voice.",
                temperature=0.25,
                mock_bucket="cover_letter_revise",
            )
        )

    def generate(
        self,
        job_title: str,
        job_description: str,
        company: str,
        location: Optional[str] = None,
        style_notes: Optional[str] = None,
        iteration: int = 1,
        feedback: Optional[str] = None,
    ) -> str:
        """Generate a cover letter from raw job posting data.
        
        Args:
            job_title: The job title
            job_description: Raw job description text
            company: Company name
            location: Job location (optional)
            style_notes: Writing style guidance (optional)
            iteration: Draft iteration number
            feedback: Previous feedback to incorporate (optional)
        """
        profile = self._load_profile()
        writing_samples = self._load_writing_samples()
        
        location_str = f"Location: {location}" if location else ""
        style_section = f"Style guidance:\n{style_notes}" if style_notes else ""
        feedback_section = f"Previous feedback to address:\n{feedback}" if feedback else ""
        samples_section = ""
        if writing_samples:
            samples_section = f"Writing samples (match this tone and style):\n{chr(10).join(writing_samples[:2])}"
        
        prompt = dedent(
            f"""
            Write a compelling cover letter for this job. Requirements:
            - 3-4 paragraphs, professional but personable tone
            - Address specific requirements from the job description
            - Highlight relevant experience from the candidate's profile
            - Use UK English
            - Return only the letter text (no code fences, no commentary)
            
            **CRITICAL: NEVER fabricate, invent, or embellish experiences, projects, skills, or achievements.**
            You must ONLY use information explicitly stated in the candidate profile below.
            If the candidate lacks certain skills or experiences mentioned in the job posting,
            focus on transferable skills and genuine experiences - do NOT make up projects or
            claim proficiency in technologies not listed in their profile. Honesty is paramount.
            
            === JOB POSTING ===
            Company: {company}
            Title: {job_title}
            {location_str}
            
            {job_description}
            === END JOB POSTING ===
            
            === CANDIDATE PROFILE ===
            {profile}
            === END PROFILE ===
            
            {samples_section}
            
            {style_section}
            
            {feedback_section}
            """
        ).strip()

        letter = self.generator_client.generate_text(
            prompt,
            metadata={
                "role": job_title,
                "company": company,
                "iteration": iteration,
            },
        )
        self._write_iteration(letter, iteration)
        return letter

    def generate_from_structured(
        self,
        role_summary: Dict[str, object],
        profile_package: Dict[str, object],
        style_profile: Dict[str, object],
        iteration: int = 1,
        feedback: Optional[Dict[str, object]] = None,
    ) -> str:
        """Legacy method: Generate cover letter from structured data."""
        selected_cv_key = role_summary.get("cv_recommendation", {}).get("selected_variant", "cv_general")
        selected_cv = profile_package.get("cv_library", {}).get(selected_cv_key, {})
        profile_text = profile_package.get("profile_text", "")
        
        prompt = dedent(
            f"""
            Compose a four-paragraph cover letter in Markdown. Requirements:
            - Tone and cadence must reflect this style fingerprint: {json.dumps(style_profile, indent=2)}
            - Address these talking points explicitly: {json.dumps(role_summary.get('mandatory_talking_points', []), indent=2)}
            - Cite achievements pulled from this selected CV: {json.dumps(selected_cv, indent=2)}
            - Reference the candidate profile when relevant
            - If HR feedback is provided, incorporate it seamlessly: {json.dumps(feedback or {}, indent=2)}
            - Use UK English.
            - Use connective phrases already favored by the writer when natural.
            - Return only the final letter (no code fences, no additional commentary).

            Role summary:
            {json.dumps(role_summary, indent=2)}
            
            Candidate Profile:
            {profile_text}
            """
        ).strip()

        letter = self.generator_client.generate_text(
            prompt,
            metadata={
                "role": role_summary.get("title"),
                "company": role_summary.get("company"),
                "iteration": iteration,
            },
        )
        self._write_iteration(letter, iteration)
        return letter

    def revise(
        self,
        current_letter: str,
        feedback: str,
        iteration: int,
        style_notes: Optional[str] = None,
    ) -> str:
        """Revise a cover letter based on feedback.
        
        Args:
            current_letter: The current draft
            feedback: Feedback to incorporate
            iteration: Revision iteration number
            style_notes: Style guidance (optional)
        """
        style_section = f"Style guidance:\n{style_notes}" if style_notes else ""
        
        prompt = dedent(
            f"""
            You are editing an existing cover letter. Apply the feedback while keeping the writer's voice intact.
            Provide only the revised letter text.
            
            **CRITICAL: NEVER fabricate, invent, or embellish experiences, projects, skills, or achievements.**
            You may only reference experiences and skills that are already in the letter or are genuine.
            If addressing feedback requires skills or projects the candidate doesn't have, focus on
            transferable skills and genuine strengths instead. Do NOT make up projects or technologies.

            {style_section}

            Feedback to address:
            {feedback}

            Current letter:
            {current_letter}
            """
        ).strip()

        revised = self.revision_client.generate_text(
            prompt,
            metadata={
                "iteration": iteration,
                "bucket_key": "revision",
            },
        )
        self._write_iteration(revised, iteration)
        return revised

    # -------------------- helpers --------------------
    def _load_profile(self) -> str:
        if not self.profile_file.exists():
            raise FileNotFoundError(f"Profile file not found: {self.profile_file}")
        return self.profile_file.read_text()
    
    def _load_writing_samples(self) -> list[str]:
        samples_dir = self.base_path / "data" / "writing_samples"
        if not samples_dir.exists():
            return []
        return [f.read_text() for f in sorted(samples_dir.glob("*.md"))]

    def _write_iteration(self, letter: str, iteration: int) -> None:
        filename = self.output_dir / f"draft_cover_letter_iter_{iteration}.md"
        filename.write_text(letter)


if __name__ == "__main__":
    # Test with raw job description
    generator = CoverLetterGeneratorAgent()
    letter = generator.generate(
        job_title="Backend Engineer",
        job_description="""
        We are looking for a Backend Engineer to join our team.
        
        Requirements:
        - 3+ years experience with Python or Go
        - Experience with Docker and Kubernetes
        - Strong understanding of distributed systems
        
        Nice to have:
        - Machine learning experience
        - Cloud experience (AWS/GCP)
        """,
        company="ExampleCorp",
        location="London, UK",
    )
    print(letter)
