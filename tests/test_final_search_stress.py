import pytest

from modpack_solver.final_dataset.search_stress import (
    build_bounded_extreme_case,
    build_search_stress_cases,
)
from modpack_solver.solver import SearchLimits, SolverStatus, solve_weighted_case


def test_all_search_stress_cases_expand_multiple_states():
    definitions = build_search_stress_cases()
    assert len(definitions) == 16
    for definition in definitions:
        result = solve_weighted_case(definition.case, max_solutions=4)
        assert result.states_expanded > 2


def test_tie_breaking_is_deterministic():
    definition = next(
        item for item in build_search_stress_cases() if item.category == "tie_breaking"
    )
    first = solve_weighted_case(definition.case, max_solutions=4)
    second = solve_weighted_case(definition.case, max_solutions=4)
    assert first.actions == second.actions


@pytest.mark.stress
def test_bounded_extreme_search_hits_explicit_state_limit():
    result = solve_weighted_case(
        build_bounded_extreme_case(),
        limits=SearchLimits(
            max_repair_actions=6,
            max_expanded_states=750,
            timeout_seconds=20,
        ),
    )
    assert result.status == SolverStatus.LIMIT_REACHED
    assert result.states_expanded == 750
