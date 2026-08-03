"""Structured models for offline evaluation runs."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from modpack_solver.models import IssueType, RepairActionType
from modpack_solver.solver.checker import CompatibilityStatus
from modpack_solver.solver.common import SearchLimits, SolverStatus


class EvaluationBaseModel(BaseModel):
    """Shared Pydantic configuration for evaluation models."""

    model_config = ConfigDict(extra="forbid")


class EvaluationSourceType(str, Enum):
    SYNTHETIC = "synthetic"
    CACHED_REAL = "cached_real"
    MODIFIED_REAL = "modified_real"


class EvaluationCaseSpec(EvaluationBaseModel):
    case_id: str
    name: str
    fixture: str
    source_type: EvaluationSourceType
    description: str | None = None

    expected_initial_status: CompatibilityStatus
    expected_solver_status: SolverStatus

    expected_issue_types: list[IssueType] = Field(default_factory=list)
    forbidden_issue_types: list[IssueType] = Field(default_factory=list)
    expected_action_types: list[RepairActionType] = Field(default_factory=list)

    expected_min_cost: int | None = None
    expected_max_cost: int | None = None
    expected_min_preservation_rate: float | None = None
    expected_final_compatible: bool = False

    search_limits: SearchLimits | None = None

    source_reference: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_expected_ranges(self) -> "EvaluationCaseSpec":
        if not self.case_id.strip():
            raise ValueError("case_id cannot be empty.")
        if not self.fixture.strip():
            raise ValueError("fixture cannot be empty.")
        if self.expected_min_preservation_rate is not None and not (0.0 <= self.expected_min_preservation_rate <= 1.0):
            raise ValueError("expected_min_preservation_rate must be between 0 and 1.")
        if (
            self.expected_min_cost is not None
            and self.expected_max_cost is not None
            and self.expected_min_cost > self.expected_max_cost
        ):
            raise ValueError("expected_min_cost cannot be greater than expected_max_cost.")
        return self


class EvaluationCaseResult(EvaluationBaseModel):
    case_id: str
    name: str
    source_type: EvaluationSourceType

    expected_initial_status: CompatibilityStatus
    expected_solver_status: SolverStatus
    expected_issue_types: list[IssueType] = Field(default_factory=list)

    initial_status: CompatibilityStatus
    solver_status: SolverStatus
    initial_issue_types: list[IssueType] = Field(default_factory=list)
    action_types: list[RepairActionType] = Field(default_factory=list)

    final_compatible: bool
    total_cost: int | None = None
    action_count: int = 0
    original_mods_preserved: int = 0
    original_mod_count: int = 0
    preservation_rate: float = 0.0
    removed_mod_count: int = 0
    runtime_seconds: float = 0.0
    states_expanded: int = 0

    status_passed: bool
    issues_passed: bool
    actions_passed: bool
    cost_passed: bool
    preservation_passed: bool
    final_compatibility_passed: bool
    exact_issue_match: bool = False
    passed: bool

    explanation_root_cause_present: bool = False
    explanation_affected_mods_present: bool = False
    explanation_repair_present: bool = False
    explanation_chain_present_when_expected: bool = False

    failure_reasons: list[str] = Field(default_factory=list)


class EvaluationSummary(EvaluationBaseModel):
    total_cases: int
    passed_cases: int
    failed_cases: int
    case_pass_rate: float

    repairable_invalid_cases: int
    successfully_repaired_cases: int
    repair_success_rate: float

    average_preservation_rate: float
    average_weighted_cost: float | None
    average_action_count: float
    average_removed_mods: float
    average_runtime_seconds: float
    average_states_expanded: float

    exact_issue_match_cases: int
    issue_detection_case_accuracy: float
    issue_detection_recall: float


class EvaluationRun(EvaluationBaseModel):
    manifest_path: str
    results: list[EvaluationCaseResult] = Field(default_factory=list)
    summary: EvaluationSummary
