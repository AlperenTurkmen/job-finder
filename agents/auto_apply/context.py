"""Shared dataclasses and helpers for the auto-apply multi-agent stack."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


@dataclass(slots=True)
class ApplyMethod:
    """Represents one detected way to open the application flow."""

    label: str
    selector: str | None
    element_type: str
    href: str | None = None
    confidence: float = 0.5
    clicked: bool = False
    notes: str | None = None


@dataclass(slots=True)
class FieldDescriptor:
    """Normalized form field description used across agents."""

    field_id: str
    label: str
    question: str
    input_type: str
    step_index: int
    required: bool
    selector: str | None
    name_attr: str | None = None
    placeholder: str | None = None
    options: List[str] = field(default_factory=list)
    option_values: Dict[str, str] = field(default_factory=dict)
    option_selectors: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, str] = field(default_factory=dict)

    def to_prompt_dict(self) -> Dict[str, object]:
        return {
            "field_id": self.field_id,
            "label": self.label,
            "question": self.question,
            "input_type": self.input_type,
            "required": self.required,
            "options": self.options,
            "option_values": self.option_values,
            "option_selectors": self.option_selectors,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class NavigatorResult:
    """Structured output emitted by the Application Navigator Agent."""

    job_url: str
    job_name: str
    apply_methods: List[ApplyMethod]
    fields: List[FieldDescriptor]
    raw_dom_snapshot_path: Path | None = None
    step_count: int = 0

    @property
    def has_apply_flow(self) -> bool:
        return bool(self.apply_methods) and bool(self.fields)


@dataclass(slots=True)
class AnswerRecord:
    """Represents a vetted answer for a specific field."""

    field_id: str
    answer: str
    source: str
    approved_by: str
    display_name: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime(ISO_FORMAT))

    def to_json(self) -> Dict[str, str]:
        return {
            "field_id": self.field_id,
            "answer": self.answer,
            "source": self.source,
            "approved_by": self.approved_by,
            "display_name": self.display_name,
            "timestamp": self.timestamp,
        }


@dataclass
class AutoApplyContext:
    """Mutable runtime context shared across agents."""

    job_url: str
    cover_letter: str
    profile_path: Path
    cv_path: Path
    cover_letter_path: Path
    knowledge_store_dir: Path
    answers_dir: Path
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime(ISO_FORMAT))
    job_name: Optional[str] = None
    navigator_result: Optional[NavigatorResult] = None
    answers: Dict[str, AnswerRecord] = field(default_factory=dict)
    pending_questions: Dict[str, Dict[str, str]] = field(default_factory=dict)
    profile_data: Optional[Dict[str, object]] = None
    answers_override_path: Optional[Path] = None
    debug_answers_only: bool = False

    def ensure_job_name(self) -> str:
        if self.job_name:
            return self.job_name
        slug = (
            self.job_url.rstrip("/")
            .split("/")[-1]
            .split("?")[0]
            .replace(".html", "")
            .replace(".htm", "")
            .replace("#", "-")
        )
        normalized = slug or "job-application"
        self.job_name = normalized.lower()
        return self.job_name

    def answers_payload(self) -> Dict[str, Dict[str, str]]:
        payload: Dict[str, Dict[str, str]] = {}
        for record in self.answers.values():
            preferred_key = (record.display_name or record.field_id or "field").strip() or record.field_id
            key = preferred_key
            if key in payload and payload[key]["field_id"] != record.field_id:
                key = f"{preferred_key} ({record.field_id})"
            payload[key] = record.to_json()
        return payload

    def record_answer(self, record: AnswerRecord) -> None:
        self.answers[record.field_id] = record

    def record_pending_question(self, field: FieldDescriptor, reason: str) -> None:
        self.pending_questions[field.field_id] = {
            "question": field.question or field.label,
            "reason": reason,
            "input_type": field.input_type,
            "required": str(field.required),
        }

    def mark_question_resolved(self, field_id: str) -> None:
        self.pending_questions.pop(field_id, None)
