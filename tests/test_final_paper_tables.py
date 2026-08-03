from modpack_solver.final_reports.paper import generate_paper_outputs
from modpack_solver.final_reports.runner import run_final_evaluation


def test_paper_tables_are_created_and_nonempty(tmp_path):
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
    outputs = generate_paper_outputs(run, tmp_path / "run")
    expected = [
        "paper_dataset_summary.csv",
        "paper_dataset_summary.tex",
        "paper_dataset_summary.md",
        "paper_solver_comparison.csv",
        "paper_solver_comparison.md",
        "paper_solver_comparison.tex",
        "paper_solver_confidence_intervals.csv",
        "paper_complexity_results.csv",
        "paper_complexity_results.tex",
        "cascading_repairs.csv",
        "cascading_repairs.tex",
        "cascading_case_study.md",
    ]
    assert all((tmp_path / "run" / "paper" / name).stat().st_size > 0 for name in expected)
    comparison = (tmp_path / "run" / "paper" / "paper_solver_comparison.csv").read_text()
    assert len(comparison.splitlines()[0].split(",")) == 8
    assert "repair_success_95_ci" not in comparison
    assert "cost" not in comparison.splitlines()[0].lower()
    assert "Weighted default" in comparison
    confidence = (
        tmp_path / "run" / "paper" / "paper_solver_confidence_intervals.csv"
    ).read_text(encoding="utf-8")
    assert "repair_success_95_ci" in confidence
    assert "mean_removals_95_ci" in confidence
    assert "median_runtime_ms_95_ci" in confidence
    solver_note = (
        tmp_path / "run" / "paper" / "paper_solver_comparison.md"
    ).read_text(encoding="utf-8")
    assert "Mean preservation is calculated among successful repairs" in solver_note
    complexity = (
        tmp_path / "run" / "paper" / "paper_complexity_results.csv"
    ).read_text(encoding="utf-8")
    assert "total_cases,repairable_cases,successful_repairs" in complexity
    assert "tabularx" in (
        tmp_path / "run" / "paper" / "paper_complexity_results.tex"
    ).read_text(encoding="utf-8")
    assert outputs


def test_complete_manifest_cases_are_reported_separately_from_reduced_real_data(
    tmp_path,
):
    run = run_final_evaluation(
        output_dir=tmp_path / "run",
        case_ids=[
            "full-fabulously-optimized-czy3bvs9",
            "full-fabulously-optimized-czy3bvs9-missing-required",
        ],
        runtime_repetitions=1,
        skip_charts=True,
    )
    generate_paper_outputs(run, tmp_path / "run")

    dataset_table = (
        tmp_path / "run" / "paper" / "paper_dataset_summary.csv"
    ).read_text(encoding="utf-8")
    summary = (
        tmp_path / "run" / "reports" / "final_evaluation_summary.md"
    ).read_text(encoding="utf-8")
    assert "Complete Modrinth controls" in dataset_table
    assert "Complete Modrinth variants" in dataset_table
    assert "1 complete cached Modrinth manifest controls" in summary
    assert "No complete live Modrinth source pack" not in summary
    assert "automated field-completeness check, not a human-readability score" in summary
    assert "Human review:" in summary
    assert "Publication-ready review:" in summary
