"""Auto-apply orchestrator wiring all agents together."""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

from .answer_validity_agent import AnswerValidityAgent, AnswerAssessment
from .application_navigator_agent import ApplicationNavigatorAgent
from .application_submit_agent import ApplicationSubmitAgent, FieldSubmissionError, SubmissionResult
from .application_writer_agent import ApplicationWriterAgent
from .context import AnswerRecord, AutoApplyContext, FieldDescriptor
from .failure_writer_agent import FailureWriterAgent
from .knowledge_base import KnowledgeBase
from .playwright_client import PlaywrightSession, PlaywrightClientError
from utils.logging import get_logger

logger = get_logger(__name__)
from .user_input_agent import PendingUserInputError, UserInputRequiredAgent


class AutoApplyOrchestrator:
    """High-level orchestrator for the auto_apply_to_job workflow."""

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or Path(__file__).resolve().parents[1]
        self.knowledge_base = KnowledgeBase(self.base_path)
        self.navigator = ApplicationNavigatorAgent(self.base_path)
        self.answer_agent = AnswerValidityAgent(self.base_path)
        self.user_input_agent = UserInputRequiredAgent(self.base_path)
        self.submit_agent = ApplicationSubmitAgent(self.base_path)
        self.success_writer = ApplicationWriterAgent()
        self.failure_writer = FailureWriterAgent()

    def run(
        self,
        job_url: str,
        cover_letter: str,
        profile_path: Path,
        cv_path: Path,
        wait_for_user: bool = True,
        answers_json: Path | None = None,
    ) -> Dict[str, object]:
        return asyncio.run(
            self.run_with_inputs_async(
                job_url,
                cover_letter,
                profile_path,
                cv_path,
                wait_for_user=wait_for_user,
                answers_json=answers_json,
            )
        )

    async def run_with_inputs_async(
        self,
        job_url: str,
        cover_letter: str,
        profile_path: Path,
        cv_path: Path,
        *,
        wait_for_user: bool = True,
        answers_json: Path | None = None,
    ) -> Dict[str, object]:
        """Async-friendly wrapper that mirrors the legacy run() signature."""
        cover_letter_text = self._resolve_cover_letter(cover_letter)
        context = self._build_context(
            job_url,
            cover_letter_text,
            profile_path,
            cv_path,
            answers_override_path=answers_json,
        )
        return await self.run_async(context, wait_for_user=wait_for_user)

    async def run_async(self, context: AutoApplyContext, wait_for_user: bool = True) -> Dict[str, object]:
        try:
            logger.info("AutoApply: starting workflow for %s", context.job_url)
            async with PlaywrightSession() as session:
                logger.info("AutoApply: Step 1/4 navigator running")
                navigator_result = await self.navigator.run_async(context, session)
                if not navigator_result.has_apply_flow:
                    logger.warning("AutoApply: navigator found no apply flow")
                    artifact = self.failure_writer.write(
                        context,
                        "No apply button or form detected on the target page.",
                        context.answers_payload(),
                    )
                    return {
                        "applied": False,
                        "reason": "apply_flow_missing",
                        "artifact": str(artifact),
                    }
                debug_mode = context.debug_answers_only
                logger.info(
                    "AutoApply: Step 2/4 assessing %d fields%s",
                    len(navigator_result.fields),
                    " (debug answers only)" if debug_mode else "",
                )
                if debug_mode:
                    self._apply_debug_answers(context, navigator_result.fields)
                    await self._handle_debug_pending_fields(context, navigator_result.fields, wait_for_user)
                else:
                    self._apply_builtin_answers(context, navigator_result.fields)
                    assessment_targets = [
                        field for field in navigator_result.fields if field.field_id not in context.answers
                    ]
                    if assessment_targets:
                        assessments = self.answer_agent.assess_fields(
                            context,
                            self.knowledge_base,
                            assessment_targets,
                        )
                    else:
                        assessments = []
                    await self._handle_pending_fields(
                        context,
                        assessments,
                        navigator_result.fields,
                        wait_for_user,
                    )
                submission = await self._run_submit_with_retries(context, session, wait_for_user)
                artifact = self.success_writer.write(context, submission)
                logger.info("AutoApply: workflow completed successfully")
                return {
                    "applied": True,
                    "artifact": str(artifact),
                    "steps": submission.steps,
                }
        except PendingUserInputError as exc:
            artifact = self.failure_writer.write(context, str(exc), context.answers_payload())
            return {
                "applied": False,
                "reason": "user_input_missing",
                "artifact": str(artifact),
            }
        except PlaywrightClientError as exc:
            logger.error("AutoApply: Playwright failure %s", exc)
            artifact = self.failure_writer.write(
                context,
                f"Playwright session failure: {exc}",
                context.answers_payload(),
            )
            return {
                "applied": False,
                "reason": "playwright_error",
                "artifact": str(artifact),
            }
        except Exception as exc:
            logger.exception("AutoApply: unexpected error")
            artifact = self.failure_writer.write(context, f"Unexpected error: {exc}", context.answers_payload())
            return {
                "applied": False,
                "reason": "unexpected_error",
                "artifact": str(artifact),
            }

    # -------------------- helpers --------------------
    def _build_context(
        self,
        job_url: str,
        cover_letter_text: str,
        profile_path: Path,
        cv_path: Path,
        answers_override_path: Path | None = None,
    ) -> AutoApplyContext:
        profile_payload = self.knowledge_base.persist_profile(profile_path)
        self.knowledge_base.parse_and_persist_cv(cv_path)
        self.knowledge_base.persist_cover_letter(cover_letter_text)
        answers_dir = self.base_path / "output" / "answers_cache"
        answers_dir.mkdir(parents=True, exist_ok=True)
        context = AutoApplyContext(
            job_url=job_url,
            cover_letter=cover_letter_text,
            profile_path=profile_path,
            cv_path=cv_path,
            cover_letter_path=self.knowledge_base.cover_letter_path,
            knowledge_store_dir=self.knowledge_base.store_dir,
            answers_dir=answers_dir,
            profile_data=profile_payload,
            answers_override_path=answers_override_path,
            debug_answers_only=bool(answers_override_path),
        )
        return context

    def _apply_builtin_answers(self, context: AutoApplyContext, fields: List[FieldDescriptor]) -> None:
        profile_data = context.profile_data or {}
        meta = profile_data.get("meta", {}) if isinstance(profile_data, dict) else {}
        contact = meta.get("contact", {}) if isinstance(meta, dict) else {}
        work_authorization = meta.get("work_authorization", {}) if isinstance(meta, dict) else {}
        location_info = self._derive_location_parts(meta)
        for field in fields:
            if field.field_id in context.answers:
                continue
            descriptor = f"{(field.label or '').lower()} {(field.question or '').lower()}"
            descriptor = descriptor.strip() or (field.name_attr or field.field_id)
            if not descriptor:
                continue
            input_type = field.input_type or ""
            if self._is_resume_field(descriptor, field):
                self._record_auto_answer(context, field, str(context.cv_path), "auto_resume")
                continue
            if "cover letter" in descriptor:
                answer = context.cover_letter if "file" not in input_type else str(context.cover_letter_path)
                self._record_auto_answer(context, field, answer, "auto_cover_letter")
                continue
            if "phone" in descriptor and contact.get("phone"):
                self._record_auto_answer(context, field, contact["phone"], "profile.phone")
                continue
            if "email" in descriptor and contact.get("email"):
                self._record_auto_answer(context, field, contact["email"], "profile.email")
                continue
            if any(keyword in descriptor for keyword in ["city", "town", "locality"]):
                if location_info["city"]:
                    self._record_auto_answer(context, field, location_info["city"], "profile.location")
                continue
            if any(keyword in descriptor for keyword in ["country", "nation"]):
                if location_info["country_full"]:
                    country_value = self._match_option(field, location_info["country_full"]) or location_info["country_full"]
                    self._record_auto_answer(context, field, country_value, "profile.location")
                continue
            if "postcode" in descriptor or "postal" in descriptor or "zip" in descriptor:
                if location_info["postal"]:
                    self._record_auto_answer(context, field, location_info["postal"], "profile.location")
                continue
            if "address" in descriptor and location_info["full"]:
                self._record_auto_answer(context, field, location_info["full"], "profile.location")
                continue
            if "right to work" in descriptor or "work author" in descriptor:
                preference = work_authorization.get("uk") or work_authorization.get("eu")
                option = self._match_option(field, preference)
                if option:
                    self._record_auto_answer(context, field, option, "profile.work_authorization")

    def _record_auto_answer(self, context: AutoApplyContext, field: FieldDescriptor, answer: str, source: str) -> None:
        if not answer:
            return
        record = AnswerRecord(
            field_id=field.field_id,
            answer=answer,
            source=source,
            approved_by="AutoHeuristics",
            display_name=field.label or field.question or field.field_id,
        )
        context.record_answer(record)

    def _derive_location_parts(self, meta: Dict[str, object]) -> Dict[str, str]:
        location_value = ""
        postal = ""
        if isinstance(meta, dict):
            location_value = str(meta.get("location", "")).strip()
            postal = str(meta.get("postal_code", "")).strip()
        parts = [part.strip() for part in re.split(r",|/", location_value) if part.strip()]
        city = parts[0] if parts else ""
        country = parts[-1] if parts else ""
        country_full = self._normalize_country_name(country)
        return {
            "full": location_value,
            "city": city,
            "country": country,
            "country_full": country_full or country,
            "postal": postal,
        }

    def _normalize_country_name(self, name: str) -> str:
        normalized = name.strip().lower()
        mapping = {
            "uk": "United Kingdom",
            "u.k.": "United Kingdom",
            "united kingdom": "United Kingdom",
            "gb": "United Kingdom",
            "great britain": "United Kingdom",
            "usa": "United States",
            "us": "United States",
        }
        return mapping.get(normalized, name.strip())

    def _match_option(self, field: FieldDescriptor, preference: str | None) -> str | None:
        if not preference:
            return None
        if not field.options:
            return preference
        pref_lower = preference.lower()
        for option in field.options:
            if option.lower() == pref_lower or pref_lower in option.lower() or option.lower() in pref_lower:
                return option
        for option in field.options:
            if any(token and token in option.lower() for token in pref_lower.split()):
                return option
        return None

    def _is_resume_field(self, descriptor: str, field: FieldDescriptor) -> bool:
        keywords = ["resume", "cv", "curriculum", "upload resume", "upload cv"]
        if any(keyword in descriptor for keyword in keywords):
            return True
        return "file" in (field.input_type or "") and any(keyword in descriptor for keyword in ["apply", "attachment"])

    async def _handle_pending_fields(
        self,
        context: AutoApplyContext,
        assessments: List[AnswerAssessment],
        fields: List[FieldDescriptor],
        wait_for_user: bool,
    ) -> None:
        reasons: Dict[str, str] = {}
        pending_fields: List[FieldDescriptor] = []
        assessment_map = {assessment.field_id: assessment for assessment in assessments}
        for field in fields:
            assessment = assessment_map.get(field.field_id)
            if not assessment:
                continue
            if assessment.needs_user_input or not assessment.can_answer:
                pending_fields.append(field)
                reason = assessment.reasoning or "Validation agent requires confirmation."
                reasons[field.field_id] = reason
                context.record_pending_question(field, reason)
        if pending_fields:
            logger.info(
                "AutoApply: Step 2b pending user input for %d fields", len(pending_fields)
            )
            self.user_input_agent.collect_answers(context, pending_fields, reasons, wait_for_user=wait_for_user)

    def _apply_debug_answers(self, context: AutoApplyContext, fields: List[FieldDescriptor]) -> None:
        if not context.answers_override_path:
            return
        try:
            answers_data = self._load_debug_answers(context.answers_override_path)
        except (ValueError, json.JSONDecodeError) as exc:
            logger.error("AutoApply: failed to load debug answers %s", exc)
            raise PendingUserInputError(f"Debug answers file invalid: {exc}") from exc
        lower_map = {key.lower(): value for key, value in answers_data.items() if isinstance(key, str)}
        for field in fields:
            entry = self._resolve_debug_answer_entry(field, answers_data, lower_map)
            if not entry:
                continue
            answer, display_name, source, approved_by = entry
            record = AnswerRecord(
                field_id=field.field_id,
                answer=str(answer),
                source=source or "debug_answers_file",
                approved_by=approved_by or "DebugAnswers",
                display_name=display_name or field.label or field.question or field.field_id,
            )
            context.record_answer(record)

    async def _handle_debug_pending_fields(
        self,
        context: AutoApplyContext,
        fields: List[FieldDescriptor],
        wait_for_user: bool,
    ) -> None:
        if not context.debug_answers_only:
            return
        missing: List[FieldDescriptor] = []
        reasons: Dict[str, str] = {}
        for field in fields:
            if not field.required:
                continue
            if self.submit_agent._has_valid_answer(context, field):
                continue
            missing.append(field)
            reason = "No answer provided in debug answers file."
            reasons[field.field_id] = reason
            context.record_pending_question(field, reason)
        if missing:
            logger.info(
                "AutoApply: debug mode pending user input for %d required fields",
                len(missing),
            )
            self.user_input_agent.collect_answers(context, missing, reasons, wait_for_user=wait_for_user)

    def _load_debug_answers(self, path: Path) -> Dict[str, object]:
        if not path.exists():
            raise ValueError(f"Debug answers file not found: {path}")
        payload = json.loads(path.read_text())
        if not isinstance(payload, dict):
            raise ValueError("Debug answers file must be a JSON object of field_id → answer")
        return payload

    def _resolve_debug_answer_entry(
        self,
        field: FieldDescriptor,
        answers_data: Dict[str, object],
        lower_map: Dict[str, object],
    ) -> Tuple[str, str | None, str | None, str | None] | None:
        candidates = [
            field.field_id,
            field.label,
            field.question,
            field.name_attr,
        ]
        for candidate in candidates:
            if not candidate:
                continue
            entry = answers_data.get(candidate)
            if entry is None:
                entry = lower_map.get(candidate.lower()) if isinstance(candidate, str) else None
            if entry is None:
                continue
            parsed = self._parse_debug_answer_entry(entry)
            if parsed:
                return parsed
        return None

    def _parse_debug_answer_entry(self, entry: object) -> Tuple[str, str | None, str | None, str | None] | None:
        if isinstance(entry, str):
            return (entry, None, None, None)
        if isinstance(entry, dict):
            answer = entry.get("answer") or entry.get("value")
            if answer is None:
                return None
            display_name = entry.get("display_name") or entry.get("label")
            source = entry.get("source")
            approved_by = entry.get("approved_by")
            return (str(answer), display_name, source, approved_by)
        return None

    def _resolve_cover_letter(self, cover_letter_or_path: str) -> str:
        path_candidate = Path(cover_letter_or_path)
        if path_candidate.exists():
            return path_candidate.read_text()
        return cover_letter_or_path

    async def _run_submit_with_retries(
        self,
        context: AutoApplyContext,
        session: PlaywrightSession,
        wait_for_user: bool,
        max_attempts: int = 3,
    ) -> SubmissionResult:
        attempt = 1
        while True:
            logger.info("AutoApply: Step 3/4 submit agent starting (attempt %d)", attempt)
            try:
                return await self.submit_agent.run_async(context, session)
            except FieldSubmissionError as exc:
                if not wait_for_user:
                    raise PendingUserInputError(
                        f"Submission blocked on field {exc.field.field_id}: {exc.message}"
                    ) from exc
                reason = (
                    f"Playwright error while filling '{exc.field.label}': {exc.message}. "
                    "Please adjust your answer or type 'skip' if you'd like to leave it blank."
                )
                logger.warning(
                    "AutoApply: submission failed on field %s (%s) — prompting user for new input",
                    exc.field.field_id,
                    exc.message,
                )
                self.user_input_agent.collect_answers(
                    context,
                    [exc.field],
                    {exc.field.field_id: reason},
                    wait_for_user=True,
                )
                attempt += 1
                if attempt > max_attempts:
                    raise PendingUserInputError(
                        f"Repeated submission failures for {exc.field.field_id}; please review manually."
                    ) from exc