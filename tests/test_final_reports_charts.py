from pathlib import Path

from modpack_solver.final_reports.charts import COLORS, generate_final_charts
from modpack_solver.final_reports.runner import run_final_evaluation


def test_final_charts_generate_headlessly(tmp_path):
    run = run_final_evaluation(
        output_dir=tmp_path / "run",
        case_ids=["synthetic-duplicate-selection"],
        runtime_repetitions=1,
        skip_charts=True,
    )
    charts = generate_final_charts(run, tmp_path / "charts-output")
    assert len(charts) == 9
    assert all(Path(chart.path).exists() and Path(chart.path).stat().st_size > 0 for chart in charts)
    assert all(chart.plotted_data for chart in charts)
    failure_chart = next(chart for chart in charts if chart.title == "Failure Categories by System")
    assert failure_chart.plotted_data["labels"] == [
        "Baseline",
        "Weighted default",
        "Preservation-focused",
    ]
    assert failure_chart.plotted_data["totals"] == [1, 0, 0]


def test_final_chart_palette_does_not_use_yellow():
    assert all(color.lower() not in {"yellow", "#ffff00", "#ffd700"} for color in COLORS)
