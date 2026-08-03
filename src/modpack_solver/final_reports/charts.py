"""Headless Matplotlib charts for final solver evaluation."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from modpack_solver.final_reports.models import (
    FinalChartOutput,
    FinalEvaluationRun,
    FinalEvaluationSystem,
)


COLORS = ["#4F772D", "#577590", "#8C5E3C", "#A44A3F", "#6C757D", "#3D5A80"]
SYSTEM_LABELS = {
    FinalEvaluationSystem.BASELINE: "Baseline",
    FinalEvaluationSystem.WEIGHTED_DEFAULT: "Weighted default",
    FinalEvaluationSystem.WEIGHTED_PRESERVATION: "Preservation-focused",
}


def generate_final_charts(run: FinalEvaluationRun, output_dir: str | Path) -> list[FinalChartOutput]:
    chart_dir = Path(output_dir) / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)
    return [
        _repair_success_by_group(run, chart_dir / "repair_success_by_case_type.png", "source_type", "Repair Success by Case Type"),
        _repair_success_by_group(run, chart_dir / "repair_success_by_pack_size.png", "pack_size_category", "Repair Success by Pack Size"),
        _metric_by_system(run, chart_dir / "preservation_by_system.png", "preservation", "Original Mod Preservation", "Rate", rate=True),
        _runtime_by_size(run, chart_dir / "runtime_by_pack_size.png"),
        _states_by_size(run, chart_dir / "states_by_pack_size.png"),
        _failure_chart(run, chart_dir / "failure_categories.png"),
        _action_distribution(run, chart_dir / "action_type_distribution.png"),
        _baseline_vs_weighted(run, chart_dir / "baseline_vs_weighted.png"),
        _explanation_completeness(run, chart_dir / "explanation_completeness.png"),
    ]


def _repair_success_by_group(run, path, attribute: str, title: str) -> FinalChartOutput:
    repairable = [result for result in run.results if result.expected_repairable]
    groups = sorted({getattr(result, attribute).value for result in repairable})
    series = {}
    for system in FinalEvaluationSystem:
        values = []
        for group in groups:
            items = [
                result for result in repairable
                if result.system == system and getattr(result, attribute).value == group
            ]
            values.append(sum(result.repair_success for result in items) / len(items) if items else 0.0)
        series[SYSTEM_LABELS[system]] = values
    return _grouped_bar(path, title, groups, series, "Repair success rate", rate=True)


def _metric_by_system(run, path, metric: str, title: str, ylabel: str, *, rate: bool) -> FinalChartOutput:
    labels = [SYSTEM_LABELS[item.system] for item in run.metrics]
    if metric == "preservation":
        values = [item.average_preservation_rate for item in run.metrics]
    else:
        values = [0.0 for _ in run.metrics]
    return _single_bar(path, title, labels, values, ylabel, rate=rate)


def _runtime_by_size(run, path) -> FinalChartOutput:
    groups = ["small", "medium", "large", "huge"]
    series = {}
    for system in FinalEvaluationSystem:
        values = []
        for group in groups:
            samples = [
                result.runtime_seconds * 1000
                for result in run.results
                if result.system == system and result.pack_size_category.value == group
            ]
            values.append(sum(samples) / len(samples) if samples else 0.0)
        series[SYSTEM_LABELS[system]] = values
    return _grouped_bar(path, "Runtime by Pack Size", groups, series, "Mean runtime (milliseconds)")


def _states_by_size(run, path) -> FinalChartOutput:
    groups = ["small", "medium", "large", "huge"]
    series = {}
    for system in (FinalEvaluationSystem.WEIGHTED_DEFAULT, FinalEvaluationSystem.WEIGHTED_PRESERVATION):
        values = []
        for group in groups:
            samples = [
                result.states_expanded
                for result in run.results
                if result.system == system and result.pack_size_category.value == group
            ]
            values.append(sum(samples) / len(samples) if samples else 0.0)
        series[SYSTEM_LABELS[system]] = values
    return _grouped_bar(path, "Search States by Pack Size", groups, series, "Mean states expanded")


def _failure_chart(run, path) -> FinalChartOutput:
    path = Path(path)
    systems = list(FinalEvaluationSystem)
    labels = [SYSTEM_LABELS[system] for system in systems]
    categories = sorted(
        {
            result.failure_category
            for result in run.results
            if result.failure_category
        }
    )
    category_values = {
        category: [
            sum(
                result.system == system and result.failure_category == category
                for result in run.results
            )
            for system in systems
        ]
        for category in categories
    }
    totals = [
        sum(result.system == system and result.failure_category is not None for result in run.results)
        for system in systems
    ]

    figure, axis = plt.subplots(figsize=(10, 6))
    bottoms = [0] * len(systems)
    if categories:
        for index, category in enumerate(categories):
            values = category_values[category]
            axis.bar(
                range(len(systems)),
                values,
                bottom=bottoms,
                label=category.replace("_", " ").title(),
                color=COLORS[index % len(COLORS)],
            )
            bottoms = [bottom + value for bottom, value in zip(bottoms, values)]
        axis.legend(title="Failure category")
    else:
        axis.bar(range(len(systems)), totals, color=COLORS[0])
        axis.text(
            0.5,
            0.5,
            "No failures were recorded.",
            transform=axis.transAxes,
            ha="center",
            va="center",
        )

    for index, total in enumerate(totals):
        axis.annotate(
            str(total),
            (index, total),
            xytext=(0, 5),
            textcoords="offset points",
            ha="center",
            fontweight="bold",
        )

    axis.set_xticks(range(len(systems)), labels)
    axis.set_ylabel("Failed case-results")
    axis.set_title("Failure Categories by System")
    axis.set_ylim(0, max(totals + [1]) * 1.2)
    axis.grid(axis="y", alpha=0.2)
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)

    plotted_data = {
        "labels": labels,
        "totals": totals,
    }
    plotted_data.update(category_values)
    return FinalChartOutput(
        path=str(path),
        title="Failure Categories by System",
        plotted_data=plotted_data,
    )


def _action_distribution(run, path) -> FinalChartOutput:
    weighted = [result for result in run.results if result.system == FinalEvaluationSystem.WEIGHTED_DEFAULT]
    counts = Counter(action.value for result in weighted for action in result.action_types)
    labels = sorted(counts) or ["none"]
    values = [counts[label] for label in labels] if counts else [0]
    return _single_bar(path, "Weighted Action Type Distribution", labels, values, "Cases containing action")


def _baseline_vs_weighted(run, path) -> FinalChartOutput:
    metrics = {metric.system: metric for metric in run.metrics}
    labels = ["Repair success", "Preservation"]
    series = {}
    for system in FinalEvaluationSystem:
        metric = metrics.get(system)
        if metric:
            series[SYSTEM_LABELS[system]] = [metric.repair_success_rate, metric.average_preservation_rate]
    return _grouped_bar(path, "Baseline vs Weighted Solver", labels, series, "Rate", rate=True)


def _explanation_completeness(run, path) -> FinalChartOutput:
    labels = []
    values = []
    for metric in run.metrics:
        if metric.explanation_completeness_rate is None:
            continue
        labels.append(SYSTEM_LABELS[metric.system])
        values.append(metric.explanation_completeness_rate)
    return _single_bar(path, "Explanation Completeness", labels or ["No weighted results"], values or [0.0], "Rate", rate=True)


def _grouped_bar(path, title, labels, series, ylabel, rate: bool = False) -> FinalChartOutput:
    path = Path(path)
    figure, axis = plt.subplots(figsize=(10, 6))
    series_count = max(1, len(series))
    width = 0.8 / series_count
    x_values = list(range(len(labels)))
    for index, (name, values) in enumerate(series.items()):
        offsets = [x + (index - (series_count - 1) / 2) * width for x in x_values]
        axis.bar(offsets, values, width=width, label=name, color=COLORS[index % len(COLORS)])
    axis.set_xticks(x_values, [label.replace("_", " ").title() for label in labels], rotation=20, ha="right")
    axis.set_ylabel(ylabel)
    axis.set_title(title)
    if rate:
        axis.set_ylim(0, 1.05)
    axis.grid(axis="y", alpha=0.2)
    if series:
        axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)
    plotted = {"labels": list(labels)}
    plotted.update({name: list(values) for name, values in series.items()})
    return FinalChartOutput(path=str(path), title=title, plotted_data=plotted)


def _single_bar(path, title, labels, values, ylabel, rate: bool = False) -> FinalChartOutput:
    path = Path(path)
    figure, axis = plt.subplots(figsize=(10, 6))
    axis.bar(range(len(labels)), values, color=[COLORS[index % len(COLORS)] for index in range(len(labels))])
    axis.set_xticks(range(len(labels)), [label.replace("_", " ").title() for label in labels], rotation=20, ha="right")
    axis.set_ylabel(ylabel)
    axis.set_title(title)
    if rate:
        axis.set_ylim(0, 1.05)
    axis.grid(axis="y", alpha=0.2)
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return FinalChartOutput(path=str(path), title=title, plotted_data={"labels": list(labels), "values": list(values)})
