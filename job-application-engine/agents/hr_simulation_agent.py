"""HR Simulation Agent backed by Gemini 2.5 Pro."""
from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent
from typing import Dict

try:
    from .gemini_client import GeminiClient, GeminiConfig
except ImportError:  # pragma: no cover - script execution fallback
    from gemini_client import GeminiClient, GeminiConfig


class HRSimulationAgent:
    MODEL_NAME = "gemini-2.5-pro"

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or Path(__file__).resolve().parents[1]
        self.output_dir = self.base_path / "output"
        self.role_summary_path = self.base_path / "memory" / "role_summary.json"
        self.client = GeminiClient(
            GeminiConfig(
                model=self.MODEL_NAME,
                system_instruction="Act as a meticulous HR reviewer scoring cover letters strictly.",
                temperature=0.15,
                mock_bucket="hr_simulation",
            )
        )

    def evaluate(
        self,
        cover_letter: str,
        selected_cv: Dict[str, object],
        iteration: int,
    ) -> Dict[str, object]:
        role_summary = json.loads(self.role_summary_path.read_text()) if self.role_summary_path.exists() else {}
        prompt = dedent(
            f"""
            Evaluate the candidate's submission. Respond ONLY with JSON containing:
            {{
              "iteration": integer,
              "score": integer (0-100),
              "positives": [string],
              "negatives": [string],
              "fix_suggestions": [string],
              "missing_qualifications": [string],
              "tone_issues": boolean,
              "culture_alignment": {{ value: boolean }}
            }}

            Requirements:
            - Weight must-have skills from the role summary heavily.
            - Penalize vagueness, missing gratitude, or tone mismatches.
            - Provide actionable fix suggestions (paragraph-level guidance).
            - Measure the length and relevance of the cover letter to the role.
            - Measure how readible the cover letter is.

            Role summary:
            {json.dumps(role_summary, indent=2)}

            Selected CV variant:
            {json.dumps(selected_cv, indent=2)}

            Cover letter:
            {cover_letter}

            Iteration: {iteration}
            """
        ).strip()

        feedback = self.client.generate_json(
            prompt,
            metadata={"iteration": iteration, "role": role_summary.get("title")},
        )
        feedback.setdefault("iteration", iteration)
        self._persist_report(feedback)
        return feedback

    def _persist_report(self, feedback: Dict[str, object]) -> None:
        report_path = self.output_dir / "hr_report.json"
        report_path.write_text(json.dumps(feedback, indent=2))


if __name__ == "__main__":
    agent = HRSimulationAgent()
    mock_cv = {"summary": "Example CV", "highlights": ["impact"]}
    result = agent.evaluate("Sample cover letter text with automation details", mock_cv, iteration=1)
    print(json.dumps(result, indent=2))
