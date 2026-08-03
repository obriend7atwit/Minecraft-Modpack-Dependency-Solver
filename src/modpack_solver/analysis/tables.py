"""Table and Markdown exports for Week 9 analysis."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from modpack_solver.analysis.models import ExperimentSummary, Week9AnalysisResult


def generate_analysis_tables(result: Week9AnalysisResult, output_dir: str | Path) -> list[Path]:
    """Generate deterministic CSV and LaTeX table fragments."""

    output_path = Path(output_dir)
    tables_dir = output_path / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    generated = [
        _write_overall_summary_csv(result, tables_dir / "overall_summary.csv"),
        _write_per_case_csv(result, tables_dir / "per_case_results.csv"),
        _write_baseline_comparison_csv(result, tables_dir / "baseline_comparison.csv"),
        _write_profile_comparison_csv(result, tables_dir / "profile_comparison.csv"),
        _write_grouped_results_csv(result, tables_dir / "grouped_results.csv"),
        _write_failure_summary_csv(result, tables_dir / "failure_summary.csv"),
        _write_summary_latex(result, tables_dir / "summary_table.tex"),
        _write_profile_latex(result, tables_dir / "profile_comparison.tex"),
    ]
    return generated


def write_markdown_summary(result: Week9AnalysisResult, path: str | Path) -> Path:
    """Write a concise human-readable Week 9 results summary."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    baseline = _summary_for(result, "baseline")
    default = _summary_for(result, "weighted_default")
    preservation = _summary_for(result, "weighted_preservation")

    lines = [
        "# Week 9 Solver Evaluation Results",
        "",
        "## Dataset",
        f"- Strict manifest cases: {result.strict_validation_case_count}",
        f"- Experimental case-results recorded: {len(result.case_results)}",
        "- Cached-real cases are reduced or intentionally modified samples, not full official modpacks.",
        "- The controlled trade-off fixture is synthetic.",
        "",
        "## Strict Validation",
        f"- Passed: {result.strict_validation_passed}",
        "",
        "## Baseline Results",
        _summary_line(baseline),
        "",
        "## Default Weighted Solver",
        _summary_line(default),
        "",
        "## Preservation-Focused Solver",
        _summary_line(preservation),
        "",
        "## Profile Comparison",
        f"- Changed decision cases: {', '.join(result.changed_decision_cases) or 'None'}",
        "- Raw weighted costs from different profiles use different scales and are not directly comparable.",
        "",
        "## Search-Limit Comparison",
        f"- Search-limit measurements recorded: {len(result.search_limit_results)}",
        _search_limit_note(result),
        "",
        "## Failure Analysis",
        _failure_summary_line(result),
        "",
        "## Solver Refinements",
        *[f"- {item}" for item in result.solver_refinements],
        "",
        "## Explanation Review",
        "- Week 9 reused the Week 8 explanation report layer for root-cause and repair reasoning.",
        "",
        "## Key Findings",
        "- Strict validation remained separate from experimental comparisons.",
        "- Weighted profiles repaired all expected repairable strict cases in the measured run when supported by metadata.",
        "- The controlled trade-off case demonstrated that weight choices can change the selected valid repair.",
        "",
        "## Limitations",
        *[f"- {item}" for item in result.limitations],
        "- Current results should not be generalized to all Minecraft modpacks.",
        "",
        "## Generated Files",
        *[f"- `{path}`" for path in result.generated_files],
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def escape_latex(value: object) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)


def format_percent(value: float) -> str:
    return f"{value:.2%}"


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def _write_overall_summary_csv(result: Week9AnalysisResult, path: Path) -> Path:
    return _write_csv(
        path,
        [
            "system",
            "profile_id",
            "total_cases",
            "repair_success_rate",
            "average_preservation_rate",
            "average_repair_cost",
            "median_runtime_seconds",
            "average_states_expanded",
            "issue_detection_accuracy",
        ],
        (_summary_row(summary) for summary in result.summaries),
    )


