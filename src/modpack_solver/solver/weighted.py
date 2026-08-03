"""Public entry points for the weighted minimal-change repair solver."""

from __future__ import annotations

from modpack_solver.models import ModpackConfig, ModProject, ModVersion, SyntheticCase
from modpack_solver.solver.common import SearchLimits, SolverComparison, SolverResult
from modpack_solver.solver.costs import RepairWeights, plan_cost
from modpack_solver.solver.search import search_weighted_repairs
from modpack_solver.solver.state import (
    count_original_mods_preserved,
    count_removed_original_mods,
    count_version_changes,
)


def solve_weighted(
    config: ModpackConfig,
    projects: list[ModProject],
    versions: list[ModVersion],
    weights: RepairWeights | None = None,
    limits: SearchLimits | None = None,
    max_solutions: int = 1,
) -> SolverResult:
    """Search for a low-cost valid repair for the supplied configuration."""

    if max_solutions < 1:
        raise ValueError("max_solutions must be at least 1.")

    resolved_weights = weights or RepairWeights()
    resolved_limits = limits or SearchLimits()
    return search_weighted_repairs(
        initial_config=config.model_copy(deep=True),
        projects=[project.model_copy(deep=True) for project in projects],
        versions=[version.model_copy(deep=True) for version in versions],
        weights=resolved_weights,
        limits=resolved_limits,
        max_solutions=max_solutions,
    )


def solve_weighted_case(
    case: SyntheticCase,
    weights: RepairWeights | None = None,
    limits: SearchLimits | None = None,
    max_solutions: int = 1,
) -> SolverResult:
    """Run the weighted solver for a synthetic fixture case."""

    return solve_weighted(
        config=case.config.model_copy(deep=True),
        projects=[project.model_copy(deep=True) for project in case.projects],
        versions=[version.model_copy(deep=True) for version in case.versions],
        weights=weights,
        limits=limits,
        max_solutions=max_solutions,
    )


def compare_baseline_and_weighted(
    case: SyntheticCase,
    weights: RepairWeights | None = None,
    limits: SearchLimits | None = None,
) -> SolverComparison:
    """Compare baseline repair suggestions with the weighted solver result."""

    resolved_weights = weights or RepairWeights()
    from modpack_solver.solver.common import evaluate_config

    initial_report = evaluate_config(case.config, case.projects, case.versions)
    result = solve_weighted_case(case=case, weights=resolved_weights, limits=limits)
    baseline_actions = list(initial_report.repair_actions)

    reference_config = result.repaired_config or result.best_partial_config or case.config
    return SolverComparison(
        baseline_actions=baseline_actions,
        baseline_action_count=len(baseline_actions),
        baseline_estimated_cost=plan_cost(baseline_actions, resolved_weights) if baseline_actions else 0,
        weighted_status=result.status,
        weighted_actions=list(result.actions),
        weighted_action_count=len(result.actions),
        weighted_cost=result.total_cost,
        original_mods_preserved=count_original_mods_preserved(case.config, reference_config),
        removed_mods=count_removed_original_mods(case.config, reference_config),
        runtime_seconds=result.runtime_seconds,
    )


class WeightedSolver:
    """Backward-compatible wrapper around the functional weighted solver API."""

    def __init__(
        self,
        *,
        weights: RepairWeights | None = None,
        limits: SearchLimits | None = None,
        max_solutions: int = 1,
    ) -> None:
        self.weights = weights or RepairWeights()
        self.limits = limits or SearchLimits()
        self.max_solutions = max_solutions

    def solve(
        self,
        config: ModpackConfig,
        projects: list[ModProject],
        versions: list[ModVersion],
    ) -> SolverResult:
        return solve_weighted(
            config=config,
            projects=projects,
            versions=versions,
            weights=self.weights,
            limits=self.limits,
            max_solutions=self.max_solutions,
        )
