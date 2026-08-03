"""Deterministic supplementary cases for bounded search-state scaling."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from modpack_solver.analysis import RuntimeMeasurements, get_default_profile, measure_runtime
from modpack_solver.final_dataset.export import write_pretty_json
from modpack_solver.final_dataset.models import GroundTruthMethod
from modpack_solver.final_dataset.repair_trace import replay_repair_plan
from modpack_solver.metadata.synthetic import load_synthetic_case
from modpack_solver.models import (
    Dependency,
    DependencyType,
    MetadataSource,
    ModProject,
    ModVersion,
    ModpackConfig,
    RepairAction,
    RepairActionType,
    SelectedMod,
    SyntheticCase,
)
from modpack_solver.solver import SearchLimits, SolverStatus, solve_weighted_case
from modpack_solver.solver.costs import RepairWeights, action_cost


class SearchScalingBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchScalingCaseSpec(SearchScalingBaseModel):
    case_id: str
    display_name: str
    fixture_path: str
    decision_mod_count: int = Field(ge=1)
    compatible_alternatives_per_mod: int = Field(ge=1)
    includes_dependency_conflict_trap: bool = False
    target_min_states: int = Field(ge=1)
    target_max_states: int = Field(ge=1)
    search_limits: SearchLimits
    expected_solution_status: SolverStatus
    expected_limit_reached: bool = False
    ground_truth_method: GroundTruthMethod
    known_valid_repair: list[RepairAction] = Field(default_factory=list)
    known_minimum_cost: int | None = Field(default=None, ge=0)
    generation_notes: str

    @model_validator(mode="after")
    def validate_target(self) -> "SearchScalingCaseSpec":
        if self.target_max_states < self.target_min_states:
            raise ValueError("target_max_states must be at least target_min_states.")
        return self


class SearchScalingManifest(SearchScalingBaseModel):
    dataset_name: str
    dataset_version: str
    description: str
    cases: list[SearchScalingCaseSpec]


class SearchScalingResult(SearchScalingBaseModel):
    case_id: str
    expected_solution_status: SolverStatus
    observed_status: SolverStatus
    final_compatible: bool
    known_repair_compatible: bool
    known_minimum_cost: int | None = None
    observed_cost: int | None = None
    action_count: int
    states_expanded: int
    target_min_states: int
    target_max_states: int
    target_range_met: bool
    search_limit: int
    limit_reached: bool
    median_runtime_seconds: float
    minimum_runtime_seconds: float
    maximum_runtime_seconds: float
    runtime_samples_seconds: list[float] = Field(default_factory=list)
    ground_truth_method: GroundTruthMethod
    optimal_plan_agreement: bool | None = None
    outcome_correct: bool


class SearchScalingRun(SearchScalingBaseModel):
    manifest_path: str
    runtime_repetitions: int
    results: list[SearchScalingResult]
    all_outcomes_correct: bool
    all_target_ranges_met: bool
    note: str


CASE_CONFIGS = (
    {
        "case_id": "search-scale-01-moderate",
        "display_name": "Moderate candidate product",
        "decision_mod_count": 5,
        "alternatives": 1,
        "trap": False,
        "target": (25, 60),
        "max_states": 2000,
        "expected_limit": False,
    },
    {
        "case_id": "search-scale-02-intermediate",
        "display_name": "Intermediate candidate product",
        "decision_mod_count": 7,
        "alternatives": 1,
        "trap": False,
        "target": (70, 150),
        "max_states": 2000,
        "expected_limit": False,
    },
    {
        "case_id": "search-scale-03-deep-interaction",
        "display_name": "Deep equal-cost candidate interaction",
        "decision_mod_count": 5,
        "alternatives": 2,
        "trap": False,
        "target": (175, 350),
        "max_states": 2000,
        "expected_limit": False,
    },
    {
        "case_id": "search-scale-04-high-bounded",
        "display_name": "High bounded candidate interaction",
        "decision_mod_count": 6,
        "alternatives": 2,
        "trap": False,
        "target": (350, 650),
        "max_states": 500,
        "expected_limit": True,
    },
    {
        "case_id": "search-scale-05-extreme-bounded",
        "display_name": "Extreme bounded interaction with dependency trap",
        "decision_mod_count": 5,
        "alternatives": 3,
        "trap": True,
        "target": (650, 850),
        "max_states": 750,
        "expected_limit": True,
    },
)


def generate_search_scaling_dataset(
    output_root: str | Path = "data/final_dataset",
) -> SearchScalingManifest:
    """Write five cases without invoking the weighted solver under evaluation."""

    root = Path(output_root)
    fixture_dir = root / "search_scaling"
    specs = []
    for config in CASE_CONFIGS:
        case, repair = _build_candidate_product_case(
            config["case_id"],
            decision_mod_count=config["decision_mod_count"],
            alternatives=config["alternatives"],
            include_trap=config["trap"],
        )
        trace = replay_repair_plan(case, repair)
        if not trace.final_compatible:
            raise ValueError(
                f"Known inverse repair for '{config['case_id']}' is not compatible."
            )
        fixture_path = fixture_dir / f"{config['case_id']}.json"
        write_pretty_json(fixture_path, case)
        limits = SearchLimits(
            max_repair_actions=config["decision_mod_count"],
            max_expanded_states=config["max_states"],
            timeout_seconds=30.0,
        )
        specs.append(
            SearchScalingCaseSpec(
                case_id=config["case_id"],
                display_name=config["display_name"],
                fixture_path=fixture_path.relative_to(root).as_posix(),
                decision_mod_count=config["decision_mod_count"],
                compatible_alternatives_per_mod=config["alternatives"],
                includes_dependency_conflict_trap=config["trap"],
                target_min_states=config["target"][0],
                target_max_states=config["target"][1],
                search_limits=limits,
                expected_solution_status=SolverStatus.SOLUTION_FOUND,
                expected_limit_reached=config["expected_limit"],
                ground_truth_method=GroundTruthMethod.INVERSE_INJECTION,
                known_valid_repair=repair,
                generation_notes=(
                    "Selected incompatible versions were substituted for known compatible "
                    "versions. The stored inverse upgrades restore compatibility. State "
                    "targets describe observed search effort, not expected-answer creation."
                ),
            )
        )
    manifest = SearchScalingManifest(
        dataset_name="Controlled Search Scaling Supplement",
        dataset_version="1.0.0",
        description=(
            "Five deterministic candidate-product cases kept separate from the main "
            "evaluation corpus. They measure bounded search-state growth and are not "
            "complete official modpacks."
        ),
        cases=specs,
    )
    write_pretty_json(root / "search_scaling_manifest.json", manifest)
    return manifest


def load_search_scaling_manifest(
    path: str | Path = "data/final_dataset/search_scaling_manifest.json",
) -> SearchScalingManifest:
    return SearchScalingManifest.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def run_search_scaling_experiment(
    *,
    manifest_path: str | Path = "data/final_dataset/search_scaling_manifest.json",
    output_dir: str | Path = "results/final/search_scaling",
    runtime_repetitions: int = 3,
    offline: bool = True,
) -> SearchScalingRun:
    """Measure solver-only runtime with one warm-up and repeated timed runs."""

    if not offline:
        raise ValueError("Search scaling is intentionally offline.")
    manifest_file = Path(manifest_path)
    if not manifest_file.exists():
        generate_search_scaling_dataset(manifest_file.parent)
    manifest = load_search_scaling_manifest(manifest_file)
    results = []
    for spec in manifest.cases:
        fixture = manifest_file.parent / spec.fixture_path
        case = load_synthetic_case(fixture)
        known_trace = replay_repair_plan(case, spec.known_valid_repair)
        operation = lambda: solve_weighted_case(
            case,
            weights=get_default_profile().weights,
            limits=spec.search_limits,
            max_solutions=1,
        )
        solver, timing = measure_runtime(
            operation,
            repetitions=runtime_repetitions,
            warmup_runs=1,
        )
        final_report = solver.final_report or solver.best_partial_report
        final_compatible = bool(
            final_report
            and not any(issue.severity == "error" for issue in final_report.issues)
        )
        target_met = (
            spec.target_min_states
            <= solver.states_expanded
            <= spec.target_max_states
        )
        outcome_correct = (
            solver.status == SolverStatus.LIMIT_REACHED and solver.limit_reached
            if spec.expected_limit_reached
            else solver.status == spec.expected_solution_status and final_compatible
        )
        results.append(
            SearchScalingResult(
                case_id=spec.case_id,
                expected_solution_status=spec.expected_solution_status,
                observed_status=solver.status,
                final_compatible=final_compatible,
                known_repair_compatible=known_trace.final_compatible,
                known_minimum_cost=spec.known_minimum_cost,
                observed_cost=solver.total_cost,
                action_count=len(solver.actions),
                states_expanded=solver.states_expanded,
                target_min_states=spec.target_min_states,
                target_max_states=spec.target_max_states,
                target_range_met=target_met,
                search_limit=spec.search_limits.max_expanded_states,
                limit_reached=solver.limit_reached,
                median_runtime_seconds=timing.median_seconds,
                minimum_runtime_seconds=timing.minimum_seconds,
                maximum_runtime_seconds=timing.maximum_seconds,
                runtime_samples_seconds=timing.samples_seconds,
                ground_truth_method=spec.ground_truth_method,
                optimal_plan_agreement=(
                    solver.total_cost == spec.known_minimum_cost
                    if spec.known_minimum_cost is not None and solver.total_cost is not None
                    else None
                ),
                outcome_correct=outcome_correct and known_trace.final_compatible,
            )
        )
    run = SearchScalingRun(
        manifest_path=str(manifest_file),
        runtime_repetitions=runtime_repetitions,
        results=results,
        all_outcomes_correct=all(item.outcome_correct for item in results),
        all_target_ranges_met=all(item.target_range_met for item in results),
        note=(
            "This supplementary controlled experiment measures search-state growth. "
            "It is separate from the main corpus and does not represent complete "
            "official modpacks."
        ),
    )
    _write_search_scaling_outputs(run, output_dir)
    return run


def _build_candidate_product_case(
    case_id: str,
    *,
    decision_mod_count: int,
    alternatives: int,
    include_trap: bool,
) -> tuple[SyntheticCase, list[RepairAction]]:
    projects: list[ModProject] = []
    versions: list[ModVersion] = []
    selected: list[ModVersion] = []
    repair: list[RepairAction] = []

    anchor_id = f"{case_id}-anchor"
    helper_id = f"{case_id}-helper"
    transitive_id = f"{case_id}-transitive"
    if include_trap:
        projects.extend(_project(mod_id) for mod_id in (anchor_id, helper_id, transitive_id))
        anchor = _version(anchor_id, "1.0.0", "selected")
        helper = _version(
            helper_id,
            "1.0.0",
            "missing",
            dependencies=[_dependency(transitive_id, DependencyType.REQUIRED)],
        )
        transitive = _version(transitive_id, "1.0.0", "missing")
        versions.extend([anchor, helper, transitive])
        selected.append(anchor)

    for index in range(decision_mod_count):
        mod_id = f"{case_id}-decision-{index:02d}"
        projects.append(_project(mod_id))
        bad = _version(
            mod_id,
            "1.0.0",
            "injected-bad",
            game_versions=["1.19.4"],
        )
        versions.append(bad)
        selected.append(bad)
        clean = _version(mod_id, "2.0.0", "clean-a")
        versions.append(clean)
        action = RepairAction(
            action_type=RepairActionType.UPGRADE_MOD,
            target_mod_id=mod_id,
            target_version_id=clean.version_id,
            target_version_number=clean.version_number,
            reason="Restore the independently constructed compatible version.",
        )
        action.cost = action_cost(action, RepairWeights())
        repair.append(action)
        for alternative_index in range(1, alternatives):
            dependencies = []
            if include_trap and alternative_index == alternatives - 1:
                dependencies = [
                    _dependency(helper_id, DependencyType.REQUIRED),
                    _dependency(anchor_id, DependencyType.INCOMPATIBLE),
                ]
            versions.append(
                _version(
                    mod_id,
                    f"{alternative_index + 2}.0.0",
                    f"alternative-{alternative_index}",
                    dependencies=dependencies,
                )
            )

    case = SyntheticCase(
        config=ModpackConfig(
            minecraft_version="1.20.1",
            loader="fabric",
            selected_mods=[
                SelectedMod(
                    mod_id=version.mod_id,
                    version_id=version.version_id,
                    version_number=version.version_number,
                )
                for version in selected
            ],
        ),
        projects=projects,
        versions=versions,
    )
    return case, repair


def _project(mod_id: str) -> ModProject:
    return ModProject(
        mod_id=mod_id,
        name=mod_id.replace("-", " ").title(),
        slug=mod_id,
        source=MetadataSource.SYNTHETIC,
    )


def _version(
    mod_id: str,
    version_number: str,
    suffix: str,
    *,
    game_versions: list[str] | None = None,
    dependencies: list[Dependency] | None = None,
) -> ModVersion:
    return ModVersion(
        version_id=f"{mod_id}-{suffix}",
        mod_id=mod_id,
        version_number=version_number,
        game_versions=game_versions or ["1.20.1"],
        loaders=["fabric"],
        dependencies=dependencies or [],
    )


def _dependency(target_mod_id: str, kind: DependencyType) -> Dependency:
    return Dependency(
        target_mod_id=target_mod_id,
        dependency_type=kind,
        source=MetadataSource.SYNTHETIC,
    )


def _write_search_scaling_outputs(
    run: SearchScalingRun,
    output_dir: str | Path,
) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    write_pretty_json(output / "search_scaling_results.json", run)
    rows = [
        {
            "case_id": item.case_id,
            "expected_status": item.expected_solution_status.value,
            "observed_status": item.observed_status.value,
            "final_compatible": item.final_compatible,
            "known_repair_compatible": item.known_repair_compatible,
            "observed_cost": item.observed_cost if item.observed_cost is not None else "N/A",
            "actions": item.action_count,
            "states_expanded": item.states_expanded,
            "target_range": f"{item.target_min_states}-{item.target_max_states}",
            "search_limit": item.search_limit,
            "limit_reached": item.limit_reached,
            "median_runtime_ms": f"{item.median_runtime_seconds * 1000:.3f}",
            "minimum_runtime_ms": f"{item.minimum_runtime_seconds * 1000:.3f}",
            "maximum_runtime_ms": f"{item.maximum_runtime_seconds * 1000:.3f}",
            "ground_truth": item.ground_truth_method.value,
            "outcome_correct": item.outcome_correct,
        }
        for item in run.results
    ]
    _write_csv(output / "search_scaling_results.csv", rows)
    _write_latex(output / "search_scaling_table.tex", rows)
    _write_summary(output / "search_scaling_summary.md", run, rows)


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_latex(path: Path, rows: list[dict]) -> None:
    lines = [
        r"\begin{tabularx}{\columnwidth}{lrrrr}",
        r"\hline",
        r"Case & Status & States & Limit & Median ms \\",
        r"\hline",
    ]
    for row in rows:
        lines.append(
            f"{_latex(row['case_id'])} & {_latex(row['observed_status'])} & "
            f"{row['states_expanded']} & {row['search_limit']} & "
            f"{row['median_runtime_ms']} \\\\"
        )
    lines.extend([r"\hline", r"\end{tabularx}"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_summary(path: Path, run: SearchScalingRun, rows: list[dict]) -> None:
    lines = [
        "# Search Scaling Supplement",
        "",
        run.note,
        "",
        f"One unmeasured warm-up preceded {run.runtime_repetitions} measured solver-only repetitions. "
        "Runtime uses `time.perf_counter()` and reports the median with retained minima and maxima.",
        "",
        "| Case | Observed status | States | Target | Median ms | Correct |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    lines.extend(
        f"| {row['case_id']} | {row['observed_status']} | {row['states_expanded']} | "
        f"{row['target_range']} | {row['median_runtime_ms']} | {row['outcome_correct']} |"
        for row in rows
    )
    lines.extend(
        [
            "",
            "Limit-reached cases retain independently replayed valid repairs; reaching a configured "
            "bound is not evidence that no valid repair exists. These controlled cases do not establish "
            "real-world launcher scalability.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _latex(value: object) -> str:
    return str(value).replace("_", r"\_").replace("%", r"\%")
