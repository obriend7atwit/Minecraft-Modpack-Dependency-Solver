import json

from modpack_solver.final_dataset.exclusion_review import (
    ExclusionCause,
    classify_exclusion,
    review_excluded_manifests,
)
from modpack_solver.final_dataset.export import write_pretty_json
from modpack_solver.metadata.synthetic import load_synthetic_case


def test_exclusion_classification_is_conservative():
    cause, confidence = classify_exclusion(
        issue_types=["missing_dependency", "minecraft_version_mismatch"],
        metadata_coverage_rate=1.0,
        unresolved_files=0,
    )
    assert cause == ExclusionCause.REQUIRES_MANUAL_REVIEW
    assert confidence == "low"


def test_incomplete_collection_is_not_labeled_as_a_broken_pack():
    cause, _ = classify_exclusion(
        issue_types=["missing_dependency"],
        metadata_coverage_rate=0.95,
        unresolved_files=1,
    )
    assert cause == ExclusionCause.INCOMPLETE_METADATA_COLLECTION


def test_review_outputs_recovered_case_but_keeps_it_quarantined(tmp_path):
    dataset = tmp_path / "dataset"
    fixture = dataset / "original_real" / "clean.json"
    write_pretty_json(fixture, load_synthetic_case("data/synthetic/valid_modpack.json"))
    quarantine = dataset / "quarantine"
    quarantine.mkdir(parents=True)
    (quarantine / "analysis-clean.json").write_text(
        json.dumps(
            {
                "slug": "clean",
                "version_id": "version1",
                "normalized_case_path": str(fixture),
                "checker_errors": [{"issue_type": "missing_dependency"}],
            }
        ),
        encoding="utf-8",
    )
    write_pretty_json(
        dataset / "metadata_cache" / "full_pack_collection.json",
        {
            "collected": [
                {
                    "slug": "clean",
                    "metadata_coverage_rate": 1.0,
                    "unresolved_mod_count": 0,
                }
            ],
            "quarantined": {
                "unresolved-pack": "invalid version-like file reference"
            },
        },
    )

    summary = review_excluded_manifests(dataset, tmp_path / "results")

    clean = next(record for record in summary.records if record.source_pack == "clean")
    unresolved = next(
        record for record in summary.records if record.source_pack == "unresolved-pack"
    )
    assert clean.recovered
    assert clean.remains_quarantined
    assert unresolved.likely_cause == ExclusionCause.FILE_RESOLUTION_FAILURE
    markdown = (tmp_path / "results" / "excluded_manifest_review.md").read_text(
        encoding="utf-8"
    )
    assert "not** treated as proof" in markdown
    assert "broken" in markdown
