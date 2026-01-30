"""For-Me Score Agent: delegates preference scoring to Gemini 2.5."""
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
class ForMeScoreResult:
    for_me_score: float
    reasoning: str
    dimension_scores: Dict[str, float]

    def to_dict(self) -> Dict[str, object]:
        return {
            "for_me_score": round(self.for_me_score, 2),
            "reasoning": self.reasoning,
            "dimension_scores": {k: round(v, 2) for k, v in self.dimension_scores.items()},
        }


class ForMeScoreAgent:
    MODEL_NAME = "gemini-2.5-pro"

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or Path(__file__).resolve().parents[2]
        self.profile_file = self.base_path / "data" / "profile.md"
        self.preferences_file = self.base_path / "data" / "preferences.md"
        self.client = GeminiClient(
            GeminiConfig(
                model=self.MODEL_NAME,
                system_instruction=
                "You are an AI career coach who scores how well a role matches the candidate's preferences.",
                temperature=0.2,
                json_mode=True,
                mock_bucket="for_me_score",
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
    ) -> ForMeScoreResult:
        """Evaluate how appealing a role is for the candidate.
        
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
        preferences = self._load_text(self.preferences_file)
        
        # Support both structured and raw input
        if job_title and job_description:
            response = self._call_gemini_raw(
                job_title=job_title,
                job_description=job_description,
                company=company or "Unknown",
                location=location,
                profile=profile,
                preferences=preferences,
            )
        elif role_payload:
            response = self._call_gemini(role_payload, profile, preferences)
        else:
            raise ValueError("Must provide either role_payload or job_title + job_description")
        
        dimension_scores = response.get("dimension_scores", {})
        return ForMeScoreResult(
            for_me_score=float(response.get("for_me_score", 0)),
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
        preferences: str,
    ) -> Dict[str, object]:
        """Call Gemini with raw job title and description."""
        location_str = f"Location: {location}" if location else "Location: Not specified"
        
        prompt = dedent(
            f"""
            Score how appealing this role is *for the candidate* using the supplied profile + preferences.
            
            Analyze the raw job posting below and extract relevant information about:
            - Location and remote/hybrid/onsite work model
            - Salary/compensation (if mentioned, otherwise mark as unknown)
            - Job type (full-time, contract, etc.)
            - Technical stack and responsibilities
            - Interest alignment with candidate's goals
            
            If compensation is not mentioned, DO NOT cap the For-Me score—treat it as "unknown" and reason from preferences tolerance.
            Always justify trade-offs using concrete quotes (max 2 sentences).

            Return ONLY JSON with the shape:
            {{
                "for_me_score": number 0-100,
                "dimension_scores": {{
                    "location": number,
                    "salary": number,
                    "job_type": number,
                    "interest_alignment": number
                }},
                "reasoning": "short paragraph"
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

            === CANDIDATE PREFERENCES ===
            {preferences}
            === END PREFERENCES ===
            """
        ).strip()

        return self.client.generate_json(
            prompt,
            metadata={"role": job_title, "company": company},
        )

    def _call_gemini(
        self,
        role_payload: Dict[str, object],
        profile: str,
        preferences: str,
    ) -> Dict[str, object]:
        prompt = dedent(
            f"""
            Score how appealing this role is *for the candidate* using the supplied profile + preferences.
            Consider location, salary/compensation (or explain assumptions if missing), working model (remote/on-site, job_type), and interest alignment.
            If compensation is null or omitted, DO NOT cap the For-Me score—treat the salary dimension as "unknown" and reason from preferences tolerance.
            Always justify trade-offs using concrete quotes (max 2 sentences).

            Return ONLY JSON with the shape:
                        {{
                            "for_me_score": number 0-100,
                            "dimension_scores": {{
                                    "location": number,
                                    "salary": number,
                                    "job_type": number,
                                    "interest_alignment": number
                            }},
              "reasoning": "short paragraph"
            }}

            Role JSON:
            {json.dumps(role_payload, indent=2)}

            === CANDIDATE PROFILE ===
            {profile}
            === END PROFILE ===

            === CANDIDATE PREFERENCES ===
            {preferences}
            === END PREFERENCES ===
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
    agent = ForMeScoreAgent()
    
    # Test with raw job description
    result = agent.evaluate(
        job_title="Backend Engineer",
        job_description="""
        We are looking for a Backend Engineer to join our team in London.
        
        Requirements:
        - 3+ years experience with Go or Python
        - Experience with Docker and Kubernetes
        - Strong understanding of distributed systems
        
        Benefits:
        - Competitive salary £60-75k
        - Hybrid working (2 days in office)
        - 25 days holiday
        """,
        company="ExampleCorp",
        location="London, UK",
    )
    print(result.to_dict())
