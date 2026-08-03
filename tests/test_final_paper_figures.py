import inspect

from modpack_solver.final_reports import paper
from modpack_solver.final_reports.runner import run_final_evaluation


def test_paper_figures_work_headlessly_without_prohibited_palette(tmp_path):
    run = run_final_evaluation(
        output_dir=tmp_path / "run",
        case_ids=[
            "synthetic-missing-dependency",
            "cascade-01-missing-chain",
            "search-profile-01",
        ],
        runtime_repetitions=1,
        skip_charts=True,
    )
    paper.generate_paper_outputs(run, tmp_path / "run")
    heatmap = tmp_path / "run" / "paper" / "issue_success_heatmap.png"
    runtime = tmp_path / "run" / "paper" / "runtime_complexity.png"
    assert heatmap.stat().st_size > 1000
    assert runtime.stat().st_size > 1000
    source = inspect.getsource(paper).lower()
    assert '"yellow"' not in source
