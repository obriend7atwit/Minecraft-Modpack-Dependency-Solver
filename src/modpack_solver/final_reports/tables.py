"""CSV, Markdown, and LaTeX tables for the final evaluation."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Iterable, Sequence

from modpack_solver.final_dataset.manifest import load_final_dataset_manifest
from modpack_solver.final_reports.models import (
    FinalCaseEvaluation,
    FinalEvaluationRun,
    FinalEvaluationSystem,
)


def generate_final_tables(run: FinalEvaluationRun, output_dir: str | Path) -> list[Path]:
    table_dir = Path(output_dir) / "tables"
    table_dir.mkdir(parents=True, exist_ok=True)
    unique_cases = _unique_case_results(run.results)
    manifest = load_final_dataset_manifest(run.manifest_path)

    dataset_rows = _dataset_summary_rows(unique_cases)
    category_rows = _case_category_rows(unique_cases)
    metric_rows = _overall_metric_rows(run)
    baseline_rows = _baseline_comparison_rows(run)
    profile_rows = _profile_comparison_rows(run)
    largest_rows = _largest_case_rows(unique_cases)
    failure_rows = _failure_rows(run.results)
    manual_rows = _manual_review_rows(manifest.cases)
    limitation_rows = _limitation_rows(run)

    outputs = [
        _write_csv(table_dir / "dataset_summary.csv", dataset_rows),
        _write_latex(table_dir / "dataset_summary.tex", dataset_rows),
        _write_csv(table_dir / "case_categories.csv", category_rows),
        _write_csv(table_dir / "overall_metrics.csv", metric_rows),
        _write_latex(table_dir / "overall_metrics.tex", metric_rows),
        _write_csv(table_dir / "baseline_comparison.csv", baseline_rows),
        _write_latex(table_dir / "baseline_comparison.tex", baseline_rows),
        _write_csv(table_dir / "weight_profile_comparison.csv", profile_rows),
        _write_csv(table_dir / "largest_modpacks.csv", largest_rows),
        _write_csv(table_dir / "failure_analysis.csv", failure_rows),
        _write_csv(table_dir / "manual_review.csv", manual_rows),
        _write_latex(table_dir / "limitations.tex", limitation_rows),
        _write_markdown(table_dir / "dataset_summary.md", dataset_rows, "Dataset Summary"),
        _write_markdown(table_dir / "overall_metrics.md", metric_rows, "Overall Metrics"),
        _write_markdown(table_dir / "baseline_comparison.md", baseline_rows, "Baseline Comparison"),
    ]
    return outputs


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
    return "".join(replacements.get(character, character) for character in text)


def _dataset_summary_rows(results: Sequence[FinalCaseEvaluation]) -> list[dict]:
    rows = [{
        "dimension": "all",
        "category": "all",
        "case_count": len(results),
        "source_family_count": len({result.source_family_id for result in results}),
    }]
    source_counts = Counter(result.source_type.value for result in results)
    size_counts = Counter(result.pack_size_category.value for result in results)
    topology_counts = Counter(result.topology or "not_applicable" for result in results)
    ground_truth_counts = Counter(result.ground_truth_method.value for result in results)
    review_counts = Counter(result.review_status for result in results)
    ordered_complexity = sorted(
        results,
        key=lambda item: (
            item.required_edge_density,
            item.maximum_required_depth,
            item.case_id,
        ),
    )
    complexity_quartiles = {
        result.case_id: f"Q{min(4, (index * 4) // max(len(ordered_complexity), 1) + 1)}"
        for index, result in enumerate(ordered_complexity)
    }
    complexity_counts = Counter(complexity_quartiles.values())
    modification_counts = Counter(
        "original/control" if result.modification_type.value == "none" else "modified/injected"
        for result in results
    )
    real_scope_counts = Counter(
        (
            "complete_manifest"
            if result.collection_method
            else "reduced_metadata"
        )
        for result in results
        if result.source_type.value in {"original_real", "modified_real"}
    )
    rows.extend(
        {
            "dimension": "source_type",
            "category": key,
            "case_count": value,
            "source_family_count": len({
                result.source_family_id for result in results
                if result.source_type.value == key
            }),
        }
        for key, value in sorted(source_counts.items())
    )
    rows.extend(
        {
            "dimension": "pack_size",
            "category": key,
            "case_count": value,
            "source_family_count": len({
                result.source_family_id for result in results
                if result.pack_size_category.value == key
            }),
        }
        for key, value in sorted(size_counts.items())
    )
    rows.extend(
        {
            "dimension": "case_origin",
            "category": key,
            "case_count": value,
            "source_family_count": len({
                result.source_family_id for result in results
                if (
                    "original/control"
                    if result.modification_type.value == "none"
                    else "modified/injected"
                ) == key
            }),
        }
        for key, value in sorted(modification_counts.items())
    )
    rows.extend(
        {
            "dimension": "real_data_scope",
            "category": key,
            "case_count": value,
            "source_family_count": len({
                result.source_family_id
                for result in results
                if result.source_type.value in {"original_real", "modified_real"}
                and (
                    "complete_manifest"
                    if result.collection_method
                    else "reduced_metadata"
                )
                == key
            }),
        }
        for key, value in sorted(real_scope_counts.items())
    )
    for dimension, counts, getter in (
        ("topology", topology_counts, lambda item: item.topology or "not_applicable"),
        ("ground_truth", ground_truth_counts, lambda item: item.ground_truth_method.value),
        ("review_status", review_counts, lambda item: item.review_status),
        (
            "complexity_quartile",
            complexity_counts,
            lambda item: complexity_quartiles[item.case_id],
        ),
    ):
        rows.extend(
            {
                "dimension": dimension,
                "category": key,
                "case_count": value,
                "source_family_count": len({
                    result.source_family_id for result in results
                    if getter(result) == key
                }),
            }
            for key, value in sorted(counts.items())
        )
    return rows


def _case_category_rows(results: Sequence[FinalCaseEvaluation]) -> list[dict]:
    return [
        {
            "case_id": result.case_id,
            "source_type": result.source_type.value,
            "source_family_id": result.source_family_id,
            "source_pack_slug": result.source_pack_slug or "",
            "collection_method": result.collection_method or "",
            "ground_truth_method": result.ground_truth_method.value,
            "modification_type": result.modification_type.value,
            "topology": result.topology or "",
            "pack_size_category": result.pack_size_category.value,
            "selected_mod_count": result.selected_mod_count,
            "dependency_edge_count": result.dependency_edge_count,
            "required_edge_count": result.required_edge_count,
            "required_edge_density": f"{result.required_edge_density:.4f}",
            "maximum_required_depth": result.maximum_required_depth,
            "mean_candidate_versions_per_mod": f"{result.mean_candidate_versions_per_mod:.3f}",
            "expected_repairable": result.expected_repairable,
            "expected_initial_status": result.expected_initial_status.value,
        }
        for result in sorted(results, key=lambda item: item.case_id)
    ]


def _overall_metric_rows(run: FinalEvaluationRun) -> list[dict]:
    return [
        {
            "system": metric.system.value,
            "total_cases": metric.total_cases,
            "repairable_cases": metric.repairable_cases,
            "successful_repairs": metric.successful_repairs,
            "repair_success_rate": _percent(metric.repair_success_rate),
            "average_preservation_rate": _percent(metric.average_preservation_rate),
            "full_preservation_repairs": metric.full_preservation_repairs,
            "full_preservation_rate_all_expected_repairs": _percent(metric.full_preservation_rate),
            "preserved_mod_fraction_all_expected_repairs": _percent(
                metric.preserved_mod_fraction_all_expected_repairs
            ),
            "average_weighted_cost": _number(metric.average_weighted_cost),
            "average_action_count": f"{metric.average_action_count:.3f}",
            "average_removed_mods": f"{metric.average_removed_mods:.3f}",
            "median_runtime_ms": f"{metric.median_runtime_seconds * 1000:.3f}",
            "average_states_expanded": f"{metric.average_states_expanded:.3f}",
            "cascading_repair_success": (
                _percent(metric.cascading_repair_success_rate)
                if metric.cascading_repair_success_rate is not None
                else "N/A"
            ),
            "optimal_plan_agreement": (
                _percent(metric.optimal_plan_agreement_rate)
                if metric.optimal_plan_agreement_rate is not None
                else "N/A"
            ),
            "no_solution_correctness": (
                _percent(metric.no_solution_correctness_rate)
                if metric.no_solution_correctness_rate is not None
                else "N/A"
            ),
            "explanation_completeness": (
                _percent(metric.explanation_completeness_rate)
                if metric.explanation_completeness_rate is not None
                else "N/A"
            ),
            "dependency_chain_explanation_accuracy": (
                _percent(metric.dependency_chain_explanation_accuracy)
                if metric.dependency_chain_explanation_accuracy is not None
                else "N/A"
            ),
            "cascading_step_explanation_accuracy": (
                _percent(metric.cascading_step_explanation_accuracy)
                if metric.cascading_step_explanation_accuracy is not None
                else "N/A"
            ),
            "global_plan_reason_accuracy": (
                _percent(metric.global_plan_reason_accuracy)
                if metric.global_plan_reason_accuracy is not None
                else "N/A"
            ),
        }
        for metric in run.metrics
    ]


def _baseline_comparison_rows(run: FinalEvaluationRun) -> list[dict]:
    metrics = {metric.system: metric for metric in run.metrics}
    baseline = metrics.get(FinalEvaluationSystem.BASELINE)
    weighted = metrics.get(FinalEvaluationSystem.WEIGHTED_DEFAULT)
    if baseline is None or weighted is None:
        return [{"metric": "availability", "baseline": "missing", "weighted_default": "missing", "difference": "N/A"}]
    return [
        {
            "metric": "repair_success_rate",
            "baseline": _percent(baseline.repair_success_rate),
            "weighted_default": _percent(weighted.repair_success_rate),
            "difference": _percentage_points(weighted.repair_success_rate - baseline.repair_success_rate),
        },
        {
            "metric": "average_preservation_rate",
            "baseline": _percent(baseline.average_preservation_rate),
            "weighted_default": _percent(weighted.average_preservation_rate),
            "difference": _percentage_points(weighted.average_preservation_rate - baseline.average_preservation_rate),
        },
        {
            "metric": "full_preservation_rate_all_expected_repairs",
            "baseline": _percent(baseline.full_preservation_rate),
            "weighted_default": _percent(weighted.full_preservation_rate),
            "difference": _percentage_points(
                weighted.full_preservation_rate - baseline.full_preservation_rate
            ),
        },
        {
            "metric": "preserved_mod_fraction_all_expected_repairs",
            "baseline": _percent(
                baseline.preserved_mod_fraction_all_expected_repairs
            ),
            "weighted_default": _percent(
                weighted.preserved_mod_fraction_all_expected_repairs
            ),
            "difference": _percentage_points(
                weighted.preserved_mod_fraction_all_expected_repairs
                - baseline.preserved_mod_fraction_all_expected_repairs
            ),
        },
        {
            "metric": "median_runtime_ms",
            "baseline": f"{baseline.median_runtime_seconds * 1000:.3f}",
            "weighted_default": f"{weighted.median_runtime_seconds * 1000:.3f}",
            "difference": f"{(weighted.median_runtime_seconds - baseline.median_runtime_seconds) * 1000:.3f}",
        },
        {
            "metric": "suggestion_coverage_rate",
            "baseline": _percent(baseline.suggestion_coverage_rate or 0.0),
            "weighted_default": "N/A",
            "difference": "N/A",
        },
        {
            "metric": "executable_suggestion_rate",
            "baseline": _percent(baseline.executable_suggestion_rate or 0.0),
            "weighted_default": "N/A",
            "difference": "N/A",
        },
    ]


def _profile_comparison_rows(run: FinalEvaluationRun) -> list[dict]:
    metrics = {
        metric.system: metric
        for metric in run.metrics
        if metric.system != FinalEvaluationSystem.BASELINE
    }
    return [
        {
            "profile": metric.system.value,
            "repair_success_rate": _percent(metric.repair_success_rate),
            "average_preservation_rate": _percent(metric.average_preservation_rate),
            "average_weighted_cost_within_profile": _number(metric.average_weighted_cost),
            "average_action_count": f"{metric.average_action_count:.3f}",
            "average_removed_mods": f"{metric.average_removed_mods:.3f}",
            "median_runtime_ms": f"{metric.median_runtime_seconds * 1000:.3f}",
            "note": "Raw weighted costs use this profile's own scale and are not cross-profile comparable.",
        }
        for _, metric in sorted(metrics.items(), key=lambda item: item[0].value)
    ]


def _largest_case_rows(results: Sequence[FinalCaseEvaluation]) -> list[dict]:
    return [
        {
            "case_id": result.case_id,
            "display_name": result.display_name,
            "source_type": result.source_type.value,
            "pack_size_category": result.pack_size_category.value,
            "selected_mod_count": result.selected_mod_count,
            "dependency_edge_count": result.dependency_edge_count,
            "note": (
                "Custom deterministic scale case"
                if result.source_type.value == "custom_modpack"
                else "Reduced/cached or synthetic case"
            ),
        }
        for result in sorted(results, key=lambda item: (-item.selected_mod_count, item.case_id))[:12]
    ]


def _failure_rows(results: Sequence[FinalCaseEvaluation]) -> list[dict]:
    counts = Counter(
        (result.system.value, result.failure_category or "none")
        for result in results
    )
    return [
        {"system": system, "failure_category": category, "case_count": count}
        for (system, category), count in sorted(counts.items())
    ]


def _manual_review_rows(specs) -> list[dict]:
    return [
        {
            "case_id": spec.case_id,
            "source_type": spec.source_type.value,
            "manually_reviewed": spec.manually_reviewed,
            "review_notes": spec.review_notes or "",
        }
        for spec in sorted(specs, key=lambda item: item.case_id)
        if spec.source_type.value in {"original_real", "modified_real", "existing_broken"}
    ]


def _limitation_rows(run: FinalEvaluationRun) -> list[dict]:
    return [
        {"area": "Ecosystem", "limitation": "Evaluation is limited to Fabric-oriented Modrinth metadata."},
        {"area": "Runtime compatibility", "limitation": "Passing metadata checks does not guarantee Minecraft will launch."},
        {"area": "Real packs", "limitation": "Named real-pack cases are reduced cached examples, not complete official exports."},
        {"area": "Large and huge packs", "limitation": "Current large/huge cases are deterministic custom scale cases."},
        {"area": ".mrpack", "limitation": "The reader extracts manifest metadata but does not install or regenerate packs."},
        {"area": "Live API", "limitation": "Published results use offline cached metadata; live collection can change over time."},
        {"area": "Validation", "limitation": f"Automated validation passed {run.validation.passed_cases}/{run.validation.total_cases} cases."},
    ]


def _write_csv(path: Path, rows: Sequence[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else ["note"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        if rows:
            writer.writerows(rows)
        else:
            writer.writerow({"note": "No data available"})
    return path


def _write_latex(path: Path, rows: Sequence[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("% No data available\n", encoding="utf-8")
        return path
    headers = list(rows[0])
    lines = [
        r"\begin{tabular}{" + "l" * len(headers) + "}",
        r"\hline",
        " & ".join(escape_latex(header.replace("_", " ").title()) for header in headers) + r" \\",
        r"\hline",
    ]
    for row in rows:
        lines.append(" & ".join(escape_latex(row.get(header, "")) for header in headers) + r" \\")
    lines.extend([r"\hline", r"\end{tabular}"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_markdown(path: Path, rows: Sequence[dict], title: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {title}", ""]
    if not rows:
        lines.append("No data available.")
    else:
        headers = list(rows[0])
        lines.append("| " + " | ".join(header.replace("_", " ").title() for header in headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        for row in rows:
            lines.append("| " + " | ".join(str(row.get(header, "")).replace("|", "\\|") for header in headers) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _unique_case_results(results: Sequence[FinalCaseEvaluation]) -> list[FinalCaseEvaluation]:
    preferred = {}
    for result in results:
        current = preferred.get(result.case_id)
        if current is None or result.system == FinalEvaluationSystem.WEIGHTED_DEFAULT:
            preferred[result.case_id] = result
    return [preferred[key] for key in sorted(preferred)]


def _percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def _percentage_points(value: float) -> str:
    return f"{value * 100:+.2f} percentage points"


def _number(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.3f}"
