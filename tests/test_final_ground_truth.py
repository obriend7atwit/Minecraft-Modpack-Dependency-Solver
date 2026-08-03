from modpack_solver.final_dataset.expanded_corpus import generate_expanded_corpus
from modpack_solver.final_dataset.models import GroundTruthMethod


def test_expanded_generation_does_not_call_weighted_solver(monkeypatch, tmp_path):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Weighted solver must not define dataset ground truth.")

    monkeypatch.setattr(
        "modpack_solver.solver.weighted.solve_weighted_case",
        fail_if_called,
    )
    manifest = generate_expanded_corpus(
        output_dir=tmp_path,
        legacy_manifest_path="data/final_dataset/manifest_v1.json",
    )
    assert len(manifest.cases) >= 120
    assert all(case.ground_truth_method for case in manifest.cases)


def test_expected_and_observed_results_are_separate_in_manifest(tmp_path):
    manifest = generate_expanded_corpus(
        output_dir=tmp_path,
        legacy_manifest_path="data/final_dataset/manifest_v1.json",
        generate_dense=False,
        generate_cascading=True,
        generate_search=True,
    )
    enumerated = [
        case
        for case in manifest.cases
        if case.ground_truth_method == GroundTruthMethod.REFERENCE_ENUMERATION
    ]
    assert enumerated
    assert all(case.minimum_cost_verified for case in enumerated)
    assert all(
        "observed_solver_result" not in case.model_dump()
        for case in manifest.cases
    )
