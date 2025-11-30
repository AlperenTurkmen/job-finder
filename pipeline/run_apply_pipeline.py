"""End-to-end pipeline: careers URLs → job URLs → structured roles → scoring → cover letters → auto-apply."""
from __future__ import annotations

import argparse
import asyncio
import csv
import importlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
JOB_ENGINE_ROOT = PROJECT_ROOT / "job-application-engine"
JOB_ENGINE_AGENTS = JOB_ENGINE_ROOT / "agents"

# Ensure both the workspace root (for scraping agents) and the job-application-engine
# (for cover letter + auto-apply agents) are importable.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(JOB_ENGINE_AGENTS) not in sys.path:
    sys.path.insert(0, str(JOB_ENGINE_AGENTS))

from typing import Tuple

from logging_utils import configure_logging, get_logger  # noqa: E402
from agents.job_url_extractor_agent import extract_all_job_urls  # noqa: E402
from pipeline.scrape_and_normalize import run_full_pipeline  # noqa: E402

logger = get_logger(__name__)

DEFAULT_COMPANIES_CSV = PROJECT_ROOT / "data" / "companies" / "example_companies.csv"
DEFAULT_JOB_URLS_CSV = PROJECT_ROOT / "data" / "job_urls" / "sample_urls.csv"
DEFAULT_INTERMEDIATE_CSV = PROJECT_ROOT / "data" / "roles_for_llm" / "sample_urls_scraped.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "roles"
JOB_ENGINE_INPUT_DIR = JOB_ENGINE_ROOT / "input"
JOB_ENGINE_OUTPUT_DIR = JOB_ENGINE_ROOT / "output"
DEFAULT_PROFILE_JSON = JOB_ENGINE_INPUT_DIR / "profile.json"
DEFAULT_CV_PDF = JOB_ENGINE_INPUT_DIR / "user_uploaded_cv.pdf"
ROLE_JSON_PATH = JOB_ENGINE_INPUT_DIR / "role.json"
ALL_JOBS_PATH = JOB_ENGINE_INPUT_DIR / "all_jobs.json"
COVER_LETTER_PATH = JOB_ENGINE_OUTPUT_DIR / "final_cover_letter.md"
SUMMARY_PATH = PROJECT_ROOT / "results.json"

RoleEvaluationEngineCls = None
OrchestratorAgentCls = None
AutoApplyOrchestratorCls = None


def load_job_engine_components() -> Tuple[Any, Any, Any]:
    """Import job-application-engine components lazily to avoid path issues."""
    global RoleEvaluationEngineCls, OrchestratorAgentCls, AutoApplyOrchestratorCls
    if RoleEvaluationEngineCls is None:
        RoleEvaluationEngineCls = importlib.import_module("role_evaluation_engine").RoleEvaluationEngine
    if OrchestratorAgentCls is None:
        OrchestratorAgentCls = importlib.import_module("orchestrator_agent").OrchestratorAgent
    if AutoApplyOrchestratorCls is None:
        AutoApplyOrchestratorCls = importlib.import_module("auto_apply.orchestrator").AutoApplyOrchestrator
    return RoleEvaluationEngineCls, OrchestratorAgentCls, AutoApplyOrchestratorCls


@dataclass
class JobRecord:
    company: str
    role: str
    job_id: str
    job_url: str | None
    evaluation_payload: Dict[str, Any]
    role_payload: Dict[str, Any]
    normalized_payload: Dict[str, Any]
    output_path: Path


def slugify(value: str, fallback: str = "role") -> str:
    base = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return base or fallback


def collect_success_urls(intermediate_csv: Path) -> List[str]:
    success_urls: List[str] = []
    if not intermediate_csv.exists():
        return success_urls
    with intermediate_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            status = (row.get("status") or "").strip().lower()
            raw_text = (row.get("raw_text") or "").strip()
            url = (row.get("url") or "").strip()
            if status == "success" and raw_text and url:
                success_urls.append(url)
    return success_urls


