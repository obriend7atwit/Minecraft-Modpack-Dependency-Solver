"""Compact tables and figures intended for the six-page final report."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
import statistics
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

from modpack_solver.final_dataset.manifest import load_final_dataset_manifest
from modpack_solver.final_reports.models import (
    FinalCaseEvaluation,
    FinalEvaluationRun,
    FinalEvaluationSystem,
)
from modpack_solver.final_reports.statistics import cluster_bootstrap_metric
from modpack_solver.models import IssueType


SYSTEM_LABELS = {
    FinalEvaluationSystem.BASELINE: "Baseline",
    FinalEvaluationSystem.WEIGHTED_DEFAULT: "Weighted default",
    FinalEvaluationSystem.WEIGHTED_PRESERVATION: "Preservation-focused",
}


def generate_paper_outputs(
    run: FinalEvaluationRun,
    output_dir: str | Path,
) -> list[Path]:
    paper_dir = Path(output_dir) / "paper"
    paper_dir.mkdir(parents=True, exist_ok=True)
    unique_cases = _results_for_system(run, FinalEvaluationSystem.WEIGHTED_DEFAULT)

    dataset_rows = _dataset_rows(unique_cases)
    solver_rows = _solver_rows(run)
    solver_ci_rows = _solver_confidence_interval_rows(run)
    complexity_rows = _complexity_rows(unique_cases)
    cascading_rows = _cascading_rows(run)
    outputs = []
    for stem, rows in (
        ("paper_dataset_summary", dataset_rows),
        ("paper_complexity_results", complexity_rows),
    ):
        outputs.extend(_write_table_set(paper_dir / stem, rows))
    outputs.extend(_write_solver_table_set(paper_dir / "paper_solver_comparison", solver_rows))
    outputs.extend(
        _write_table_set(
            paper_dir / "paper_solver_confidence_intervals", solver_ci_rows
        )
    )
    outputs.extend(
        [
            _write_csv(paper_dir / "cascading_repairs.csv", cascading_rows),
            _write_latex(paper_dir / "cascading_repairs.tex", cascading_rows),
            _write_cascading_case_study(run, paper_dir / "cascading_case_study.md"),
            _write_evidence_scope(paper_dir / "evidence_scope.md", latex=False),
            _write_evidence_scope(paper_dir / "evidence_scope.tex", latex=True),
            _issue_success_heatmap(run, paper_dir / "issue_success_heatmap.png"),
            _runtime_complexity_figure(run, paper_dir / "runtime_complexity.png"),
        ]
    )
    return outputs


def _dataset_rows(results: Sequence[FinalCaseEvaluation]) -> list[dict]:
    groups = {
        "Synthetic": [item for item in results if item.source_type.value == "synthetic"],
        "Reduced real controls": [
            item
            for item in results
            if item.source_type.value == "original_real" and not item.collection_method
        ],
        "Complete Modrinth controls": [
            item
            for item in results
            if item.source_type.value == "original_real" and item.collection_method
        ],
        "Reduced real variants": [
            item
            for item in results
            if item.source_type.value == "modified_real" and not item.collection_method
        ],
        "Complete Modrinth variants": [
            item
            for item in results
            if item.source_type.value == "modified_real" and item.collection_method
        ],
        "Legacy custom scale": [
            item
            for item in results
            if item.source_type.value == "custom_modpack"
        ],
        "Custom topology": [
            item
            for item in results
            if item.source_type.value == "custom_topology"
        ],
        "Cascading stress": [
            item for item in results if item.source_type.value == "cascading_stress"
        ],
        "Search stress": [
            item for item in results if item.source_type.value == "search_stress"
        ],
        "Total": list(results),
    }
    rows = []
    for label, values in groups.items():
        if not values:
            continue
        rows.append(
            {
                "source_group": label,
                "cases": len(values),
                "source_families": len({item.source_family_id for item in values}),
                "median_selected_mods": _median(item.selected_mod_count for item in values),
                "median_required_edges": _median(item.required_edge_count for item in values),
                "median_required_edge_density": f"{_median(item.required_edge_density for item in values):.3f}",
                "median_maximum_depth": _median(item.maximum_required_depth for item in values),
                "median_candidate_versions": f"{_median(item.mean_candidate_versions_per_mod for item in values):.2f}",
                "controls": sum(item.modification_type.value == "none" for item in values),
                "modified": sum(item.modification_type.value != "none" for item in values),
            }
        )
    return rows


def _solver_rows(run: FinalEvaluationRun) -> list[dict]:
    return [
        {
            "method": SYSTEM_LABELS[metric.system],
            "repairs": f"{metric.successful_repairs}/{metric.repairable_cases}",
            "success": _percent(metric.repair_success_rate),
            "full_preservation": f"{metric.full_preservation_repairs}/{metric.repairable_cases}",
            "mean_preservation": _percent(metric.average_preservation_rate),
            "mean_removals": f"{metric.average_removed_mods:.3f}",
            "median_runtime_ms": f"{metric.median_runtime_seconds * 1000:.3f}",
            "failures": metric.repairable_cases - metric.successful_repairs,
        }
        for metric in run.metrics
    ]


def _solver_confidence_interval_rows(run: FinalEvaluationRun) -> list[dict]:
    rows = []
    for metric in run.metrics:
        values = [item for item in run.results if item.system == metric.system]
        repairable = [item for item in values if item.expected_repairable]
        success_ci = _cluster_ci(
            repairable,
            lambda items: _mean_bool(item.repair_success for item in items),
        )
        full_ci = _cluster_ci(
            repairable,
            lambda items: _mean_bool(
                item.repair_success and item.preservation_rate == 1.0
                for item in items
            ),
        )
        preservation_ci = _cluster_ci(
            repairable,
            lambda items: _mean(
                item.preservation_rate for item in items if item.repair_success
            ),
        )
        successful = [item for item in repairable if item.repair_success]
        removals_ci = _cluster_ci(
            successful,
            lambda items: _mean(item.removed_mod_count for item in items),
        )
        runtime_ci = _cluster_ci(
            values,
            lambda items: _median(item.runtime_seconds * 1000 for item in items),
        )
        rows.append(
            {
                "method": SYSTEM_LABELS[metric.system],
                "repair_success_95_ci": _ci_text(success_ci),
                "full_preservation_95_ci": _ci_text(full_ci),
                "preservation_95_ci": _ci_text(preservation_ci),
                "mean_removals_95_ci": _number_ci_text(removals_ci),
                "median_runtime_ms_95_ci": _number_ci_text(runtime_ci),
            }
        )
    return rows


def _complexity_rows(results: Sequence[FinalCaseEvaluation]) -> list[dict]:
    density_values = sorted(item.required_edge_density for item in results)
    low_cut = _quantile(density_values, 1 / 3)
    high_cut = _quantile(density_values, 2 / 3)
    groups = {
        **{
            size.title(): [
                item for item in results if item.pack_size_category.value == size
            ]
            for size in ("small", "medium", "large", "huge")
        },
        "Low density": [
            item for item in results if item.required_edge_density <= low_cut
        ],
        "Medium density": [
            item
            for item in results
            if low_cut < item.required_edge_density <= high_cut
        ],
        "High density": [
            item for item in results if item.required_edge_density > high_cut
        ],
        "Shallow": [item for item in results if item.maximum_required_depth <= 2],
        "Medium depth": [
            item for item in results if 2 < item.maximum_required_depth <= 10
        ],
        "Deep": [item for item in results if item.maximum_required_depth > 10],
    }
    return [
        {
            "group": label,
            "total_cases": len(values),
            "repairable_cases": sum(item.expected_repairable for item in values),
            "successful_repairs": sum(item.repair_success for item in values if item.expected_repairable),
            "repair_success": _percent(
                _mean_bool(item.repair_success for item in values if item.expected_repairable)
            ),
            "median_runtime_ms": f"{_median(item.runtime_seconds * 1000 for item in values):.3f}",
            "median_states": f"{_median(item.states_expanded for item in values):.1f}",
            "mean_repair_actions": f"{_mean(item.action_count for item in values if item.expected_repairable):.2f}",
        }
        for label, values in groups.items()
        if values
    ]


def _cascading_rows(run: FinalEvaluationRun) -> list[dict]:
    manifest = load_final_dataset_manifest(run.manifest_path)
    specs = {spec.case_id: spec for spec in manifest.cases}
    weighted = _results_for_system(run, FinalEvaluationSystem.WEIGHTED_DEFAULT)
    rows = []
    for result in weighted:
        if not result.is_cascading:
            continue
        spec = specs[result.case_id]
        first = spec.expected_issue_trace[0] if spec.expected_issue_trace else None
        rows.append(
            {
                "case_id": result.case_id,
                "initial_issue": _issue_list(
                    first.expected_issue_types_before if first else result.issue_types
                ),
                "revealed_after_first": _issue_list(
                    first.expected_issue_types_after if first else []
                ),
                "repair_depth": result.action_count,
                "weighted_actions": ", ".join(
                    action.value for action in result.action_types
                )
                or "none",
                "total_cost": result.total_cost if result.total_cost is not None else "N/A",
                "states_expanded": result.states_expanded,
                "final_status": "compatible" if result.final_compatible else result.solver_status.value,
            }
        )
    return rows


def _issue_success_heatmap(run: FinalEvaluationRun, path: Path) -> Path:
    systems = [
        FinalEvaluationSystem.BASELINE,
        FinalEvaluationSystem.WEIGHTED_DEFAULT,
    ]
    categories = [
        ("Missing dependency", lambda item: IssueType.MISSING_DEPENDENCY in item.issue_types),
        (
            "Minecraft mismatch",
            lambda item: IssueType.MINECRAFT_VERSION_MISMATCH in item.issue_types,
        ),
        ("Loader mismatch", lambda item: IssueType.LOADER_MISMATCH in item.issue_types),
        ("Hard conflict", lambda item: IssueType.HARD_CONFLICT in item.issue_types),
        (
            "Duplicate version",
            lambda item: IssueType.DUPLICATE_MOD_VERSION in item.issue_types,
        ),
        ("Cascading dependency", lambda item: item.is_cascading),
        ("Multi-error", lambda item: item.modification_type.value == "multi_error"),
        (
            "Candidate/search stress",
            lambda item: item.source_type.value == "search_stress",
        ),
    ]
    values = []
    annotations = []
    for _, predicate in categories:
        value_row = []
        annotation_row = []
        for system in systems:
            matching = [
                item
                for item in run.results
                if item.system == system and item.expected_repairable and predicate(item)
            ]
            successes = sum(item.repair_success for item in matching)
            rate = successes / len(matching) if matching else 0.0
            value_row.append(rate)
            annotation_row.append(
                f"{successes}/{len(matching)}\n{rate:.0%}" if matching else "0/0\nN/A"
            )
        values.append(value_row)
        annotations.append(annotation_row)

    cmap = LinearSegmentedColormap.from_list(
        "muted_red_to_teal",
        ["#a4473f", "#f1ece3", "#176f73"],
    )
    fig, axis = plt.subplots(figsize=(7.2, 5.2))
    image = axis.imshow(values, vmin=0, vmax=1, cmap=cmap, aspect="auto")
    axis.set_xticks(range(len(systems)), [SYSTEM_LABELS[system] for system in systems])
    axis.set_yticks(range(len(categories)), [label for label, _ in categories])
    axis.set_title("Repair Success by Issue Category")
    for row_index, row in enumerate(annotations):
        for column_index, text in enumerate(row):
            axis.text(column_index, row_index, text, ha="center", va="center", fontsize=9)
    fig.colorbar(image, ax=axis, label="Repair success rate", fraction=0.04)
    fig.text(
        0.01,
        0.01,
        "Issue categories are not mutually exclusive for multi-error cases.",
        fontsize=8,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def _runtime_complexity_figure(run: FinalEvaluationRun, path: Path) -> Path:
    baseline = _results_for_system(run, FinalEvaluationSystem.BASELINE)
    weighted = _results_for_system(run, FinalEvaluationSystem.WEIGHTED_DEFAULT)
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.6))
    colors = {
        FinalEvaluationSystem.BASELINE: "#a4473f",
        FinalEvaluationSystem.WEIGHTED_DEFAULT: "#176f73",
    }
    for system, values in (
        (FinalEvaluationSystem.BASELINE, baseline),
        (FinalEvaluationSystem.WEIGHTED_DEFAULT, weighted),
    ):
        axes[0].scatter(
            [item.selected_mod_count for item in values],
            [max(item.runtime_seconds * 1000, 0.001) for item in values],
            alpha=0.55,
            s=24,
            color=colors[system],
            label=SYSTEM_LABELS[system],
            edgecolors="none",
        )
    axes[0].set_xlabel("Selected mods")
    axes[0].set_ylabel("Median runtime (ms)")
    axes[0].set_yscale("log")
    axes[0].set_title("A. Runtime vs. selected-mod count")
    axes[0].legend(frameon=False)

    axes[1].scatter(
        [item.required_edge_count for item in weighted],
        [max(item.runtime_seconds * 1000, 0.001) for item in weighted],
        s=[24 + min(item.states_expanded, 100) * 1.5 for item in weighted],
        c=[item.maximum_required_depth for item in weighted],
        cmap=LinearSegmentedColormap.from_list(
            "depth_teal_blue",
            ["#8eb7ad", "#176f73", "#1f4f75"],
        ),
        alpha=0.62,
        edgecolors="none",
    )
    axes[1].set_xlabel("Required dependency edges")
    axes[1].set_ylabel("Weighted runtime (ms)")
    axes[1].set_yscale("log")
    axes[1].set_title("B. Weighted runtime vs. graph complexity")
    axes[1].text(
        0.02,
        0.98,
        "Point size = states expanded\nColor = maximum dependency depth",
        transform=axes[1].transAxes,
        va="top",
        fontsize=8,
    )
    fig.suptitle("Runtime on Controlled Metadata Cases and Dependency-Dense Scale Tests")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def _write_cascading_case_study(run: FinalEvaluationRun, path: Path) -> Path:
    manifest = load_final_dataset_manifest(run.manifest_path)
    available_case_ids = {
        item.case_id
        for item in run.results
        if item.system == FinalEvaluationSystem.WEIGHTED_DEFAULT and item.is_cascading
    }
    if not available_case_ids:
        path.write_text(
            "# Cascading Repair Case Study\n\nNo cascading case was included in this run.\n",
            encoding="utf-8",
        )
        return path
    spec = next(
        (
            item
            for item in manifest.cases
            if item.case_id == "cascade-01-missing-chain"
            and item.case_id in available_case_ids
        ),
        next(
            item
            for item in manifest.cases
            if item.is_cascading and item.case_id in available_case_ids
        ),
    )
    result = next(
        item
        for item in run.results
        if item.case_id == spec.case_id
        and item.system == FinalEvaluationSystem.WEIGHTED_DEFAULT
    )
    lines = [
        "# Cascading Repair Case Study",
        "",
        f"**Case:** {spec.display_name}",
        "",
        f"**Initial configuration:** {spec.selected_mod_count} selected mod(s), Minecraft {spec.minecraft_version}, {spec.loader}.",
        "",
        f"**Initial issue:** {_issue_list(spec.expected_issue_types)}.",
        "",
    ]
    for step in spec.expected_issue_trace:
        lines.extend(
            [
                f"**Step {step.step_number}:** {step.action_type.value} `{step.target_mod_id or 'configuration'}`.",
                "",
                f"After this action: {_issue_list(step.expected_issue_types_after) or 'no remaining issues'}.",
                "",
            ]
        )
    lines.extend(
        [
            f"**Final result:** {'Compatible' if result.final_compatible else result.solver_status.value}.",
            "",
            (
                f"**Why the complete plan was preferred:** The weighted solver evaluated the "
                f"whole {result.action_count}-action sequence at total cost {result.total_cost}, "
                "rather than stopping after the first locally useful dependency addition."
            ),
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_table_set(base: Path, rows: list[dict]) -> list[Path]:
    return [
        _write_csv(base.with_suffix(".csv"), rows),
        _write_latex(base.with_suffix(".tex"), rows),
        _write_markdown(base.with_suffix(".md"), rows),
    ]


def _write_solver_table_set(base: Path, rows: list[dict]) -> list[Path]:
    outputs = _write_table_set(base, rows)
    note = (
        "Mean preservation is calculated among successful repairs. "
        "Full-preservation repair counts use all expected-repair cases as a common denominator."
    )
    markdown_path = base.with_suffix(".md")
    markdown_path.write_text(
        markdown_path.read_text(encoding="utf-8") + f"\n*{note}*\n",
        encoding="utf-8",
    )
    latex_path = base.with_suffix(".tex")
    latex_path.write_text(
        latex_path.read_text(encoding="utf-8")
        + "\n\\par\\footnotesize "
        + _latex(note)
        + "\n",
        encoding="utf-8",
    )
    return outputs


def _write_csv(path: Path, rows: Sequence[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = list(rows[0]) if rows else ["note"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows or [{"note": "No data available"}])
    return path


def _write_latex(path: Path, rows: Sequence[dict]) -> Path:
    if not rows:
        path.write_text("% No data available\n", encoding="utf-8")
        return path
    headers = list(rows[0])
    lines = [
        r"\begin{tabularx}{\linewidth}{@{}" + "l" + "X" * (len(headers) - 1) + "@{}}",
        r"\hline",
        " & ".join(_latex(header.replace("_", " ").title()) for header in headers)
        + r" \\",
        r"\hline",
    ]
    for row in rows:
        lines.append(
            " & ".join(_latex(row.get(header, "")) for header in headers) + r" \\"
        )
    lines.extend([r"\hline", r"\end{tabularx}"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_markdown(path: Path, rows: Sequence[dict]) -> Path:
    if not rows:
        path.write_text("No data available.\n", encoding="utf-8")
        return path
    headers = list(rows[0])
    lines = [
        "| " + " | ".join(header.replace("_", " ").title() for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend(
        "| "
        + " | ".join(str(row.get(header, "")).replace("|", "\\|") for header in headers)
        + " |"
        for row in rows
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_evidence_scope(path: Path, *, latex: bool) -> Path:
    text = (
        "Complete-manifest cases demonstrate application to real Modrinth metadata, "
        "while modified real-derived cases provide controlled injections on real metadata "
        "structures. Dense topology, cascading, and search cases provide the dependency "
        "interactions needed for algorithmic comparison. The separate search-scaling "
        "supplement measures bounded search-state growth. These metadata-level results do "
        "not guarantee that a repaired pack will launch successfully, and the overall "
        "baseline difference should not be attributed solely to complete Modrinth packs."
    )
    path.write_text((_latex(text) if latex else text) + "\n", encoding="utf-8")
    return path


def _cluster_ci(values, metric):
    return cluster_bootstrap_metric(
        values,
        family_id_getter=lambda item: item.source_family_id,
        metric=metric,
        repetitions=2000,
        seed=42,
    )


def _results_for_system(run, system):
    return [item for item in run.results if item.system == system]


def _median(values) -> float:
    materialized = list(values)
    return float(statistics.median(materialized)) if materialized else 0.0


def _mean(values) -> float:
    materialized = list(values)
    return float(statistics.fmean(materialized)) if materialized else 0.0


def _mean_bool(values) -> float:
    materialized = list(values)
    return sum(materialized) / len(materialized) if materialized else 0.0


def _quantile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    index = min(round((len(values) - 1) * quantile), len(values) - 1)
    return float(values[index])


def _percent(value: float) -> str:
    return f"{value:.1%}"


def _ci_text(interval) -> str:
    return f"[{interval.lower:.1%}, {interval.upper:.1%}]"


def _number_ci_text(interval) -> str:
    return f"[{interval.lower:.3f}, {interval.upper:.3f}]"


def _issue_list(values) -> str:
    return ", ".join(
        value.value if hasattr(value, "value") else str(value)
        for value in values
    )


def _latex(value: object) -> str:
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
    }
    return "".join(replacements.get(character, character) for character in text)