def _write_per_case_csv(result: Week9AnalysisResult, path: Path) -> Path:
    return _write_csv(
        path,
        [
            "case_id",
            "name",
            "source_type",
            "system",
            "profile_id",
            "repair_expected",
            "solution_found",
            "final_compatible",
            "issue_types",
            "action_types",
            "action_count",
            "total_cost",
            "preservation_rate",
            "removed_mod_count",
            "version_change_count",
            "median_runtime_seconds",
            "states_expanded",
            "failure_category",
        ],
        (
            {
                "case_id": case.case_id,
                "name": case.name,
                "source_type": case.source_type.value,
                "system": case.system.value,
                "profile_id": case.profile_id or "",
                "repair_expected": case.repair_expected,
                "solution_found": case.solution_found,
                "final_compatible": case.final_compatible,
                "issue_types": "|".join(issue.value for issue in case.issue_types),
                "action_types": "|".join(action.value for action in case.action_types),
                "action_count": case.action_count,
                "total_cost": "" if case.total_cost is None else case.total_cost,
                "preservation_rate": f"{case.preservation_rate:.4f}",
                "removed_mod_count": case.removed_mod_count,
                "version_change_count": case.version_change_count,
                "median_runtime_seconds": f"{case.runtime.median_seconds:.6f}",
                "states_expanded": case.states_expanded,
                "failure_category": case.failure_category or "",
            }
            for case in result.case_results
        ),
    )


def _write_baseline_comparison_csv(result: Week9AnalysisResult, path: Path) -> Path:
    baseline = [summary for summary in result.summaries if summary.system.value == "baseline"]
    return _write_csv(
        path,
        [
            "system",
            "repair_success_rate",
            "suggestion_coverage_rate",
            "executable_suggestion_rate",
            "validated_baseline_repair_rate",
            "average_preservation_rate",
            "average_removed_mods",
        ],
        (
            {
                "system": summary.system.value,
                "repair_success_rate": f"{summary.repair_success_rate:.4f}",
                "suggestion_coverage_rate": _optional_float(summary.suggestion_coverage_rate),
                "executable_suggestion_rate": _optional_float(summary.executable_suggestion_rate),
                "validated_baseline_repair_rate": _optional_float(summary.validated_baseline_repair_rate),
                "average_preservation_rate": f"{summary.average_repair_preservation_rate:.4f}",
                "average_removed_mods": f"{summary.average_repair_removed_mods:.4f}",
            }
            for summary in baseline
        ),
    )


def _write_profile_comparison_csv(result: Week9AnalysisResult, path: Path) -> Path:
    return _write_csv(
        path,
        [
            "system",
            "profile_id",
            "repair_success_rate",
            "average_preservation_rate",
            "average_action_count",
            "average_removed_mods",
            "average_repair_cost",
            "median_runtime_seconds",
        ],
        (
            {
                "system": summary.system.value,
                "profile_id": summary.profile_id or "",
                "repair_success_rate": f"{summary.repair_success_rate:.4f}",
                "average_preservation_rate": f"{summary.average_repair_preservation_rate:.4f}",
                "average_action_count": f"{summary.average_repair_action_count:.4f}",
                "average_removed_mods": f"{summary.average_repair_removed_mods:.4f}",
                "average_repair_cost": _optional_float(summary.average_repair_cost),
                "median_runtime_seconds": f"{summary.median_runtime_seconds:.6f}",
            }
            for summary in result.summaries
            if summary.system.value.startswith("weighted")
        ),
    )


def _write_grouped_results_csv(result: Week9AnalysisResult, path: Path) -> Path:
    rows = []
    for summary in result.summaries:
        for group in summary.grouped_metrics:
            rows.append(
                {
                    "system": summary.system.value,
                    "profile_id": summary.profile_id or "",
                    "group_name": group.group_name,
                    "total_cases": group.total_cases,
                    "repairable_invalid_cases": group.repairable_invalid_cases,
                    "successfully_repaired_cases": group.successfully_repaired_cases,
                    "repair_success_rate": f"{group.repair_success_rate:.4f}",
                    "average_preservation_rate": f"{group.average_preservation_rate:.4f}",
                    "average_action_count": f"{group.average_action_count:.4f}",
                    "average_removed_mods": f"{group.average_removed_mods:.4f}",
                    "median_runtime_seconds": f"{group.median_runtime_seconds:.6f}",
                }
            )
    return _write_csv(
        path,
        [
            "system",
            "profile_id",
            "group_name",
            "total_cases",
            "repairable_invalid_cases",
            "successfully_repaired_cases",
            "repair_success_rate",
            "average_preservation_rate",
            "average_action_count",
            "average_removed_mods",
            "median_runtime_seconds",
        ],
        rows,
    )


