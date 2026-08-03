import csv

from modpack_solver.final_reports.runner import run_final_evaluation
from modpack_solver.final_reports.tables import escape_latex


def test_final_tables_are_generated_with_deterministic_headers(tmp_path):
    run_final_evaluation(
        output_dir=tmp_path,
        max_cases=4,
        runtime_repetitions=1,
        skip_charts=True,
    )
    expected = [
        "dataset_summary.csv",
        "dataset_summary.tex",
        "case_categories.csv",
        "overall_metrics.csv",
        "overall_metrics.tex",
        "baseline_comparison.csv",
        "baseline_comparison.tex",
        "weight_profile_comparison.csv",
        "largest_modpacks.csv",
        "failure_analysis.csv",
        "manual_review.csv",
        "limitations.tex",
    ]
    assert all((tmp_path / "tables" / name).exists() for name in expected)
    with (tmp_path / "tables" / "overall_metrics.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["system"] for row in rows] == [
        "baseline",
        "weighted_default",
        "weighted_preservation",
    ]
    assert "dependency_chain_explanation_accuracy" in rows[0]
    assert "cascading_step_explanation_accuracy" in rows[0]
    assert "global_plan_reason_accuracy" in rows[0]


def test_latex_escaping_handles_common_special_characters():
    escaped = escape_latex("mod_name & 50% #1")
    assert r"mod\_name" in escaped
    assert r"\&" in escaped
    assert r"50\%" in escaped
    assert r"\#1" in escaped
