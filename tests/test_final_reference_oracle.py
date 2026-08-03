from modpack_solver.final_dataset.reference_oracle import enumerate_reference_repairs
from modpack_solver.final_dataset.search_stress import build_search_stress_cases


def _case(category):
    return next(item for item in build_search_stress_cases() if item.category == category)


def test_oracle_finds_known_minimum_without_weighted_search():
    definition = _case("candidate_explosion")
    result = enumerate_reference_repairs(definition.case)
    assert result.exhaustive
    assert result.valid_configurations_found > 0
    assert result.minimum_default_cost == 4
    assert result.minimum_preservation_cost == 5


def test_oracle_detects_profile_sensitive_minima():
    definition = _case("profile_sensitive")
    result = enumerate_reference_repairs(definition.case)
    assert result.minimum_default_cost == 10
    assert result.minimum_preservation_cost == 15
    assert result.best_default_actions != result.best_preservation_actions


def test_oracle_proves_controlled_unsatisfiable_core():
    definition = _case("no_solution")
    result = enumerate_reference_repairs(definition.case)
    assert result.exhaustive
    assert result.valid_configurations_found == 0
    assert result.minimum_default_cost is None


def test_oracle_reports_non_exhaustive_bound():
    definition = _case("candidate_explosion")
    result = enumerate_reference_repairs(
        definition.case,
        max_configurations=2,
    )
    assert not result.exhaustive
    assert result.configurations_checked == 2
