from modpack_solver.final_reports.models import FinalEvaluationSystem
from modpack_solver.final_reports.runner import run_final_evaluation


def test_family_and_common_denominator_metrics_are_recorded(tmp_path):
    run = run_final_evaluation(
        output_dir=tmp_path,
        case_ids=[
            "synthetic-duplicate-selection",
            "cascade-01-missing-chain",
            "search-profile-01",
        ],
        runtime_repetitions=1,
        skip_charts=True,
    )
    metrics = {item.system: item for item in run.metrics}
    baseline = metrics[FinalEvaluationSystem.BASELINE]
    weighted = metrics[FinalEvaluationSystem.WEIGHTED_DEFAULT]
    assert weighted.full_preservation_rate >= baseline.full_preservation_rate
    assert 0 <= weighted.preserved_mod_fraction_all_expected_repairs <= 1
    assert weighted.cascading_cases == 1
    assert weighted.maximum_repair_depth >= 3
    assert all(result.source_family_id for result in run.results)
