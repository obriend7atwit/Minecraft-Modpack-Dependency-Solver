from __future__ import annotations

from pathlib import Path

from modpack_solver.metadata.synthetic import load_synthetic_case
from modpack_solver.solver import (
    CompatibilityStatus,
    RepairWeights,
    SearchLimits,
    compare_baseline_and_weighted,
    evaluate_config,
    solve_weighted_case,
)
from modpack_solver.solver.checker import IssueSeverity
from modpack_solver.solver.costs import plan_cost


FIXTURE_DIR = Path("data/synthetic")


def _load_case(name: str):
    return load_synthetic_case(FIXTURE_DIR / name)


def _assert_valid_solution(case_name: str) -> None:
    case = _load_case(case_name)
    result = solve_weighted_case(case)

    assert result.repaired_config is not None
    final_report = evaluate_config(result.repaired_config, case.projects, case.versions)
    assert not any(issue.severity == IssueSeverity.ERROR.value for issue in final_report.issues)


def test_valid_modpack_returns_already_compatible() -> None:
    case = _load_case("valid_modpack.json")
    result = solve_weighted_case(case)

    assert result.status.value == "already_compatible"
    assert result.total_cost == 0
    assert result.actions == []
    assert result.final_report is not None
    assert result.final_report.status == CompatibilityStatus.COMPATIBLE


def test_missing_required_dependency_finds_add_dependency_solution() -> None:
    case = _load_case("missing_required_dependency.json")
    result = solve_weighted_case(case)

    assert result.status.value == "solution_found"
    assert any(action.action_type.value == "add_dependency" for action in result.actions)
    _assert_valid_solution("missing_required_dependency.json")


def test_hard_conflict_finds_valid_repair() -> None:
    case = _load_case("hard_conflict.json")
    result = solve_weighted_case(case)

    assert result.status.value == "solution_found"
    assert any(action.action_type.value == "remove_mod" for action in result.actions)
    _assert_valid_solution("hard_conflict.json")


def test_version_choice_prefers_lower_cost_upgrade_by_default() -> None:
    case = _load_case("version_choice.json")
    result = solve_weighted_case(case)

    assert result.status.value == "solution_found"
    assert result.actions[0].action_type.value == "upgrade_mod"
    assert result.actions[0].target_version_id == "example-client-ui-2.0.0"
    _assert_valid_solution("version_choice.json")


def test_loader_mismatch_returns_no_solution_without_alternative_version() -> None:
    case = _load_case("loader_mismatch.json")
    result = solve_weighted_case(case)

    assert result.status.value == "no_solution"


def test_multi_repair_requires_more_than_one_action() -> None:
    case = _load_case("multi_repair.json")
    result = solve_weighted_case(case)

    assert result.status.value == "solution_found"
    assert len(result.actions) > 1
    assert result.total_cost == plan_cost(result.actions, RepairWeights())
    _assert_valid_solution("multi_repair.json")


def test_lower_cost_repair_selection_avoids_high_cost_removal() -> None:
    case = _load_case("tie_breaking.json")
    result = solve_weighted_case(case)

    assert result.status.value == "solution_found"
    assert all(action.action_type.value != "remove_mod" for action in result.actions)
    _assert_valid_solution("tie_breaking.json")


def test_tie_breaking_prefers_expected_deterministic_solution() -> None:
    case = _load_case("tie_breaking.json")
    result = solve_weighted_case(case)

    assert result.status.value == "solution_found"
    assert result.actions[0].target_mod_id == "example-storage"
    assert result.actions[0].target_version_id == "example-storage-1.1.0"
    _assert_valid_solution("tie_breaking.json")


def test_no_solution_case_returns_structured_failure() -> None:
    case = _load_case("no_solution.json")
    result = solve_weighted_case(case)

    assert result.status.value == "no_solution"
    assert result.best_partial_config is not None
    assert result.best_partial_report is not None


def test_search_limit_case_returns_limit_reached() -> None:
    case = _load_case("multi_repair.json")
    result = solve_weighted_case(
        case,
        limits=SearchLimits(max_repair_actions=1, max_expanded_states=50, timeout_seconds=10.0),
    )

    assert result.status.value == "limit_reached"
    assert result.limit_reached is True


def test_custom_weights_can_change_selected_repair() -> None:
    case = _load_case("version_choice.json")
    result = solve_weighted_case(
        case,
        weights=RepairWeights(upgrade_selected_mod=9, downgrade_selected_mod=1),
    )

    assert result.status.value == "solution_found"
    assert result.actions[0].action_type.value == "downgrade_mod"
    assert result.actions[0].target_version_id == "example-client-ui-1.0.0"


def test_original_case_and_config_remain_unchanged_after_solving() -> None:
    case = _load_case("multi_repair.json")
    original_case_dump = case.model_dump()

    solve_weighted_case(case)

    assert case.model_dump() == original_case_dump


def test_every_reported_solution_revalidates_with_checker() -> None:
    for case_name in [
        "missing_required_dependency.json",
        "hard_conflict.json",
        "version_choice.json",
        "multi_repair.json",
        "tie_breaking.json",
    ]:
        _assert_valid_solution(case_name)


def test_compare_baseline_and_weighted_returns_structured_summary() -> None:
    case = _load_case("missing_required_dependency.json")
    comparison = compare_baseline_and_weighted(case)

    assert comparison.weighted_status.value in {"solution_found", "already_compatible"}
    assert comparison.baseline_action_count >= 1
