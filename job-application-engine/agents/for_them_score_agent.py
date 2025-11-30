"""For-Them Score Agent: estimates employer fit via Gemini 2.5."""
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
        self.base_path = base_path or Path(__file__).resolve().parents[1]
        self.profile_file = self.base_path / "memory" / "profile_store" / "profile.json"
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

    def evaluate(self, role_payload: Dict[str, object]) -> ForThemScoreResult:
        profile = self._load_json(self.profile_file)
        response = self._call_gemini(role_payload, profile)
        dimension_scores = response.get("dimension_scores", {})
        return ForThemScoreResult(
            for_them_score=float(response.get("for_them_score", 0)),
            reasoning=response.get("reasoning", "No reasoning returned"),
            dimension_scores={k: float(v) for k, v in dimension_scores.items()},
        )

    def _call_gemini(self, role_payload: Dict[str, object], profile: Dict[str, object]) -> Dict[str, object]:
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

            Candidate profile JSON:
            {json.dumps(profile, indent=2)}
            """
        ).strip()

        return self.client.generate_json(
            prompt,
            metadata={
                "role": role_payload.get("role"),
                "company": role_payload.get("company"),
            },
        )

    def _load_json(self, path: Path) -> Dict[str, object]:
        if not path.exists():
            raise FileNotFoundError(f"Expected file missing: {path}")
        return json.loads(path.read_text())


if __name__ == "__main__":  # pragma: no cover - manual test requires API key
    agent = ForThemScoreAgent()
    mock_role = {
        "company": "ExampleCorp",
        "role": "Backend Engineer",
        "location": "London",
        "tech_stack": ["Go", "Docker", "Kubernetes"],
        "responsibilities": ["Design APIs", "Scale distributed systems"],
    }
    print(agent.evaluate(mock_role).to_dict())
