"""Traceable automated evidence and human review records for final cases."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from modpack_solver.final_dataset.export import write_pretty_json
from modpack_solver.final_dataset.manifest import (
    load_final_dataset_manifest,
    resolve_final_case_path,
    resolve_optional_manifest_path,
)
from modpack_solver.final_dataset.models import FinalDatasetCaseSpec, ModificationType
from modpack_solver.final_dataset.repair_trace import replay_repair_plan
from modpack_solver.graph import build_graph_from_synthetic_case
from modpack_solver.metadata.synthetic import load_synthetic_case
from modpack_solver.solver import build_explanation_report, solve_weighted_case
from modpack_solver.solver.checker import check_graph


class ReviewBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewStatus(str, Enum):
    NOT_STARTED = "not_started"
    AUTOMATED_EVIDENCE_READY = "automated_evidence_ready"
    HUMAN_REVIEW_IN_PROGRESS = "human_review_in_progress"
    HUMAN_REVIEWED = "human_reviewed"
    PUBLICATION_READY = "publication_ready"
    REJECTED = "rejected"


class AutomatedReviewEvidence(ReviewBaseModel):
    case_id: str
    source_family_id: str | None = None
    source_url_present: bool
    source_version_present: bool
    manifest_hash_present: bool
    fixture_exists: bool
    metadata_cache_exists: bool
    graph_builds: bool
    checker_matches_expected: bool
    known_repair_replays: bool | None = None
    final_known_repair_compatible: bool | None = None
    injection_log_exists: bool | None = None
    injection_matches_case_diff: bool | None = None
    metadata_coverage_rate: float | None = None
    observed_status: str | None = None
    observed_issue_types: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ready(self) -> bool:
        required = [
            self.fixture_exists,
            self.graph_builds,
            self.checker_matches_expected,
        ]
        if self.known_repair_replays is not None:
            required.extend(
                [self.known_repair_replays, bool(self.final_known_repair_compatible)]
            )
        if self.injection_log_exists is not None:
            required.extend(
                [self.injection_log_exists, bool(self.injection_matches_case_diff)]
            )
        return all(required)


class HumanReviewRecord(ReviewBaseModel):
    case_id: str
    reviewer: str | None = None
    reviewed_at: str | None = None
    source_provenance_valid: bool | None = None
    normalized_mod_list_reasonable: bool | None = None
    minecraft_version_correct: bool | None = None
    loader_correct: bool | None = None
    injection_matches_description: bool | None = None
    expected_issue_correct: bool | None = None
    known_repair_valid: bool | None = None
    solver_result_reasonable: bool | None = None
    explanation_understandable: bool | None = None
    notes: str = ""
    review_status: ReviewStatus = ReviewStatus.NOT_STARTED

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_record(cls, value):
        if not isinstance(value, dict):
            return value
        data = dict(value)
        data.setdefault("normalized_mod_list_reasonable", None)
        data.setdefault("minecraft_version_correct", None)
        data.setdefault("loader_correct", None)
        data.setdefault("review_status", ReviewStatus.NOT_STARTED.value)
        return data

    @model_validator(mode="after")
    def enforce_status_evidence(self) -> "HumanReviewRecord":
        judgments = self.subjective_judgments()
        if self.review_status in {
            ReviewStatus.HUMAN_REVIEWED,
            ReviewStatus.PUBLICATION_READY,
        }:
            if not (self.reviewer or "").strip() or not self.reviewed_at:
                raise ValueError(
                    f"{self.review_status.value} requires a reviewer and timestamp."
                )
            try:
                datetime.fromisoformat(self.reviewed_at.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("reviewed_at must be an ISO-8601 timestamp.") from exc
            if any(value is None for value in judgments.values()):
                raise ValueError(
                    f"{self.review_status.value} requires every human judgment."
                )
        if self.review_status == ReviewStatus.PUBLICATION_READY and not all(
            value is True for value in judgments.values()
        ):
            raise ValueError(
                "publication_ready requires every human judgment to be true."
            )
        return self

    def subjective_judgments(self) -> dict[str, bool | None]:
        return {
            field_name: getattr(self, field_name)
            for field_name in HUMAN_JUDGMENT_FIELDS
        }


HUMAN_JUDGMENT_FIELDS = (
    "source_provenance_valid",
    "normalized_mod_list_reasonable",
    "minecraft_version_correct",
    "loader_correct",
    "injection_matches_description",
    "expected_issue_correct",
    "known_repair_valid",
    "solver_result_reasonable",
    "explanation_understandable",
)


class ManualReviewSummary(ReviewBaseModel):
    total_queued: int
    automated_evidence_ready: int
    human_reviewed: int
    publication_ready: int
    rejected: int
    remaining_review_count: int
    status_counts: dict[str, int] = Field(default_factory=dict)
    source_type_counts: dict[str, int] = Field(default_factory=dict)
    size_category_counts: dict[str, int] = Field(default_factory=dict)


def select_review_specs(
    manifest_path: str | Path = "data/final_dataset/manifest.json",
    *,
    review_dir: str | Path = "data/final_dataset/manual_review",
) -> list[FinalDatasetCaseSpec]:
    """Select the required review strata plus any already queued records."""

    manifest = load_final_dataset_manifest(manifest_path)
    existing_ids = {
        path.stem
        for path in Path(review_dir).glob("*.json")
        if path.is_file()
    }
    selected = []
    for spec in manifest.cases:
        required = (
            bool(spec.collection_method)
            or spec.is_cascading
            or spec.expected_solver_status.value == "no_solution"
            or (
                spec.source_type.value == "custom_topology"
                and spec.modification_type == ModificationType.NONE
            )
        )
        if required or spec.case_id in existing_ids:
            selected.append(spec)
    return sorted(selected, key=lambda item: item.case_id)


def generate_automated_evidence(
    spec: FinalDatasetCaseSpec,
    *,
    manifest_path: str | Path = "data/final_dataset/manifest.json",
) -> AutomatedReviewEvidence:
    """Build one evidence packet from files and existing domain APIs only."""

    warnings: list[str] = []
    fixture_path = resolve_final_case_path(spec, manifest_path)
    fixture_exists = fixture_path.exists()
    metadata_cache_exists = _metadata_cache_exists(spec, manifest_path)
    if spec.collection_method and not metadata_cache_exists:
        warnings.append("Complete-manifest source metadata cache was not located.")

    graph_builds = False
    checker_matches = False
    observed_status = None
    observed_issue_types: list[str] = []
    known_repair_replays = None
    final_known_repair_compatible = None
    case = None
    if fixture_exists:
        try:
            case = load_synthetic_case(fixture_path)
            graph = build_graph_from_synthetic_case(case)
            report = check_graph(graph)
            graph_builds = True
            observed_status = report.status.value
            observed_issue_types = sorted(
                {issue.issue_type.value for issue in report.issues}
            )
            checker_matches = (
                report.status == spec.expected_initial_status
                and set(spec.expected_issue_types).issubset(
                    {issue.issue_type for issue in report.issues}
                )
            )
        except Exception as exc:
            warnings.append(f"Graph/checker verification failed: {type(exc).__name__}: {exc}")
    else:
        warnings.append(f"Fixture is missing: {fixture_path}")

    if spec.known_valid_repair:
        try:
            trace = replay_repair_plan(case, spec.known_valid_repair) if case else None
            known_repair_replays = trace is not None
            final_known_repair_compatible = bool(trace and trace.final_compatible)
        except Exception as exc:
            known_repair_replays = False
            final_known_repair_compatible = False
            warnings.append(f"Known repair replay failed: {type(exc).__name__}: {exc}")

    injection_log_exists = None
    injection_matches_case_diff = None
    if spec.modification_type != ModificationType.NONE:
        log_path = resolve_optional_manifest_path(spec.injection_log, manifest_path)
        injection_log_exists = bool(log_path and log_path.exists())
        if injection_log_exists and case is not None:
            try:
                log = json.loads(log_path.read_text(encoding="utf-8"))
                injection_matches_case_diff = _injection_evidence_matches(
                    spec,
                    case.model_dump(mode="json"),
                    log,
                    manifest_path,
                )
            except Exception as exc:
                injection_matches_case_diff = False
                warnings.append(
                    f"Injection evidence comparison failed: {type(exc).__name__}: {exc}"
                )
        elif not injection_log_exists:
            injection_matches_case_diff = False
            warnings.append("Modified case has no readable injection log.")

    if spec.manually_reviewed and not _human_record_has_review_evidence(
        Path(manifest_path).parent / "manual_review" / f"{spec.case_id}.json"
    ):
        warnings.append(
            "Manifest carries a legacy manually_reviewed flag, but the human record "
            "does not contain a reviewer, timestamp, and completed judgments."
        )

    return AutomatedReviewEvidence(
        case_id=spec.case_id,
        source_family_id=spec.source_family_id,
        source_url_present=bool(spec.source_url),
        source_version_present=bool(
            spec.source_pack_version_id or spec.source_version_id
        ),
        manifest_hash_present=bool(spec.source_manifest_sha256),
        fixture_exists=fixture_exists,
        metadata_cache_exists=metadata_cache_exists,
        graph_builds=graph_builds,
        checker_matches_expected=checker_matches,
        known_repair_replays=known_repair_replays,
        final_known_repair_compatible=final_known_repair_compatible,
        injection_log_exists=injection_log_exists,
        injection_matches_case_diff=injection_matches_case_diff,
        metadata_coverage_rate=spec.metadata_coverage_rate,
        observed_status=observed_status,
        observed_issue_types=observed_issue_types,
        warnings=warnings,
    )


def generate_review_queue(
    *,
    manifest_path: str | Path = "data/final_dataset/manifest.json",
    review_dir: str | Path = "data/final_dataset/manual_review",
    output_dir: str | Path = "results/final/review",
) -> ManualReviewSummary:
    """Generate objective evidence, migrate records, and write review summaries."""

    review_root = Path(review_dir)
    evidence_dir = review_root / "evidence"
    output = Path(output_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    specs = select_review_specs(manifest_path, review_dir=review_root)
    rows = []
    records: list[HumanReviewRecord] = []
    for spec in specs:
        evidence = generate_automated_evidence(spec, manifest_path=manifest_path)
        write_pretty_json(evidence_dir / f"{spec.case_id}.json", evidence)
        record_path = review_root / f"{spec.case_id}.json"
        record = _load_or_create_human_record(record_path, spec.case_id)
        if record.review_status == ReviewStatus.NOT_STARTED and evidence.ready:
            record = record.model_copy(
                update={"review_status": ReviewStatus.AUTOMATED_EVIDENCE_READY}
            )
        write_pretty_json(record_path, record)
        records.append(record)
        rows.append(
            {
                "case_id": spec.case_id,
                "source_type": spec.source_type.value,
                "size_category": spec.pack_size_category.value,
                "source_family_id": spec.source_family_id,
                "review_status": record.review_status.value,
                "automated_evidence_ready": evidence.ready,
                "human_review_required": record.review_status
                not in {ReviewStatus.HUMAN_REVIEWED, ReviewStatus.PUBLICATION_READY},
                "publication_ready": record.review_status
                == ReviewStatus.PUBLICATION_READY,
                "warning_count": len(evidence.warnings),
            }
        )

    summary = _summarize(specs, records)
    _write_csv(output / "review_queue.csv", rows)
    _write_csv(output / "manual_review_summary.csv", _summary_rows(summary))
    (output / "manual_review_summary.md").write_text(
        _format_summary_markdown(summary),
        encoding="utf-8",
    )
    return summary


def format_case_review_packet(
    case_id: str,
    *,
    manifest_path: str | Path = "data/final_dataset/manifest.json",
    review_dir: str | Path = "data/final_dataset/manual_review",
) -> str:
    """Return a compact packet with automated facts and pending judgments."""

    manifest = load_final_dataset_manifest(manifest_path)
    spec = next((item for item in manifest.cases if item.case_id == case_id), None)
    if spec is None:
        raise ValueError(f"Unknown final dataset case ID: {case_id}.")
    evidence = generate_automated_evidence(spec, manifest_path=manifest_path)
    record = _load_or_create_human_record(
        Path(review_dir) / f"{case_id}.json",
        case_id,
    )
    case = load_synthetic_case(resolve_final_case_path(spec, manifest_path))
    graph = build_graph_from_synthetic_case(case)
    report = check_graph(graph)
    solver = solve_weighted_case(case, max_solutions=4)
    explanation = build_explanation_report(
        case=case,
        graph_result=graph,
        initial_report=report,
        solver_result=solver,
    )
    log_path = resolve_optional_manifest_path(spec.injection_log, manifest_path)
    log_summary = "not applicable"
    if log_path and log_path.exists():
        log = json.loads(log_path.read_text(encoding="utf-8"))
        log_summary = str(log.get("description") or "recorded without description")
    known_actions = ", ".join(
        f"{action.action_type.value}:{action.target_mod_id}"
        for action in spec.known_valid_repair
    ) or "none"
    pending = [
        name for name, value in record.subjective_judgments().items() if value is None
    ]
    return "\n".join(
        [
            f"CASE: {spec.case_id}",
            f"Source: {spec.source_type.value} | family={spec.source_family_id}",
            f"Provenance: url={spec.source_url or 'none'} | version={spec.source_pack_version_id or spec.source_version_id or 'none'} | hash={spec.source_manifest_sha256 or 'none'}",
            f"Input: {spec.selected_mod_count} selected mods | {spec.required_edge_count} required edges | density={spec.required_edge_density:.3f} | depth={spec.maximum_required_depth}",
            f"Expected: status={spec.expected_initial_status.value} | issues={','.join(item.value for item in spec.expected_issue_types) or 'none'} | solver={spec.expected_solver_status.value}",
            f"Observed checker: status={report.status.value} | issues={','.join(evidence.observed_issue_types) or 'none'} | matches={evidence.checker_matches_expected}",
            f"Injection: {log_summary}",
            f"Known repair: {known_actions} | replay compatible={evidence.final_known_repair_compatible}",
            f"Observed solver: {solver.status.value} | actions={len(solver.actions)} | cost={solver.total_cost}",
            f"Explanation summary: {explanation.overall_summary}",
            f"Automated evidence ready: {evidence.ready} | warnings={len(evidence.warnings)}",
            f"Human review status: {record.review_status.value}",
            "Human judgment still required: " + (", ".join(pending) or "none"),
        ]
    )


def _load_or_create_human_record(path: Path, case_id: str) -> HumanReviewRecord:
    if not path.exists():
        return HumanReviewRecord(case_id=case_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return HumanReviewRecord.model_validate(payload)


def _metadata_cache_exists(spec: FinalDatasetCaseSpec, manifest_path: str | Path) -> bool:
    explicit = resolve_optional_manifest_path(spec.cached_metadata_path, manifest_path)
    if explicit is not None:
        return explicit.exists()
    if not spec.collection_method:
        return False
    cache_root = Path(manifest_path).resolve().parent / "metadata_cache"
    slug = (spec.source_pack_slug or "").lower()
    version = (spec.source_pack_version_id or "").lower()
    return any(
        slug in path.name.lower() and version in path.name.lower()
        for path in cache_root.rglob("*.json")
    )


def _injection_evidence_matches(
    spec: FinalDatasetCaseSpec,
    case_payload: dict[str, Any],
    log: dict[str, Any],
    manifest_path: str | Path,
) -> bool:
    if log.get("case_id") != spec.case_id or not str(log.get("description") or "").strip():
        return False
    logged_repair = log.get("known_inverse_repair") or []
    expected_repair = [
        action.model_dump(mode="json") for action in spec.known_valid_repair
    ]
    if logged_repair != expected_repair:
        return False
    parent_id = spec.parent_case_id or spec.original_case_id
    if not parent_id:
        return True
    manifest = load_final_dataset_manifest(manifest_path)
    parent = next((item for item in manifest.cases if item.case_id == parent_id), None)
    if parent is None:
        return False
    parent_payload = load_synthetic_case(
        resolve_final_case_path(parent, manifest_path)
    ).model_dump(mode="json")
    return parent_payload != case_payload and log.get("parent_case_id") == parent_id


def _human_record_has_review_evidence(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        record = _load_or_create_human_record(path, path.stem)
    except Exception:
        return False
    return bool(
        record.reviewer
        and record.reviewed_at
        and all(value is not None for value in record.subjective_judgments().values())
    )


def _summarize(
    specs: list[FinalDatasetCaseSpec],
    records: list[HumanReviewRecord],
) -> ManualReviewSummary:
    statuses = Counter(record.review_status.value for record in records)
    reviewed = sum(
        record.review_status
        in {ReviewStatus.HUMAN_REVIEWED, ReviewStatus.PUBLICATION_READY}
        for record in records
    )
    publication_ready = statuses[ReviewStatus.PUBLICATION_READY.value]
    rejected = statuses[ReviewStatus.REJECTED.value]
    return ManualReviewSummary(
        total_queued=len(records),
        automated_evidence_ready=statuses[
            ReviewStatus.AUTOMATED_EVIDENCE_READY.value
        ],
        human_reviewed=reviewed,
        publication_ready=publication_ready,
        rejected=rejected,
        remaining_review_count=len(records) - reviewed - rejected,
        status_counts=dict(sorted(statuses.items())),
        source_type_counts=dict(
            sorted(Counter(spec.source_type.value for spec in specs).items())
        ),
        size_category_counts=dict(
            sorted(Counter(spec.pack_size_category.value for spec in specs).items())
        ),
    )


def _summary_rows(summary: ManualReviewSummary) -> list[dict[str, object]]:
    rows = [
        {"dimension": "overall", "category": name, "count": value}
        for name, value in (
            ("total_queued", summary.total_queued),
            ("automated_evidence_ready", summary.automated_evidence_ready),
            ("human_reviewed", summary.human_reviewed),
            ("publication_ready", summary.publication_ready),
            ("rejected", summary.rejected),
            ("remaining_review_count", summary.remaining_review_count),
        )
    ]
    for dimension, values in (
        ("review_status", summary.status_counts),
        ("source_type", summary.source_type_counts),
        ("size_category", summary.size_category_counts),
    ):
        rows.extend(
            {"dimension": dimension, "category": key, "count": value}
            for key, value in values.items()
        )
    return rows


def _format_summary_markdown(summary: ManualReviewSummary) -> str:
    return "\n".join(
        [
            "# Manual Review Summary",
            "",
            f"- Total queued: {summary.total_queued}",
            f"- Automated evidence ready: {summary.automated_evidence_ready}",
            f"- Human reviewed: {summary.human_reviewed}",
            f"- Publication ready: {summary.publication_ready}",
            f"- Rejected: {summary.rejected}",
            f"- Remaining human review: {summary.remaining_review_count}",
            "",
            "All queued cases have machine-generated evidence where verification succeeds. "
            "Automated evidence is not a human judgment. Complete-manifest cases remain "
            "pending human publication review unless their records explicitly prove otherwise.",
            "",
        ]
    )


def _write_csv(path: Path, rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = list(rows[0]) if rows else ["note"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows or [{"note": "No review records."}])
    return path
