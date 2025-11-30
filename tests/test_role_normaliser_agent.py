from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from agents.role_normaliser_agent import (
    DEFAULT_PROMPT,
    ConversionResult,
    convert_raw_text,
    convert_roles_csv,
    _load_text,
)


class FakeLLM:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.prompts: list[str] = []

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        self.prompts.append(prompt)
        if not self.responses:
            pytest.fail("LLM invoked more times than expected")
        return self.responses.pop(0)


def test_convert_raw_text_parses_valid_json() -> None:
    llm = FakeLLM([
        json.dumps({
            "id": "sample-role",
            "company_name": "Acme",
            "role_title": "Engineer",
        })
    ])
    payload, prompt = convert_raw_text(
        "Acme Engineer role description",
        llm=llm,
        prompt_template="Example: {example_json}\nRole: {raw_text}",
        example_json="{}",
    )
    assert payload["company_name"] == "Acme"
    assert "Acme Engineer" in prompt


def test_convert_roles_csv_writes_expected_files(tmp_path: Path) -> None:
    csv_path = tmp_path / "roles.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["raw_text"])
        writer.writerow(["First role description"])
        writer.writerow(["Second role description"])

    responses = [
        json.dumps({"id": "role-one", "company_name": "Foo", "role_title": "Engineer"}),
        json.dumps({"id": "role-two", "company_name": "Bar", "role_title": "Designer"}),
    ]
    llm = FakeLLM(responses)

    results = convert_roles_csv(
        csv_path,
        llm=llm,
        prompt_template=DEFAULT_PROMPT,
        example_json=json.dumps({"id": "example"}, indent=2),
        output_dir=tmp_path / "output",
        overwrite=True,
    )

    assert isinstance(results[0], ConversionResult)
    assert results[0].status == "created"
    written_files = sorted(path.name for path in (tmp_path / "output").iterdir())
    assert written_files == ["role-one.json", "role-two.json"]

    saved_payload = json.loads((tmp_path / "output" / "role-one.json").read_text(encoding="utf-8"))
    assert saved_payload["company_name"] == "Foo"


def test_convert_roles_csv_skips_duplicates(tmp_path: Path) -> None:
    csv_path = tmp_path / "roles.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["raw_text"])
        writer.writerow(["Duplicate role description"])

    responses = [json.dumps({"id": "role-one", "company_name": "Foo", "role_title": "Engineer"})]
    llm = FakeLLM(responses.copy())

    convert_roles_csv(
        csv_path,
        llm=llm,
        prompt_template=DEFAULT_PROMPT,
        example_json=json.dumps({"id": "example"}, indent=2),
        output_dir=tmp_path / "output",
        overwrite=True,
    )

    llm_second = FakeLLM(responses.copy())
    second_results = convert_roles_csv(
        csv_path,
        llm=llm_second,
        prompt_template=DEFAULT_PROMPT,
        example_json=json.dumps({"id": "example"}, indent=2),
        output_dir=tmp_path / "output",
        overwrite=False,
    )

    assert second_results[0].status == "unchanged"


def test_load_text_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    missing_path = tmp_path / "missing.json"
    result = _load_text(missing_path)
    captured = capsys.readouterr()
    assert result is None
    assert "auxiliary file not found" in captured.err