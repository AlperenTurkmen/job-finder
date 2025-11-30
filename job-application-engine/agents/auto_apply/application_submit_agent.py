"""Application Submit Agent - fills validated fields and submits via Playwright."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from .context import AnswerRecord, AutoApplyContext, FieldDescriptor, NavigatorResult
from .playwright_client import PlaywrightSession, PlaywrightClientError
from .user_input_agent import PendingUserInputError
from logging_utils import get_logger

logger = get_logger(__name__)

SUBMIT_KEYWORDS = ["submit", "finish", "send", "apply", "complete"]
TRUTHY_VALUES = {"1", "true", "yes", "y"}
FALSY_VALUES = {"0", "false", "no", "n"}


@dataclass
class SubmissionResult:
    success: bool
    message: str
    steps: List[str] = field(default_factory=list)


@dataclass
class FieldSubmissionError(RuntimeError):
    field: FieldDescriptor
    message: str

    def __str__(self) -> str:  # pragma: no cover - human-readable
        return self.message


class ApplicationSubmitAgent:
    """Executes the final form fill + submission via Playwright MCP."""

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or Path(__file__).resolve().parents[1]

    def run(self, context: AutoApplyContext, session: PlaywrightSession) -> SubmissionResult:
        return asyncio.run(self.run_async(context, session))

    async def run_async(self, context: AutoApplyContext, session: PlaywrightSession) -> SubmissionResult:
        navigator_result = self._require_navigator(context)
        logger.info("Submit: reopening job URL %s", context.job_url)
        await session.goto(context.job_url)
        await asyncio.sleep(1)
        await self._reopen_application(session, navigator_result)
        missing = [
            field
            for field in navigator_result.fields
            if field.required and not self._has_valid_answer(context, field)
        ]
        if missing:
            raise PendingUserInputError(
                f"Missing validated answers for: {[field.field_id for field in missing]}"
            )
        submission_log: List[str] = []
        for field in navigator_result.fields:
            record = context.answers.get(field.field_id)
            if not record or (not record.answer and not self._is_checkbox(field) and field.required):
                raise PendingUserInputError(f"Missing validated answer for required field {field.field_id}")
            if not record or not record.answer:
                submission_log.append(f"Skipped {field.label}: no answer provided")
                logger.info("Submit: skipping %s (no answer)", field.label)
                continue
            try:
                if self._is_cv_upload(field):
                    logger.info("Submit: uploading CV for field %s", field.label)
                    await session.upload_file(field.selector or f"[name='{field.name_attr}']", str(context.cv_path))
                    submission_log.append(f"Uploaded CV for {field.label}")
                    continue
                if self._is_cover_letter_upload(field):
                    logger.info("Submit: uploading cover letter for field %s", field.label)
                    await session.upload_file(field.selector or f"[name='{field.name_attr}']", str(context.cover_letter_path))
                    submission_log.append(f"Uploaded cover letter for {field.label}")
                    continue
                if self._is_checkbox(field):
                    selector = self._resolve_selector(field)
                    if not selector:
                        submission_log.append(f"Skipped {field.label}: missing selector for checkbox")
                        continue
                    value = record.answer.strip().lower()
                    checked = value in TRUTHY_VALUES
                    await session.set_checkbox(selector, checked)
                    submission_log.append(f"Set checkbox {field.label}={'ON' if checked else 'OFF'}")
                    continue
                if self._is_radio(field):
                    selector = self._resolve_option_selector(field, record.answer)
                    if not selector:
                        submission_log.append(f"Skipped {field.label}: option '{record.answer}' not found")
                        logger.warning("Submit: radio option '%s' not found for %s", record.answer, field.label)
                        continue
                    await session.click(selector=selector)
                    submission_log.append(f"Selected {field.label}: {record.answer}")
                    continue
                if self._is_select(field):
                    selector = self._resolve_selector(field)
                    if not selector:
                        submission_log.append(f"Skipped {field.label}: missing selector for select")
                        logger.warning("Submit: missing selector for select %s", field.label)
                        continue
                    option_value = self._resolve_option_value(field, record.answer)
                    await session.select_option(selector, value=option_value, label=None if option_value else record.answer)
                    submission_log.append(f"Selected option for {field.label}: {record.answer}")
                    continue
                if self._is_combobox(field):
                    selector = self._resolve_selector(field)
                    if not selector:
                        submission_log.append(f"Skipped {field.label}: missing selector for combobox")
                        logger.warning("Submit: missing selector for combobox %s", field.label)
                        continue
                    listbox_selector = self._resolve_listbox_selector(field)
                    logger.info("Submit: selecting combobox %s", field.label)
                    await session.select_combobox(selector, record.answer, listbox_selector=listbox_selector)
                    submission_log.append(f"Selected {field.label}: {record.answer}")
                    continue
                selector = field.selector or (f"[name='{field.name_attr}']" if field.name_attr else None)
                if not selector:
                    submission_log.append(f"Skipped {field.label}: no selector available")
                    logger.warning("Submit: skipping %s due to missing selector", field.label)
                    continue
                logger.info("Submit: filling %s", field.label)
                await session.fill(selector, record.answer)
                submission_log.append(f"Filled {field.label}")
            except PlaywrightClientError as exc:
                raise FieldSubmissionError(field, str(exc)) from exc
        await self._click_submit(session, submission_log)
        return SubmissionResult(success=True, message="Application submitted", steps=submission_log)

    # -------------------- helpers --------------------
    def _require_navigator(self, context: AutoApplyContext) -> NavigatorResult:
        if not context.navigator_result or not context.navigator_result.fields:
            raise ValueError("Navigator result missing - run ApplicationNavigatorAgent first.")
        return context.navigator_result

    async def _reopen_application(self, session: PlaywrightSession, navigator_result: NavigatorResult) -> None:
        for method in navigator_result.apply_methods:
            try:
                logger.info(
                    "Submit: replaying apply method '%s' (selector=%s)",
                    method.label or method.selector,
                    method.selector,
                )
                await session.click(selector=method.selector, text=method.label)
                await asyncio.sleep(2)
                return
            except Exception:  # pragma: no cover - runtime integration
                continue

    async def _click_submit(self, session: PlaywrightSession, submission_log: List[str]) -> None:
        try:
            dom = await session.get_dom()
        except PlaywrightClientError:
            submission_log.append("Could not retrieve DOM before submit")
            logger.warning("Submit: unable to read DOM prior to submit click")
            return
        from bs4 import BeautifulSoup  # local import to avoid global dependency cost

        soup = BeautifulSoup(dom, "html.parser")
        for button in soup.find_all(["button", "a"]):
            text = " ".join((button.get_text() or "").split()).lower()
            if any(keyword in text for keyword in SUBMIT_KEYWORDS):
                selector = self._build_selector(button)
                try:
                    await session.click(selector=selector, text=button.get_text())
                    submission_log.append(f"Clicked submit button: {button.get_text().strip()}")
                    logger.info("Submit: clicked submit button '%s'", button.get_text().strip())
                    return
                except Exception:  # pragma: no cover - runtime integration
                    continue
        submission_log.append("No submit button detected; manual review may be required")
        logger.warning("Submit: no submit button detected in DOM")

    def _build_selector(self, element) -> str | None:
        element_id = element.get("id")
        if element_id:
            return f"#{element_id}"
        classes = element.get("class")
        if classes:
            return "." + ".".join(classes[:3])
        return None

    def _is_cv_upload(self, field: FieldDescriptor) -> bool:
        if "file" in field.input_type:
            return True
        label = field.label.lower()
        return any(keyword in label for keyword in ["cv", "résumé", "resume", "curriculum"]) or "upload" in label

    def _is_cover_letter_upload(self, field: FieldDescriptor) -> bool:
        label = field.label.lower()
        return "file" in field.input_type and "cover letter" in label

    def _is_checkbox(self, field: FieldDescriptor) -> bool:
        return "checkbox" in (field.input_type or "")

    def _is_radio(self, field: FieldDescriptor) -> bool:
        return "radio" in (field.input_type or "")

    def _is_select(self, field: FieldDescriptor) -> bool:
        input_type = field.input_type or ""
        return input_type.startswith("select")

    def _is_combobox(self, field: FieldDescriptor) -> bool:
        metadata = field.metadata or {}
        role = metadata.get("role", "").lower()
        aria_has_popup = metadata.get("aria-haspopup", "").lower()
        readonly = metadata.get("readonly", "").lower()
        data_input_type = metadata.get("data-input-type", "").lower()
        if role == "combobox" or aria_has_popup == "listbox":
            return True
        if data_input_type == "select" and "input" in (field.input_type or ""):
            return True
        if readonly in {"true", "1", "yes"} and "input" in (field.input_type or "") and metadata.get("aria-controls"):
            return True
        return False

    def _has_valid_answer(self, context: AutoApplyContext, field: FieldDescriptor) -> bool:
        record = context.answers.get(field.field_id)
        if not record:
            return False
        if self._is_checkbox(field):
            return True  # unchecked allowed as False
        return bool(record.answer)

    def _resolve_selector(self, field: FieldDescriptor) -> str | None:
        if field.selector:
            return field.selector
        if field.name_attr:
            return f"[name='{field.name_attr}']"
        return None

    def _resolve_option_selector(self, field: FieldDescriptor, answer: str) -> str | None:
        if not field.option_selectors:
            return None
        normalized = answer.strip().lower()
        for label, selector in field.option_selectors.items():
            if label.strip().lower() == normalized:
                return selector
        return field.option_selectors.get(answer)

    def _resolve_option_value(self, field: FieldDescriptor, answer: str) -> str | None:
        if not field.option_values:
            return None
        normalized = answer.strip().lower()
        for label, value in field.option_values.items():
            if label.strip().lower() == normalized:
                return value
        return field.option_values.get(answer)

    def _resolve_listbox_selector(self, field: FieldDescriptor) -> str | None:
        if not field.metadata:
            return None
        for key in ("aria-controls", "aria-owns"):
            candidate = field.metadata.get(key)
            if candidate:
                candidate = candidate.strip()
                if candidate:
                    return candidate if candidate.startswith("#") else f"#{candidate}"
        return None
