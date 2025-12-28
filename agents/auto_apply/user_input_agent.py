"""User Input Required Agent - coordinates human-in-the-loop answers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from .context import AnswerRecord, AutoApplyContext, FieldDescriptor


class PendingUserInputError(RuntimeError):
    """Raised when the workflow must pause for user responses."""


class UserInputRequiredAgent:
    """Communicates missing answers and blocks until the user responds."""

    def __init__(self, base_path: Path | None = None, poll_interval: float = 5.0) -> None:
        self.base_path = base_path or Path(__file__).resolve().parents[1]
        self.poll_interval = poll_interval
        self.output_dir = self.base_path / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.pending_path = self.output_dir / "pending_questions.json"
        self.pending_md_path = self.output_dir / "pending_questions.md"
        self.answers_file = self.base_path / "input" / "user_answers.json"

    def collect_answers(
        self,
        context: AutoApplyContext,
        pending_fields: Iterable[FieldDescriptor],
        reasons: Dict[str, str],
        wait_for_user: bool = True,
    ) -> Dict[str, str]:
        pending_list = list(pending_fields)
        if not pending_list:
            return {}
        request_payload = self._write_pending_file(context, pending_list, reasons)
        if not wait_for_user:
            raise PendingUserInputError("User input required. Set wait_for_user=True to block.")
        responses = self._prompt_user_inputs(pending_list, reasons)
        for field in pending_list:
            entry = responses.get(field.field_id)
            if not entry:
                continue
            answer, skipped = entry
            record = AnswerRecord(
                field_id=field.field_id,
                answer=answer,
                source="user_skipped" if skipped else "user_provided",
                approved_by="UserInputRequiredAgent",
                display_name=field.label or field.question or field.field_id,
            )
            context.record_answer(record)
            context.mark_question_resolved(field.field_id)
        # clean up request file now that answers were captured
        request_payload["status"] = "resolved"
        self.pending_path.write_text(json.dumps(request_payload, indent=2))
        self.pending_md_path.write_text("All pending questions have been answered. ✅\n")
        return responses

    # -------------------- helpers --------------------
    def _write_pending_file(
        self,
        context: AutoApplyContext,
        pending_fields: List[FieldDescriptor],
        reasons: Dict[str, str],
    ) -> Dict[str, object]:
        job_name = context.ensure_job_name()
        questions = [
            {
                "field_id": field.field_id,
                "question": field.question or field.label,
                "input_type": field.input_type,
                "required": field.required,
                "reason": reasons.get(field.field_id, ""),
            }
            for field in pending_fields
        ]
        payload = {
            "status": "awaiting_user",
            "job_name": job_name,
            "job_url": context.job_url,
            "questions": questions,
            "instructions": (
                "Answer the prompts directly in the terminal (type 'skip' to leave blank) or optionally pre-fill "
                "input/user_answers.json with field_id → answer pairs to auto-populate the prompts."
            ),
        }
        self.pending_path.write_text(json.dumps(payload, indent=2))
        self.pending_md_path.write_text(self._build_markdown(payload))
        return payload

    def _build_markdown(self, payload: Dict[str, object]) -> str:
        lines = [f"# Pending Questions for {payload['job_name']}", "", f"Job URL: {payload['job_url']}", ""]
        lines.append("You can answer interactively in the CLI or edit `input/user_answers.json` with entries like:")
        lines.append("")
        lines.append("```json")
        lines.append("{")
        for question in payload["questions"]:
            lines.append(f'  "{question["field_id"]}": "<your answer>",')
        lines.append("}")
        lines.append("```")
        lines.append("")
        lines.append("## Questions")
        for question in payload["questions"]:
            lines.append(
                f"- **{question['field_id']}** — {question['question']} (required: {question['required']}) | Reason: {question['reason']}"
            )
        return "\n".join(lines)

    def _prompt_user_inputs(
        self,
        pending_fields: List[FieldDescriptor],
        reasons: Dict[str, str],
    ) -> Dict[str, Tuple[str, bool]]:
        responses: Dict[str, Tuple[str, bool]] = {}
        cached_answers = self._load_prefilled_answers()
        print("\n=== Additional Information Required ===")
        for field in pending_fields:
            display_name = field.question or field.label or field.field_id
            reason = reasons.get(field.field_id, "")
            required_label = "required" if field.required else "optional"
            default_value = cached_answers.get(field.field_id)
            prompt_header = ["", f"{display_name} ({required_label})"]
            prompt_header.append(f"Type: {self._describe_field(field)}")
            if reason:
                prompt_header.append(f"Reason: {reason}")
            if field.options:
                prompt_header.append("Options:")
                for idx, option in enumerate(field.options, start=1):
                    prompt_header.append(f"  {idx}. {option}")
            prompt_header.append("(Enter 'skip' to leave blank)")
            print("\n".join(prompt_header))
            response = self._prompt_single_field(field, default_value)
            responses[field.field_id] = response
        print("\nThanks! Continuing with the workflow...\n")
        return responses

    def _prompt_single_field(self, field: FieldDescriptor, default_value: str | None) -> Tuple[str, bool]:
        while True:
            default_hint = f" [default: {default_value}]" if default_value else ""
            user_input = input(f"> Enter answer{default_hint}: ").strip()
            if not user_input and default_value:
                user_input = default_value
            normalized = user_input.strip()
            if not normalized and not field.required and not self._is_checkbox(field):
                return "", False
            lower = normalized.lower()
            if lower == "skip":
                if field.required:
                    confirm = input("Field is required. Type 'skip!' to confirm or provide a value: ").strip().lower()
                    if confirm != "skip!":
                        continue
                if self._is_checkbox(field):
                    return ("false", True)
                return ("", True)
            if not normalized:
                print("This field is required; please provide a value or type 'skip'.")
                continue
            parsed = self._interpret_answer(field, normalized)
            if parsed is None:
                print("Input not recognized. Please try again or type 'skip'.")
                continue
            return parsed

    def _interpret_answer(self, field: FieldDescriptor, user_input: str) -> Tuple[str, bool] | None:
        if self._is_checkbox(field):
            lower = user_input.lower()
            if lower in {"y", "yes"}:
                return ("true", False)
            if lower in {"n", "no"}:
                return ("false", False)
            print("Please enter 'y' or 'n' for this checkbox field.")
            return None
        if field.options:
            choice = self._resolve_option_choice(field, user_input)
            if choice:
                return (choice, False)
            return None
        return (user_input, False)

    def _resolve_option_choice(self, field: FieldDescriptor, user_input: str) -> str | None:
        if user_input.isdigit():
            idx = int(user_input)
            if 1 <= idx <= len(field.options):
                return field.options[idx - 1]
        normalized = user_input.lower()
        for option in field.options:
            if option.lower() == normalized:
                return option
        if field.option_values:
            for label, value in field.option_values.items():
                if value.lower() == normalized:
                    return label
        return None

    def _describe_field(self, field: FieldDescriptor) -> str:
        if self._is_checkbox(field):
            return "checkbox (y/n)"
        if self._is_radio(field):
            return "single-select (radio)"
        if field.options:
            return "single-select (dropdown)"
        if field.input_type.startswith("textarea"):
            return "multiline text"
        return "text"

    def _is_checkbox(self, field: FieldDescriptor) -> bool:
        return "checkbox" in (field.input_type or "")

    def _is_radio(self, field: FieldDescriptor) -> bool:
        return "radio" in (field.input_type or "")

    def _load_prefilled_answers(self) -> Dict[str, str]:
        if not self.answers_file.exists():
            return {}
        try:
            payload = json.loads(self.answers_file.read_text())
        except json.JSONDecodeError:
            return {}
        return {field_id: str(answer).strip() for field_id, answer in payload.items() if str(answer).strip()}