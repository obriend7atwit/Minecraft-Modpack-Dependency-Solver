"""Offline, conservative classification of excluded complete-manifest packs."""

from __future__ import annotations

import csv
from collections import Counter
from enum import Enum
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from modpack_solver.graph import build_graph_from_synthetic_case
from modpack_solver.metadata.synthetic import load_synthetic_case
from modpack_solver.solver.checker import check_graph


class ExclusionCause(str, Enum):
    ACTUAL_METADATA_INCOMPATIBILITY = "actual_metadata_incompatibility"
    OPTIONAL_OR_SIDE_SPECIFIC_DEPENDENCY = "optional_or_side_specific_dependency"
    LOADER_PROVIDED_DEPENDENCY = "loader_provided_dependency"
    EMBEDDED_OR_BUNDLED_DEPENDENCY = "embedded_or_bundled_dependency"
    INCOMPLETE_METADATA_COLLECTION = "incomplete_metadata_collection"
    FILE_RESOLUTION_FAILURE = "file_resolution_failure"
    VERSION_DECLARATION_MISMATCH = "version_declaration_mismatch"
    NORMALIZATION_LIMITATION = "normalization_limitation"
    UNSUPPORTED_METADATA_PATTERN = "unsupported_metadata_pattern"
    REQUIRES_MANUAL_REVIEW = "requires_manual_review"


class ExclusionReviewRecord(BaseModel):
    """Evidence and cautious classification for one excluded source pack."""

    model_config = ConfigDict(extra="forbid")

    source_pack: str
    source_version: str | None = None
    source_url: str | None = None
    normalized_case_path: str | None = None
    metadata_coverage_rate: float | None = None
    unresolved_files: int | None = None
    checker_issue_types: list[str] = Field(default_factory=list)
    checker_issue_count: int = 0
    dependency_types: list[str] = Field(default_factory=list)
    client_server_environment: dict[str, int] = Field(default_factory=dict)
    embedded_or_loader_supplied_status: str = "not established by cached metadata"
    likely_cause: ExclusionCause
    confidence: str
    manual_review_required: bool = True
    recovered: bool = False
    remains_quarantined: bool = True
    notes: list[str] = Field(default_factory=list)


class ExclusionReviewSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_exclusions: int
    incomplete_resolution: int
    metadata_semantics: int
    ambiguous: int
    recovered: int
    still_quarantined: int
    cause_counts: dict[str, int]
    records: list[ExclusionReviewRecord]


def review_excluded_manifests(
    dataset_dir: str | Path = "data/final_dataset",
    output_dir: str | Path = "results/final/exclusions",
) -> ExclusionReviewSummary:
    """Recheck cached exclusions and write paper-auditable CSV and Markdown."""

    dataset = Path(dataset_dir)
    output = Path(output_dir)
    collection = _load_json(dataset / "metadata_cache" / "full_pack_collection.json", {})
    collected_by_slug = {
        str(item.get("slug")): item for item in collection.get("collected", [])
    }
    records: list[ExclusionReviewRecord] = []

    for analysis_path in sorted((dataset / "quarantine").glob("analysis-*.json")):
        analysis = _load_json(analysis_path, {})
        slug = str(analysis.get("slug") or analysis_path.stem.removeprefix("analysis-"))
        collection_record = collected_by_slug.get(slug, {})
        records.append(
            _review_cached_analysis(
                dataset,
                analysis,
                collection_record,
            )
        )

    analyzed_slugs = {record.source_pack for record in records}
    for slug, reason in sorted((collection.get("quarantined") or {}).items()):
        if slug in analyzed_slugs:
            continue
        cached_candidates = list(
            (dataset / "metadata_cache" / "raw" / "pack_manifests").glob(f"{slug}-*.json")
        )
        notes = [str(reason)]
        if not cached_candidates:
            notes.append(
                "Offline reprocessing was not possible because the failed source manifest was not cached."
            )
        records.append(
            ExclusionReviewRecord(
                source_pack=str(slug),
                likely_cause=ExclusionCause.FILE_RESOLUTION_FAILURE,
                confidence="high",
                notes=notes,
            )
        )

    records.sort(key=lambda item: item.source_pack)
    cause_counts = Counter(record.likely_cause.value for record in records)
    incomplete_causes = {
        ExclusionCause.FILE_RESOLUTION_FAILURE,
        ExclusionCause.INCOMPLETE_METADATA_COLLECTION,
    }
    semantic_causes = {
        ExclusionCause.NORMALIZATION_LIMITATION,
        ExclusionCause.VERSION_DECLARATION_MISMATCH,
        ExclusionCause.OPTIONAL_OR_SIDE_SPECIFIC_DEPENDENCY,
        ExclusionCause.LOADER_PROVIDED_DEPENDENCY,
        ExclusionCause.EMBEDDED_OR_BUNDLED_DEPENDENCY,
        ExclusionCause.UNSUPPORTED_METADATA_PATTERN,
    }
    summary = ExclusionReviewSummary(
        total_exclusions=len(records),
        incomplete_resolution=sum(record.likely_cause in incomplete_causes for record in records),
        metadata_semantics=sum(record.likely_cause in semantic_causes for record in records),
        ambiguous=sum(
            record.likely_cause == ExclusionCause.REQUIRES_MANUAL_REVIEW for record in records
        ),
        recovered=sum(record.recovered for record in records),
        still_quarantined=sum(record.remains_quarantined for record in records),
        cause_counts=dict(sorted(cause_counts.items())),
        records=records,
    )
    _write_outputs(output, summary)
    return summary


