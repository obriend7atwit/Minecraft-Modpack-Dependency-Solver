"""Structured state shared by the final GUI presenter and exports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modpack_solver.graph import GraphBuildResult
from modpack_solver.final_dataset.models import FinalDatasetCaseSpec
from modpack_solver.models import SyntheticCase
from modpack_solver.solver import CompatibilityReport, ExplanationReport, SolverResult


@dataclass
class FinalGuiState:
    loaded_case: SyntheticCase | None = None
    loaded_source_label: str | None = None
    loaded_input_type: str | None = None
    loaded_pack_name: str | None = None
    loaded_dataset_spec: FinalDatasetCaseSpec | None = None
    graph_result: GraphBuildResult | None = None
    compatibility_report: CompatibilityReport | None = None
    solver_result: SolverResult | None = None
    explanation_report: ExplanationReport | None = None
    selected_profile_id: str = "default"
    offline_mode: bool = True
    metadata_mode_used: str = "offline"
    progress_stage: str = "Ready"
    last_text_report: str | None = None
    last_json_report: dict[str, Any] | None = None
    messages: list[str] = field(default_factory=list)
    advanced_details_visible: bool = False
    analysis_in_progress: bool = False

    @property
    def can_analyze(self) -> bool:
        return self.loaded_case is not None and not self.analysis_in_progress

    @property
    def can_export(self) -> bool:
        return self.solver_result is not None and not self.analysis_in_progress

    def set_advanced_details_visible(self, visible: bool) -> None:
        self.advanced_details_visible = visible

    def begin_analysis(self) -> None:
        if self.loaded_case is None:
            raise ValueError("Load a modpack before starting analysis.")
        if self.analysis_in_progress:
            raise RuntimeError("An analysis is already running.")
        self.analysis_in_progress = True
        self.progress_stage = "Analyzing metadata"

    def finish_analysis(self) -> None:
        self.analysis_in_progress = False
        self.progress_stage = "Ready"

    def clear_analysis(self) -> None:
        self.graph_result = None
        self.compatibility_report = None
        self.solver_result = None
        self.explanation_report = None
        self.last_text_report = None
        self.last_json_report = None

    def clear(self) -> None:
        profile = self.selected_profile_id
        offline = self.offline_mode
        self.__dict__.update(FinalGuiState(selected_profile_id=profile, offline_mode=offline).__dict__)
