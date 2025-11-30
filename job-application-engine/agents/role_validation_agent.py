"""LLM-backed role validation agent for the evaluation workflow."""
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
class RoleValidationResult:
    is_valid: bool
    blocking_gaps: List[str]
    warnings: List[str]
    confidence: float
    summary: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "is_valid": self.is_valid,
            "blocking_gaps": self.blocking_gaps,
            "warnings": self.warnings,
            "confidence": self.confidence,
            "summary": self.summary,
        }


class RoleValidationAgent:
    MODEL_NAME = "gemini-2.5-pro"

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or Path(__file__).resolve().parents[1]
        self.client = GeminiClient(
            GeminiConfig(
                model=self.MODEL_NAME,
                system_instruction=
                "You are a recruiting operations specialist who checks job descriptions for missing or risky data before downstream scoring.",
                temperature=0.05,
                mock_bucket="role_validation",
            )
        )

    def evaluate(self, role_payload: Dict[str, object]) -> RoleValidationResult:
        prompt = dedent(
            f"""
            Review the following role description JSON and determine whether it is ready for scoring.
            Flag *blocking_gaps* for any missing critical data (company, title, must-have qualifications, core responsibilities, etc.).
            Missing compensation/salary data should be reported as a *warning* only—never make it blocking.
            If qualifications are described elsewhere (e.g., responsibilities, skills, tech_stack), treat that as sufficient—do NOT require a separate "Qualifications" header.
            Provide *warnings* for softer issues to fix later.

            Return ONLY JSON shaped exactly like:
            {{
              "is_valid": boolean,
              "blocking_gaps": ["..."],
              "warnings": ["..."],
              "confidence": number between 0 and 1,
              "summary": "one sentence overview"
            }}

            Role JSON:
            {json.dumps(role_payload, indent=2)}
            """
        ).strip()

        response = self.client.generate_json(
            prompt,
            metadata={
                "role": role_payload.get("role") or role_payload.get("title"),
                "company": role_payload.get("company"),
            },
        )
        blocking_gaps = response.get("blocking_gaps", [])
        warnings = response.get("warnings", [])
        blocking_gaps, warnings = self._downgrade_compensation_gaps(blocking_gaps, warnings)
        blocking_gaps, warnings = self._downgrade_qualification_gaps(role_payload, blocking_gaps, warnings)
        is_valid = len(blocking_gaps) == 0
        return RoleValidationResult(
            is_valid=is_valid,
            blocking_gaps=blocking_gaps,
            warnings=warnings,
            confidence=float(response.get("confidence", 0.5)),
            summary=response.get("summary", "No summary provided"),
        )

    @staticmethod
    def _downgrade_compensation_gaps(blocking_gaps: List[str], warnings: List[str]) -> tuple[List[str], List[str]]:
        compensation_keywords = ("salary", "compensation", "pay", "remuneration", "package")
        filtered_blocking = []
        updated_warnings = list(warnings)
        for gap in blocking_gaps:
            lower = gap.lower()
            if any(keyword in lower for keyword in compensation_keywords):
                updated_warnings.append(gap)
            else:
                filtered_blocking.append(gap)
        return filtered_blocking, updated_warnings

    @staticmethod
    def _downgrade_qualification_gaps(
        role_payload: Dict[str, object],
        blocking_gaps: List[str],
        warnings: List[str],
    ) -> tuple[List[str], List[str]]:
        if RoleValidationAgent._has_qualification_signal(role_payload):
            filtered = []
            updated_warnings = list(warnings)
            for gap in blocking_gaps:
                lower = gap.lower()
                if "qualification" in lower or "requirement" in lower:
                    updated_warnings.append(gap)
                else:
                    filtered.append(gap)
            return filtered, updated_warnings
        return blocking_gaps, warnings

    @staticmethod
    def _has_qualification_signal(role_payload: Dict[str, object]) -> bool:
        candidate_sections = (
            "qualifications",
            "requirements",
            "responsibilities",
            "tech_stack",
            "skills",
            "experience",
        )
        for key in candidate_sections:
            value = role_payload.get(key)
            if isinstance(value, list) and any(str(item).strip() for item in value):
                return True
            if isinstance(value, str) and value.strip():
                return True
        return False


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    agent = RoleValidationAgent()
    demo_role = {"company": "DemoCorp", "role": "AI Engineer", "location": "Remote"}
    print(agent.evaluate(demo_role).to_dict())