def _review_cached_analysis(
    dataset: Path,
    analysis: dict,
    collection_record: dict,
) -> ExclusionReviewRecord:
    slug = str(analysis.get("slug") or "unknown")
    normalized_path = _resolve_repository_path(analysis.get("normalized_case_path"))
    notes: list[str] = []
    observed_issues = analysis.get("checker_errors") or []
    dependency_types: set[str] = set()
    environment: dict[str, int] = {}
    embedded_status = "not established by cached metadata"

    if normalized_path and normalized_path.exists():
        case = load_synthetic_case(normalized_path)
        report = check_graph(build_graph_from_synthetic_case(case))
        observed_issues = [issue.model_dump(mode="json") for issue in report.issues]
        affected = {
            mod_id
            for issue in observed_issues
            for mod_id in issue.get("affected_mod_ids", [])
        }
        for version in case.versions:
            for dependency in version.dependencies:
                if dependency.target_mod_id in affected:
                    dependency_types.add(dependency.dependency_type.value)
                    if dependency.dependency_type.value == "embedded":
                        embedded_status = "embedded dependency declared in normalized metadata"
    else:
        notes.append("The normalized case file is unavailable.")

    raw_manifest = _find_raw_manifest(dataset, slug, analysis.get("version_id"))
    if raw_manifest:
        environment = _summarize_environment(_load_json(raw_manifest, {}))
    else:
        notes.append("The cached raw source manifest is unavailable.")

    issue_types = sorted({str(issue.get("issue_type")) for issue in observed_issues})
    error_issue_types = sorted(
        {
            str(issue.get("issue_type"))
            for issue in observed_issues
            if str(issue.get("severity")) == "error"
        }
    )
    coverage = collection_record.get("metadata_coverage_rate")
    unresolved = collection_record.get("unresolved_mod_count")
    recovered = not any(str(issue.get("severity")) == "error" for issue in observed_issues)
    cause, confidence = classify_exclusion(
        issue_types=error_issue_types,
        metadata_coverage_rate=coverage,
        unresolved_files=unresolved,
        recovered=recovered,
    )
    if recovered:
        notes.append(
            "The current normalized case no longer has checker errors, but inclusion still requires independent ground truth and human review."
        )
    else:
        notes.append(
            "A checker finding is not evidence that the published pack fails at launch."
        )
    return ExclusionReviewRecord(
        source_pack=slug,
        source_version=analysis.get("version_id"),
        source_url=analysis.get("source_url"),
        normalized_case_path=str(normalized_path) if normalized_path else None,
        metadata_coverage_rate=coverage,
        unresolved_files=unresolved,
        checker_issue_types=issue_types,
        checker_issue_count=len(observed_issues),
        dependency_types=sorted(dependency_types),
        client_server_environment=environment,
        embedded_or_loader_supplied_status=embedded_status,
        likely_cause=cause,
        confidence=confidence,
        recovered=recovered,
        remains_quarantined=True,
        notes=notes,
    )