def normalize_payload(payload: Dict[str, Any], job_url: str | None) -> tuple[Dict[str, Any], Dict[str, Any], str]:
    company = str(payload.get("company_name") or payload.get("company") or payload.get("employer") or "Unknown Company").strip()
    title = str(payload.get("job_title") or payload.get("role_name") or payload.get("title") or "Unknown Role").strip()
    location = str(
        payload.get("location")
        or ", ".join([loc for loc in payload.get("location_names", []) if isinstance(loc, str) and loc.strip()])
        or payload.get("country")
        or ""
    ).strip()
    job_type_field = payload.get("job_type") or payload.get("employment_type") or ""
    if isinstance(job_type_field, (list, tuple)):
        job_type = ", ".join(str(item) for item in job_type_field if str(item).strip())
    else:
        job_type = str(job_type_field or "").strip()
    salary = str(
        payload.get("salary")
        or payload.get("salary_range")
        or payload.get("compensation", {}).get("salary")
        or payload.get("compensation")
        or ""
    ).strip()
    responsibilities: Sequence[str] = payload.get("responsibilities") or payload.get("duties") or []
    if not responsibilities:
        responsibilities = payload.get("requirements", {}).get("must_have", []) if isinstance(payload.get("requirements"), dict) else []
    responsibilities = [str(item).strip() for item in responsibilities if str(item).strip()]
    requirements = payload.get("requirements") if isinstance(payload.get("requirements"), dict) else {}
    must_have = requirements.get("must_have") or requirements.get("required") or []
    nice_to_have = requirements.get("nice_to_have") or requirements.get("preferred") or []
    must_have = [str(item).strip() for item in must_have if str(item).strip()]
    nice_to_have = [str(item).strip() for item in nice_to_have if str(item).strip()]
    tech_stack = payload.get("tech_stack_detected") or payload.get("tech_stack") or []
    if not tech_stack and isinstance(payload.get("skills"), list):
        tech_stack = [skill.get("name") for skill in payload["skills"] if isinstance(skill, dict) and skill.get("name")]
    tech_stack = [str(item).strip() for item in tech_stack if str(item).strip()]
    job_id = str(payload.get("job_id") or slugify(f"{company}-{title}")).strip()

    base_payload = {
        "job_id": job_id,
        "company": company,
        "role": title,
        "location": location,
        "salary": salary,
        "job_type": job_type or "",
        "tech_stack": tech_stack,
        "responsibilities": responsibilities,
        "must_haves": must_have,
        "nice_to_haves": nice_to_have,
        "job_url": job_url,
        "raw_text": payload.get("raw_text", ""),
    }

    role_payload = {
        **base_payload,
        # Cover-letter stack expects these exact keys.
        "company": company,
        "role": title,
    }
    evaluation_payload = {
        key: value
        for key, value in base_payload.items()
        if key in {"company", "role", "location", "salary", "job_type", "tech_stack", "responsibilities", "job_url"}
    }
    evaluation_payload["tech_stack"] = tech_stack
    evaluation_payload["job_type"] = role_payload["job_type"]
    evaluation_payload.setdefault("responsibilities", responsibilities)
    evaluation_payload.setdefault("tech_stack", tech_stack)

    return evaluation_payload, role_payload, job_id


def build_job_records(conversion_results: Sequence[Any], intermediate_csv: Path) -> List[JobRecord]:
    success_urls = collect_success_urls(intermediate_csv)
    records: List[JobRecord] = []
    for idx, result in enumerate(conversion_results):
        payload = result.payload if hasattr(result, "payload") else None
        output_path = Path(result.output_path) if hasattr(result, "output_path") else None
        if payload is None:
            if output_path is None or not output_path.exists():
                logger.warning("Conversion result #%d missing payload; skipping", idx + 1)
                continue
            payload = json.loads(output_path.read_text())
        job_url = success_urls[idx] if idx < len(success_urls) else None
        evaluation_payload, role_payload, job_id = normalize_payload(payload, job_url)
        records.append(
            JobRecord(
                company=role_payload["company"],
                role=role_payload["role"],
                job_id=job_id,
                job_url=job_url,
                evaluation_payload=evaluation_payload,
                role_payload=role_payload,
                normalized_payload=payload,
                output_path=output_path or Path("unknown.json"),
            )
        )
    if len(success_urls) != len(records):
        logger.warning(
            "Success URL count (%d) does not match normalized roles (%d). Some roles may be missing job URLs.",
            len(success_urls),
            len(records),
        )
    return records


