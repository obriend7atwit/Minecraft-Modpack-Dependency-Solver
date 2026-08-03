import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from modpack_solver.final_dataset.manual_review import (
    HUMAN_JUDGMENT_FIELDS,
    HumanReviewRecord,
    ReviewStatus,
    format_case_review_packet,
    generate_automated_evidence,
    generate_review_queue,
)
from modpack_solver.final_dataset.manifest import load_final_dataset_manifest


def _all_true_record(**updates):
    payload = {
        "case_id": "review-case",
        "reviewer": "Reviewer",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "review_status": ReviewStatus.PUBLICATION_READY,
        **{field: True for field in HUMAN_JUDGMENT_FIELDS},
        **updates,
    }
    return payload


def test_automated_evidence_does_not_fill_subjective_fields():
    manifest = load_final_dataset_manifest("data/final_dataset/manifest.json")
    spec = next(
        item for item in manifest.cases
        if item.case_id == "full-fabulously-optimized-czy3bvs9"
    )
    evidence = generate_automated_evidence(spec)
    record = HumanReviewRecord(case_id=spec.case_id)
    assert evidence.graph_builds
    assert evidence.checker_matches_expected
    assert all(value is None for value in record.subjective_judgments().values())


def test_publication_ready_requires_complete_human_evidence():
    with pytest.raises(ValidationError, match="every human judgment"):
        HumanReviewRecord.model_validate(
            _all_true_record(explanation_understandable=None)
        )
    with pytest.raises(ValidationError, match="every human judgment to be true"):
        HumanReviewRecord.model_validate(
            _all_true_record(explanation_understandable=False)
        )
    assert (
        HumanReviewRecord.model_validate(_all_true_record()).review_status
        == ReviewStatus.PUBLICATION_READY
    )


def test_review_queue_writes_summary_without_claiming_human_review(tmp_path):
    review_dir = tmp_path / "review"
    output_dir = tmp_path / "output"
    summary = generate_review_queue(
        review_dir=review_dir,
        output_dir=output_dir,
    )
    assert summary.total_queued >= 58
    assert summary.automated_evidence_ready > 0
    assert summary.human_reviewed == 0
    assert summary.publication_ready == 0
    assert (output_dir / "manual_review_summary.csv").exists()
    assert (output_dir / "manual_review_summary.md").exists()
    assert (output_dir / "review_queue.csv").exists()
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in review_dir.glob("*.json")
    ]
    assert records
    assert all(record["explanation_understandable"] is None for record in records)


def test_case_packet_lists_remaining_human_judgments(tmp_path):
    text = format_case_review_packet(
        "cascade-01-missing-chain",
        review_dir=tmp_path,
    )
    assert "Observed checker" in text
    assert "Known repair" in text
    assert "Human judgment still required" in text
