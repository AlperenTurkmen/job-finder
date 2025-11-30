"""Style Extractor Agent that defers analysis to Gemini 2.5 Flash."""
from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent
from typing import Dict, List

try:
    from .gemini_client import GeminiClient, GeminiConfig
except ImportError:  # pragma: no cover - script execution fallback
    from gemini_client import GeminiClient, GeminiConfig


class StyleExtractorAgent:
    MODEL_NAME = "gemini-2.5-flash"

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or Path(__file__).resolve().parents[1]
        self.profile_store = self.base_path / "memory" / "profile_store"
        self.samples_dir = self.profile_store / "writing_samples"
        self.output_path = self.base_path / "memory" / "style_profile.json"
        self.client = GeminiClient(
            GeminiConfig(
                model=self.MODEL_NAME,
                system_instruction="Extract stylistic fingerprints from provided writing samples.",
                temperature=0.2,
                mock_bucket="style_extractor",
            )
        )

    def run(self) -> Dict[str, object]:
        samples = [path.read_text() for path in sorted(self.samples_dir.glob("*.md"))]
        if not samples:
            raise FileNotFoundError("At least one writing sample is required for style extraction.")
        metrics = self._query_model(samples)
        self.output_path.write_text(json.dumps(metrics, indent=2))
        return metrics

    def _query_model(self, samples: List[str]) -> Dict[str, object]:
        prompt = dedent(
            f"""
            You are a writing-style analyst. Summarize the stylistic fingerprint of the author.
            Return JSON exactly with these keys:
            {{
              "model": "gemini-2.5-flash",
              "average_sentence_length": number,
              "tone": string,
              "technical_density": number,
              "transition_frequency": {{ "connector": integer }},
              "vocabulary_density": number,
              "connectors": [string]
            }}

            Base the metrics on the provided samples (treat newline separators as paragraph breaks):
            ---
            {"\n\n".join(samples)}
            ---
            """
        ).strip()
        return self.client.generate_json(prompt, metadata={"bucket_key": "style"})


if __name__ == "__main__":
    profile = StyleExtractorAgent()
    print(json.dumps(profile.run(), indent=2))
