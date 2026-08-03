from pathlib import Path

from modpack_solver.final_reports.models import FinalEvaluationSystem
from modpack_solver.final_reports.runner import run_final_evaluation


def test_final_evaluation_runs_three_systems_offline(tmp_path):
    run = run_final_evaluation(
        output_dir=tmp_path,
        max_cases=4,
        runtime_repetitions=1,
        skip_charts=True,
    )
    assert run.validation.passed
    assert len(run.results) == 12
    assert run.runtime_repetitions == 1
    assert run.warmup_runs == 1
    assert run.timer == "time.perf_counter"
    assert all(len(result.runtime_samples_seconds) == 1 for result in run.results)
    assert all(
        result.runtime_minimum_seconds
        <= result.runtime_seconds
        <= result.runtime_maximum_seconds
        for result in run.results
    )
    assert {metric.system for metric in run.metrics} == set(FinalEvaluationSystem)
    assert not [
        result
        for result in run.results
        if result.system != FinalEvaluationSystem.BASELINE and not result.passed
    ]
    expected = [
        "evaluation/final_results.json",
        "evaluation/final_results.csv",
        "evaluation/default_profile.json",
        "evaluation/preservation_profile.json",
        "evaluation/baseline_results.json",
        "reports/final_evaluation_summary.md",
    ]
    assert all((tmp_path / path).exists() for path in expected)


def test_final_evaluation_can_select_one_case(tmp_path):
    run = run_final_evaluation(
        output_dir=tmp_path,
        case_ids=["synthetic-missing-dependency"],
        runtime_repetitions=1,
        skip_charts=True,
    )
    assert {result.case_id for result in run.results} == {"synthetic-missing-dependency"}
    assert len(run.results) == 3
