import json
from zipfile import ZipFile

from modpack_solver.final_gui.presenter import (
    analyze_loaded_case,
    build_result_summary,
    format_explanation,
    format_graph_summary,
    format_modpack_summary,
    format_repair_plan,
    format_repair_trace,
    load_builtin_sample,
    load_dataset_case,
    load_json_into_state,
    load_modrinth_url_into_state,
    load_mrpack_into_state,
    load_project_list_into_state,
)
from modpack_solver.final_gui.state import FinalGuiState


def test_presenter_loads_json_builtin_and_dataset_cases():
    state = FinalGuiState()
    load_json_into_state(state, "data/synthetic/valid_modpack.json")
    assert state.loaded_input_type == "json"
    load_builtin_sample(state, "missing_required_dependency.json")
    assert state.loaded_input_type == "built_in_sample"
    load_dataset_case(state, "real-additive-valid")
    assert state.loaded_input_type == "final_dataset"


def test_presenter_analysis_produces_summary_plan_and_explanation():
    state = FinalGuiState()
    load_builtin_sample(state, "missing_required_dependency.json")
    analyze_loaded_case(state)
    assert "Minecraft version" in format_modpack_summary(state)
    assert "Required dependency edges" in format_modpack_summary(state)
    assert "Selected actions" in format_repair_plan(state)
    assert "REPAIR TRACE" in format_repair_trace(state)
    assert "COMPLEXITY SUMMARY" in format_graph_summary(state)
    assert "USER-FRIENDLY SUMMARY" in format_explanation(state)


def test_result_summary_formats_already_compatible_case():
    state = FinalGuiState()
    load_builtin_sample(state, "valid_modpack.json")
    analyze_loaded_case(state)
    summary = build_result_summary(state)
    assert summary.status == "compatible"
    assert summary.total_cost == "0"
    assert summary.actions == ("Keep the current modpack selection.",)


def test_result_summary_formats_successful_repair_case():
    state = FinalGuiState()
    load_builtin_sample(state, "missing_required_dependency.json")
    analyze_loaded_case(state)
    summary = build_result_summary(state)
    assert summary.status == "repair_found"
    assert summary.actions
    assert summary.preserved == "1/1"


def test_result_summary_formats_no_solution_case():
    state = FinalGuiState()
    load_builtin_sample(state, "no_solution.json")
    analyze_loaded_case(state)
    summary = build_result_summary(state)
    assert summary.status == "no_solution"
    assert "available metadata" in summary.message


def test_gui_state_defaults_to_simple_mode_and_tracks_button_readiness():
    state = FinalGuiState()
    assert state.advanced_details_visible is False
    assert state.can_analyze is False
    assert state.can_export is False
    state.set_advanced_details_visible(True)
    assert state.advanced_details_visible is True
    load_builtin_sample(state, "valid_modpack.json")
    assert state.can_analyze is True
    state.begin_analysis()
    assert state.can_analyze is False
    state.finish_analysis()
    analyze_loaded_case(state)
    assert state.can_export is True


def test_presenter_project_list_and_modrinth_url_use_offline_cache():
    state = FinalGuiState()
    load_project_list_into_state(
        state,
        "fabric-api,modmenu",
        "1.20.1",
        "fabric",
        allow_live=False,
    )
    assert len(state.loaded_case.config.selected_mods) == 2
    load_modrinth_url_into_state(
        state,
        "https://modrinth.com/modpack/fabulously-optimized",
        allow_live=False,
    )
    assert state.loaded_pack_name == "fabulously-optimized"


def test_presenter_loads_basic_mrpack_from_cached_ids(tmp_path):
    path = tmp_path / "cached.mrpack"
    payload = {
        "name": "Cached Pack",
        "versionId": "1",
        "dependencies": {"minecraft": "1.20.1", "fabric-loader": "0.15.0"},
        "files": [
            {
                "path": "mods/fabric-api.jar",
                "hashes": {},
                "downloads": ["https://cdn.modrinth.com/data/P7dR8mSH/versions/hu6gukgT/file.jar"],
            }
        ],
    }
    with ZipFile(path, "w") as archive:
        archive.writestr("modrinth.index.json", json.dumps(payload))
    state = FinalGuiState()
    load_mrpack_into_state(state, path, allow_live=False)
    assert state.loaded_input_type == "mrpack"
    assert state.loaded_pack_name == "Cached Pack"
