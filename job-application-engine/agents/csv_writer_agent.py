"""CSV Writer Agent: appends evaluation rows to job_scores.csv."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict


class CSVWriterAgent:
    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or Path(__file__).resolve().parents[1]
        self.output_file = self.base_path / "output" / "job_scores.csv"
        self.output_file.parent.mkdir(parents=True, exist_ok=True)

    def append_row(
        self,
        company: str,
        role: str,
        for_me_score: float,
        for_them_score: float,
        insight: str,
    ) -> str:
        write_header = not self.output_file.exists()
        with self.output_file.open("a", newline="") as csvfile:
            writer = csv.writer(csvfile)
            if write_header:
                writer.writerow(["Company", "Role", "ForMeScore", "ForThemScore", "Insight"])
            writer.writerow([company, role, round(for_me_score, 2), round(for_them_score, 2), insight])
        return ",".join(
            [company, role, f"{for_me_score:.2f}", f"{for_them_score:.2f}", insight]
        )


if __name__ == "__main__":
    agent = CSVWriterAgent()
    print(
        agent.append_row(
            "ExampleCorp",
            "AI Engineer",
            82.5,
            88.2,
            "Solid match; apply.",
        )
    )