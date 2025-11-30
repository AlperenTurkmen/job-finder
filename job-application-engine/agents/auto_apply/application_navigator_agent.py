"""Application Navigator Agent: maps the application flow via native Playwright."""
from __future__ import annotations

import asyncio
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple
from uuid import uuid4

from bs4 import BeautifulSoup

from .context import ApplyMethod, AutoApplyContext, FieldDescriptor, NavigatorResult
from .playwright_client import PlaywrightSession, PlaywrightClientError
from logging_utils import get_logger

logger = get_logger(__name__)

APPLY_KEYWORDS = [
    "apply",
    "proceed",
    "get started",
    "submit",
    "continue",
    "next",
    "apply now",
    "apply with",
]

COOKIE_ACCEPT_SELECTORS = [
    "[data-ui='cookie-consent-accept']",
    "#onetrust-accept-btn-handler",
    "button[aria-label='Accept Cookies']",
]

COOKIE_ACCEPT_TEXTS = [
    "accept all",
    "accept",
    "agree",
    "allow all",
    "got it",
]

CONTENT_READY_SELECTORS = [
    "[data-ui='apply-button']",
    "[data-ui='careers-page-content']",
    "a[href*='/apply']",
]


class ApplicationNavigatorAgent:
    """Detects apply flows and extracts form descriptors."""

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or Path(__file__).resolve().parents[1]
        self.snapshot_dir = self.base_path / "output" / "dom_snapshots"
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    # -------------------- public API --------------------
    def run(self, context: AutoApplyContext, session: PlaywrightSession) -> NavigatorResult:
        return asyncio.run(self.run_async(context, session))

    async def run_async(self, context: AutoApplyContext, session: PlaywrightSession) -> NavigatorResult:
        logger.info("Navigator: loading job URL %s", context.job_url)
        try:
            await session.goto(context.job_url, wait_until="domcontentloaded")
        except PlaywrightClientError as exc:
            logger.warning(
                "Navigator: initial load failed (%s); retrying with 'load' wait", exc
            )
            await session.goto(context.job_url, wait_until="load")
        await self._dismiss_blocking_ui(session)
        await self._wait_for_primary_content(session)
        await asyncio.sleep(0.5)
        dom_html = await session.get_dom()
        job_name = context.ensure_job_name()
        dom_path = self._write_snapshot(job_name, 0, dom_html)
        logger.info("Navigator: captured initial DOM snapshot at %s", dom_path)

        apply_methods = self._detect_apply_methods(dom_html)
        logger.info("Navigator: detected %d potential apply methods", len(apply_methods))
        fields = self._extract_fields(dom_html, step_index=0)
        logger.info("Navigator: extracted %d fields on initial step", len(fields))

        # attempt to click first viable apply method to capture subsequent forms
        for idx, apply_method in enumerate(apply_methods, start=1):
            if apply_method.selector is None and not apply_method.label:
                continue
            try:
                logger.info(
                    "Navigator: attempting apply method '%s' (selector=%s)",
                    apply_method.label or apply_method.selector,
                    apply_method.selector,
                )
                await session.click(selector=apply_method.selector, text=apply_method.label)
                apply_method.clicked = True
                await asyncio.sleep(2)
                dom_after_click = await session.get_dom()
                self._write_snapshot(job_name, idx, dom_after_click)
                new_fields = self._extract_fields(dom_after_click, step_index=idx)
                if new_fields:
                    logger.info(
                        "Navigator: found %d new fields after clicking '%s'",
                        len(new_fields),
                        apply_method.label or apply_method.selector,
                    )
                    fields.extend(new_fields)
                    break
            except PlaywrightClientError as exc:  # pragma: no cover - runtime integration
                apply_method.notes = f"click failed: {exc}"
                logger.warning(
                    "Navigator: click failed for '%s' (%s)",
                    apply_method.label or apply_method.selector,
                    exc,
                )
                continue
            except Exception as exc:  # pragma: no cover - defensive
                apply_method.notes = f"click error: {exc}"
                logger.exception(
                    "Navigator: unexpected error while clicking '%s'",
                    apply_method.label or apply_method.selector,
                )
                continue

        navigator_result = NavigatorResult(
            job_url=context.job_url,
            job_name=job_name,
            apply_methods=apply_methods,
            fields=fields,
            raw_dom_snapshot_path=dom_path,
            step_count=max([field.step_index for field in fields], default=0) + 1,
        )
        context.navigator_result = navigator_result
        return navigator_result

    # -------------------- helpers --------------------
    def _write_snapshot(self, job_name: str, step_index: int, dom_html: str) -> Path:
        path = self.snapshot_dir / f"{job_name}_step{step_index}.html"
        path.write_text(dom_html)
        logger.debug("Navigator: wrote DOM snapshot %s", path)
        return path

    def _detect_apply_methods(self, dom_html: str) -> List[ApplyMethod]:
        soup = BeautifulSoup(dom_html, "html.parser")
        methods: List[ApplyMethod] = []
        for element in soup.find_all(["button", "a"]):
            label = self._clean_text(element.get_text())
            if not label:
                continue
            lower_label = label.lower()
            if not any(keyword in lower_label for keyword in APPLY_KEYWORDS):
                continue
            selector = self._build_selector(element)
            methods.append(
                ApplyMethod(
                    label=label,
                    selector=selector,
                    element_type=element.name,
                    href=element.get("href"),
                    confidence=0.9 if "apply" in lower_label else 0.6,
                )
            )
        return methods

    async def _dismiss_blocking_ui(self, session: PlaywrightSession) -> None:
        """Best-effort dismissal of cookie consent / overlays before parsing DOM."""

        # Attempt selector-based clicks first (e.g., Workable, OneTrust, generic aria labels).
        for selector in COOKIE_ACCEPT_SELECTORS:
            try:
                await session.wait_for_selector(selector, timeout=2)
                await session.click(selector=selector)
                logger.info("Navigator: dismissed blocking UI via selector %s", selector)
                await asyncio.sleep(0.3)
                return
            except PlaywrightClientError:
                continue

        # Fall back to text-based buttons.
        for text in COOKIE_ACCEPT_TEXTS:
            try:
                await session.click(text=text)
                logger.info("Navigator: dismissed blocking UI via text '%s'", text)
                await asyncio.sleep(0.3)
                return
            except PlaywrightClientError:
                continue

    async def _wait_for_primary_content(self, session: PlaywrightSession) -> None:
        """Wait for core apply content so that DOM snapshots include real forms."""

        for selector in CONTENT_READY_SELECTORS:
            try:
                await session.wait_for_selector(selector, timeout=5)
                logger.info("Navigator: detected primary content via %s", selector)
                return
            except PlaywrightClientError:
                continue
        logger.info("Navigator: primary content selectors not found; continuing with raw DOM")

    def _extract_fields(self, dom_html: str, step_index: int) -> List[FieldDescriptor]:
        soup = BeautifulSoup(dom_html, "html.parser")
        fields: List[FieldDescriptor] = []
        forms = soup.find_all("form") or [soup]
        radio_groups: Dict[str, List[Tuple]] = defaultdict(list)
        for form_idx, form in enumerate(forms):
            candidates = form.find_all(["input", "textarea", "select"])
            for element in candidates:
                input_type = (element.get("type") or "").lower()
                if input_type in {"hidden", "submit", "button"}:
                    continue
                if element.name == "input" and input_type == "radio":
                    group_key = element.get("name") or element.get("id") or f"radio-{uuid4()}"
                    radio_groups[group_key].append((element, form_idx, step_index))
                    continue
                field = self._build_field_descriptor(
                    soup=soup,
                    element=element,
                    form_idx=form_idx,
                    step_index=step_index,
                )
                fields.append(field)

        for group_key, group_entries in radio_groups.items():
            radio_field = self._build_radio_descriptor(group_key, group_entries, soup)
            if radio_field:
                fields.append(radio_field)
        return fields

    def _build_field_descriptor(self, soup, element, form_idx: int, step_index: int) -> FieldDescriptor:
        field_id = (
            element.get("name")
            or element.get("id")
            or element.get("data-ui")
            or str(uuid4())
        )
        label_text = self._normalize_label(self._find_label(soup, element, field_id))
        placeholder = element.get("placeholder")
        question = label_text or placeholder or element.get("aria-label") or ""
        options, option_values = self._extract_options(element)
        input_type = element.name + (f":{element.get('type')}" if element.name == "input" and element.get("type") else "")
        selector = self._build_selector(element)
        return FieldDescriptor(
            field_id=field_id,
            label=label_text or element.get("aria-label") or placeholder or field_id,
            question=question,
            input_type=input_type,
            step_index=step_index or form_idx,
            required=element.has_attr("required"),
            selector=selector,
            name_attr=element.get("name"),
            placeholder=placeholder,
            options=options,
            option_values=option_values,
            option_selectors={},
            metadata={
                "form_index": str(form_idx),
                "aria-label": element.get("aria-label", ""),
                "aria-haspopup": element.get("aria-haspopup", ""),
                "aria-controls": element.get("aria-controls", ""),
                "aria-owns": element.get("aria-owns", ""),
                "aria-autocomplete": element.get("aria-autocomplete", ""),
                "data-question": element.get("data-question", ""),
                "data-ui": element.get("data-ui", ""),
                "data-input-type": element.get("data-input-type", ""),
                "role": element.get("role", ""),
                "readonly": "true" if element.has_attr("readonly") else "",
            },
        )

    def _build_radio_descriptor(self, group_key: str, entries: List[Tuple], soup) -> FieldDescriptor | None:
        if not entries:
            return None
        first_element, form_idx, step_index = entries[0]
        question = self._normalize_label(
            self._find_group_label(soup, first_element)
            or self._aria_reference_text(soup, first_element)
            or self._find_container_hint(first_element)
        )
        options: List[str] = []
        option_values: Dict[str, str] = {}
        option_selectors: Dict[str, str] = {}
        required = False
        for element, _, _ in entries:
            option_label = self._normalize_label(
                self._find_label(soup, element, element.get("id") or "")
            ) or (element.get("value") or "Option")
            selector = self._build_selector(element, prefer_unique=True)
            if not selector:
                continue
            options.append(option_label)
            option_values[option_label] = element.get("value") or option_label
            option_selectors[option_label] = selector
            required = required or element.has_attr("required")
        if not options:
            return None
        label = question or options[0]
        return FieldDescriptor(
            field_id=f"{group_key}_{step_index or form_idx}",
            label=label,
            question=question or label,
            input_type="input:radio",
            step_index=step_index or form_idx,
            required=required,
            selector=None,
            name_attr=group_key,
            placeholder=None,
            options=options,
            option_values=option_values,
            option_selectors=option_selectors,
            metadata={
                "form_index": str(form_idx),
                "group_name": group_key,
            },
        )

    def _find_label(self, soup: BeautifulSoup, element, field_id: str) -> str:
        aria_label_text = self._aria_reference_text(soup, element)
        if aria_label_text:
            return aria_label_text
        if field_id:
            label = soup.find("label", attrs={"for": field_id})
            if label:
                return self._clean_text(label.get_text())
        parent_label = element.find_parent("label")
        if parent_label:
            return self._clean_text(parent_label.get_text())
        container_hint = self._find_container_hint(element)
        if container_hint:
            return container_hint
        return ""

    def _aria_reference_text(self, soup: BeautifulSoup, element) -> str:
        aria_labelledby = element.get("aria-labelledby")
        if not aria_labelledby:
            return ""
        pieces = []
        for ref in aria_labelledby.split():
            node = soup.find(id=ref)
            if node:
                pieces.append(self._clean_text(node.get_text()))
        return " ".join(filter(None, pieces))

    def _find_container_hint(self, element) -> str:
        def class_matches(tag) -> bool:
            classes = tag.get("class") or []
            if isinstance(classes, str):
                classes = [classes]
            return any("styles--3aPac" in cls for cls in classes)

        ancestor = element.find_parent(class_matches)
        if ancestor:
            strong_nodes = ancestor.find_all("strong")
            for node in strong_nodes:
                text = self._clean_text(node.get_text())
                if text and text != "*":
                    return text
            text = self._clean_text(ancestor.get_text())
            if text:
                return text
        ancestor = element.find_parent(attrs={"data-question": True})
        if ancestor and ancestor.get("data-question"):
            return self._clean_text(ancestor.get("data-question"))
        return ""

    def _find_group_label(self, soup: BeautifulSoup, element) -> str:
        fieldset = element.find_parent("fieldset")
        if fieldset:
            aria_label = self._aria_reference_text(soup, fieldset)
            if aria_label:
                return aria_label
            legend = fieldset.find("legend")
            if legend:
                return self._clean_text(legend.get_text())
        container = element.find_parent(attrs={"data-question": True})
        if container and container.get("data-question"):
            return self._clean_text(container.get("data-question"))
        parent_heading = element.find_parent(["h1", "h2", "h3", "h4"])
        if parent_heading:
            return self._clean_text(parent_heading.get_text())
        return ""

    def _build_selector(self, element, prefer_unique: bool = False) -> str | None:
        if prefer_unique:
            name_attr = element.get("name")
            value_attr = element.get("value")
            if name_attr and value_attr:
                return f"input[name='{name_attr}'][value='{value_attr}']"
            element_id = element.get("id")
            if element_id:
                return f"#{element_id}"
        name_attr = element.get("name")
        if name_attr and not prefer_unique:
            return f"[name='{name_attr}']"
        data_ui = element.get("data-ui")
        if data_ui:
            return f"[data-ui='{data_ui}']"
        data_testid = element.get("data-testid")
        if data_testid:
            return f"[data-testid='{data_testid}']"
        element_id = element.get("id")
        if element_id:
            return f"#{element_id}"
        aria_labelledby = element.get("aria-labelledby")
        if aria_labelledby:
            first = aria_labelledby.split()[0]
            return f"[aria-labelledby~='{first}']"
        classes = element.get("class")
        if classes:
            class_list = classes if isinstance(classes, list) else [classes]
            return "." + ".".join(class_list[:3])
        placeholder = element.get("placeholder")
        if placeholder:
            return f"[placeholder='{placeholder}']"
        if name_attr:
            return f"[name='{name_attr}']"
        return None

    def _extract_options(self, element) -> Tuple[List[str], Dict[str, str]]:
        if element.name != "select":
            return [], {}
        options: List[str] = []
        option_values: Dict[str, str] = {}
        for option in element.find_all("option"):
            label = self._clean_text(option.get_text())
            if not label:
                continue
            value = option.get("value") or label
            options.append(label)
            option_values[label] = value
        return options, option_values

    def _clean_text(self, text: str | None) -> str:
        if not text:
            return ""
        cleaned = " ".join(text.split())
        return cleaned.replace("SVGs not supported by this browser.", "").strip()

    def _normalize_label(self, text: str) -> str:
        return text.replace("SVGs not supported by this browser.", "").strip()
