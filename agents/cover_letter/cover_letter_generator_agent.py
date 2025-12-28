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
    """Combines role, profile, and style insights to craft letters."""

    REASONING_MODEL = "gemini-2.5-pro"
    STYLE_MODEL = "gemini-2.5-flash"

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or Path(__file__).resolve().parents[2]
        self.output_dir = self.base_path / "data" / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
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
        role_summary: Dict[str, object],
        profile_package: Dict[str, object],
        style_profile: Dict[str, object],
        iteration: int = 1,
        feedback: Optional[Dict[str, object]] = None,
    ) -> str:
        """Return the draft cover letter content using Gemini."""
        selected_cv_key = role_summary.get("cv_recommendation", {}).get("selected_variant", "cv_general")
        selected_cv = profile_package.get("cv_library", {}).get(selected_cv_key, {})
        prompt = dedent(
            f"""
            Compose a four-paragraph cover letter in Markdown. Requirements:
            - Tone and cadence must reflect this style fingerprint: {json.dumps(style_profile, indent=2)}
            - Address these talking points explicitly: {json.dumps(role_summary.get('mandatory_talking_points', []), indent=2)}
            - Cite achievements pulled from this selected CV: {json.dumps(selected_cv, indent=2)}
            - Reference broader profile context when relevant: {json.dumps(self._profile_summary(profile_package), indent=2)}
            - If HR feedback is provided, incorporate it seamlessly: {json.dumps(feedback or {}, indent=2)}
            - Use UK English.
            - Use connective phrases already favored by the writer when natural.
            - Return only the final letter (no code fences, no additional commentary).

            Role summary for grounding:
            {json.dumps(role_summary, indent=2)}
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
        feedback: Dict[str, object],
        style_profile: Dict[str, object],
        iteration: int,
    ) -> str:
        """Use Gemini Flash to apply HR suggestions while preserving tone."""
        prompt = dedent(
            f"""
            You are editing an existing cover letter. Apply the feedback while keeping the user's style intact.
            Provide only the revised Markdown letter.

            Style fingerprint:
            {json.dumps(style_profile, indent=2)}

            HR feedback (authoritative):
            {json.dumps(feedback, indent=2)}

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
    def _profile_summary(self, profile_package: Dict[str, object]) -> Dict[str, object]:
        return {
            "qualifications": profile_package.get("qualifications", {}).get("degrees", []),
            "skills": profile_package.get("skills", {}).get("core_skills", []),
            "experience": [role.get("title") for role in profile_package.get("experience", {}).get("roles", [])],
            "projects": [project.get("name") for project in profile_package.get("projects", {}).get("projects", [])],
        }

    def _write_iteration(self, letter: str, iteration: int) -> None:
        filename = self.output_dir / f"draft_cover_letter_iter_{iteration}.md"
        filename.write_text(letter)


if __name__ == "__main__":
    from agents.common.role_analysis_agent import RoleAnalysisAgent
    from agents.common.profile_agent import ProfileAgent
    from agents.cover_letter.style_extractor_agent import StyleExtractorAgent

    base_path = Path(__file__).resolve().parents[2]
    role = RoleAnalysisAgent(base_path).run()
    profile = ProfileAgent(base_path).load_profile()
    style = StyleExtractorAgent(base_path).run()
    generator = CoverLetterGeneratorAgent(base_path)
    print(generator.generate(role.to_dict(), profile, style))
