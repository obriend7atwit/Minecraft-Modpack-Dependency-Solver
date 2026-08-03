from modpack_solver.final_dataset.cascading import build_cascading_cases
from modpack_solver.models import IssueType
from modpack_solver.solver import SolverStatus, solve_weighted_case


def _definitions():
    return {item.case_id: item for item in build_cascading_cases()}


def test_all_twelve_cascading_cases_are_present_and_stable():
    definitions = build_cascading_cases()
    assert len(definitions) == 12
    assert len({item.case_id for item in definitions}) == 12


def test_missing_chain_reveals_each_dependency_and_solver_finds_three_steps():
    definition = _definitions()["cascade-01-missing-chain"]
    assert definition.trace.final_compatible
    assert len(definition.trace.steps) == 3
    assert definition.trace.steps[0].issue_types_before == [
        IssueType.MISSING_DEPENDENCY
    ]
    assert definition.trace.steps[-1].issue_types_after == []
    result = solve_weighted_case(definition.case)
    assert result.status == SolverStatus.SOLUTION_FOUND
    assert len(result.actions) == 3


def test_cycle_case_does_not_loop_and_known_repair_succeeds():
    definition = _definitions()["cascade-08-cycle"]
    assert definition.trace.final_compatible
    assert len(definition.trace.steps) == 1


def test_multi_error_case_requires_at_least_four_actions_without_mutation():
    definition = _definitions()["cascade-12-multi-error"]
    original = definition.case.model_dump(mode="json")
    result = solve_weighted_case(definition.case)
    assert len(result.actions) >= 4
    assert result.status == SolverStatus.SOLUTION_FOUND
    assert definition.case.model_dump(mode="json") == original


def test_cascading_no_solution_is_reported():
    definition = _definitions()["cascade-11-no-solution"]
    result = solve_weighted_case(definition.case)
    assert definition.expected_solver_status == SolverStatus.NO_SOLUTION
    assert result.status == SolverStatus.NO_SOLUTION
