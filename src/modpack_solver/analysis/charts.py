"""Headless PNG chart generation for Week 9 analysis."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_MPLCONFIGDIR = Path(".test-artifacts") / "matplotlib"
_MPLCONFIGDIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MPLCONFIGDIR.resolve()))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from modpack_solver.analysis.models import ExperimentSummary, Week9AnalysisResult


PALETTE = {
    "blue": "#377eb8",
    "green": "#4daf4a",
    "red": "#e41a1c",
    "purple": "#984ea3",
    "gray": "#999999",
    "orange": "#ff7f00",
}


@dataclass(frozen=True)
class ChartOutput:
    path: Path
    labels: list[str]
    values: list[float]
    colors: list[str]


def generate_all_charts(result: Week9AnalysisResult, output_dir: str | Path) -> list[ChartOutput]:
    charts_dir = Path(output_dir) / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    return [
        generate_repair_success_chart(result.summaries, charts_dir / "repair_success.png"),
        generate_preservation_chart(result.summaries, charts_dir / "preservation.png"),
        generate_runtime_chart(result.summaries, charts_dir / "median_runtime.png"),
        generate_failure_category_chart(result, charts_dir / "failure_categories.png"),
        generate_baseline_vs_weighted_chart(result.summaries, charts_dir / "baseline_vs_weighted.png"),
    ]


def generate_repair_success_chart(summaries: list[ExperimentSummary], path: str | Path) -> ChartOutput:
    selected = _ordered_summaries(summaries)
    labels = [_summary_label(summary) for summary in selected]
    values = [summary.repair_success_rate for summary in selected]
    colors = _colors(len(values))
    return _bar_chart(Path(path), "Repair Success Rate", labels, values, colors, y_label="Rate", rate_axis=True)


def generate_preservation_chart(summaries: list[ExperimentSummary], path: str | Path) -> ChartOutput:
    selected = _ordered_summaries(summaries)
    labels = [_summary_label(summary) for summary in selected]
    values = [summary.average_repair_preservation_rate for summary in selected]
    colors = _colors(len(values))
    return _bar_chart(Path(path), "Average Preservation Rate", labels, values, colors, y_label="Rate", rate_axis=True)


def generate_runtime_chart(summaries: list[ExperimentSummary], path: str | Path) -> ChartOutput:
    selected = _ordered_summaries(summaries)
    labels = [_summary_label(summary) for summary in selected]
    values = [summary.median_runtime_seconds * 1000 for summary in selected]
    colors = _colors(len(values))
    return _bar_chart(Path(path), "Median Runtime", labels, values, colors, y_label="Milliseconds")


def generate_failure_category_chart(result: Week9AnalysisResult, path: str | Path) -> ChartOutput:
    counts: dict[str, int] = {}
    for summary in result.summaries:
        for category, count in summary.failure_counts.items():
            counts[category] = counts.get(category, 0) + count
    if not counts:
        return _message_chart(Path(path), "Failure Categories", "No failed evaluation cases were observed.")
    labels = sorted(counts)
    values = [float(counts[label]) for label in labels]
    colors = _colors(len(values))
    return _bar_chart(Path(path), "Failure Categories", labels, values, colors, y_label="Count")


def generate_baseline_vs_weighted_chart(summaries: list[ExperimentSummary], path: str | Path) -> ChartOutput:
    selected = _ordered_summaries(summaries)
    labels = [_summary_label(summary) for summary in selected]
    values = [
        summary.validated_baseline_repair_rate
        if summary.system.value == "baseline" and summary.validated_baseline_repair_rate is not None
        else summary.repair_success_rate
        for summary in selected
    ]
    colors = _colors(len(values))
    return _bar_chart(
        Path(path),
        "Validated Repair Rate by System",
        labels,
        values,
        colors,
        y_label="Rate",
        rate_axis=True,
    )


def _bar_chart(
    path: Path,
    title: str,
    labels: list[str],
    values: list[float],
    colors: list[str],
    *,
    y_label: str,
    rate_axis: bool = False,
) -> ChartOutput:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.bar(labels, values, color=colors)
    ax.set_title(title)
    ax.set_ylabel(y_label)
    ax.set_ylim(bottom=0)
    if rate_axis:
        ax.set_ylim(0, 1.05)
    ax.tick_params(axis="x", labelrotation=20)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return ChartOutput(path=path, labels=labels, values=values, colors=colors)


def _message_chart(path: Path, title: str, message: str) -> ChartOutput:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.set_title(title)
    ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=13)
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return ChartOutput(path=path, labels=[message], values=[0.0], colors=[PALETTE["gray"]])


def _ordered_summaries(summaries: list[ExperimentSummary]) -> list[ExperimentSummary]:
    order = {"baseline": 0, "weighted_default": 1, "weighted_preservation": 2}
    return sorted(summaries, key=lambda summary: (order.get(summary.system.value, 99), summary.profile_id or ""))


def _summary_label(summary: ExperimentSummary) -> str:
    if summary.system.value == "baseline":
        return "Baseline"
    if summary.profile_id == "preservation":
        return "Preservation"
    return "Default"


def _colors(count: int) -> list[str]:
    base = [
        PALETTE["blue"],
        PALETTE["green"],
        PALETTE["red"],
        PALETTE["purple"],
        PALETTE["gray"],
        PALETTE["orange"],
    ]
    return [base[index % len(base)] for index in range(count)]
