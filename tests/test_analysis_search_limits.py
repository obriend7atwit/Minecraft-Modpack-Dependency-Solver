from __future__ import annotations

from pathlib import Path

from modpack_solver.analysis import get_default_profile, run_search_limit_experiment


def test_5000_and_10000_state_configurations_are_applied() -> None:
    results = run_search_limit_experiment(
        Path("data/evaluation/manifest.json"),
        get_default_profile(),
        state_limits=(5000, 10000),
        runtime_repetitions=1,
    )

    assert {result.max_expanded_states for result in results} == {5000, 10000}


def test_results_record_status_runtime_and_states_expanded() -> None:
    results = run_search_limit_experiment(
        Path("data/evaluation/manifest.json"),
        get_default_profile(),
        state_limits=(5000,),
        runtime_repetitions=1,
    )

    assert results
    assert results[0].status.value
    assert results[0].runtime.samples_seconds
    assert results[0].states_expanded >= 0


def test_identical_outcomes_are_reported_without_false_improvement_claim() -> None:
    results = run_search_limit_experiment(
        Path("data/evaluation/manifest.json"),
        get_default_profile(),
        state_limits=(5000, 10000),
        runtime_repetitions=1,
    )
    by_case = {}
    for result in results:
        by_case.setdefault(result.case_id, set()).add((result.status, result.final_compatible, result.total_cost))

    assert any(len(outcomes) == 1 for outcomes in by_case.values())
