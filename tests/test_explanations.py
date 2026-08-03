from __future__ import annotations

from pathlib import Path

import networkx as nx

from modpack_solver.graph import (
    GraphBuildResult,
    GraphEdgeType,
    GraphNodeType,
    build_graph_from_synthetic_case,
    project_node_id,
    version_node_id,
)
from modpack_solver.metadata.synthetic import load_synthetic_case
from modpack_solver.models import ModpackConfig, SelectedMod
from modpack_solver.solver import (
    SearchLimits,
    build_explanation_report,
    check_graph,
    explain_issue,
    find_dependency_chain,
    format_compatibility_report,
    format_explanation_report,
    solve_weighted_case,
)


FIXTURE_DIR = Path("data/synthetic")


def test_format_compatibility_report_includes_expected_sections() -> None:
    _, report, _, _ = _analyze_case("missing_required_dependency.json")
    text = format_compatibility_report(report)

    assert "Status:" in text
    assert "Errors:" in text
    assert "Warnings:" in text
    assert "Baseline repair suggestions:" in text


def test_valid_report_formatter_shows_compatible_status_and_no_errors() -> None:
    _, report, _, _ = _analyze_case("valid_modpack.json")
    text = format_compatibility_report(report)

    assert "COMPATIBLE" in text
    assert "Errors:\n  None" in text


def test_missing_dependency_explanation_is_understandable_and_technical() -> None:
    graph_result, report, _, _ = _analyze_case("missing_required_dependency.json")
    explanation = explain_issue(report.issues[0], graph_result)

    assert "missing" in explanation.short_summary.lower()
    assert "Example Library" in explanation.short_summary
    assert "example-machines" in explanation.technical_detail
    assert "example-library" in explanation.technical_detail


def test_minecraft_mismatch_explanation_mentions_selected_version() -> None:
    graph_result, report, _, _ = _analyze_case("minecraft_version_mismatch.json")
    explanation = explain_issue(report.issues[0], graph_result)

    assert "1.20.1" in explanation.short_summary
    assert "1.20.1" in explanation.technical_detail


def test_loader_mismatch_explanation_mentions_selected_loader() -> None:
    graph_result, report, _, _ = _analyze_case("loader_mismatch.json")
    explanation = explain_issue(report.issues[0], graph_result)

    assert "fabric" in explanation.short_summary.lower()
    assert "fabric" in explanation.technical_detail.lower()


def test_hard_conflict_explanation_mentions_both_mods() -> None:
    graph_result, report, _, _ = _analyze_case("hard_conflict.json")
    explanation = explain_issue(report.issues[0], graph_result)

    assert "Example Machines" in explanation.short_summary
    assert "Example Storage" in explanation.short_summary


def test_optional_dependency_explanation_is_non_fatal() -> None:
    graph_result, report, _, _ = _analyze_case("optional_dependency_warning.json")
    explanation = explain_issue(report.issues[0], graph_result)

    assert "warning" in explanation.short_summary.lower()
    assert "non-fatal" in explanation.technical_detail.lower()


def test_embedded_dependency_explanation_says_separate_installation_not_required() -> None:
    graph_result, report, _, _ = _analyze_case("embedded_dependency.json")
    explanation = explain_issue(report.issues[0], graph_result)

    assert "bundled" in explanation.short_summary.lower()
    assert "separate installation is not required" in explanation.technical_detail.lower()


def test_no_solution_explanation_does_not_claim_universal_impossibility() -> None:
    _, _, _, explanation_report = _analyze_case("no_solution.json")
    repair_explanation = explanation_report.repair_explanation

    assert repair_explanation is not None
    assert "available metadata" in repair_explanation.short_summary.lower()
    assert "only describes the current metadata" in repair_explanation.technical_detail.lower()


def test_limit_reached_explanation_says_search_was_incomplete() -> None:
    _, _, _, explanation_report = _analyze_case(
        "multi_repair.json",
        limits=SearchLimits(max_repair_actions=1, max_expanded_states=50, timeout_seconds=10.0),
    )
    repair_explanation = explanation_report.repair_explanation

    assert repair_explanation is not None
    assert "stopped early" in repair_explanation.short_summary.lower()
    assert "incomplete" in repair_explanation.short_summary.lower()


def test_explanation_formatting_contains_stable_headings() -> None:
    _, _, _, explanation_report = _analyze_case("missing_required_dependency.json")
    text = format_explanation_report(explanation_report)

    assert "USER-FRIENDLY SUMMARY" in text
    assert "ROOT CAUSES" in text
    assert "DEPENDENCY CHAINS" in text
    assert "SELECTED REPAIR" in text
    assert "WHY THIS REPAIR WON" in text
    assert "REJECTED ALTERNATIVES" in text
    assert "FINAL STATUS" in text
    assert "TECHNICAL DETAILS" in text


def test_direct_dependency_chain_uses_human_readable_labels() -> None:
    case = load_synthetic_case(FIXTURE_DIR / "missing_required_dependency.json")
    graph_result = build_graph_from_synthetic_case(case)

    chain = find_dependency_chain(graph_result, "example-machines", "example-library")

    assert chain == ["Example Machines", "Example Library"]


def test_two_step_dependency_chain_is_found() -> None:
    case = load_synthetic_case(FIXTURE_DIR / "dependency_chain_missing.json")
    graph_result = build_graph_from_synthetic_case(case)

    chain = find_dependency_chain(graph_result, "example-tech-pack", "example-library")

    assert chain == ["Example Technology Pack", "Example Machines", "Example Library"]


