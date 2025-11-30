from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.careers_page_finder_agent import choose_careers_page, choose_from_file, format_prompt


class FakeLLM:
	def __init__(self, response: str) -> None:
		self.response = response
		self.prompts: list[str] = []

	def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
		self.prompts.append(prompt)
		assert temperature == 0.0
		return self.response


SAMPLE_RESULTS = [
	{
		"rank": 1,
		"title": "Rockstar Games Careers",
		"url": "https://www.rockstargames.com/careers",
		"snippet": "Browse open positions at Rockstar Games.",
	},
	{
		"rank": 2,
		"title": "Indeed Jobs",
		"url": "https://www.indeed.com/q-Rockstar-jobs.html",
		"snippet": "Find Rockstar jobs on Indeed.",
	},
]


def test_format_prompt_contains_results_json() -> None:
	prompt = format_prompt(SAMPLE_RESULTS)
	assert "Rockstar Games Careers" in prompt
	assert "https://www.rockstargames.com/careers" in prompt


def test_choose_careers_page_parses_llm_json(tmp_path: Path) -> None:
	llm = FakeLLM('{"chosen_url": "https://www.rockstargames.com/careers", "confidence": "high", "evidence": "Title explicitly says careers"}')
	result = choose_careers_page(SAMPLE_RESULTS, llm)
	assert result["chosen_url"] == "https://www.rockstargames.com/careers"
	assert result["confidence"] == "high"


def test_choose_from_file(tmp_path: Path) -> None:
	temp_file = tmp_path / "results.json"
	temp_file.write_text(json.dumps(SAMPLE_RESULTS), encoding="utf-8")
	llm = FakeLLM('{"chosen_url": "https://www.rockstargames.com/careers", "confidence": "medium", "evidence": "Official domain"}')
	result = choose_from_file(temp_file, llm)
	assert result["confidence"] == "medium"


def test_choose_careers_page_raises_on_invalid_json() -> None:
	llm = FakeLLM("not json")
	with pytest.raises(ValueError):
		choose_careers_page(SAMPLE_RESULTS, llm)