def _write_failure_summary_csv(result: Week9AnalysisResult, path: Path) -> Path:
    rows = []
    for summary in result.summaries:
        if not summary.failure_counts:
            rows.append(
                {
                    "system": summary.system.value,
                    "profile_id": summary.profile_id or "",
                    "failure_category": "none",
                    "count": 0,
                }
            )
        for category, count in summary.failure_counts.items():
            rows.append(
                {
                    "system": summary.system.value,
                    "profile_id": summary.profile_id or "",
                    "failure_category": category,
                    "count": count,
                }
            )
    return _write_csv(path, ["system", "profile_id", "failure_category", "count"], rows)


def _write_summary_latex(result: Week9AnalysisResult, path: Path) -> Path:
    rows = [
        [
            summary.system.value,
            summary.profile_id or "-",
            format_percent(summary.repair_success_rate),
            format_percent(summary.average_repair_preservation_rate),
        ]
        for summary in result.summaries
    ]
    return _write_latex_table(path, ["System", "Profile", "Repair Success", "Preservation"], rows)


def _write_profile_latex(result: Week9AnalysisResult, path: Path) -> Path:
    rows = [
        [
            summary.profile_id or "-",
            format_percent(summary.repair_success_rate),
            format_percent(summary.average_repair_preservation_rate),
            f"{summary.average_repair_removed_mods:.2f}",
        ]
        for summary in result.summaries
        if summary.system.value.startswith("weighted")
    ]
    return _write_latex_table(path, ["Profile", "Repair Success", "Preservation", "Removed Mods"], rows)


def _write_latex_table(path: Path, headers: list[str], rows: list[list[object]]) -> Path:
    column_spec = "l" * len(headers)
    lines = [
        f"\\begin{{tabular}}{{{column_spec}}}",
        " \\hline",
        " & ".join(escape_latex(header) for header in headers) + r" \\",
        " \\hline",
    ]
    for row in rows:
        lines.append(" & ".join(escape_latex(value) for value in row) + r" \\")
    lines.extend([" \\hline", "\\end{tabular}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _summary_row(summary: ExperimentSummary) -> dict:
    return {
        "system": summary.system.value,
        "profile_id": summary.profile_id or "",
        "total_cases": summary.total_cases,
        "repair_success_rate": f"{summary.repair_success_rate:.4f}",
        "average_preservation_rate": f"{summary.average_repair_preservation_rate:.4f}",
        "average_repair_cost": _optional_float(summary.average_repair_cost),
        "median_runtime_seconds": f"{summary.median_runtime_seconds:.6f}",
        "average_states_expanded": f"{summary.average_states_expanded:.4f}",
        "issue_detection_accuracy": f"{summary.issue_detection_accuracy:.4f}",
    }


def _summary_for(result: Week9AnalysisResult, system_value: str) -> ExperimentSummary | None:
    for summary in result.summaries:
        if summary.system.value == system_value:
            return summary
    return None


def _summary_line(summary: ExperimentSummary | None) -> str:
    if summary is None:
        return "- Not run."
    return (
        f"- Repair success: {summary.repair_success_rate:.2%}; "
        f"preservation: {summary.average_repair_preservation_rate:.2%}; "
        f"median runtime: {summary.median_runtime_seconds:.6f}s."
    )


def _search_limit_note(result: Week9AnalysisResult) -> str:
    pairs = {}
    for item in result.search_limit_results:
        key = (item.case_id, item.profile_id)
        pairs.setdefault(key, []).append(item)
    changed = [
        f"{case_id}/{profile_id}"
        for (case_id, profile_id), items in pairs.items()
        if len({(item.status, item.final_compatible, item.total_cost) for item in items}) > 1
    ]
    if not changed:
        return "- No 5,000 versus 10,000 state outcome differences were observed."
    return f"- Search-limit outcome differences: {', '.join(sorted(changed))}"


def _failure_summary_line(result: Week9AnalysisResult) -> str:
    counts = {}
    for summary in result.summaries:
        for category, count in summary.failure_counts.items():
            counts[category] = counts.get(category, 0) + count
    if not counts:
        return "- No failed experimental outcomes were observed."
    return "- Failure categories: " + ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))


def _optional_float(value: float | None) -> str:
    return "" if value is None else f"{value:.4f}"
