"""Replay independently defined repair plans through the normal checker."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from modpack_solver.models import IssueType, RepairAction, SyntheticCase
from modpack_solver.solver.checker import CompatibilityReport, IssueSeverity
from modpack_solver.solver.common import evaluate_config
from modpack_solver.solver.search import apply_repair_action
from modpack_solver.solver.state import SolverState


class RepairTraceStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_number: int = Field(ge=1)
    action: RepairAction
    report_before: CompatibilityReport
    report_after: CompatibilityReport
    issue_types_before: list[IssueType] = Field(default_factory=list)
    issue_types_after: list[IssueType] = Field(default_factory=list)


class RepairTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_report: CompatibilityReport
    steps: list[RepairTraceStep] = Field(default_factory=list)
    final_report: CompatibilityReport
    final_compatible: bool


def replay_repair_plan(
    case: SyntheticCase,
    actions: Sequence[RepairAction],
) -> RepairTrace:
    """Apply a repair sequence immutably and record checker output after each step."""

    state = SolverState(config=case.config.model_copy(deep=True))
    original_report = evaluate_config(state.config, case.projects, case.versions)
    report = original_report
    steps: list[RepairTraceStep] = []

    for step_number, action in enumerate(actions, start=1):
        next_state = apply_repair_action(
            state=state,
            action=action.model_copy(deep=True),
            versions=case.versions,
        )
        if next_state is None:
            raise ValueError(
                f"Repair step {step_number} could not be applied: "
                f"{action.action_type.value} {action.target_mod_id}."
            )
        next_report = evaluate_config(next_state.config, case.projects, case.versions)
        steps.append(
            RepairTraceStep(
                step_number=step_number,
                action=action.model_copy(deep=True),
                report_before=report,
                report_after=next_report,
                issue_types_before=_issue_types(report),
                issue_types_after=_issue_types(next_report),
            )
        )
        state = next_state
        report = next_report

    return RepairTrace(
        original_report=original_report,
        steps=steps,
        final_report=report,
        final_compatible=not any(
            issue.severity == IssueSeverity.ERROR.value for issue in report.issues
        ),
    )


def _issue_types(report: CompatibilityReport) -> list[IssueType]:
    seen: set[IssueType] = set()
    ordered: list[IssueType] = []
    for issue in report.issues:
        if issue.issue_type in seen:
            continue
        seen.add(issue.issue_type)
        ordered.append(issue.issue_type)
    return ordered
