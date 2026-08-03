from __future__ import annotations

import uuid
from pathlib import Path

import matplotlib.pyplot as plt

from modpack_solver.analysis import generate_all_charts, run_week9_analysis
from modpack_solver.analysis.charts import PALETTE


def test_required_png_charts_are_created_and_nonempty() -> None:
    output_dir = _workspace_dir()
    result = run_week9_analysis(
        output_dir=output_dir,
        runtime_repetitions=1,
        skip_charts=True,
        case_ids={"synthetic-valid", "synthetic-missing-dependency"},
    )
    charts = generate_all_charts(result, output_dir)

    assert {chart.path.name for chart in charts} == {
        "repair_success.png",
        "preservation.png",
        "median_runtime.png",
        "failure_categories.png",
        "baseline_vs_weighted.png",
    }
    assert all(chart.path.exists() and chart.path.stat().st_size > 0 for chart in charts)


def test_chart_outputs_include_labels_values_and_no_yellow() -> None:
    output_dir = _workspace_dir()
    result = run_week9_analysis(output_dir=output_dir, runtime_repetitions=1, skip_charts=True, case_ids={"synthetic-valid"})
    charts = generate_all_charts(result, output_dir)

    assert charts[0].labels
    assert charts[0].values
    assert all("yellow" not in color.lower() and color.lower() != "#ffff00" for color in PALETTE.values())


def test_figures_are_closed_after_generation() -> None:
    output_dir = _workspace_dir()
    result = run_week9_analysis(output_dir=output_dir, runtime_repetitions=1, skip_charts=True, case_ids={"synthetic-valid"})
    generate_all_charts(result, output_dir)

    assert plt.get_fignums() == []


def test_no_failure_chart_is_created_successfully() -> None:
    output_dir = _workspace_dir()
    result = run_week9_analysis(output_dir=output_dir, runtime_repetitions=1, skip_charts=True, case_ids={"synthetic-valid"})
    charts = generate_all_charts(result, output_dir)
    failure_chart = next(chart for chart in charts if chart.path.name == "failure_categories.png")

    assert failure_chart.labels


def _workspace_dir() -> Path:
    path = Path(".test-artifacts") / "analysis-charts" / uuid.uuid4().hex
    path.mkdir(parents=True)
    return path