def write_all_jobs(records: Sequence[JobRecord], destination: Path) -> None:
    payload = [record.evaluation_payload for record in records]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Wrote %d roles to %s", len(payload), destination)


def write_role_file(role_payload: Dict[str, Any]) -> None:
    ROLE_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    ROLE_JSON_PATH.write_text(json.dumps(role_payload, indent=2), encoding="utf-8")


def select_jobs(records: Sequence[JobRecord], evaluation_results: Sequence[Dict[str, Any]], threshold: float) -> List[tuple[JobRecord, Dict[str, Any]]]:
    eligible: List[tuple[JobRecord, Dict[str, Any]]] = []
    for record, result in zip(records, evaluation_results):
        if result.get("status") == "skipped":
            continue
        for_me = float(result.get("for_me", {}).get("for_me_score", 0))
        for_them = float(result.get("for_them", {}).get("for_them_score", 0))
        if for_me >= threshold and for_them >= threshold:
            eligible.append((record, {"for_me": for_me, "for_them": for_them, "insight": result.get("insight")}))
    return eligible


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the complete pipeline from careers URLs through auto-apply decisions.",
    )
    parser.add_argument("--companies-csv", type=Path, default=DEFAULT_COMPANIES_CSV, help="CSV with company names and careers URLs")
    parser.add_argument("--job-urls-csv", type=Path, default=DEFAULT_JOB_URLS_CSV, help="Intermediate CSV for job URLs")
    parser.add_argument("--intermediate-csv", type=Path, default=DEFAULT_INTERMEDIATE_CSV, help="Intermediate scraped CSV path")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for normalized roles")
    parser.add_argument("--profile-json", type=Path, default=DEFAULT_PROFILE_JSON, help="Candidate profile JSON for auto-apply")
    parser.add_argument("--cv-pdf", type=Path, default=DEFAULT_CV_PDF, help="Candidate CV PDF for auto-apply")
    parser.add_argument("--apply-threshold", type=float, default=60.0, help="Minimum For-Me and For-Them score required to auto-apply")
    parser.add_argument("--max-applications", type=int, help="Optional limit on auto applications per run")
    parser.add_argument("--max-companies", type=int, help="Limit companies processed when extracting URLs")
    parser.add_argument("--max-urls", type=int, help="Limit job URLs scraped/normalized")
    parser.add_argument("--url-extraction-timeout", type=int, default=60000, help="Timeout (ms) when loading careers pages")
    parser.add_argument("--scrape-timeout", type=float, default=60.0, help="Timeout (s) per job page scrape")
    parser.add_argument("--normalization-model", default="gemini-2.0-flash-exp", help="Gemini model for normalization step")
    parser.add_argument("--url-model", default="gemini-2.0-flash-exp", help="Gemini model for job URL filtering")
    parser.add_argument("--temperature", type=float, default=0.0, help="LLM temperature for normalization")
    parser.add_argument("--prompt-file", type=Path, help="Custom prompt for normalization")
    parser.add_argument("--example-json", type=Path, help="Few-shot example JSON for normalization")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing normalized role files")
    parser.add_argument("--no-clean", action="store_true", help="Disable LLM content cleaning during scraping")
    parser.add_argument(
        "--mock-normalized-json",
        type=Path,
        help="Optional JSON file used instead of the normalization LLM (must include job_url keys)",
    )
    parser.add_argument(
        "--mock-llm-responses",
        type=Path,
        help="Path to canned LLM responses consumed by job-application-engine agents",
    )
    parser.add_argument(
        "--no-wait-for-user",
        dest="wait_for_user",
        action="store_false",
        default=True,
        help="Do not pause for manual answers during auto-apply (default: waits for user input)",
    )
    parser.add_argument("--answers-json", type=Path, help="Optional debug answers file forwarded to auto-apply orchestrator")
    return parser.parse_args()


