from __future__ import annotations

from pathlib import Path

from modpack_solver.analysis import get_default_profile, get_preservation_profile
from modpack_solver.evaluation import load_evaluation_manifest
from modpack_solver.metadata.synthetic import load_synthetic_case
from modpack_solver.solver import evaluate_config, solve_weighted_case


TRADEOFF_PATH = Path("data/experiments/preservation_tradeoff.json")


def test_controlled_fixture_loads() -> None:
    case = load_synthetic_case(TRADEOFF_PATH)

    assert case.projects
    assert case.versions


def test_at_least_two_valid_repair_strategies_exist() -> None:
    case = load_synthetic_case(TRADEOFF_PATH)
    result = solve_weighted_case(case, max_solutions=4)

    assert result.solutions_found >= 2


def test_default_profile_chooses_expected_default_repair() -> None:
    case = load_synthetic_case(TRADEOFF_PATH)
    result = solve_weighted_case(case, weights=get_default_profile().weights, max_solutions=4)

    assert [(action.action_type.value, action.target_mod_id) for action in result.actions] == [
        ("remove_mod", "experiment-suite")
    ]


def test_preservation_profile_chooses_expected_preservation_repair() -> None:
    case = load_synthetic_case(TRADEOFF_PATH)
    result = solve_weighted_case(case, weights=get_preservation_profile().weights, max_solutions=4)

    assert len(result.actions) == 3
    assert all(action.action_type.value == "upgrade_mod" for action in result.actions)


def test_both_final_configurations_pass_checker() -> None:
    case = load_synthetic_case(TRADEOFF_PATH)

    for profile in [get_default_profile(), get_preservation_profile()]:
        result = solve_weighted_case(case, weights=profile.weights, max_solutions=4)
        assert result.repaired_config is not None
        assert evaluate_config(result.repaired_config, case.projects, case.versions).status.value == "compatible"


def test_preservation_profile_preserves_more_original_mods() -> None:
    case = load_synthetic_case(TRADEOFF_PATH)
    default = solve_weighted_case(case, weights=get_default_profile().weights, max_solutions=4)
    preservation = solve_weighted_case(case, weights=get_preservation_profile().weights, max_solutions=4)

    assert preservation.original_mods_preserved > default.original_mods_preserved


def test_results_are_deterministic() -> None:
    case = load_synthetic_case(TRADEOFF_PATH)
    first = solve_weighted_case(case, weights=get_preservation_profile().weights, max_solutions=4)
    second = solve_weighted_case(case, weights=get_preservation_profile().weights, max_solutions=4)

    assert [action.model_dump() for action in first.actions] == [action.model_dump() for action in second.actions]


def test_main_25_case_strict_manifest_remains_unchanged() -> None:
    specs = load_evaluation_manifest(Path("data/evaluation/manifest.json"))

    assert len(specs) == 25
    assert all(spec.case_id != "controlled-preservation-tradeoff" for spec in specs)
