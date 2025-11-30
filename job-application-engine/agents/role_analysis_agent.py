"""Role Analysis Agent powered by Gemini 2.5 Pro."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Dict, List

try:
    from .gemini_client import GeminiClient, GeminiConfig
except ImportError:  # pragma: no cover - script execution fallback
    from gemini_client import GeminiClient, GeminiConfig


@dataclass
class RoleSummary:
    """Serializable container for downstream agents."""

    title: str
    company: str
    location: str
    responsibilities: List[str]
    must_haves: List[str]
    nice_to_haves: List[str]
    company_values: List[str]
    responsibility_clusters: Dict[str, List[str]]
    priority_tags: List[str]
    role_vector: Dict[str, float]
    cv_recommendation: Dict[str, str]
    mandatory_talking_points: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "responsibilities": self.responsibilities,
            "must_haves": self.must_haves,
            "nice_to_haves": self.nice_to_haves,
            "company_values": self.company_values,
            "responsibility_clusters": self.responsibility_clusters,
            "priority_tags": self.priority_tags,
            "role_vector": self.role_vector,
            "cv_recommendation": self.cv_recommendation,
            "mandatory_talking_points": self.mandatory_talking_points,
        }


class RoleAnalysisAgent:
    """Extracts semantic structure from the provided role JSON using Gemini."""

    MODEL_NAME = "gemini-2.5-pro"

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or Path(__file__).resolve().parents[1]
        self.input_role_path = self.base_path / "input" / "role.json"
        self.role_summary_path = self.base_path / "memory" / "role_summary.json"
        self.cv_library_path = self.base_path / "memory" / "profile_store" / "cv_library"
        self.gemini = GeminiClient(
            GeminiConfig(
                model=self.MODEL_NAME,
                system_instruction=
                "You are an expert role analyst. Provide structured summaries for downstream hiring agents.",
                temperature=0.15,
                mock_bucket="role_analysis",
            )
        )

    def run(self) -> RoleSummary:
        role_payload = self._load_role()
        cv_library = self._load_cv_library()
        llm_summary = self._call_gemini(role_payload, cv_library)

        summary = RoleSummary(
            title=role_payload.get("title", llm_summary.get("title", "Unknown")),
            company=role_payload.get("company", llm_summary.get("company", "Unknown")),
            location=role_payload.get("location", llm_summary.get("location", "Unknown")),
            responsibilities=role_payload.get("responsibilities", []),
            must_haves=role_payload.get("must_haves", []),
            nice_to_haves=role_payload.get("nice_to_haves", []),
            company_values=role_payload.get("company_values", []),
            responsibility_clusters=llm_summary.get("responsibility_clusters", {}),
            priority_tags=llm_summary.get("priority_tags", []),
            role_vector=llm_summary.get("role_vector", {}),
            cv_recommendation=llm_summary.get("cv_recommendation", {"selected_variant": "cv_general"}),
            mandatory_talking_points=llm_summary.get("mandatory_talking_points", []),
        )

        self._store_summary(summary)
        return summary

    # -------------------- helpers --------------------
    def _load_role(self) -> Dict[str, object]:
        if not self.input_role_path.exists():  # pragma: no cover - defensive
            raise FileNotFoundError(f"Role file missing at {self.input_role_path}")
        return json.loads(self.input_role_path.read_text())

    def _load_cv_library(self) -> Dict[str, Dict[str, object]]:
        library: Dict[str, Dict[str, object]] = {}
        for path in sorted(self.cv_library_path.glob("*.json")):
            library[path.stem] = json.loads(path.read_text())
        return library

    def _call_gemini(self, role_payload: Dict[str, object], cv_library: Dict[str, object]) -> Dict[str, object]:
        prompt = dedent(
            f"""
            You receive:
            1. A role description JSON.
            2. A dictionary of CV variants where keys are filenames and values include "summary" and "highlights".

            Task:
            - Cluster responsibilities into meaningful buckets (keys should be short lowercase tokens).
            - Produce priority tags (ordered list of keywords/phrases to emphasize).
            - Output a role_vector dictionary with normalized weights (0-1) summarizing emphasis areas.
            - Recommend the single best CV variant. Include "selected_variant", "confidence" (0-1 string), and "rationale".
            - List 3-5 mandatory talking points that *must* appear in the cover letter.

            Return ONLY JSON with the following shape:
            {{
              "responsibility_clusters": {{ "cluster": ["sent", ...] }},
              "priority_tags": ["tag", ...],
              "role_vector": {{ "dimension": number }},
              "cv_recommendation": {{ "selected_variant": str, "confidence": str, "rationale": str }},
              "mandatory_talking_points": ["point", ...]
            }}

            Role JSON:
            {json.dumps(role_payload, indent=2)}

            CV Library:
            {json.dumps(cv_library, indent=2)}
            """
        ).strip()

        return self.gemini.generate_json(
            prompt,
            metadata={
                "role": role_payload.get("role") or role_payload.get("title"),
                "company": role_payload.get("company"),
            },
        )

    def _store_summary(self, summary: RoleSummary) -> None:
        self.role_summary_path.write_text(json.dumps(summary.to_dict(), indent=2))


if __name__ == "__main__":  # Manual trigger convenience
    agent = RoleAnalysisAgent()
    output = agent.run()
    print(json.dumps(output.to_dict(), indent=2))
