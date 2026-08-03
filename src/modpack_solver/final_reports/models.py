"""Structured final evaluation and report models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from modpack_solver.final_dataset.models import (
    FinalCaseSourceType,
    FinalDatasetValidationResult,
    GroundTruthMethod,
    ModificationType,
)
from modpack_solver.final_dataset.sizing import PackSizeCategory
from modpack_solver.models import IssueType, RepairActionType
from modpack_solver.solver.checker import CompatibilityStatus
from modpack_solver.solver.common import SolverStatus


class FinalReportBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FinalEvaluationSystem(str, Enum):
    BASELINE = "baseline"
    WEIGHTED_DEFAULT = "weighted_default"
    WEIGHTED_PRESERVATION = "weighted_preservation"


class FinalCaseEvaluation(FinalReportBaseModel):
    case_id: str
    display_name: str
    system: FinalEvaluationSystem
    profile_id: str | None = None
    source_type: FinalCaseSourceType
    source_family_id: str = ""
    source_pack_slug: str | None = None
    collection_method: str | None = None
    ground_truth_method: GroundTruthMethod = GroundTruthMethod.ORIGINAL_CONTROL
    review_status: str = "generated"
    modification_type: ModificationType
    topology: str | None = None
    is_cascading: bool = False
    pack_size_category: PackSizeCategory
    selected_mod_count: int
    dependency_edge_count: int
    required_edge_count: int = 0
    total_dependency_edge_count: int = 0
    required_edge_density: float = 0.0
    maximum_required_depth: int = 0
    mean_required_branching_factor: float = 0.0
    mean_candidate_versions_per_mod: float = 0.0
    maximum_candidate_versions_per_mod: int = 0
    metadata_coverage_rate: float | None = None
    expected_repairable: bool
    expected_repair_action_count: int | None = None
    known_minimum_default_cost: int | None = None
    known_minimum_preservation_cost: int | None = None
    minimum_cost_verified: bool = False
    expected_initial_status: CompatibilityStatus
    expected_solver_status: SolverStatus
    initial_status: CompatibilityStatus
    solver_status: SolverStatus
    issue_types: list[IssueType] = Field(default_factory=list)
    action_types: list[RepairActionType] = Field(default_factory=list)
    action_count: int = 0
    final_compatible: bool = False
    repair_success: bool = False
    total_cost: int | None = None
    original_mod_count: int = 0
    original_mods_preserved: int = 0
    preservation_rate: float = 0.0
    removed_mod_count: int = 0
    version_change_count: int = 0
    runtime_seconds: float = 0.0
    runtime_samples_seconds: list[float] = Field(default_factory=list)
    runtime_minimum_seconds: float = 0.0
    runtime_maximum_seconds: float = 0.0
    states_expanded: int = 0
    repair_depth: int = 0
    issue_count_temporarily_increased: bool = False
    issue_type_changed_after_action: bool = False
    cascading_step_explanation_correct: bool | None = None
    dependency_chain_explanation_correct: bool | None = None
    global_plan_reason_correct: bool | None = None
    optimal_plan_agreement: bool | None = None
    no_solution_correct: bool | None = None
    suggestion_count: int = 0
    executable_suggestion_count: int = 0
    explanation_complete: bool = False
    issue_detection_correct: bool = False
    passed: bool = False
    failure_category: str | None = None
    failure_detail: str | None = None


class FinalSystemMetrics(FinalReportBaseModel):
    system: FinalEvaluationSystem
    total_cases: int
    repairable_cases: int
    successful_repairs: int
    repair_success_rate: float
    average_preservation_rate: float
    full_preservation_repairs: int = 0
    full_preservation_rate: float = 0.0
    preserved_mod_fraction_all_expected_repairs: float = 0.0
    average_weighted_cost: float | None = None
    average_action_count: float
    average_removed_mods: float
    median_runtime_seconds: float
    average_states_expanded: float
    issue_detection_accuracy: float
    explanation_completeness_rate: float | None = None
    suggestion_coverage_rate: float | None = None
    executable_suggestion_rate: float | None = None
    cascading_cases: int = 0
    successful_cascading_repairs: int = 0
    cascading_repair_success_rate: float | None = None
    mean_cascading_actions: float | None = None
    maximum_repair_depth: int = 0
    cases_with_temporary_issue_increase: int = 0
    cases_with_issue_type_change: int = 0
    oracle_verified_cases: int = 0
    optimal_plan_agreements: int = 0
    optimal_plan_agreement_rate: float | None = None
    no_solution_cases: int = 0
    correct_no_solution_cases: int = 0
    no_solution_correctness_rate: float | None = None
    dependency_chain_explanation_accuracy: float | None = None
    cascading_step_explanation_accuracy: float | None = None
    global_plan_reason_accuracy: float | None = None


class FinalEvaluationRun(FinalReportBaseModel):
    manifest_path: str
    output_dir: str
    generated_at: str
    runtime_repetitions: int = 3
    warmup_runs: int = 1
    timer: str = "time.perf_counter"
    timing_scope: str = "algorithm_only"
    validation: FinalDatasetValidationResult
    results: list[FinalCaseEvaluation] = Field(default_factory=list)
    metrics: list[FinalSystemMetrics] = Field(default_factory=list)
    generated_files: list[str] = Field(default_factory=list)


class FinalChartOutput(FinalReportBaseModel):
    path: str
    title: str
    plotted_data: dict[str, list[float] | list[str]] = Field(default_factory=dict)
