"""For-Them Score Agent: estimates employer fit via Gemini 2.5."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Dict, Optional

try:
    from agents.common.gemini_client import GeminiClient, GeminiConfig
except ImportError:  # pragma: no cover - script execution fallback
    from ..common.gemini_client import GeminiClient, GeminiConfig


@dataclass
class ForThemScoreResult:
    for_them_score: float
    reasoning: str
    dimension_scores: Dict[str, float]

    def to_dict(self) -> Dict[str, object]:
        return {
            "for_them_score": round(self.for_them_score, 2),
            "reasoning": self.reasoning,
            "dimension_scores": {k: round(v, 2) for k, v in self.dimension_scores.items()},
        }


class ForThemScoreAgent:
    MODEL_NAME = "gemini-2.5-pro"

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or Path(__file__).resolve().parents[2]
        self.profile_file = self.base_path / "data" / "profile.md"
        self.client = GeminiClient(
            GeminiConfig(
                model=self.MODEL_NAME,
                system_instruction=
                "You are a hiring panel summarizer who estimates how strong the candidate looks for a role.",
                temperature=0.25,
                json_mode=True,
                mock_bucket="for_them_score",
            )
        )

    def evaluate(
        self,
        role_payload: Optional[Dict[str, object]] = None,
        *,
        job_title: Optional[str] = None,
        job_description: Optional[str] = None,
        company: Optional[str] = None,
        location: Optional[str] = None,
    ) -> ForThemScoreResult:
        """Evaluate how convincing the candidate would look to the employer.
        
        Can be called in two ways:
        1. With structured role_payload dict (legacy)
        2. With raw job_title + job_description (preferred for raw data)
        
        Args:
            role_payload: Structured dict with role info (legacy)
            job_title: Raw job title string
            job_description: Raw job description text
            company: Company name (optional)
            location: Job location (optional)
        """
        profile = self._load_text(self.profile_file)
        
        # Support both structured and raw input
        if job_title and job_description:
            response = self._call_gemini_raw(
                job_title=job_title,
                job_description=job_description,
                company=company or "Unknown",
                location=location,
                profile=profile,
            )
        elif role_payload:
            response = self._call_gemini(role_payload, profile)
        else:
            raise ValueError("Must provide either role_payload or job_title + job_description")
        
        dimension_scores = response.get("dimension_scores", {})
        return ForThemScoreResult(
            for_them_score=float(response.get("for_them_score", 0)),
            reasoning=response.get("reasoning", "No reasoning returned"),
            dimension_scores={k: float(v) for k, v in dimension_scores.items()},
        )

    def _call_gemini_raw(
        self,
        job_title: str,
        job_description: str,
        company: str,
        location: Optional[str],
        profile: str,
    ) -> Dict[str, object]:
        """Call Gemini with raw job title and description."""
        location_str = f"Location: {location}" if location else "Location: Not specified"
        
        prompt = dedent(
            f"""
            Evaluate how convincing this candidate would look to the employer for the role below.
            
            Analyze the raw job posting and extract the requirements, then compare against the candidate profile.
            Consider five dimensions:
            - skill_match: How well do the candidate's technical skills match the requirements?
            - experience_relevance: Is the candidate's experience relevant to this role?
            - domain_fit: Does the candidate have experience in this industry/domain?
            - location_convenience: Can the candidate work from the required location?
            - interest_alignment: Does this role align with the candidate's stated interests?
            
            Each dimension must be a score between 0 and 100.
            Also produce an overall for_them_score plus one short paragraph of reasoning quoting specifics from both the job posting and the candidate's profile.

            Return ONLY JSON:
            {{
                "for_them_score": number,
                "dimension_scores": {{
                    "skill_match": number,
                    "experience_relevance": number,
                    "domain_fit": number,
                    "location_convenience": number,
                    "interest_alignment": number
                }},
                "reasoning": "..."
            }}

            === JOB POSTING ===
            Company: {company}
            Title: {job_title}
            {location_str}
            
            Description:
            {job_description}
            === END JOB POSTING ===

            === CANDIDATE PROFILE ===
            {profile}
            === END PROFILE ===
            """
        ).strip()

        return self.client.generate_json(
            prompt,
            metadata={"role": job_title, "company": company},
        )

    def _call_gemini(self, role_payload: Dict[str, object], profile: str) -> Dict[str, object]:
        prompt = dedent(
            f"""
            Evaluate how convincing this candidate would look to the employer.
            Consider five dimensions: skill_match, experience_relevance, domain_fit, location_convenience, and interest_alignment.
            Each dimension must be a score between 0 and 100. Also produce an overall for_them_score plus one short paragraph of reasoning quoting specifics.

            Return ONLY JSON:
            {{
              "for_them_score": number,
              "dimension_scores": {{
                  "skill_match": number,
                  "experience_relevance": number,
                  "domain_fit": number,
                  "location_convenience": number,
                  "interest_alignment": number
              }},
              "reasoning": "..."
            }}

            Role JSON:
            {json.dumps(role_payload, indent=2)}

            === CANDIDATE PROFILE ===
            {profile}
            === END PROFILE ===
            """
        ).strip()

        return self.client.generate_json(
            prompt,
            metadata={
                "role": role_payload.get("role"),
                "company": role_payload.get("company"),
            },
        )

    def _load_text(self, path: Path) -> str:
        if not path.exists():
            raise FileNotFoundError(f"Expected file missing: {path}")
        return path.read_text()


if __name__ == "__main__":  # pragma: no cover - manual test requires API key
    agent = ForThemScoreAgent()
    
    # Test with raw job description
    result = agent.evaluate(
        job_title="Backend Engineer",
        job_description="""
        We are looking for a Backend Engineer to join our team in London.
        
        Requirements:
        - 3+ years experience with Go or Python
        - Experience with Docker and Kubernetes
        - Strong understanding of distributed systems
        - Experience designing and building APIs
        
        Nice to have:
        - Experience with machine learning pipelines
        - Cloud experience (AWS/GCP)
        """,
        company="ExampleCorp",
        location="London",
    )
    print(result.to_dict())
