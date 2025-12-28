"""Role Evaluation Engine orchestrating the multi-agent scoring pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

try:  # pragma: no cover - import flexibility for script/module execution
    from agents.common.csv_writer_agent import CSVWriterAgent
    from agents.scoring.for_me_score_agent import ForMeScoreAgent
    from agents.scoring.for_them_score_agent import ForThemScoreAgent
    from agents.common.insight_generator_agent import InsightGeneratorAgent
    from agents.scoring.role_validation_agent import RoleValidationAgent
except ModuleNotFoundError:  # fallback when run from inside agents package
    from ..common.csv_writer_agent import CSVWriterAgent
    from .for_me_score_agent import ForMeScoreAgent
    from .for_them_score_agent import ForThemScoreAgent
    from ..common.insight_generator_agent import InsightGeneratorAgent
    from .role_validation_agent import RoleValidationAgent


class RoleEvaluationEngine:
    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or Path(__file__).resolve().parents[2]
        self.input_file = self.base_path / "data" / "output" / "all_jobs.json"
        self.output_file = self.base_path / "data" / "output" / "evaluation_results.json"
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        self.validator = RoleValidationAgent(self.base_path)
        self.for_me_agent = ForMeScoreAgent(self.base_path)
        self.for_them_agent = ForThemScoreAgent(self.base_path)
        self.insight_agent = InsightGeneratorAgent(self.base_path)
        self.csv_agent = CSVWriterAgent(self.base_path)

    def run(self) -> List[Dict[str, object]]:
        roles = self._load_roles()
        results = []
        for role in roles:
            validation = self.validator.evaluate(role)
            if not validation.is_valid:
                results.append(
                    {
                        "company": role.get("company"),
                        "role": role.get("role"),
                        "status": "skipped",
                        "blocking_gaps": validation.blocking_gaps,
                        "warnings": validation.warnings,
                        "summary": validation.summary,
                    }
                )
                continue
            for_me = self.for_me_agent.evaluate(role).to_dict()
            for_them = self.for_them_agent.evaluate(role).to_dict()
            insight = self.insight_agent.synthesize(role, for_me, for_them).to_dict()
            self.csv_agent.append_row(
                role.get("company", "Unknown"),
                role.get("role", "Unknown"),
                for_me["for_me_score"],
                for_them["for_them_score"],
                insight["insight"],
            )
            results.append(
                {
                    "company": role.get("company"),
                    "role": role.get("role"),
                    "for_me": for_me,
                    "for_them": for_them,
                    "insight": insight,
                }
            )
        self.output_file.write_text(json.dumps(results, indent=2))
        return results

    def _load_roles(self) -> List[Dict[str, object]]:
        if not self.input_file.exists():
            raise FileNotFoundError(f"all_jobs.json not found at {self.input_file}")
        data = json.loads(self.input_file.read_text())
        if not isinstance(data, list):
            raise ValueError("all_jobs.json must contain a JSON array of roles")
        return data


if __name__ == "__main__":
    engine = RoleEvaluationEngine()
    payload = engine.run()
    print(json.dumps(payload, indent=2))
