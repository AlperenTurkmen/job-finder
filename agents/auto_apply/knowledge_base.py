"""Persistent profile + CV knowledge store with lightweight semantic search."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from pypdf import PdfReader

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")


def _normalize_text(text: str) -> str:
    return " ".join(text.replace("\u00a0", " ").split())


def _tokenize(text: str) -> List[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


@dataclass(slots=True)
class KnowledgeChunk:
    """Normalized chunk for semantic lookup."""

    text: str
    source: str
    page: int | None = None
    tokens: List[str] = field(default_factory=list)

    def ensure_tokens(self) -> None:
        if not self.tokens:
            self.tokens = _tokenize(self.text)


class KnowledgeBase:
    """Manages profile + CV context for downstream agents."""

    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path
        self.store_dir = self.base_path / "memory" / "profile_store"
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.persisted_profile_path = self.store_dir / "profile_application.json"
        self.parsed_cv_path = self.store_dir / "parsed_cv.json"
        self.cover_letter_path = self.store_dir / "cover_letter.txt"
        self.chunks: List[KnowledgeChunk] = []

    # -------------------- persistence --------------------
    def persist_profile(self, profile_path: Path) -> Dict[str, object]:
        data = json.loads(profile_path.read_text())
        self.persisted_profile_path.write_text(json.dumps(data, indent=2))
        self.chunks = [chunk for chunk in self.chunks if chunk.source != "profile"]
        self._ingest_profile(data)
        return data

    def parse_and_persist_cv(self, cv_path: Path) -> Dict[str, object]:
        reader = PdfReader(str(cv_path))
        pages: List[Dict[str, object]] = []
        structured_chunks: List[Dict[str, object]] = []
        chunk_id = 1
        self.chunks = [chunk for chunk in self.chunks if chunk.source != "cv"]
        for idx, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            normalized = _normalize_text(text)
            pages.append({"page": idx, "text": normalized})
            for block in self._split_paragraphs(normalized):
                structured_chunks.append(
                    {
                        "id": f"chunk-{chunk_id}",
                        "page": idx,
                        "text": block,
                        "tokens": _tokenize(block),
                    }
                )
                chunk_id += 1
                self.chunks.append(KnowledgeChunk(text=block, source="cv", page=idx))
        payload = {
            "source_pdf": str(cv_path),
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "pages": pages,
            "chunks": structured_chunks,
        }
        self.parsed_cv_path.write_text(json.dumps(payload, indent=2))
        return payload

    def persist_cover_letter(self, text: str) -> None:
        cleaned = text.strip()
        self.cover_letter_path.write_text(cleaned)
        self.chunks = [chunk for chunk in self.chunks if chunk.source != "cover_letter"]
        if cleaned:
            self.chunks.append(KnowledgeChunk(text=cleaned, source="cover_letter"))

    def load_profile(self) -> Dict[str, object]:
        if not self.persisted_profile_path.exists():
            raise FileNotFoundError(f"Profile file missing at {self.persisted_profile_path}")
        data = json.loads(self.persisted_profile_path.read_text())
        self.chunks = [chunk for chunk in self.chunks if chunk.source != "profile"]
        self._ingest_profile(data)
        return data

    def load_parsed_cv(self) -> Dict[str, object]:
        if not self.parsed_cv_path.exists():
            raise FileNotFoundError("CV has not been parsed yet. Run parse_and_persist_cv first.")
        payload = json.loads(self.parsed_cv_path.read_text())
        existing_cv = [chunk for chunk in self.chunks if chunk.source == "cv"]
        if not existing_cv:
            for chunk in payload.get("chunks", []):
                self.chunks.append(
                    KnowledgeChunk(text=chunk["text"], source="cv", page=chunk.get("page"))
                )
        return payload

    # -------------------- search --------------------
    def search(self, query: str, top_k: int = 5) -> List[KnowledgeChunk]:
        if not query.strip():
            return []
        tokens = set(_tokenize(query))
        if not tokens:
            return []
        scored: List[tuple[float, KnowledgeChunk]] = []
        for chunk in self.chunks:
            chunk.ensure_tokens()
            if not chunk.tokens:
                continue
            overlap = tokens.intersection(chunk.tokens)
            if not overlap:
                continue
            score = len(overlap) / len(tokens)
            scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [chunk for _, chunk in scored[:top_k]]

    # -------------------- helpers --------------------
    def _ingest_profile(self, profile_data: Dict[str, object]) -> None:
        flattened = list(self._flatten_dict(profile_data))
        for path, value in flattened:
            text_value = _normalize_text(str(value))
            if not text_value:
                continue
            self.chunks.append(
                KnowledgeChunk(text=f"{path}: {text_value}", source="profile")
            )

    def _flatten_dict(self, data: object, prefix: str = "profile") -> Iterable[tuple[str, object]]:
        if isinstance(data, dict):
            for key, value in data.items():
                new_prefix = f"{prefix}.{key}"
                yield from self._flatten_dict(value, new_prefix)
        elif isinstance(data, list):
            for idx, item in enumerate(data):
                new_prefix = f"{prefix}[{idx}]"
                yield from self._flatten_dict(item, new_prefix)
        else:
            yield prefix, data

    def _split_paragraphs(self, text: str) -> Sequence[str]:
        blocks = [block.strip() for block in text.split("\n\n") if block.strip()]
        if blocks:
            return blocks
        return [text] if text else []
