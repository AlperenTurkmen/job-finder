"""Profile Agent responsible for loading user-specific assets into memory."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List


class ProfileAgent:
    """Aggregates profile.json, CV variants, and writing samples."""

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or Path(__file__).resolve().parents[2]
        self.profile_path = self.base_path / "data"
        self.profile_file = self.profile_path / "profile.json"
        self.cv_library_path = self.profile_path / "cv_library"
        self.uploaded_cv_path = self.base_path / "data" / "user_uploaded_cv.pdf"
        self.converted_cv_path = self.cv_library_path / "cv_uploaded.json"

    def load_profile(self) -> Dict[str, object]:
        """Return the normalized profile data structure."""
        raw_profile = self._load_profile_json()
        package = self._normalize_profile(raw_profile)
        package["profile"] = raw_profile
        package["cv_library"] = self._load_cv_library()
        package["writing_samples"] = self._load_writing_samples()
        package["cv_library"]["cv_uploaded"] = self._convert_uploaded_cv()
        return package

    # -------------------- helpers --------------------
    def _load_profile_json(self) -> Dict[str, object]:
        if not self.profile_file.exists():
            raise FileNotFoundError(
                f"profile.json not found at {self.profile_file}. Please create it to continue."
            )
        return json.loads(self.profile_file.read_text())

    def _normalize_profile(self, raw_profile: Dict[str, object]) -> Dict[str, object]:
        return {
            "qualifications": self._normalize_qualifications(raw_profile),
            "skills": self._normalize_skills(raw_profile),
            "experience": self._normalize_experience(raw_profile),
            "projects": self._normalize_projects(raw_profile),
        }

    def _normalize_qualifications(self, raw_profile: Dict[str, object]) -> Dict[str, object]:
        if "qualifications" in raw_profile:
            data = raw_profile["qualifications"]
            return {
                "degrees": data.get("degrees", raw_profile.get("education", [])),
                "certifications": data.get("certifications", raw_profile.get("certifications", [])),
            }
        return {
            "degrees": raw_profile.get("education", []),
            "certifications": raw_profile.get("certifications", []),
        }

    def _normalize_skills(self, raw_profile: Dict[str, object]) -> Dict[str, List[str]]:
        if "skills" in raw_profile:
            return raw_profile["skills"]
        technical = raw_profile.get("technical_skills", {})
        return {
            "core_skills": technical.get("languages", []),
            "specialist_skills": technical.get("frameworks_libraries", []) + technical.get("ai_ml", []),
            "soft_skills": raw_profile.get("strengths", []),
        }

    def _normalize_experience(self, raw_profile: Dict[str, object]) -> Dict[str, List[Dict[str, object]]]:
        experience_block = raw_profile.get("experience", [])
        if isinstance(experience_block, dict):
            if "roles" in experience_block:
                return experience_block
            return {"roles": experience_block.get("roles", [])}
        return {"roles": experience_block}

    def _normalize_projects(self, raw_profile: Dict[str, object]) -> Dict[str, List[Dict[str, object]]]:
        projects_block = raw_profile.get("projects", [])
        if isinstance(projects_block, dict):
            return projects_block if "projects" in projects_block else {"projects": []}
        return {"projects": projects_block}

    def _load_cv_library(self) -> Dict[str, Dict[str, object]]:
        payload: Dict[str, Dict[str, object]] = {}
        for path in sorted(self.cv_library_path.glob("*.json")):
            payload[path.stem] = json.loads(path.read_text())
        return payload

    def _load_writing_samples(self) -> List[str]:
        samples_dir = self.profile_path / "writing_samples"
        samples = []
        for sample_file in sorted(samples_dir.glob("*.md")):
            samples.append(sample_file.read_text())
        return samples

    def _convert_uploaded_cv(self) -> Dict[str, object]:
        """Mock conversion pipeline from PDF to structured JSON."""
        if not self.uploaded_cv_path.exists():
            return {
                "summary": "No uploaded CV detected.",
                "sections": {},
            }
        text = self.uploaded_cv_path.read_text(errors="ignore")
        pseudo_bullets = [line.strip() for line in text.splitlines() if line.strip()]
        extracted_sections = {
            "overview": pseudo_bullets[:3],
            "meta": {
                "source": str(self.uploaded_cv_path.name),
                "model": "gemini-2.5-pro",
            },
        }
        structured = {
            "summary": "Auto-converted CV prepared for downstream filtering.",
            "highlights": pseudo_bullets[:5],
            "sections": extracted_sections,
        }
        self.converted_cv_path.write_text(json.dumps(structured, indent=2))
        return structured


if __name__ == "__main__":
    agent = ProfileAgent()
    package = agent.load_profile()
    print(json.dumps(package, indent=2, default=str))
