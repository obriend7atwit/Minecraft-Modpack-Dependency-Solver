from __future__ import annotations

from pathlib import Path

from modpack_solver.metadata.synthetic import load_synthetic_case
from modpack_solver.solver import RepairWeights, SearchLimits
from modpack_solver.solver.search import search_weighted_repairs


FIXTURE_DIR = Path("data/synthetic")


def _load_case(name: str):
    return load_synthetic_case(FIXTURE_DIR / name)


def test_repeated_states_are_not_expanded_indefinitely() -> None:
    case = _load_case("multi_repair.json")
    result = search_weighted_repairs(case.config, case.projects, case.versions, RepairWeights(), SearchLimits())

    assert result.status.value == "solution_found"
    assert result.states_expanded <= 4


def test_best_known_cost_logic_skips_duplicate_final_state_paths() -> None:
    case = _load_case("multi_repair.json")
    result = search_weighted_repairs(case.config, case.projects, case.versions, RepairWeights(), SearchLimits())

    assert result.solutions_found == 1
    assert result.candidate_actions_generated <= 4


def test_maximum_action_depth_is_enforced() -> None:
    case = _load_case("multi_repair.json")
    result = search_weighted_repairs(
        case.config,
        case.projects,
        case.versions,
        RepairWeights(),
        SearchLimits(max_repair_actions=1, max_expanded_states=50, timeout_seconds=10.0),
    )

    assert result.status.value == "limit_reached"
    assert result.limit_reached is True


def test_expanded_state_limit_is_enforced() -> None:
    case = _load_case("hard_conflict.json")
    result = search_weighted_repairs(
        case.config,
        case.projects,
        case.versions,
        RepairWeights(),
        SearchLimits(max_repair_actions=6, max_expanded_states=1, timeout_seconds=10.0),
    )

    assert result.status.value == "limit_reached"
    assert result.limit_reached is True


def test_timeout_returns_structured_timeout_status(monkeypatch) -> None:
    case = _load_case("hard_conflict.json")
    calls = iter([0.0, 0.0, 1.0, 2.0, 3.0])

    monkeypatch.setattr("modpack_solver.solver.search.time.monotonic", lambda: next(calls))
    result = search_weighted_repairs(
        case.config,
        case.projects,
        case.versions,
        RepairWeights(),
        SearchLimits(max_repair_actions=6, max_expanded_states=5000, timeout_seconds=0.5),
    )

    assert result.status.value == "timeout"


def test_equal_priority_entries_do_not_raise_comparison_errors() -> None:
    case = _load_case("tie_breaking.json")
    result = search_weighted_repairs(case.config, case.projects, case.versions, RepairWeights(), SearchLimits())

    assert result.status.value == "solution_found"


def test_tie_breaking_is_deterministic() -> None:
    case = _load_case("tie_breaking.json")
    first = search_weighted_repairs(case.config, case.projects, case.versions, RepairWeights(), SearchLimits())
    second = search_weighted_repairs(case.config, case.projects, case.versions, RepairWeights(), SearchLimits())

    assert first.actions[0].target_mod_id == second.actions[0].target_mod_id
    assert first.repaired_config == second.repaired_config