def classify_exclusion(
    *,
    issue_types: list[str],
    metadata_coverage_rate: float | None,
    unresolved_files: int | None,
    recovered: bool = False,
) -> tuple[ExclusionCause, str]:
    """Classify only what offline evidence supports; ambiguous cases stay ambiguous."""

    if recovered:
        return ExclusionCause.NORMALIZATION_LIMITATION, "medium"
    if (unresolved_files or 0) > 0 or (
        metadata_coverage_rate is not None and metadata_coverage_rate < 1.0
    ):
        return ExclusionCause.INCOMPLETE_METADATA_COLLECTION, "high"
    issue_set = set(issue_types)
    dependency_issues = {"unknown_dependency_target", "missing_dependency"}
    has_version_issue = "minecraft_version_mismatch" in issue_set
    has_dependency_issue = bool(issue_set & dependency_issues)
    if has_version_issue and has_dependency_issue:
        return ExclusionCause.REQUIRES_MANUAL_REVIEW, "low"
    if has_version_issue and issue_set <= {"minecraft_version_mismatch"}:
        return ExclusionCause.VERSION_DECLARATION_MISMATCH, "medium"
    if has_dependency_issue:
        return ExclusionCause.NORMALIZATION_LIMITATION, "medium"
    return ExclusionCause.REQUIRES_MANUAL_REVIEW, "low"


def _summarize_environment(payload: dict) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in payload.get("files") or []:
        if not isinstance(item, dict):
            continue
        environment = item.get("env") or {}
        client = environment.get("client", "unspecified")
        server = environment.get("server", "unspecified")
        counts[f"client={client};server={server}"] += 1
    return dict(sorted(counts.items()))


def _find_raw_manifest(dataset: Path, slug: str, version_id: object) -> Path | None:
    directory = dataset / "metadata_cache" / "raw" / "pack_manifests"
    if version_id:
        exact = directory / f"{slug}-{version_id}.json"
        if exact.exists():
            return exact
    candidates = sorted(directory.glob(f"{slug}-*.json"))
    return candidates[0] if candidates else None


def _resolve_repository_path(value: object) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    return path if path.is_absolute() else Path.cwd() / path


def _load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_outputs(output: Path, summary: ExclusionReviewSummary) -> None:
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "excluded_manifest_review.csv"
    fieldnames = [
        "source_pack",
        "source_version",
        "metadata_coverage_rate",
        "unresolved_files",
        "checker_issue_types",
        "checker_issue_count",
        "dependency_types",
        "client_server_environment",
        "likely_cause",
        "confidence",
        "manual_review_required",
        "recovered",
        "remains_quarantined",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in summary.records:
            row = record.model_dump(mode="json")
            row["checker_issue_types"] = ";".join(record.checker_issue_types)
            row["dependency_types"] = ";".join(record.dependency_types)
            row["client_server_environment"] = json.dumps(
                record.client_server_environment, sort_keys=True
            )
            writer.writerow({key: row.get(key) for key in fieldnames})

    cause_rows = "\n".join(
        f"| `{cause}` | {count} |" for cause, count in summary.cause_counts.items()
    )
    detail_rows = "\n".join(
        f"| {record.source_pack} | {record.metadata_coverage_rate if record.metadata_coverage_rate is not None else 'unknown'} | "
        f"{record.unresolved_files if record.unresolved_files is not None else 'unknown'} | "
        f"`{record.likely_cause.value}` | {record.confidence} | yes |"
        for record in summary.records
    )
    markdown = f"""# Excluded Complete-Manifest Review

This offline review classifies collection and normalization limitations. A checker finding is **not** treated as proof that a public modpack is broken or unable to launch.

| Measure | Count |
| --- | ---: |
| Total exclusions reviewed | {summary.total_exclusions} |
| Incomplete resolution or collection | {summary.incomplete_resolution} |
| Likely metadata-semantics or normalization cases | {summary.metadata_semantics} |
| Ambiguous cases | {summary.ambiguous} |
| Recovered after recheck | {summary.recovered} |
| Still quarantined | {summary.still_quarantined} |

## Cause Counts

| Conservative classification | Count |
| --- | ---: |
{cause_rows}

## Pack Review

| Source pack | Coverage | Unresolved files | Classification | Confidence | Manual review |
| --- | ---: | ---: | --- | --- | --- |
{detail_rows}

All recovered cases, if any, remain outside the scored corpus until metadata completeness, independent ground truth, automated validation, and human review are established. These findings belong in limitations and future-work discussion.
"""
    (output / "excluded_manifest_review.md").write_text(markdown, encoding="utf-8")