def test_missing_chain_target_falls_back_to_direct_labels() -> None:
    case = load_synthetic_case(FIXTURE_DIR / "missing_required_dependency.json")
    graph_result = build_graph_from_synthetic_case(case)

    chain = find_dependency_chain(graph_result, "example-machines", "ghost-mod")

    assert chain == ["Example Machines", "ghost-mod"]


def test_dependency_chain_cycle_protection_is_deterministic() -> None:
    graph_result = _build_cyclic_graph_result()

    first = find_dependency_chain(graph_result, "mod-a", "mod-b")
    second = find_dependency_chain(graph_result, "mod-a", "mod-b")

    assert first == ["Mod A", "Mod B"]
    assert first == second


def test_dependency_chain_respects_max_depth() -> None:
    case = load_synthetic_case(FIXTURE_DIR / "dependency_chain_missing.json")
    graph_result = build_graph_from_synthetic_case(case)

    chain = find_dependency_chain(graph_result, "example-tech-pack", "example-library", max_depth=1)

    assert chain == ["Example Technology Pack", "Example Library"]


def test_selected_repair_explanation_includes_actions_cost_and_preservation() -> None:
    _, _, solver_result, explanation_report = _analyze_case("missing_required_dependency.json")
    repair_explanation = explanation_report.repair_explanation

    assert repair_explanation is not None
    assert repair_explanation.selected_actions == solver_result.actions
    assert repair_explanation.total_cost == 1
    assert repair_explanation.original_mods_preserved == 1


def test_equal_cost_alternative_uses_tie_breaking_reason() -> None:
    _, _, _, explanation_report = _analyze_case("tie_breaking.json")
    repair_explanation = explanation_report.repair_explanation

    assert repair_explanation is not None
    assert repair_explanation.alternatives
    assert "deterministic tie-breaking" in repair_explanation.alternatives[0].reason.lower()


def test_higher_cost_alternative_reason_mentions_cost_difference() -> None:
    _, _, _, explanation_report = _analyze_case("version_choice.json")
    repair_explanation = explanation_report.repair_explanation

    assert repair_explanation is not None
    assert repair_explanation.alternatives
    assert "weighted cost" in repair_explanation.alternatives[0].reason.lower()


def test_no_alternatives_are_handled_cleanly() -> None:
    _, _, _, explanation_report = _analyze_case("multi_repair.json")
    text = format_explanation_report(explanation_report)

    assert "No additional valid repair plans were returned by the current search." in text


def test_up_to_three_alternatives_are_shown() -> None:
    _, _, _, explanation_report = _analyze_case("tie_breaking.json")
    repair_explanation = explanation_report.repair_explanation

    assert repair_explanation is not None
    assert len(repair_explanation.alternatives) == 3


def test_already_compatible_case_says_no_repair_was_needed() -> None:
    _, _, _, explanation_report = _analyze_case("valid_modpack.json")
    repair_explanation = explanation_report.repair_explanation

    assert repair_explanation is not None
    assert "no repair was needed" in repair_explanation.short_summary.lower()


def _analyze_case(fixture_name: str, limits: SearchLimits | None = None):
    case = load_synthetic_case(FIXTURE_DIR / fixture_name)
    graph_result = build_graph_from_synthetic_case(case)
    report = check_graph(graph_result)
    solver_result = solve_weighted_case(case, limits=limits, max_solutions=4)
    explanation_report = build_explanation_report(
        case=case,
        graph_result=graph_result,
        initial_report=report,
        solver_result=solver_result,
        max_alternatives=3,
    )
    return graph_result, report, solver_result, explanation_report


def _build_cyclic_graph_result() -> GraphBuildResult:
    graph = nx.DiGraph()
    graph.add_node(project_node_id("mod-a"), node_type=GraphNodeType.PROJECT.value, mod_id="mod-a", label="Mod A")
    graph.add_node(project_node_id("mod-b"), node_type=GraphNodeType.PROJECT.value, mod_id="mod-b", label="Mod B")
    graph.add_node(version_node_id("mod-a-1"), node_type=GraphNodeType.VERSION.value, mod_id="mod-a", label="mod-a@1.0.0")
    graph.add_node(version_node_id("mod-b-1"), node_type=GraphNodeType.VERSION.value, mod_id="mod-b", label="mod-b@1.0.0")
    graph.add_edge(version_node_id("mod-a-1"), project_node_id("mod-b"), edge_type=GraphEdgeType.REQUIRES.value)
    graph.add_edge(version_node_id("mod-b-1"), project_node_id("mod-a"), edge_type=GraphEdgeType.REQUIRES.value)

    return GraphBuildResult(
        graph=graph,
        project_nodes={"mod-a": project_node_id("mod-a"), "mod-b": project_node_id("mod-b")},
        version_nodes={"mod-a-1": version_node_id("mod-a-1"), "mod-b-1": version_node_id("mod-b-1")},
        selected_version_nodes={"mod-a": version_node_id("mod-a-1"), "mod-b": version_node_id("mod-b-1")},
        config=ModpackConfig(
            minecraft_version="1.20.1",
            loader="fabric",
            selected_mods=[
                SelectedMod(mod_id="mod-a", version_id="mod-a-1"),
                SelectedMod(mod_id="mod-b", version_id="mod-b-1"),
            ],
        ),
    )