async def run_pipeline(args: argparse.Namespace) -> Dict[str, Any]:
    configure_logging()
    if args.mock_llm_responses:
        os.environ["MOCK_LLM_RESPONSES"] = str(args.mock_llm_responses)
    logger.info("=" * 80)
    logger.info("Starting full apply pipeline")
    logger.info("=" * 80)

    # Step 1: Extract job URLs
    extraction_results = await extract_all_job_urls(
        args.companies_csv,
        args.job_urls_csv,
        model=args.url_model,
        timeout=args.url_extraction_timeout,
        max_companies=args.max_companies,
    )
    success_companies = sum(1 for result in extraction_results if result.status == "success" and result.job_urls)
    total_urls = sum(len(result.job_urls) for result in extraction_results)
    if success_companies == 0 or total_urls == 0:
        raise RuntimeError("Job URL extraction produced no usable URLs")

    # Step 2: Scrape + normalize
    intermediate_csv = args.intermediate_csv or DEFAULT_INTERMEDIATE_CSV
    scraped_count, failed_count, conversion_results = await run_full_pipeline(
        args.job_urls_csv,
        intermediate_csv=intermediate_csv,
        output_dir=args.output_dir,
        scrape_timeout=args.scrape_timeout,
        clean_with_llm=not args.no_clean,
        max_urls=args.max_urls,
        model=args.normalization_model,
        temperature=args.temperature,
        prompt_path=args.prompt_file,
        example_path=args.example_json,
        overwrite=args.overwrite,
        mock_normalized_json=args.mock_normalized_json,
    )
    if scraped_count == 0:
        raise RuntimeError("Scraping step did not succeed for any URLs")

    records = build_job_records(conversion_results, intermediate_csv)
    if not records:
        raise RuntimeError("No normalized roles available for scoring")
    write_all_jobs(records, ALL_JOBS_PATH)

    # Step 3: Score roles
    RoleEvaluationEngineCls, OrchestratorAgentCls, AutoApplyOrchestratorCls = load_job_engine_components()
    evaluation_engine = RoleEvaluationEngineCls(JOB_ENGINE_ROOT)
    evaluation_results = evaluation_engine.run()
    if not evaluation_results:
        raise RuntimeError("Role evaluation returned no results")

    eligible_jobs = select_jobs(records, evaluation_results, args.apply_threshold)
    if not eligible_jobs:
        logger.info("No roles met the score threshold of %.1f", args.apply_threshold)
    else:
        logger.info("%d roles met the threshold", len(eligible_jobs))

    # Step 4: Cover letter + auto apply
    orchestrator = OrchestratorAgentCls(JOB_ENGINE_ROOT)
    auto_apply = AutoApplyOrchestratorCls(JOB_ENGINE_ROOT)
    applications: List[Dict[str, Any]] = []
    limit = args.max_applications or len(eligible_jobs)
    for record, score_info in eligible_jobs[:limit]:
        if not record.job_url:
            logger.warning("Skipping %s at %s (missing job URL)", record.role, record.company)
            continue
        write_role_file(record.role_payload)
        orchestrator.run()
        apply_result = await auto_apply.run_with_inputs_async(
            job_url=record.job_url,
            cover_letter=str(COVER_LETTER_PATH),
            profile_path=args.profile_json,
            cv_path=args.cv_pdf,
            wait_for_user=args.wait_for_user,
            answers_json=args.answers_json,
        )
        applications.append(
            {
                "job_id": record.job_id,
                "company": record.company,
                "role": record.role,
                "job_url": record.job_url,
                "scores": score_info,
                "applied": apply_result.get("applied", False),
                "auto_apply_result": apply_result,
            }
        )

    summary = {
        "job_url_extraction": {
            "companies_processed": len(extraction_results),
            "successful_companies": success_companies,
            "job_urls_found": total_urls,
            "output_csv": str(args.job_urls_csv),
        },
        "scraping": {
            "scraped": scraped_count,
            "failed": failed_count,
            "intermediate_csv": str(intermediate_csv),
            "output_dir": str(args.output_dir),
        },
        "scoring": {
            "roles_scored": len(records),
            "eligible_roles": len(eligible_jobs),
            "threshold": args.apply_threshold,
        },
        "applications": applications,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info("Pipeline summary written to %s", SUMMARY_PATH)
    return summary


def main() -> int:
    args = parse_args()
    try:
        asyncio.run(run_pipeline(args))
        return 0
    except Exception as exc:  # pragma: no cover - CLI ergonomics
        logger.exception("End-to-end apply pipeline failed: %s", exc)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
