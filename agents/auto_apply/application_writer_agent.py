"""Application Writer Agent - persists success JSON artifacts."""
from __future__ import annotations

import json
from pathlib import Path

from .context import AutoApplyContext
from .application_submit_agent import SubmissionResult


class ApplicationWriterAgent:
    """Writes the applied payload to answers/applied."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path(__file__).resolve().parents[3]
        self.applied_dir = self.repo_root / "answers" / "applied"
        self.applied_dir.mkdir(parents=True, exist_ok=True)

    def write(self, context: AutoApplyContext, submission: SubmissionResult) -> Path:
        job_name = context.ensure_job_name()
        payload = {
            "job_url": context.job_url,
            "job_name": job_name,
            "applied": True,
            "answers_used": context.answers_payload(),
            "timestamp": context.timestamp,
            "status": "successful_application",
            "submission_steps": submission.steps,
        }
        path = self.applied_dir / f"a_{job_name}.json"
        path.write_text(json.dumps(payload, indent=2))
        return path
