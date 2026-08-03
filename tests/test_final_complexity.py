from modpack_solver.final_dataset.complexity import calculate_case_complexity
from modpack_solver.models import (
    Dependency,
    DependencyType,
    MetadataSource,
    ModProject,
    ModVersion,
    ModpackConfig,
    SelectedMod,
    SyntheticCase,
)


def _case(node_count, edges=(), extra_versions=()):
    projects = [
        ModProject(
            mod_id=f"m{index}",
            name=f"Mod {index}",
            source=MetadataSource.SYNTHETIC,
        )
        for index in range(node_count)
    ]
    versions = [
        ModVersion(
            version_id=f"m{index}-v1",
            mod_id=f"m{index}",
            version_number="1.0.0",
            game_versions=["1.20.1"],
            loaders=["fabric"],
        )
        for index in range(node_count)
    ]
    for source, target in edges:
        versions[source].dependencies.append(
            Dependency(
                target_mod_id=f"m{target}",
                dependency_type=DependencyType.REQUIRED,
            )
        )
    for mod_index in extra_versions:
        versions.append(
            ModVersion(
                version_id=f"m{mod_index}-v2",
                mod_id=f"m{mod_index}",
                version_number="2.0.0",
                game_versions=["1.20.1"],
                loaders=["fabric"],
            )
        )
    return SyntheticCase(
        config=ModpackConfig(
            minecraft_version="1.20.1",
            loader="fabric",
            selected_mods=[
                SelectedMod(mod_id=f"m{index}", version_id=f"m{index}-v1")
                for index in range(node_count)
            ],
        ),
        projects=projects,
        versions=versions,
    )


def test_empty_graph_metrics_are_safe():
    metrics = calculate_case_complexity(_case(0))
    assert metrics.selected_mod_count == 0
    assert metrics.connected_component_count == 0
    assert metrics.required_edge_density == 0


def test_direct_dependency_density_and_depth():
    metrics = calculate_case_complexity(_case(2, [(0, 1)]))
    assert metrics.required_edge_count == 1
    assert metrics.required_edge_density == 0.5
    assert metrics.maximum_required_depth == 1


def test_long_chain_tree_and_diamond_depths():
    chain = calculate_case_complexity(_case(4, [(0, 1), (1, 2), (2, 3)]))
    tree = calculate_case_complexity(_case(4, [(0, 1), (0, 2), (1, 3)]))
    diamond = calculate_case_complexity(
        _case(4, [(0, 1), (0, 2), (1, 3), (2, 3)])
    )
    assert chain.maximum_required_depth == 3
    assert tree.maximum_required_depth == 2
    assert tree.maximum_required_branching_factor == 2
    assert diamond.maximum_required_depth == 2


def test_cycle_is_condensed_and_counted_without_looping():
    metrics = calculate_case_complexity(_case(2, [(0, 1), (1, 0)]))
    assert metrics.required_cycle_count == 1
    assert metrics.strongly_connected_component_count == 1
    assert metrics.maximum_required_depth == 0


def test_components_and_candidate_versions_are_counted():
    metrics = calculate_case_complexity(
        _case(4, [(0, 1)], extra_versions=(0, 2))
    )
    assert metrics.connected_component_count == 3
    assert metrics.largest_component_mod_count == 2
    assert metrics.mean_candidate_versions_per_mod == 1.5
    assert metrics.maximum_candidate_versions_per_mod == 2
    assert metrics.mods_with_multiple_candidate_versions == 2


def test_complexity_output_is_deterministic():
    case = _case(5, [(0, 1), (0, 2), (2, 3), (3, 4)])
    assert calculate_case_complexity(case) == calculate_case_complexity(case)
