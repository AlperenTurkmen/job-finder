"""Top-level Orchestrator Agent driving the multi-step workflow."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

from agents.cover_letter.cover_letter_generator_agent import CoverLetterGeneratorAgent
from agents.cover_letter.hr_simulation_agent import HRSimulationAgent
from agents.common.profile_agent import ProfileAgent
from agents.common.role_analysis_agent import RoleAnalysisAgent
from agents.cover_letter.style_extractor_agent import StyleExtractorAgent


class OrchestratorAgent:
    """Coordinates the ADK workflow end-to-end."""

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or Path(__file__).resolve().parents[2]
        self.output_dir = self.base_path / "data" / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.revision_path = self.output_dir / "revision_history.md"
        self.final_letter_path = self.output_dir / "final_cover_letter.md"
        self.role_fit_path = self.output_dir / "role_fit_score.json"
        self.selected_cv_path = self.output_dir / "selected_cv.json"

        # subagents
        self.role_agent = RoleAnalysisAgent(self.base_path)
        self.profile_agent = ProfileAgent(self.base_path)
        self.style_agent = StyleExtractorAgent(self.base_path)
        self.cover_agent = CoverLetterGeneratorAgent(self.base_path)
        self.hr_agent = HRSimulationAgent(self.base_path)

    def run(self) -> Dict[str, object]:
        """Execute the orchestrated workflow and return the final payload."""
        profile_package = self.profile_agent.load_profile()
        role_summary = self.role_agent.run().to_dict()
        style_profile = self.style_agent.run()

        selected_variant = role_summary.get("cv_recommendation", {}).get("selected_variant", "cv_general")
        selected_cv = profile_package["cv_library"].get(selected_variant, {})
        self.selected_cv_path.write_text(
            json.dumps({"selected_variant": selected_variant, "cv": selected_cv}, indent=2)
        )

        letter, history = self._iterative_loop(role_summary, profile_package, style_profile, selected_cv)

        self.final_letter_path.write_text(letter)
        self.role_fit_path.write_text(json.dumps({"score": history[-1]["score"]}, indent=2))
        self._write_history(history)

        return {
            "final_cover_letter": letter,
            "hr_report": history[-1],
            "revision_history": history,
            "selected_cv": selected_variant,
            "role_fit_score": history[-1]["score"],
        }

    def select_cv_only(self) -> Dict[str, object]:
        """Utility entry point for workflow engines that only need CV data."""
        profile_package = self.profile_agent.load_profile()
        role_summary = self.role_agent.run().to_dict()
        selected_variant = role_summary.get("cv_recommendation", {}).get("selected_variant", "cv_general")
        selected_cv = profile_package["cv_library"].get(selected_variant, {})
        payload = {"selected_variant": selected_variant, "cv": selected_cv}
        self.selected_cv_path.write_text(json.dumps(payload, indent=2))
        return payload

    # -------------------- iterative loop --------------------
    def _iterative_loop(
        self,
        role_summary: Dict[str, object],
        profile_package: Dict[str, object],
        style_profile: Dict[str, object],
        selected_cv: Dict[str, object],
    ) -> Tuple[str, List[Dict[str, object]]]:
        history: List[Dict[str, object]] = []
        score = 0
        iteration = 1
        letter = ""
        feedback: Dict[str, object] | None = None
        while score < 100 and iteration <= 5:
            letter = self.cover_agent.generate(role_summary, profile_package, style_profile, iteration, feedback)
            feedback = self.hr_agent.evaluate(letter, selected_cv, iteration)
            score = feedback["score"]
            history.append(feedback)
            if score >= 100 or iteration == 5:
                break
            letter = self.cover_agent.revise(letter, feedback, style_profile, iteration + 1)
            iteration += 1
        return letter, history

    def _write_history(self, history: List[Dict[str, object]]) -> None:
        header = ["# Cover Letter Revision History", "", "| Iteration | Score | Notes |", "| --- | --- | --- |"]
        rows = [f"| {item['iteration']} | {item['score']} | {', '.join(item['positives'])} |" for item in history]
        self.revision_path.write_text("\n".join(header + rows))


if __name__ == "__main__":
    orchestrator = OrchestratorAgent()
    result = orchestrator.run()
    print(json.dumps(result, indent=2))
