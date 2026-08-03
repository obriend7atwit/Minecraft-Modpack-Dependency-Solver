"""Cache-first collection of complete Modrinth pack manifests without mod JARs."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
from urllib.parse import quote
from zipfile import BadZipFile, ZipFile

import httpx
from pydantic import BaseModel, ConfigDict, Field

from modpack_solver.final_dataset.cache import ModrinthCacheMode, save_cached_json
from modpack_solver.final_dataset.complexity import calculate_case_complexity
from modpack_solver.final_dataset.export import write_pretty_json
from modpack_solver.final_dataset.sizing import classify_pack_size
from modpack_solver.graph import build_graph_from_synthetic_case
from modpack_solver.importers.mrpack_importer import extract_modrinth_ids_from_downloads
from modpack_solver.metadata.modrinth import (
    MODRINTH_BASE_URL,
    USER_AGENT,
    normalize_modrinth_version,
)
from modpack_solver.models import (
    MetadataSource,
    ModProject,
    ModpackConfig,
    SelectedMod,
    SyntheticCase,
)
from modpack_solver.solver.checker import check_graph


class CollectedPackRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    slug: str
    version_id: str
    source_url: str
    collected_at: str
    source_manifest_sha256: str
    manifest_file_count: int
    resolved_mod_count: int
    unresolved_mod_count: int
    metadata_coverage_rate: float
    selected_mod_count: int
    pack_size_category: str
    required_edge_count: int
    maximum_required_depth: int
    normalized_case_path: str
    provenance_path: str
    file_resolution_path: str | None = None
    resolution_methods: dict[str, int] = Field(default_factory=dict)


class FileResolutionMethod(str, Enum):
    """Supported ways to map a manifest file to Modrinth version metadata."""

    EXPLICIT_VERSION_ID = "explicit_version_id"
    GLOBAL_VERSION_LOOKUP = "global_version_lookup"
    FILE_HASH = "file_hash_lookup"
    PROJECT_VERSION_MATCH = "project_version_match"
    DOWNLOAD_URL_MATCH = "download_url_match"
    UNRESOLVED = "unresolved"


class FileResolutionRecord(BaseModel):
    """Auditable outcome for one file in a complete Modrinth manifest."""

    model_config = ConfigDict(extra="forbid")

    file_path: str
    attempted_reference: str | None = None
    project_id: str | None = None
    version_id: str | None = None
    sha1: str | None = None
    sha512: str | None = None
    method: FileResolutionMethod
    successful: bool
    messages: list[str] = Field(default_factory=list)


class FullPackCollectionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ModrinthCacheMode
    target_source_packs: int
    collected: list[CollectedPackRecord] = Field(default_factory=list)
    quarantined: dict[str, str] = Field(default_factory=dict)
    skipped: list[str] = Field(default_factory=list)


def collect_full_modrinth_packs(
    *,
    output_dir: str | Path,
    cache_dir: str | Path,
    mode: ModrinthCacheMode,
    target_source_packs: int = 20,
    client: httpx.Client | None = None,
) -> FullPackCollectionSummary:
    """Collect normalized `.mrpack` manifests in explicit offline or live mode."""

    if target_source_packs < 1:
        raise ValueError("target_source_packs must be at least 1.")
    mode = ModrinthCacheMode(mode)
    output = Path(output_dir)
    cache = Path(cache_dir)
    index_path = cache / "full_pack_collection.json"
    if mode == ModrinthCacheMode.OFFLINE:
        if not index_path.exists():
            return FullPackCollectionSummary(
                mode=mode,
                target_source_packs=target_source_packs,
                skipped=["No cached full-pack collection index is available."],
            )
        return FullPackCollectionSummary.model_validate_json(
            index_path.read_text(encoding="utf-8")
        ).model_copy(update={"mode": mode})

    owns_client = client is None
    active_client = client or httpx.Client(
        base_url=MODRINTH_BASE_URL,
        headers={"User-Agent": USER_AGENT},
        timeout=30.0,
        follow_redirects=True,
    )
    summary = FullPackCollectionSummary(
        mode=mode,
        target_source_packs=target_source_packs,
    )
    try:
        hits = _discover_fabric_modpacks(active_client, target_source_packs * 3)
        for hit in hits:
            if len(summary.collected) >= target_source_packs:
                break
            project_id = str(hit.get("project_id") or hit.get("project_id") or "")
            slug = str(hit.get("slug") or project_id)
            if not project_id:
                summary.skipped.append("Search result without a project ID.")
                continue
            try:
                record = _collect_one_pack(
                    active_client,
                    output=output,
                    cache=cache,
                    project_id=project_id,
                    slug=slug,
                )
                summary.collected.append(record)
            except Exception as exc:
                reason = f"{type(exc).__name__}: {exc}"
                summary.quarantined[slug or project_id] = reason
                _write_quarantine_record(output, project_id, slug, reason)
    finally:
        if owns_client:
            active_client.close()
    write_pretty_json(index_path, summary)
    return summary


def extract_mrpack_index(archive_bytes: bytes) -> dict:
    """Extract the JSON index from an in-memory `.mrpack` archive."""

    try:
        with ZipFile(BytesIO(archive_bytes)) as archive:
            raw = archive.read("modrinth.index.json")
    except (BadZipFile, KeyError) as exc:
        raise ValueError("Downloaded .mrpack does not contain a valid modrinth.index.json.") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("modrinth.index.json is not valid UTF-8 JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("modrinth.index.json must contain an object.")
    return payload


def calculate_metadata_coverage(index_payload: dict, resolved_version_ids: set[str]) -> tuple[int, int, float]:
    """Return relevant file count, unresolved count, and coverage rate."""

    relevant = [
        item
        for item in index_payload.get("files", [])
        if isinstance(item, dict)
        and str(item.get("path") or "").lower().startswith("mods/")
        and str(item.get("path") or "").lower().endswith(".jar")
    ]
    resolved = 0
    for item in relevant:
        _, version_id = extract_modrinth_ids_from_downloads(item.get("downloads") or [])
        if version_id and version_id in resolved_version_ids:
            resolved += 1
    unresolved = len(relevant) - resolved
    coverage = resolved / len(relevant) if relevant else 0.0
    return len(relevant), unresolved, coverage


def _discover_fabric_modpacks(client, limit: int) -> list[dict]:
    payload = _get_json(
        client,
        "/search",
        params={
            "facets": json.dumps(
                [["project_type:modpack"], ["categories:fabric"]]
            ),
            "index": "downloads",
            "limit": min(limit, 100),
        },
    )
    hits = payload.get("hits") if isinstance(payload, dict) else None
    if not isinstance(hits, list):
        raise ValueError("Modrinth search did not return a hit list.")
    return [item for item in hits if isinstance(item, dict)]


def _collect_one_pack(
    client,
    *,
    output: Path,
    cache: Path,
    project_id: str,
    slug: str,
) -> CollectedPackRecord:
    raw_project = _get_json(client, f"/project/{quote(project_id)}")
    raw_versions = _get_json(client, f"/project/{quote(project_id)}/version")
    if not isinstance(raw_versions, list):
        raise ValueError("Pack version response must be a list.")
    pack_version, pack_file = _select_mrpack_file(raw_versions)
    archive_bytes = _get_bytes(client, pack_file["url"])
    index_payload = extract_mrpack_index(archive_bytes)
    manifest_digest = sha256(
        json.dumps(index_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    minecraft_version, loader = _pack_environment(index_payload)
    if loader != "fabric":
        raise ValueError(f"Unsupported loader '{loader or 'unknown'}'.")
    if not minecraft_version:
        raise ValueError("Pack manifest does not declare a Minecraft version.")

    projects = {}
    versions = {}
    selected_by_version = {}
    relevant_files = [
        item
        for item in index_payload.get("files", [])
        if isinstance(item, dict)
        and str(item.get("path") or "").lower().startswith("mods/")
        and str(item.get("path") or "").lower().endswith(".jar")
    ]
    candidate_version_ids: list[str] = []
    for item in relevant_files:
        _project_ref, version_ref = extract_modrinth_ids_from_downloads(
            item.get("downloads") or []
        )
        explicit_ref = item.get("version_id")
        reference = str(explicit_ref or version_ref or "")
        if _is_plausible_modrinth_id(reference):
            candidate_version_ids.append(reference)

    raw_version_values = _get_many_by_ids(
        client,
        "/versions",
        candidate_version_ids,
        fallback_prefix="/version",
    )
    raw_versions_by_id = {
        str(item.get("id")): item
        for item in raw_version_values
        if isinstance(item, dict) and item.get("id")
    }
    project_versions_cache: dict[str, list[dict]] = {}
    resolution_cache: dict[str, dict] = {}
    resolution_records: list[FileResolutionRecord] = []
    resolved_file_versions: list[dict] = []
    for item in relevant_files:
        raw_version, record = resolve_modrinth_file(
            client,
            item,
            raw_versions_by_id=raw_versions_by_id,
            project_versions_cache=project_versions_cache,
            resolution_cache=resolution_cache,
        )
        resolution_records.append(record)
        if raw_version is not None:
            resolved_file_versions.append(raw_version)
            raw_versions_by_id[str(raw_version["id"])] = raw_version

    project_ids = sorted({
        str(item.get("project_id"))
        for item in resolved_file_versions
        if item.get("project_id")
    })
    raw_project_values = _get_many_by_ids(
        client,
        "/projects",
        project_ids,
        fallback_prefix="/project",
    )
    raw_projects_by_id = {
        str(item.get("id")): item
        for item in raw_project_values
        if isinstance(item, dict) and item.get("id")
    }

    for raw_version in resolved_file_versions:
        project_ref = str(raw_version.get("project_id") or "")
        if not project_ref:
            continue
        raw_dependency = dict(raw_version)
        raw_dependency.setdefault("project_id", project_ref)
        version = normalize_modrinth_version(raw_dependency)
        versions[version.version_id] = version
        raw_mod_project = raw_projects_by_id.get(project_ref, {})
        projects[project_ref] = _normalize_project(raw_mod_project, project_ref)
        selected_by_version[version.version_id] = (
            SelectedMod(
                mod_id=project_ref,
                version_id=version.version_id,
                version_number=version.version_number,
            )
        )

    selected = list(selected_by_version.values())
    resolved_file_count = sum(record.successful for record in resolution_records)
    file_count = len(relevant_files)
    unresolved_count = max(0, file_count - resolved_file_count)
    coverage = resolved_file_count / file_count if file_count else 0.0
    if coverage < 0.90:
        raise ValueError(f"Metadata coverage {coverage:.1%} is below the 90% inclusion threshold.")

    case = SyntheticCase(
        config=ModpackConfig(
            minecraft_version=minecraft_version,
            loader=loader,
            selected_mods=selected,
        ),
        projects=sorted(projects.values(), key=lambda item: item.mod_id),
        versions=sorted(versions.values(), key=lambda item: (item.mod_id, item.version_id)),
    )
    graph_result = build_graph_from_synthetic_case(case)
    check_graph(graph_result)
    complexity = calculate_case_complexity(case, graph_result)

    version_id = str(pack_version["id"])
    safe_slug = _safe_name(slug)
    case_path = output / "original_real" / f"full-{safe_slug}-{_safe_name(version_id)}.json"
    provenance_path = output / "original_real" / f"full-{safe_slug}-{_safe_name(version_id)}.provenance.json"
    raw_manifest_path = cache / "raw" / "pack_manifests" / f"{safe_slug}-{_safe_name(version_id)}.json"
    resolution_path = (
        cache / "normalized" / "file_resolutions" / f"{safe_slug}-{_safe_name(version_id)}.json"
    )
    write_pretty_json(case_path, case)
    save_cached_json(raw_manifest_path, index_payload)
    write_pretty_json(
        resolution_path,
        [record.model_dump(mode="json") for record in resolution_records],
    )
    collected_at = datetime.now(timezone.utc).isoformat()
    source_url = f"https://modrinth.com/modpack/{slug}/version/{version_id}"
    provenance = {
        "project_id": project_id,
        "slug": slug,
        "version_id": version_id,
        "source_url": source_url,
        "collected_at": collected_at,
        "collection_method": "official_modrinth_api_mrpack_manifest_only",
        "source_manifest_sha256": manifest_digest,
        "manifest_file_count": file_count,
        "resolved_mod_count": resolved_file_count,
        "unresolved_mod_count": unresolved_count,
        "metadata_coverage_rate": coverage,
        "selected_mod_count": len(selected),
        "pack_size_category": classify_pack_size(len(selected)).value,
        "required_edge_count": complexity.required_edge_count,
        "maximum_required_depth": complexity.maximum_required_depth,
        "raw_archive_retained": False,
        "mod_jars_downloaded": False,
        "publication_ready": False,
        "manual_review_required": True,
        "pack_title": raw_project.get("title"),
        "file_resolution_path": str(resolution_path),
        "resolution_methods": _resolution_method_counts(resolution_records),
    }
    write_pretty_json(provenance_path, provenance)
    return CollectedPackRecord(
        **{
            key: provenance[key]
            for key in (
                "project_id",
                "slug",
                "version_id",
                "source_url",
                "collected_at",
                "source_manifest_sha256",
                "manifest_file_count",
                "resolved_mod_count",
                "unresolved_mod_count",
                "metadata_coverage_rate",
                "selected_mod_count",
                "pack_size_category",
                "required_edge_count",
                "maximum_required_depth",
            )
        },
        normalized_case_path=str(case_path),
        provenance_path=str(provenance_path),
        file_resolution_path=str(resolution_path),
        resolution_methods=_resolution_method_counts(resolution_records),
    )


def _select_mrpack_file(raw_versions: list[dict]) -> tuple[dict, dict]:
    for version in raw_versions:
        files = [
            item
            for item in version.get("files", [])
            if isinstance(item, dict)
            and (
                str(item.get("filename") or "").lower().endswith(".mrpack")
                or str(item.get("url") or "").lower().split("?")[0].endswith(".mrpack")
            )
        ]
        if files:
            files.sort(key=lambda item: (not bool(item.get("primary")), item.get("filename", "")))
            return version, files[0]
    raise ValueError("No published .mrpack file was found for this project.")


def _pack_environment(payload: dict) -> tuple[str | None, str | None]:
    dependencies = payload.get("dependencies") or {}
    if not isinstance(dependencies, dict):
        return None, None
    loader = "fabric" if "fabric-loader" in dependencies else None
    return dependencies.get("minecraft"), loader


def _resolve_version_by_hash(client, item: dict) -> str | None:
    payload = _resolve_version_payload_by_hash(client, item)
    version_id = payload.get("id") if payload else None
    return str(version_id) if version_id else None


def _resolve_version_payload_by_hash(client, item: dict) -> dict | None:
    hashes = item.get("hashes") or {}
    for algorithm in ("sha1", "sha512"):
        digest = hashes.get(algorithm)
        if not digest:
            continue
        try:
            payload = _get_json(
                client,
                f"/version_file/{quote(str(digest))}",
                params={"algorithm": algorithm},
            )
        except httpx.HTTPError:
            continue
        if isinstance(payload, dict) and payload.get("id"):
            return payload
    return None


def resolve_modrinth_file(
    client,
    item: dict,
    *,
    raw_versions_by_id: dict[str, dict] | None = None,
    project_versions_cache: dict[str, list[dict]] | None = None,
    resolution_cache: dict[str, dict] | None = None,
) -> tuple[dict | None, FileResolutionRecord]:
    """Resolve one manifest file without downloading the referenced mod JAR."""

    known_versions = raw_versions_by_id or {}
    project_cache = project_versions_cache if project_versions_cache is not None else {}
    successful_cache = resolution_cache if resolution_cache is not None else {}
    file_path = str(item.get("path") or "")
    hashes = item.get("hashes") or {}
    downloads = [str(value) for value in item.get("downloads") or []]
    parsed_project, parsed_version = extract_modrinth_ids_from_downloads(downloads)
    project_id = _optional_string(item.get("project_id")) or parsed_project
    explicit_version = _optional_string(item.get("version_id"))
    attempted_reference = explicit_version or parsed_version
    messages: list[str] = []
    cache_key = _file_resolution_cache_key(item)

    cached = successful_cache.get(cache_key)
    if cached:
        payload = cached.get("version") if isinstance(cached, dict) else None
        method_value = cached.get("method") if isinstance(cached, dict) else None
        if isinstance(payload, dict) and payload.get("id"):
            messages.append("Reused a successful in-memory fallback resolution.")
            return payload, _resolution_record(
                item,
                attempted_reference,
                project_id,
                payload,
                FileResolutionMethod(method_value or FileResolutionMethod.GLOBAL_VERSION_LOOKUP),
                messages,
            )

    candidate = explicit_version or parsed_version
    if candidate and _is_plausible_modrinth_id(candidate):
        method = (
            FileResolutionMethod.EXPLICIT_VERSION_ID
            if explicit_version
            else FileResolutionMethod.GLOBAL_VERSION_LOOKUP
        )
        payload = known_versions.get(candidate)
        if payload is None:
            try:
                value = _get_json(client, f"/version/{quote(candidate)}")
                payload = value if isinstance(value, dict) else None
            except (httpx.HTTPError, ValueError) as exc:
                messages.append(f"Global version lookup failed: {type(exc).__name__}.")
        if payload and payload.get("id"):
            return _successful_resolution(
                item, attempted_reference, project_id, payload, method, messages, successful_cache
            )
    elif candidate:
        messages.append(
            f"Skipped global lookup for non-ID version-like reference '{candidate}'."
        )

    payload = _resolve_version_payload_by_hash(client, item)
    if payload:
        return _successful_resolution(
            item,
            attempted_reference,
            project_id,
            payload,
            FileResolutionMethod.FILE_HASH,
            messages,
            successful_cache,
        )

    if project_id:
        project_versions = project_cache.get(project_id)
        if project_versions is None:
            try:
                value = _get_json(client, f"/project/{quote(project_id)}/version")
                project_versions = [entry for entry in value if isinstance(entry, dict)] if isinstance(value, list) else []
            except (httpx.HTTPError, ValueError) as exc:
                messages.append(f"Project-version lookup failed: {type(exc).__name__}.")
                project_versions = []
            project_cache[project_id] = project_versions
        payload, method = _match_project_version(item, candidate, project_versions)
        if payload is not None:
            return _successful_resolution(
                item, attempted_reference, project_id, payload, method, messages, successful_cache
            )

    messages.append("All supported metadata-only resolution methods were exhausted.")
    return None, _resolution_record(
        item,
        attempted_reference,
        project_id,
        None,
        FileResolutionMethod.UNRESOLVED,
        messages,
    )


def _match_project_version(
    item: dict,
    candidate: str | None,
    project_versions: list[dict],
) -> tuple[dict | None, FileResolutionMethod]:
    item_hashes = item.get("hashes") or {}
    item_downloads = set(str(value) for value in item.get("downloads") or [])
    item_filename = Path(str(item.get("path") or "")).name
    for version in project_versions:
        files = [value for value in version.get("files") or [] if isinstance(value, dict)]
        if candidate and str(version.get("version_number") or "") == candidate:
            return version, FileResolutionMethod.PROJECT_VERSION_MATCH
        for file_metadata in files:
            if any(
                digest and file_metadata.get("hashes", {}).get(algorithm) == digest
                for algorithm, digest in item_hashes.items()
            ):
                return version, FileResolutionMethod.PROJECT_VERSION_MATCH
            if item_filename and str(file_metadata.get("filename") or "") == item_filename:
                return version, FileResolutionMethod.PROJECT_VERSION_MATCH
            if str(file_metadata.get("url") or "") in item_downloads:
                return version, FileResolutionMethod.DOWNLOAD_URL_MATCH
    return None, FileResolutionMethod.UNRESOLVED


def _successful_resolution(
    item: dict,
    attempted_reference: str | None,
    project_id: str | None,
    payload: dict,
    method: FileResolutionMethod,
    messages: list[str],
    cache: dict[str, dict],
) -> tuple[dict, FileResolutionRecord]:
    cache[_file_resolution_cache_key(item)] = {
        "version": payload,
        "method": method.value,
    }
    return payload, _resolution_record(
        item, attempted_reference, project_id, payload, method, messages
    )


def _resolution_record(
    item: dict,
    attempted_reference: str | None,
    project_id: str | None,
    payload: dict | None,
    method: FileResolutionMethod,
    messages: list[str],
) -> FileResolutionRecord:
    hashes = item.get("hashes") or {}
    return FileResolutionRecord(
        file_path=str(item.get("path") or ""),
        attempted_reference=attempted_reference,
        project_id=str(payload.get("project_id") or project_id or "") or None if payload else project_id,
        version_id=str(payload.get("id")) if payload and payload.get("id") else None,
        sha1=_optional_string(hashes.get("sha1")),
        sha512=_optional_string(hashes.get("sha512")),
        method=method,
        successful=payload is not None,
        messages=list(messages),
    )


def _file_resolution_cache_key(item: dict) -> str:
    stable = {
        "path": item.get("path"),
        "hashes": item.get("hashes") or {},
        "downloads": item.get("downloads") or [],
    }
    return sha256(json.dumps(stable, sort_keys=True).encode("utf-8")).hexdigest()


def _is_plausible_modrinth_id(value: str | None) -> bool:
    return bool(value and re.fullmatch(r"[A-Za-z0-9]{8}", value))


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _resolution_method_counts(records: list[FileResolutionRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.method.value] = counts.get(record.method.value, 0) + 1
    return counts


def _normalize_project(raw: dict, project_id: str) -> ModProject:
    return ModProject(
        mod_id=project_id,
        name=str(raw.get("title") or raw.get("slug") or project_id),
        slug=raw.get("slug"),
        source=MetadataSource.MODRINTH,
        author=raw.get("author"),
        description=raw.get("description"),
    )


def _get_json(client, path: str, params: dict | None = None):
    response = client.get(path, params=params)
    response.raise_for_status()
    return response.json()


def _get_many_by_ids(
    client,
    path: str,
    identifiers: list[str],
    *,
    fallback_prefix: str,
) -> list[dict]:
    unique_ids = sorted(set(identifiers))
    values: list[dict] = []
    for start in range(0, len(unique_ids), 100):
        batch = unique_ids[start : start + 100]
        try:
            payload = _get_json(client, path, params={"ids": json.dumps(batch)})
            if not isinstance(payload, list):
                raise ValueError(f"{path} did not return a list.")
            values.extend(item for item in payload if isinstance(item, dict))
        except (httpx.HTTPError, ValueError):
            for identifier in batch:
                try:
                    item = _get_json(client, f"{fallback_prefix}/{quote(identifier)}")
                except (httpx.HTTPError, ValueError):
                    continue
                if isinstance(item, dict):
                    values.append(item)
    return values


def _get_bytes(client, url: str) -> bytes:
    response = client.get(url)
    response.raise_for_status()
    return bytes(response.content)


def _write_quarantine_record(
    output: Path,
    project_id: str,
    slug: str,
    reason: str,
) -> None:
    write_pretty_json(
        output / "quarantine" / f"{_safe_name(slug or project_id)}.json",
        {
            "project_id": project_id,
            "slug": slug,
            "rejection_reason": reason,
            "publication_ready": False,
        },
    )


def _safe_name(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in "._-" else "_"
        for character in value
    ).strip("_") or "unknown"
