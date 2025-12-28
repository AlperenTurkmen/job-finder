"""CLI entry point for the auto-apply orchestrator."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

# Allow running this file directly (python agents/auto_apply/run_auto_apply.py ...)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

dotenv_path = PROJECT_ROOT / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path, override=True)

from agents.auto_apply.orchestrator import AutoApplyOrchestrator
from utils.logging import configure_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auto-apply to a job via native Playwright")
    parser.add_argument("job_url", help="Target job application URL")
    parser.add_argument("cover_letter_file", help="Path to the cover letter text file")
    parser.add_argument("profile_json", help="Path to the profile.json file")
    parser.add_argument("cv_pdf", help="Path to the candidate CV PDF")
    parser.add_argument(
        "--no-wait-for-user",
        action="store_true",
        help="Do not block for user answers (workflow will fail instead)",
    )
    parser.add_argument(
        "--answers-json",
        help="Optional debug file with field_id → answer overrides; skips profile/CV auto answers",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging()
    orchestrator = AutoApplyOrchestrator()
    result = orchestrator.run(
        job_url=args.job_url,
        cover_letter=args.cover_letter_file,
        profile_path=Path(args.profile_json),
        cv_path=Path(args.cv_pdf),
        wait_for_user=not args.no_wait_for_user,
        answers_json=Path(args.answers_json) if args.answers_json else None,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
