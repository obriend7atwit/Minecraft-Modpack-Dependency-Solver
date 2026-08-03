"""Publication-oriented models for the final evaluation dataset."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from modpack_solver.final_dataset.sizing import PackSizeCategory, classify_pack_size
from modpack_solver.models import IssueType, RepairAction, RepairActionType, SyntheticCase
from modpack_solver.solver.checker import CompatibilityStatus
from modpack_solver.solver.common import SolverStatus


class FinalDatasetBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FinalCaseSourceType(str, Enum):
    SYNTHETIC = "synthetic"
    ORIGINAL_REAL = "original_real"
    MODIFIED_REAL = "modified_real"
    CUSTOM_MODPACK = "custom_modpack"
    CUSTOM_TOPOLOGY = "custom_topology"
    CASCADING_STRESS = "cascading_stress"
    SEARCH_STRESS = "search_stress"
    EXISTING_BROKEN = "existing_broken"


class GroundTruthMethod(str, Enum):
    """Independent basis used to establish a case's expected outcome."""

    ORIGINAL_CONTROL = "original_control"
    INVERSE_INJECTION = "inverse_injection"
    REFERENCE_ENUMERATION = "reference_enumeration"
    MANUAL_REVIEW = "manual_review"
    DOCUMENTED_REPRODUCTION = "documented_reproduction"


class ModificationType(str, Enum):
    NONE = "none"
    REMOVE_REQUIRED_DEPENDENCY = "remove_required_dependency"
    CHANGE_MINECRAFT_VERSION = "change_minecraft_version"
    CHANGE_LOADER = "change_loader"
    REPLACE_WITH_INCOMPATIBLE_VERSION = "replace_with_incompatible_version"
    ADD_CONFLICTING_MOD = "add_conflicting_mod"
    DUPLICATE_MOD_VERSION = "duplicate_mod_version"
    REMOVE_DEPENDENCY_METADATA = "remove_dependency_metadata"
    CASCADING_REPAIR = "cascading_repair"
    CANDIDATE_CHOICE = "candidate_choice"
    UNSATISFIABLE = "unsatisfiable"
    TIE_BREAKING = "tie_breaking"
    MULTI_ERROR = "multi_error"
    MANUAL = "manual"


class ExpectedRepairStep(FinalDatasetBaseModel):
    """One independently defined step in a known repair sequence."""

    step_number: int = Field(ge=1)
    action_type: RepairActionType
    target_mod_id: str | None = None
    expected_issue_types_before: list[IssueType] = Field(default_factory=list)
    expected_issue_types_after: list[IssueType] = Field(default_factory=list)
    description: str


