"""Shared Gemini 2.5 client helpers for the job application engine."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

from utils.logging import get_logger

try:  # pragma: no cover - mock helper is optional
    from utils.mock_llm import get_mock_response, mock_enabled
except Exception:  # pragma: no cover - fallback when module missing
    def mock_enabled() -> bool:  # type: ignore
        return False

    def get_mock_response(*_, **__):  # type: ignore
        return None


@dataclass
class GeminiConfig:
    model: str
    system_instruction: str | None = None
    temperature: float = 0.0
    json_mode: bool = False
    mock_bucket: str | None = None


class GeminiClient:
    """Minimal REST client for the Gemini Generative Language API."""

    BASE_URL = os.getenv("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta")
    TIMEOUT_SECONDS = float(os.getenv("GEMINI_TIMEOUT", "30"))

    def __init__(self, config: GeminiConfig) -> None:
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Set GEMINI_API_KEY or GOOGLE_API_KEY before running the job application engine."
            )
        self.api_key = api_key
        self.config = config
        self.logger = get_logger(__name__)

    def generate_text(
        self,
        prompt: str,
        *,
        temperature: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        response_text = self._generate(prompt, temperature=temperature, metadata=metadata)
        if not response_text:
            raise RuntimeError("Gemini response had no text content.")
        return response_text

    def generate_json(
        self,
        prompt: str,
        *,
        temperature: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        response_text = self._generate(
            prompt,
            temperature=temperature,
            response_mime_type="application/json",
            metadata=metadata,
        )
        if not response_text:
            raise RuntimeError("Gemini JSON response had no text content.")
        return self._parse_json(response_text)

    def _generate(
        self,
        prompt: str,
        *,
        temperature: Optional[float] = None,
        response_mime_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        if mock_enabled() and self.config.mock_bucket:
            mock_value = get_mock_response(
                self.config.mock_bucket,
                metadata=metadata or {},
                prompt=prompt,
            )
            if mock_value is not None:
                if isinstance(mock_value, (dict, list)):
                    return json.dumps(mock_value)
                return str(mock_value)

        url = f"{self.BASE_URL}/models/{self.config.model}:generateContent"
        generation_config: Dict[str, Any] = {
            "temperature": temperature if temperature is not None else self.config.temperature,
        }
        if response_mime_type:
            generation_config["responseMimeType"] = response_mime_type

        payload: Dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": generation_config,
        }
        if self.config.system_instruction:
            payload["systemInstruction"] = {
                "role": "system",
                "parts": [{"text": self.config.system_instruction}],
            }

        params = {"key": self.api_key}
        response = requests.post(
            url,
            params=params,
            json=payload,
            timeout=self.TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            self.logger.error(
                "Gemini API error %s: %s",
                response.status_code,
                response.text,
            )
            raise RuntimeError(
                f"Gemini API request failed with status {response.status_code}: {response.text}"
            )
        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
        return "\n".join(filter(None, texts)).strip()

    @staticmethod
    def _parse_json(payload: str) -> Dict[str, Any]:
        cleaned = payload.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            # Log the full payload for debugging
            from utils.logging import get_logger
            logger = get_logger(__name__)
            logger.error(f"Failed to parse JSON. Full payload ({len(cleaned)} chars): {cleaned[:1000]}")
            raise ValueError(f"Gemini response was not valid JSON: {cleaned[:200]}") from exc