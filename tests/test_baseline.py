from __future__ import annotations

from pathlib import Path

from modpack_solver.metadata.synthetic import load_synthetic_case
from modpack_solver.solver.baseline import suggest_baseline_repairs
from modpack_solver.solver.checker import check_synthetic_case
from modpack_solver.graph import build_graph_from_synthetic_case


FIXTURE_DIR = Path("data/synthetic")


def _report_and_result(name: str):
    case = load_synthetic_case(FIXTURE_DIR / name)
    result = build_graph_from_synthetic_case(case)
    report = check_synthetic_case(case)
    return report, result


def test_missing_dependency_generates_add_dependency_suggestion() -> None:
    report, result = _report_and_result("missing_required_dependency.json")
    repairs = suggest_baseline_repairs(result, report.issues)

    assert any(repair.action_type.value == "add_dependency" for repair in repairs)


def test_hard_conflict_generates_remove_mod_suggestion() -> None:
    report, result = _report_and_result("hard_conflict.json")
    repairs = suggest_baseline_repairs(result, report.issues)

    assert any(repair.action_type.value == "remove_mod" for repair in repairs)


def test_optional_dependency_generates_low_priority_add_suggestion() -> None:
    report, result = _report_and_result("optional_dependency_warning.json")
    repairs = suggest_baseline_repairs(result, report.issues)

    assert any(
        repair.action_type.value == "add_dependency" and "optional" in (repair.reason or "").lower()
        for repair in repairs
    )
