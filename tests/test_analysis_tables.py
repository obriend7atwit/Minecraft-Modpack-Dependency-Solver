from __future__ import annotations

import csv
import uuid
from pathlib import Path

from modpack_solver.analysis import escape_latex, format_percent, generate_analysis_tables, run_week9_analysis
from modpack_solver.analysis.tables import write_markdown_summary


def test_tables_and_latex_files_are_generated() -> None:
    output_dir = _workspace_dir()
    result = run_week9_analysis(
        output_dir=output_dir,
        runtime_repetitions=1,
        skip_charts=True,
        case_ids={"synthetic-valid", "synthetic-missing-dependency"},
    )
    generated = generate_analysis_tables(result, output_dir)

    names = {path.name for path in generated}
    assert "overall_summary.csv" in names
    assert "per_case_results.csv" in names
    assert "baseline_comparison.csv" in names
    assert "profile_comparison.csv" in names
    assert "grouped_results.csv" in names
    assert "failure_summary.csv" in names
    assert "summary_table.tex" in names
    assert "profile_comparison.tex" in names

    for path in generated:
        assert path.exists()
        assert path.stat().st_size > 0


def test_csv_contains_rows_and_latex_contains_tabular() -> None:
    output_dir = _workspace_dir()
    result = run_week9_analysis(output_dir=output_dir, runtime_repetitions=1, skip_charts=True, case_ids={"synthetic-valid"})
    generate_analysis_tables(result, output_dir)

    with (output_dir / "tables" / "overall_summary.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert "tabular" in (output_dir / "tables" / "summary_table.tex").read_text(encoding="utf-8")


def test_latex_special_characters_are_escaped_and_percentages_format() -> None:
    assert escape_latex("A&B_50%") == r"A\&B\_50\%"
    assert format_percent(0.125) == "12.50%"


def test_markdown_summary_is_written() -> None:
    output_dir = _workspace_dir()
    result = run_week9_analysis(output_dir=output_dir, runtime_repetitions=1, skip_charts=True, case_ids={"synthetic-valid"})
    path = write_markdown_summary(result, output_dir / "analysis_summary.md")

    assert "# Week 9 Solver Evaluation Results" in path.read_text(encoding="utf-8")


def _workspace_dir() -> Path:
    path = Path(".test-artifacts") / "analysis-tables" / uuid.uuid4().hex
    path.mkdir(parents=True)
    return path
