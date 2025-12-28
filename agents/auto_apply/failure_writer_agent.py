"""Failure Writer Agent - records non-applied outcomes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from .context import AutoApplyContext


class FailureWriterAgent:
    """Writes explanatory JSON when the application cannot be completed."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path(__file__).resolve().parents[3]
        self.not_applied_dir = self.repo_root / "answers" / "not_applied"
        self.not_applied_dir.mkdir(parents=True, exist_ok=True)

    def write(self, context: AutoApplyContext, reason: str, recommended_answers: Dict[str, Dict[str, str]]) -> Path:
        job_name = context.ensure_job_name()
        payload = {
            "job_url": context.job_url,
            "job_name": job_name,
            "applied": False,
            "recommended_answers": recommended_answers,
            "reason": reason,
            "timestamp": context.timestamp,
        }
        path = self.not_applied_dir / f"a_{job_name}.json"
        path.write_text(json.dumps(payload, indent=2))
        return path
