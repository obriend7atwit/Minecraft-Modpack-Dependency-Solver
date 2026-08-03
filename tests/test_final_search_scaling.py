from pathlib import Path

from modpack_solver.final_dataset.manifest import load_final_dataset_manifest
from modpack_solver.final_dataset.search_scaling import (
    generate_search_scaling_dataset,
    load_search_scaling_manifest,
    run_search_scaling_experiment,
)
from modpack_solver.final_dataset.repair_trace import replay_repair_plan
from modpack_solver.metadata.synthetic import load_synthetic_case


def test_five_scaling_cases_are_deterministic_and_separate(tmp_path):
    first = generate_search_scaling_dataset(tmp_path)
    first_payload = first.model_dump(mode="json")
    second = generate_search_scaling_dataset(tmp_path)
    assert len(first.cases) == 5
    assert first_payload == second.model_dump(mode="json")
    assert len(load_final_dataset_manifest("data/final_dataset/manifest.json").cases) == 158


def test_scaling_ground_truth_replays_without_weighted_solver(monkeypatch, tmp_path):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Weighted solver must not define search-scaling ground truth.")

    monkeypatch.setattr(
        "modpack_solver.solver.weighted.solve_weighted_case",
        fail_if_called,
    )
    manifest = generate_search_scaling_dataset(tmp_path)
    for spec in manifest.cases:
        case = load_synthetic_case(tmp_path / spec.fixture_path)
        assert replay_repair_plan(case, spec.known_valid_repair).final_compatible


def test_scaling_runner_records_ranges_and_careful_scope(tmp_path):
    data_root = tmp_path / "data"
    generate_search_scaling_dataset(data_root)
    run = run_search_scaling_experiment(
        manifest_path=data_root / "search_scaling_manifest.json",
        output_dir=tmp_path / "results",
        runtime_repetitions=1,
    )
    assert run.all_outcomes_correct
    assert run.all_target_ranges_met
    assert all(item.runtime_samples_seconds for item in run.results)
    assert (tmp_path / "results" / "search_scaling_results.json").exists()
    summary = (tmp_path / "results" / "search_scaling_summary.md").read_text()
    assert "separate from the main corpus" in summary
    assert "do not establish real-world launcher scalability" in summary