class FinalDatasetCaseSpec(FinalDatasetBaseModel):
    case_id: str
    display_name: str
    source_type: FinalCaseSourceType
    source_modpack_name: str | None = None
    source_url: str | None = None
    source_project_id: str | None = None
    source_version_id: str | None = None
    source_family_id: str
    parent_case_id: str | None = None
    source_pack_slug: str | None = None
    source_pack_version_id: str | None = None
    source_manifest_sha256: str | None = None
    collected_at: str | None = None
    collection_method: str | None = None
    ground_truth_method: GroundTruthMethod
    review_status: str
    original_case_id: str | None = None
    modification_type: ModificationType = ModificationType.NONE
    modification_description: str | None = None
    topology: str | None = None
    generation_config: dict[str, object] | None = None
    is_cascading: bool = False
    injection_log: str | None = None
    fixture_path: str
    cached_metadata_path: str | None = None
    minecraft_version: str
    loader: str
    selected_mod_count: int = Field(ge=0)
    dependency_edge_count: int | None = Field(default=None, ge=0)
    pack_size_category: PackSizeCategory
    manifest_file_count: int | None = Field(default=None, ge=0)
    resolved_mod_count: int | None = Field(default=None, ge=0)
    unresolved_mod_count: int | None = Field(default=None, ge=0)
    metadata_coverage_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    project_count: int = Field(default=0, ge=0)
    version_count: int = Field(default=0, ge=0)
    required_edge_count: int = Field(default=0, ge=0)
    optional_edge_count: int = Field(default=0, ge=0)
    incompatible_edge_count: int = Field(default=0, ge=0)
    embedded_edge_count: int = Field(default=0, ge=0)
    total_dependency_edge_count: int = Field(default=0, ge=0)
    required_edge_density: float = Field(default=0.0, ge=0.0)
    total_edge_density: float = Field(default=0.0, ge=0.0)
    maximum_required_depth: int = Field(default=0, ge=0)
    mean_required_depth: float = Field(default=0.0, ge=0.0)
    mean_required_branching_factor: float = Field(default=0.0, ge=0.0)
    maximum_required_branching_factor: int = Field(default=0, ge=0)
    connected_component_count: int = Field(default=0, ge=0)
    largest_component_mod_count: int = Field(default=0, ge=0)
    required_cycle_count: int = Field(default=0, ge=0)
    strongly_connected_component_count: int = Field(default=0, ge=0)
    mean_candidate_versions_per_mod: float = Field(default=0.0, ge=0.0)
    maximum_candidate_versions_per_mod: int = Field(default=0, ge=0)
    mods_with_multiple_candidate_versions: int = Field(default=0, ge=0)
    injected_error_count: int = Field(default=0, ge=0)
    expected_issue_count: int = Field(default=0, ge=0)
    expected_repair_action_count: int | None = Field(default=None, ge=0)
    known_valid_repair: list[RepairAction] = Field(default_factory=list)
    expected_issue_trace: list[ExpectedRepairStep] = Field(default_factory=list)
    known_minimum_default_cost: int | None = Field(default=None, ge=0)
    known_minimum_preservation_cost: int | None = Field(default=None, ge=0)
    minimum_cost_verified: bool = False
    expected_initial_status: CompatibilityStatus
    expected_solver_status: SolverStatus
    expected_issue_types: list[IssueType] = Field(default_factory=list)
    expected_action_types: list[RepairActionType] = Field(default_factory=list)
    expected_repairable: bool = False
    expected_final_compatible: bool = False
    manually_reviewed: bool = False
    review_notes: str | None = None
    license_or_terms_note: str | None = None
    dataset_notes: str | None = None

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_fields(cls, value):
        """Supply explicit v2 values while accepting the immutable v1 corpus."""

        if not isinstance(value, dict):
            return value
        data = dict(value)
        case_id = str(data.get("case_id") or "")
        modification = data.get("modification_type", ModificationType.NONE.value)
        data.setdefault("source_family_id", data.get("original_case_id") or case_id)
        data.setdefault(
            "ground_truth_method",
            (
                GroundTruthMethod.INVERSE_INJECTION.value
                if modification != ModificationType.NONE.value
                else GroundTruthMethod.ORIGINAL_CONTROL.value
            ),
        )
        data.setdefault(
            "review_status",
            "manually_reviewed" if data.get("manually_reviewed") else "generated",
        )
        data.setdefault("expected_issue_count", len(data.get("expected_issue_types") or []))
        expected_actions = data.get("expected_action_types") or []
        if "expected_repair_action_count" not in data and expected_actions:
            data["expected_repair_action_count"] = len(expected_actions)
        return data

    @model_validator(mode="after")
    def validate_case(self) -> "FinalDatasetCaseSpec":
        if not self.case_id.strip():
            raise ValueError("case_id cannot be empty.")
        if not self.display_name.strip():
            raise ValueError("display_name cannot be empty.")
        if not self.fixture_path.strip():
            raise ValueError("fixture_path cannot be empty.")
        if not self.source_family_id.strip():
            raise ValueError("source_family_id cannot be empty.")
        if not self.review_status.strip():
            raise ValueError("review_status cannot be empty.")
        expected_size = classify_pack_size(self.selected_mod_count)
        if self.pack_size_category != expected_size:
            raise ValueError(
                f"pack_size_category must be '{expected_size.value}' for {self.selected_mod_count} selected mods."
            )
        if self.source_type == FinalCaseSourceType.MODIFIED_REAL:
            if self.modification_type == ModificationType.NONE:
                raise ValueError("modified_real cases must declare a modification_type.")
            if not (self.modification_description or "").strip():
                raise ValueError("modified_real cases must include a modification_description.")
        if self.modification_type != ModificationType.NONE and not (self.modification_description or "").strip():
            raise ValueError("Modified cases must include a modification_description.")
        return self


class FinalDatasetManifest(FinalDatasetBaseModel):
    dataset_name: str
    dataset_version: str
    generated_at: str | None = None
    description: str
    cases: list[FinalDatasetCaseSpec]

    @model_validator(mode="after")
    def validate_manifest(self) -> "FinalDatasetManifest":
        if not self.dataset_name.strip() or not self.dataset_version.strip():
            raise ValueError("dataset_name and dataset_version cannot be empty.")
        case_ids = [case.case_id for case in self.cases]
        duplicates = sorted({case_id for case_id in case_ids if case_ids.count(case_id) > 1})
        if duplicates:
            raise ValueError(f"Duplicate final dataset case IDs: {', '.join(duplicates)}.")
        known_ids = set(case_ids)
        for case in self.cases:
            if case.original_case_id and case.original_case_id not in known_ids:
                raise ValueError(
                    f"Case '{case.case_id}' references unknown original_case_id '{case.original_case_id}'."
                )
            if case.source_type == FinalCaseSourceType.MODIFIED_REAL and not case.original_case_id:
                raise ValueError(f"Modified real case '{case.case_id}' must reference original_case_id.")
        return self


class InjectedCaseResult(FinalDatasetBaseModel):
    original_case_id: str | None = None
    modified_case: SyntheticCase
    modification_type: ModificationType
    modification_description: str
    expected_issue_types: list[IssueType]
    expected_action_types: list[RepairActionType] = Field(default_factory=list)
    expected_solver_status: SolverStatus
    expected_final_compatible: bool
    ground_truth_method: GroundTruthMethod = GroundTruthMethod.INVERSE_INJECTION
    known_valid_repair: list[RepairAction] = Field(default_factory=list)
    changed_mod_ids: list[str] = Field(default_factory=list)
    applied_modifications: list[ModificationType] = Field(default_factory=list)
    notes: str | None = None


class FinalDatasetValidationResult(FinalDatasetBaseModel):
    manifest_path: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    warnings: list[str] = Field(default_factory=list)
    failures: dict[str, list[str]] = Field(default_factory=dict)
    source_type_counts: dict[str, int] = Field(default_factory=dict)
    size_category_counts: dict[str, int] = Field(default_factory=dict)
    error_type_counts: dict[str, int] = Field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.failed_cases == 0
