"""For-Me Score Agent: delegates preference scoring to Gemini 2.5."""
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
        self.base_path = base_path or Path(__file__).resolve().parents[1]
        self.profile_file = self.base_path / "memory" / "profile_store" / "profile.json"
        self.preferences_file = self.base_path / "memory" / "profile_store" / "preferences.json"
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

    def evaluate(self, role_payload: Dict[str, object]) -> ForMeScoreResult:
        profile = self._load_json(self.profile_file)
        preferences = self._load_json(self.preferences_file)
        response = self._call_gemini(role_payload, profile, preferences)
        dimension_scores = response.get("dimension_scores", {})
        return ForMeScoreResult(
            for_me_score=float(response.get("for_me_score", 0)),
            reasoning=response.get("reasoning", "No reasoning returned"),
            dimension_scores={k: float(v) for k, v in dimension_scores.items()},
        )

    def _call_gemini(
        self,
        role_payload: Dict[str, object],
        profile: Dict[str, object],
        preferences: Dict[str, object],
    ) -> Dict[str, object]:
        prompt = dedent(
            f"""
            Score how appealing this role is *for the candidate* using the supplied profile + preferences.
            Consider location, salary/compensation (or explain assumptions if missing), working model (remote/on-site, job_type), and interest alignment.
            If compensation is null or omitted, DO NOT cap the For-Me score—treat the salary dimension as "unknown" and reason from preferences tolerance.
            Weighting guidance is inside preferences.json (importance fields). Always justify trade-offs using concrete quotes (max 2 sentences).

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

            Profile JSON:
            {json.dumps(profile, indent=2)}

            Preferences JSON:
            {json.dumps(preferences, indent=2)}
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
    agent = ForMeScoreAgent()
    demo_role = {
        "company": "ExampleCorp",
        "role": "Backend Engineer",
        "location": "London, UK",
        "salary": "£60-75k",
        "job_type": "Full-time",
        "tech_stack": ["Go", "Docker"],
    }
    print(agent.evaluate(demo_role).to_dict())
