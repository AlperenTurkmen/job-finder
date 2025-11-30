"""Insight Generator Agent: synthesizes scores via Gemini."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Dict

try:
    from .gemini_client import GeminiClient, GeminiConfig
except ImportError:  # pragma: no cover - script execution fallback
    from gemini_client import GeminiClient, GeminiConfig


@dataclass
class InsightResult:
    insight: str

    def to_dict(self) -> Dict[str, str]:
        return {"insight": self.insight}


class InsightGeneratorAgent:
    MODEL_NAME = "gemini-2.5-flash"

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or Path(__file__).resolve().parents[1]
        self.client = GeminiClient(
            GeminiConfig(
                model=self.MODEL_NAME,
                system_instruction=
                "You synthesize recruiter-style insights by combining candidate-centric and company-centric scores.",
                temperature=0.3,
                json_mode=True,
                mock_bucket="insight_generator",
            )
        )

    def synthesize(
        self,
        role_payload: Dict[str, object],
        for_me_output: Dict[str, object],
        for_them_output: Dict[str, object],
    ) -> InsightResult:
        prompt = dedent(
            f"""
            Combine the candidate preference score (for_me_output) with the employer-fit score (for_them_output).
            Produce a concise insight referencing the role/company plus two short bullet-style lists: strengths and risks.
            Recommendation must be one of ["Apply", "Apply with caution", "Skip"].

            Return ONLY JSON:
            {{
              "insight": "one sentence",
              "strengths": ["..."],
              "risks": ["..."],
              "recommendation": "..."
            }}

            Role JSON:
            {json.dumps(role_payload, indent=2)}

            For-Me Output:
            {json.dumps(for_me_output, indent=2)}

            For-Them Output:
            {json.dumps(for_them_output, indent=2)}
            """
        ).strip()

        response = self.client.generate_json(
            prompt,
            metadata={
                "role": role_payload.get("role"),
                "company": role_payload.get("company"),
            },
        )
        narrative = response.get("insight") or "No insight returned"
        strengths = response.get("strengths", [])
        risks = response.get("risks", [])
        recommendation = response.get("recommendation") or "Review manually"
        combined = f"{narrative} Strengths: {', '.join(strengths) or 'n/a'}. Risks: {', '.join(risks) or 'n/a'}. Recommendation: {recommendation}."
        return InsightResult(insight=combined)


if __name__ == "__main__":  # pragma: no cover - manual invocation requires API key
    agent = InsightGeneratorAgent()
    role = {"company": "ExampleCorp", "role": "AI Engineer"}
    fm = {"for_me_score": 78, "dimension_scores": {"location": 90, "salary": 70, "job_type": 80, "interest_alignment": 65}}
    ft = {
        "for_them_score": 82,
        "dimension_scores": {
            "skill_match": 80,
            "experience_relevance": 78,
            "domain_fit": 75,
            "location_convenience": 70,
            "interest_alignment": 72,
        },
    }
    print(agent.synthesize(role, fm, ft).to_dict())
