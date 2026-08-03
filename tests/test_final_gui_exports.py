import json

from modpack_solver.final_gui.exports import (
    build_json_repair_report,
    build_text_repair_report,
    save_json_report,
    save_text_report,
)
from modpack_solver.final_gui.presenter import analyze_loaded_case, load_builtin_sample
from modpack_solver.final_gui.state import FinalGuiState


def _analyzed_state():
    state = FinalGuiState()
    load_builtin_sample(state, "missing_required_dependency.json")
    analyze_loaded_case(state)
    return state


def test_gui_text_and_json_exports_are_complete_and_serializable(tmp_path):
    state = _analyzed_state()
    text = build_text_repair_report(state)
    payload = build_json_repair_report(state)
    assert "COMPATIBILITY ISSUES" in text
    assert "WEIGHTED REPAIR PLAN" in text
    assert payload["weight_profile"] == "default"
    json.dumps(payload)
    text_path = save_text_report(state, tmp_path / "report.txt")
    json_path = save_json_report(state, tmp_path / "report.json")
    assert text_path.exists()
    assert json.loads(json_path.read_text(encoding="utf-8"))["solver_result"]
