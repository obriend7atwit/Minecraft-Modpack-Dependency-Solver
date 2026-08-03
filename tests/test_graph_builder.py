from __future__ import annotations

from pathlib import Path

from modpack_solver.graph import (
    GraphEdgeType,
    build_graph_from_synthetic_case,
    summarize_graph,
)
from modpack_solver.metadata.synthetic import load_synthetic_case


FIXTURE_DIR = Path("data/synthetic")
FIXTURE_NAMES = [
    "valid_modpack.json",
    "missing_required_dependency.json",
    "minecraft_version_mismatch.json",
    "loader_mismatch.json",
    "hard_conflict.json",
    "optional_dependency_warning.json",
    "embedded_dependency.json",
]


def _load_result(fixture_name: str):
    case = load_synthetic_case(FIXTURE_DIR / fixture_name)
    return build_graph_from_synthetic_case(case)


def test_valid_modpack_graph_builds_successfully() -> None:
    result = _load_result("valid_modpack.json")

    assert result.graph.number_of_nodes() > 0
    assert result.graph.number_of_edges() > 0
    assert result.selected_version_nodes
    assert not result.unresolved_dependencies


def test_all_week4_synthetic_fixtures_build_successfully() -> None:
    for fixture_name in FIXTURE_NAMES:
        result = _load_result(fixture_name)
        assert result.graph.number_of_nodes() > 0
        assert result.graph.number_of_edges() > 0


def test_required_dependency_edge_exists() -> None:
    result = _load_result("valid_modpack.json")

    assert any(
        data.get("edge_type") == GraphEdgeType.REQUIRES.value
        for _, _, data in result.graph.edges(data=True)
    )


def test_missing_required_dependency_is_recorded_as_structural_warning() -> None:
    result = _load_result("missing_required_dependency.json")

    assert (
        result.unresolved_dependencies
        or any("requires project" in warning.lower() or "required dependency" in warning.lower() for warning in result.warnings)
    )


def test_optional_dependency_edge_exists() -> None:
    result = _load_result("optional_dependency_warning.json")

    assert any(
        data.get("edge_type") == GraphEdgeType.OPTIONAL.value
        for _, _, data in result.graph.edges(data=True)
    )


def test_incompatible_edge_exists() -> None:
    result = _load_result("hard_conflict.json")

    assert any(
        data.get("edge_type") == GraphEdgeType.INCOMPATIBLE.value
        for _, _, data in result.graph.edges(data=True)
    )


def test_embedded_edge_exists() -> None:
    result = _load_result("embedded_dependency.json")

    assert any(
        data.get("edge_type") == GraphEdgeType.EMBEDDED.value
        for _, _, data in result.graph.edges(data=True)
    )


def test_minecraft_support_edges_exist() -> None:
    result = _load_result("valid_modpack.json")

    assert any(
        data.get("edge_type") == GraphEdgeType.SUPPORTS_MINECRAFT.value
        for _, _, data in result.graph.edges(data=True)
    )


def test_loader_support_edges_exist() -> None:
    result = _load_result("valid_modpack.json")

    assert any(
        data.get("edge_type") == GraphEdgeType.SUPPORTS_LOADER.value
        for _, _, data in result.graph.edges(data=True)
    )


def test_graph_summary_returns_useful_text() -> None:
    result = _load_result("hard_conflict.json")
    summary = summarize_graph(result)

    assert "Nodes:" in summary
    assert "Edges:" in summary
    assert "Selected" in summary
    assert "requires" in summary.lower() or "incompatible" in summary.lower()


def test_valid_modpack_has_minimum_expected_node_and_edge_counts() -> None:
    result = _load_result("valid_modpack.json")

    assert result.graph.number_of_nodes() >= 6
    assert result.graph.number_of_edges() >= 6
