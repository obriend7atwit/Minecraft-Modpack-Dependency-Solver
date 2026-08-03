from __future__ import annotations

from pathlib import Path

from modpack_solver.analysis import (
    apply_baseline_suggestions,
    baseline_suggestions_for_case,
    run_baseline_experiment,
)
from modpack_solver.metadata.synthetic import load_synthetic_case
from modpack_solver.models import RepairActionType


FIXTURE_DIR = Path("data/synthetic")


def _load_case(name: str):
    return load_synthetic_case(FIXTURE_DIR / name)


def test_compatible_case_requires_no_repair() -> None:
    case = _load_case("valid_modpack.json")
    suggestions = baseline_suggestions_for_case(case)

    assert suggestions == []


def test_missing_dependency_suggestion_can_be_applied_when_metadata_exists() -> None:
    case = _load_case("missing_required_dependency.json")
    result = apply_baseline_suggestions(case, baseline_suggestions_for_case(case))

    assert result.final_compatible is True
    assert result.executable_actions[0].action_type == RepairActionType.ADD_DEPENDENCY


def test_removal_suggestion_can_be_applied() -> None:
    case = _load_case("hard_conflict.json")
    result = apply_baseline_suggestions(case, baseline_suggestions_for_case(case))

    assert result.final_compatible is True
    assert any(action.action_type == RepairActionType.REMOVE_MOD for action in result.executable_actions)


def test_generic_version_suggestion_uses_deterministic_compatible_version_ordering() -> None:
    case = _load_case("version_choice.json")
    result = apply_baseline_suggestions(case, baseline_suggestions_for_case(case))

    assert result.executable_actions[0].target_version_id == "example-client-ui-1.0.0"


def test_non_executable_suggestion_is_recorded() -> None:
    case = _load_case("no_solution.json")
    result = apply_baseline_suggestions(case, baseline_suggestions_for_case(case))

    assert result.unexecutable_suggestions
    assert result.final_compatible is False


def test_baseline_does_not_backtrack() -> None:
    case = _load_case("combined_missing_and_conflict.json")
    suggestions = baseline_suggestions_for_case(case)
    result = apply_baseline_suggestions(case, suggestions)

    assert [action.action_type for action in result.executable_actions] == [
        action.action_type for action in suggestions[: len(result.executable_actions)]
    ]


def test_baseline_does_not_compare_weighted_costs() -> None:
    case = _load_case("hard_conflict.json")
    suggestions = baseline_suggestions_for_case(case)

    assert suggestions[0].cost == 5


def test_final_checker_is_rerun() -> None:
    case = _load_case("missing_required_dependency.json")
    result = apply_baseline_suggestions(case, baseline_suggestions_for_case(case))

    assert result.final_report is not None
    assert result.final_report.status.value == "compatible"


def test_original_case_is_not_mutated() -> None:
    case = _load_case("missing_required_dependency.json")
    original = case.model_dump()

    apply_baseline_suggestions(case, baseline_suggestions_for_case(case))

    assert case.model_dump() == original


def test_validated_repair_rate_is_calculated() -> None:
    _, summary = run_baseline_experiment(
        Path("data/evaluation/manifest.json"),
        runtime_repetitions=1,
        case_ids={"synthetic-missing-dependency"},
    )

    assert summary.validated_baseline_repair_rate == 1.0
