"""Structured models for Week 9 solver analysis."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from modpack_solver.evaluation.models import EvaluationSourceType
from modpack_solver.models import IssueType, ModpackConfig, RepairAction, RepairActionType
from modpack_solver.solver.checker import CompatibilityReport
from modpack_solver.solver.common import SolverStatus


class AnalysisBaseModel(BaseModel):
    """Shared Pydantic configuration for analysis models."""

    model_config = ConfigDict(extra="forbid")


class RuntimeMeasurements(AnalysisBaseModel):
    samples_seconds: list[float] = Field(default_factory=list)
    median_seconds: float = 0.0
    minimum_seconds: float = 0.0
    maximum_seconds: float = 0.0


class ExperimentSystem(str, Enum):
    BASELINE = "baseline"
    WEIGHTED_DEFAULT = "weighted_default"
    WEIGHTED_PRESERVATION = "weighted_preservation"


class BaselineExecutionResult(AnalysisBaseModel):
    """Concrete result from applying simple baseline suggestions without search."""

    suggestions: list[RepairAction] = Field(default_factory=list)
    executable_actions: list[RepairAction] = Field(default_factory=list)
    unexecutable_suggestions: list[RepairAction] = Field(default_factory=list)
    repaired_config: ModpackConfig | None = None
    final_report: CompatibilityReport | None = None
    final_compatible: bool = False
    original_mods_preserved: int = 0
    removed_mod_count: int = 0
    version_change_count: int = 0


class ExperimentCaseResult(AnalysisBaseModel):
    case_id: str
    name: str
    source_type: EvaluationSourceType
    system: ExperimentSystem
    profile_id: str | None = None

    original_mod_count: int = 0
    initially_compatible: bool = False
    repair_expected: bool = False
    no_solution_expected: bool = False

    suggestion_count: int = 0
    executable_suggestion_count: int = 0
    solution_found: bool = False
    final_compatible: bool = False

    issue_types: list[IssueType] = Field(default_factory=list)
    action_types: list[RepairActionType] = Field(default_factory=list)

    action_count: int = 0
    total_cost: int | None = None
    original_mods_preserved: int = 0
    preservation_rate: float = 1.0
    removed_mod_count: int = 0
    version_change_count: int = 0
    states_expanded: int = 0

    runtime: RuntimeMeasurements = Field(default_factory=RuntimeMeasurements)

    status_correct: bool = False
    issue_detection_correct: bool = False
    repair_outcome_correct: bool = False

    failure_category: str | None = None
    failure_detail: str | None = None


class GroupMetrics(AnalysisBaseModel):
    group_name: str
    total_cases: int = 0
    valid_control_cases: int = 0
    repairable_invalid_cases: int = 0
    expected_no_solution_cases: int = 0
    successfully_repaired_cases: int = 0
    repair_success_rate: float = 0.0
    average_preservation_rate: float = 0.0
    average_action_count: float = 0.0
    average_removed_mods: float = 0.0
    average_states_expanded: float = 0.0
    median_runtime_seconds: float = 0.0
    issue_detection_accuracy: float = 0.0


class ExperimentSummary(AnalysisBaseModel):
    system: ExperimentSystem
    profile_id: str | None = None
    total_cases: int
    valid_control_cases: int
    repairable_invalid_cases: int
    expected_no_solution_cases: int
    successfully_repaired_cases: int
    repair_success_rate: float
    average_repair_preservation_rate: float
    average_repair_action_count: float
    average_repair_removed_mods: float
    average_repair_cost: float | None
    median_runtime_seconds: float
    average_states_expanded: float
    issue_detection_accuracy: float
    suggestion_coverage_rate: float | None = None
    executable_suggestion_rate: float | None = None
    validated_baseline_repair_rate: float | None = None
    failure_counts: dict[str, int] = Field(default_factory=dict)
    grouped_metrics: list[GroupMetrics] = Field(default_factory=list)


class SearchLimitExperimentResult(AnalysisBaseModel):
    case_id: str
    profile_id: str
    max_expanded_states: int
    solution_found: bool
    final_compatible: bool
    total_cost: int | None = None
    states_expanded: int
    runtime: RuntimeMeasurements
    status: SolverStatus


class Week9AnalysisResult(AnalysisBaseModel):
    manifest_path: str
    runtime_repetitions: int
    strict_validation_passed: bool
    strict_validation_case_count: int
    case_results: list[ExperimentCaseResult] = Field(default_factory=list)
    summaries: list[ExperimentSummary] = Field(default_factory=list)
    search_limit_results: list[SearchLimitExperimentResult] = Field(default_factory=list)
    changed_decision_cases: list[str] = Field(default_factory=list)
    solver_refinements: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    generated_files: list[str] = Field(default_factory=list)
