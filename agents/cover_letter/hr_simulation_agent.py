"""HR Simulation Agent backed by Gemini 2.5 Pro."""
from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent
from typing import Dict, Optional

try:
    from agents.common.gemini_client import GeminiClient, GeminiConfig
except ImportError:  # pragma: no cover - script execution fallback
    from ..common.gemini_client import GeminiClient, GeminiConfig


class HRSimulationAgent:
    MODEL_NAME = "gemini-2.5-pro"

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or Path(__file__).resolve().parents[2]
        self.output_dir = self.base_path / "data" / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.profile_file = self.base_path / "data" / "profile.md"
        self.client = GeminiClient(
            GeminiConfig(
                model=self.MODEL_NAME,
                system_instruction="Act as a meticulous HR reviewer scoring cover letters strictly.",
                temperature=0.15,
                json_mode=True,
                mock_bucket="hr_simulation",
            )
        )

    def evaluate(
        self,
        cover_letter: str,
        job_title: str,
        job_description: str,
        company: str,
        iteration: int = 1,
    ) -> Dict[str, object]:
        """Evaluate a cover letter against the job description.
        
        Args:
            cover_letter: The cover letter text to evaluate
            job_title: Job title
            job_description: Raw job description
            company: Company name
            iteration: Evaluation iteration number
        """
        profile = self._load_profile()
        
        prompt = dedent(
            f"""
            Evaluate this cover letter as an HR reviewer. Respond ONLY with JSON containing:
            {{
              "iteration": integer,
              "score": integer (0-100),
              "positives": [string],
              "negatives": [string],
              "fix_suggestions": [string],
              "missing_qualifications": [string],
              "tone_issues": boolean,
              "culture_alignment": boolean
            }}

            Evaluation criteria:
            - Does the letter address key requirements from the job posting?
            - Does it highlight relevant experience from the candidate?
            - Is the tone professional and appropriate?
            - Is it concise and well-structured?
            - Are there specific examples and achievements?
            - Penalize vagueness, generic statements, or mismatches
            - Provide actionable fix suggestions

            === JOB POSTING ===
            Company: {company}
            Title: {job_title}
            
            {job_description}
            === END JOB POSTING ===

            === CANDIDATE PROFILE ===
            {profile}
            === END PROFILE ===

            === COVER LETTER TO EVALUATE ===
            {cover_letter}
            === END COVER LETTER ===

            Iteration: {iteration}
            """
        ).strip()

        feedback = self.client.generate_json(
            prompt,
            metadata={"iteration": iteration, "role": job_title, "company": company},
        )
        feedback.setdefault("iteration", iteration)
        self._persist_report(feedback)
        return feedback

    def evaluate_legacy(
        self,
        cover_letter: str,
        selected_cv: Dict[str, object],
        iteration: int,
    ) -> Dict[str, object]:
        """Legacy method: Evaluate using structured role summary."""
        role_summary_path = self.output_dir / "role_summary.json"
        role_summary = json.loads(role_summary_path.read_text()) if role_summary_path.exists() else {}
        
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

    def _load_profile(self) -> str:
        if not self.profile_file.exists():
            return ""
        return self.profile_file.read_text()

    def _persist_report(self, feedback: Dict[str, object]) -> None:
        report_path = self.output_dir / "hr_report.json"
        report_path.write_text(json.dumps(feedback, indent=2))


if __name__ == "__main__":
    agent = HRSimulationAgent()
    result = agent.evaluate(
        cover_letter="Sample cover letter discussing my Python and automation experience...",
        job_title="Backend Engineer",
        job_description="""
        We need a Backend Engineer with:
        - Python experience
        - Docker/Kubernetes knowledge
        - API design skills
        """,
        company="ExampleCorp",
        iteration=1,
    )
    print(json.dumps(result, indent=2))
