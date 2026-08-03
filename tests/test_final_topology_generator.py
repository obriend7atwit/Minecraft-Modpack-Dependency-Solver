import pytest

from modpack_solver.final_dataset.complexity import calculate_case_complexity
from modpack_solver.final_dataset.sizing import PackSizeCategory, classify_pack_size
from modpack_solver.final_dataset.stress_generator import (
    StressCaseConfig,
    build_valid_stress_case,
)
from modpack_solver.final_dataset.topology import DependencyTopology
from modpack_solver.solver.checker import IssueSeverity, check_synthetic_case


def _config(topology, seed=42):
    return StressCaseConfig(
        case_id=f"test-{topology.value}",
        selected_mod_count=30,
        topology=topology,
        target_required_edge_count=45,
        target_maximum_depth=5,
        target_branching_factor=3,
        candidate_versions_per_choice_mod=4,
        choice_mod_fraction=0.2,
        optional_edge_fraction=0.1,
        seed=seed,
    )


@pytest.mark.parametrize(
    "topology",
    [
        DependencyTopology.CHAIN,
        DependencyTopology.LAYERED_DAG,
        DependencyTopology.SHARED_LIBRARY_FAN_IN,
        DependencyTopology.CLUSTERED_MODULES,
    ],
)
def test_generated_controls_are_dense_valid_and_hit_targets(topology):
    case = build_valid_stress_case(_config(topology))
    metrics = calculate_case_complexity(case)
    report = check_synthetic_case(case)
    assert len(case.config.selected_mods) == 30
    assert metrics.required_edge_count == 45
    assert metrics.maximum_required_depth == 5
    assert not [issue for issue in report.issues if issue.severity == IssueSeverity.ERROR]


def test_generation_is_deterministic_by_seed():
    first = build_valid_stress_case(_config(DependencyTopology.LAYERED_DAG))
    second = build_valid_stress_case(_config(DependencyTopology.LAYERED_DAG))
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_candidate_versions_and_size_boundaries_are_preserved():
    case = build_valid_stress_case(_config(DependencyTopology.CHAIN))
    metrics = calculate_case_complexity(case)
    assert metrics.maximum_candidate_versions_per_mod == 4
    assert metrics.mods_with_multiple_candidate_versions == 6
    assert classify_pack_size(30) == PackSizeCategory.SMALL
    assert classify_pack_size(80) == PackSizeCategory.MEDIUM
    assert classify_pack_size(150) == PackSizeCategory.LARGE
    assert classify_pack_size(220) == PackSizeCategory.HUGE
