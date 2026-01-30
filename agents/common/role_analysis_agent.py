"""Role Analysis Agent powered by Gemini 2.5 Pro."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Dict, List, Optional

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
    """Extracts semantic structure from job descriptions using Gemini."""

    MODEL_NAME = "gemini-2.5-pro"

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or Path(__file__).resolve().parents[2]
        self.input_role_path = self.base_path / "data" / "role.json"
        self.role_summary_path = self.base_path / "data" / "output" / "role_summary.json"
        self.cv_library_path = self.base_path / "data" / "cv_library"
        self.gemini = GeminiClient(
            GeminiConfig(
                model=self.MODEL_NAME,
                system_instruction=
                "You are an expert role analyst. Provide structured summaries for downstream hiring agents.",
                temperature=0.15,
                json_mode=True,
                mock_bucket="role_analysis",
            )
        )

    def analyze(
        self,
        job_title: str,
        job_description: str,
        company: str,
        location: Optional[str] = None,
    ) -> RoleSummary:
        """Analyze a raw job description and extract structured information.
        
        Args:
            job_title: The job title
            job_description: Raw job description text
            company: Company name
            location: Job location (optional)
        """
        llm_summary = self._call_gemini_raw(job_title, job_description, company, location)
        
        summary = RoleSummary(
            title=job_title,
            company=company,
            location=location or llm_summary.get("location", "Unknown"),
            responsibilities=llm_summary.get("responsibilities", []),
            must_haves=llm_summary.get("must_haves", []),
            nice_to_haves=llm_summary.get("nice_to_haves", []),
            company_values=llm_summary.get("company_values", []),
            responsibility_clusters=llm_summary.get("responsibility_clusters", {}),
            priority_tags=llm_summary.get("priority_tags", []),
            role_vector=llm_summary.get("role_vector", {}),
            cv_recommendation=llm_summary.get("cv_recommendation", {"selected_variant": "cv_general"}),
            mandatory_talking_points=llm_summary.get("mandatory_talking_points", []),
        )

        self._store_summary(summary)
        return summary

    def run(self) -> RoleSummary:
        """Legacy method: Load from role.json file."""
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
    def _call_gemini_raw(
        self,
        job_title: str,
        job_description: str,
        company: str,
        location: Optional[str],
    ) -> Dict[str, object]:
        """Analyze raw job description with Gemini."""
        location_str = f"Location: {location}" if location else ""
        
        prompt = dedent(
            f"""
            Analyze this job posting and extract structured information.
            
            Return ONLY JSON with the following shape:
            {{
              "responsibilities": ["responsibility 1", ...],
              "must_haves": ["required skill/experience 1", ...],
              "nice_to_haves": ["optional skill 1", ...],
              "company_values": ["value 1", ...],
              "responsibility_clusters": {{ "cluster_name": ["task 1", ...] }},
              "priority_tags": ["tag 1", ...],
              "role_vector": {{ "dimension": 0.0-1.0 }},
              "mandatory_talking_points": ["point 1", ...]
            }}
            
            Guidelines:
            - Extract all key responsibilities mentioned
            - Separate must-have requirements from nice-to-haves
            - Identify any company values or culture hints
            - Cluster responsibilities into meaningful groups
            - Provide priority tags (keywords to emphasize in applications)
            - Create a role_vector with normalized weights for emphasis areas
            - List 3-5 mandatory talking points for a cover letter

            === JOB POSTING ===
            Company: {company}
            Title: {job_title}
            {location_str}
            
            {job_description}
            === END JOB POSTING ===
            """
        ).strip()

        return self.gemini.generate_json(
            prompt,
            metadata={"role": job_title, "company": company},
        )

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
        self.role_summary_path.parent.mkdir(parents=True, exist_ok=True)
        self.role_summary_path.write_text(json.dumps(summary.to_dict(), indent=2))


if __name__ == "__main__":  # Manual trigger convenience
    agent = RoleAnalysisAgent()
    
    # Test with raw job description
    summary = agent.analyze(
        job_title="Backend Engineer",
        job_description="""
        We're looking for a Backend Engineer to help build our platform.
        
        Requirements:
        - 3+ years Python experience
        - Experience with Docker and Kubernetes
        - Strong API design skills
        
        Nice to have:
        - ML/AI experience
        - Cloud experience
        """,
        company="ExampleCorp",
        location="London",
    )
    print(json.dumps(summary.to_dict(), indent=2))
