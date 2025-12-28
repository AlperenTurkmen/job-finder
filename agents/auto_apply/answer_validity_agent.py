"""Answer Validity Agent - gatekeeper that prevents hallucinated answers."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

try:  # Local package import when running inside agents package
    from agents.common.gemini_client import GeminiClient, GeminiConfig
except ImportError:  # Fallback for relative imports
    from ..common.gemini_client import GeminiClient, GeminiConfig  # type: ignore
from .context import AnswerRecord, AutoApplyContext, FieldDescriptor
from .knowledge_base import KnowledgeBase, KnowledgeChunk


@dataclass(slots=True)
class AnswerAssessment:
    field_id: str
    field_name: str
    can_answer: bool
    extracted_answer: str | None
    needs_user_input: bool
    reasoning: str
    provenance: str | None = None

    def to_json(self) -> Dict[str, object]:
        return {
            "field_id": self.field_id,
            "field_name": self.field_name,
            "can_answer": self.can_answer,
            "extracted_answer": self.extracted_answer,
            "needs_user_input": self.needs_user_input,
            "reasoning": self.reasoning,
            "provenance": self.provenance,
        }


class AnswerValidityAgent:
    """LLM-backed validation layer to ensure data provenance."""

    MODEL_NAME = os.getenv("AUTO_APPLY_GEMINI_MODEL") or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or Path(__file__).resolve().parents[1]
        self.gemini = GeminiClient(
            GeminiConfig(
                model=self.MODEL_NAME,
                system_instruction=(
                    "You are a strict validation agent. Only approve answers that are explicitly backed by the provided user data."
                    "If there is any doubt or the field requires brand-new information, request user input."
                ),
                temperature=0.05,
                mock_bucket="answer_validity",
            )
        )

    def assess_fields(
        self,
        context: AutoApplyContext,
        knowledge_base: KnowledgeBase,
        fields: Iterable[FieldDescriptor],
    ) -> List[AnswerAssessment]:
        field_list = list(fields)
        assessments: List[AnswerAssessment] = []
        for field in field_list:
            assessments.append(self._assess_single_field(field, knowledge_base))
        field_lookup = {field.field_id: field for field in field_list}
        for assessment in assessments:
            if assessment.can_answer and assessment.extracted_answer:
                if assessment.field_id in context.answers:
                    continue
                descriptor = field_lookup.get(assessment.field_id)
                display_name = None
                if descriptor:
                    display_name = descriptor.label or descriptor.question or descriptor.field_id
                record = AnswerRecord(
                    field_id=assessment.field_id,
                    answer=assessment.extracted_answer,
                    source=assessment.provenance or "knowledge_base",
                    approved_by="AnswerValidityAgent",
                    display_name=display_name,
                )
                context.record_answer(record)
        return assessments

    def _assess_single_field(self, field: FieldDescriptor, knowledge_base: KnowledgeBase) -> AnswerAssessment:
        query = " ".join(
            filter(
                None,
                [field.label, field.question, field.placeholder, field.name_attr, field.metadata.get("data-question")],
            )
        )
        context_chunks = knowledge_base.search(query, top_k=6)
        if not context_chunks:
            return AnswerAssessment(
                field_id=field.field_id,
                field_name=field.label,
                can_answer=False,
                extracted_answer=None,
                needs_user_input=True,
                reasoning="No supporting evidence found in profile/CV/cover letter.",
                provenance=None,
            )
        prompt = self._build_prompt(field, context_chunks)
        response = self.gemini.generate_json(
            prompt,
            metadata={"field_id": field.field_id, "field_name": field.label},
        )
        return AnswerAssessment(
            field_id=field.field_id,
            field_name=field.label,
            can_answer=bool(response.get("can_answer")),
            extracted_answer=response.get("extracted_answer"),
            needs_user_input=bool(response.get("needs_user_input")),
            reasoning=response.get("reasoning", ""),
            provenance=response.get("provenance"),
        )

    def _build_prompt(self, field: FieldDescriptor, context_chunks: List[KnowledgeChunk]) -> str:
        context_payload = [
            {
                "source": chunk.source,
                "page": chunk.page,
                "text": chunk.text,
            }
            for chunk in context_chunks
        ]
        instructions = {
            "field": field.to_prompt_dict(),
            "evidence": context_payload,
            "requirements": [
                "Only answer if the evidence explicitly contains the required information.",
                "If the answer would involve guessing (e.g., government IDs, salary expectations), set can_answer=false and needs_user_input=true.",
                "When quoting experience or numbers, cite which evidence chunk you used in the provenance field.",
            ],
            "output_schema": {
                "can_answer": "boolean",
                "field_name": "string",
                "extracted_answer": "string | null",
                "needs_user_input": "boolean",
                "reasoning": "string",
                "provenance": "string | null"
            },
        }
        return (
            "You receive a single form field and evidence pulled from the candidate's profile, CV, and cover letter. "
            "Return strict JSON describing whether the field can be auto-filled.\n" + json.dumps(instructions, indent=2)
        )
