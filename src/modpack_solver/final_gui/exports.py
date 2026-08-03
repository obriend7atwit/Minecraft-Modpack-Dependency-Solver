"""Text and JSON repair report exports for the final user workflow."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modpack_solver.final_gui.presenter import (
    format_explanation,
    format_graph_summary,
    format_issues,
    format_modpack_summary,
    format_repair_plan,
)
from modpack_solver.final_gui.state import FinalGuiState


def build_text_repair_report(state: FinalGuiState) -> str:
    lines = [
        "MINECRAFT MODPACK WEIGHTED REPAIR REPORT",
        "",
        "INPUT SUMMARY",
        format_modpack_summary(state),
        "",
        "COMPATIBILITY ISSUES",
        format_issues(state),
        "",
        "WEIGHTED REPAIR PLAN",
        format_repair_plan(state),
        "",
        "EXPLANATION",
        format_explanation(state),
        "",
        "DEPENDENCY GRAPH SUMMARY",
        format_graph_summary(state),
        "",
        "LIMITATIONS",
        "This report evaluates available metadata. It does not guarantee launch-time compatibility, install mods, or generate a repaired .mrpack.",
    ]
    report = "\n".join(lines)
    state.last_text_report = report
    return report


def build_json_repair_report(state: FinalGuiState) -> dict[str, Any]:
    if not all((state.loaded_case, state.compatibility_report, state.solver_result, state.explanation_report)):
        raise ValueError("Run analysis before building a JSON report.")
    payload = {
        "app": {"name": "minecraft-modpack-solver", "version": "0.1.0"},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": {
            "source_label": state.loaded_source_label,
            "input_type": state.loaded_input_type,
            "pack_name": state.loaded_pack_name,
            "metadata_mode": state.metadata_mode_used,
            "case": state.loaded_case.model_dump(mode="json"),
        },
        "weight_profile": state.selected_profile_id,
        "compatibility_report": state.compatibility_report.model_dump(mode="json"),
        "solver_result": state.solver_result.model_dump(mode="json"),
        "explanation_report": state.explanation_report.model_dump(mode="json"),
        "limitations": [
            "Metadata compatibility does not guarantee launch-time compatibility.",
            "The system outputs a repair plan and does not modify or install the modpack.",
        ],
    }
    state.last_json_report = payload
    return payload


def save_text_report(state: FinalGuiState, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_text_repair_report(state), encoding="utf-8")
    return output_path


def save_json_report(state: FinalGuiState, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(build_json_repair_report(state), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return output_path
