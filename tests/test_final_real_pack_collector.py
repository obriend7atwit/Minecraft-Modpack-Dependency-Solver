from io import BytesIO
import json
from zipfile import ZipFile

import httpx
import pytest

from modpack_solver.final_dataset.cache import ModrinthCacheMode
from modpack_solver.final_dataset.modrinth_pack_collector import (
    FileResolutionMethod,
    _get_many_by_ids,
    calculate_metadata_coverage,
    collect_full_modrinth_packs,
    extract_mrpack_index,
    resolve_modrinth_file,
)
from modpack_solver.final_dataset.expanded_corpus import _write_collected_real_cases
from modpack_solver.final_dataset.export import write_pretty_json
from modpack_solver.metadata.synthetic import load_synthetic_case


class FakeResponse:
    def __init__(self, *, payload=None, content=b""):
        self.payload = payload
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FailedResponse(FakeResponse):
    def __init__(self, path):
        super().__init__()
        self.path = path

    def raise_for_status(self):
        request = httpx.Request("GET", f"https://api.modrinth.com/v2{self.path}")
        response = httpx.Response(400, request=request)
        raise httpx.HTTPStatusError("invalid reference", request=request, response=response)


class ResolutionClient:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    def get(self, path, params=None):
        self.requests.append((path, params))
        value = self.responses.get(path)
        if value is None:
            return FailedResponse(path)
        return FakeResponse(payload=value)


class FakeClient:
    def __init__(self, archive, *, resolvable=True):
        self.archive = archive
        self.resolvable = resolvable
        self.requests = []

    def get(self, path, params=None):
        self.requests.append((path, params))
        if path == "/search":
            return FakeResponse(payload={"hits": [{"project_id": "pack1", "slug": "pack-one"}]})
        if path == "/project/pack1":
            return FakeResponse(payload={"id": "pack1", "slug": "pack-one", "title": "Pack One"})
        if path == "/project/pack1/version":
            return FakeResponse(
                payload=[
                    {
                        "id": "pack-version",
                        "files": [
                            {
                                "filename": "pack-one.mrpack",
                                "url": "https://cdn.example/pack-one.mrpack",
                                "primary": True,
                            }
                        ],
                    }
                ]
            )
        if path == "https://cdn.example/pack-one.mrpack":
            return FakeResponse(content=self.archive)
        if path == "/versions":
            return FakeResponse(
                payload=[
                    {
                        "id": "ver1ABCD",
                        "project_id": "mod1",
                        "version_number": "1.0.0",
                        "game_versions": ["1.20.1"],
                        "loaders": ["fabric"],
                        "dependencies": [],
                    }
                ]
            )
        if path == "/projects":
            return FakeResponse(
                payload=[{"id": "mod1", "slug": "mod-one", "title": "Mod One"}]
            )
        if path == "/version/ver1ABCD":
            return FakeResponse(
                payload={
                    "id": "ver1ABCD",
                    "project_id": "mod1",
                    "version_number": "1.0.0",
                    "game_versions": ["1.20.1"],
                    "loaders": ["fabric"],
                    "dependencies": [],
                }
            )
        if path == "/project/mod1":
            return FakeResponse(payload={"id": "mod1", "slug": "mod-one", "title": "Mod One"})
        raise AssertionError(f"Unexpected request: {path}")


def _archive(*, resolvable=True):
    download = (
        "https://cdn.modrinth.com/data/mod1/versions/ver1ABCD/mod.jar"
        if resolvable
        else "https://example.invalid/mod.jar"
    )
    payload = {
        "name": "Pack One",
        "dependencies": {"minecraft": "1.20.1", "fabric-loader": "0.15.0"},
        "files": [
            {
                "path": "mods/mod.jar",
                "hashes": {},
                "downloads": [download],
            }
        ],
    }
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("modrinth.index.json", json.dumps(payload))
    return buffer.getvalue(), payload


def test_mrpack_extraction_and_coverage_are_deterministic():
    archive, payload = _archive()
    assert extract_mrpack_index(archive) == payload
    assert calculate_metadata_coverage(payload, {"ver1ABCD"}) == (1, 0, 1.0)


def test_live_collection_uses_only_mrpack_and_writes_provenance(tmp_path):
    archive, _ = _archive()
    client = FakeClient(archive)
    summary = collect_full_modrinth_packs(
        output_dir=tmp_path,
        cache_dir=tmp_path / "cache",
        mode=ModrinthCacheMode.LIVE,
        target_source_packs=1,
        client=client,
    )
    assert len(summary.collected) == 1
    record = summary.collected[0]
    assert record.metadata_coverage_rate == 1.0
    assert (tmp_path / "original_real").exists()
    assert not list(tmp_path.rglob("*.mrpack"))
    assert not list(tmp_path.rglob("*.jar"))
    assert all(
        not str(path).lower().endswith(".jar")
        for path, _params in client.requests
    )

    offline = collect_full_modrinth_packs(
        output_dir=tmp_path,
        cache_dir=tmp_path / "cache",
        mode=ModrinthCacheMode.OFFLINE,
        target_source_packs=1,
    )
    assert len(offline.collected) == 1


def test_incomplete_pack_is_quarantined_with_reason(tmp_path):
    archive, _ = _archive(resolvable=False)
    summary = collect_full_modrinth_packs(
        output_dir=tmp_path,
        cache_dir=tmp_path / "cache",
        mode=ModrinthCacheMode.LIVE,
        target_source_packs=1,
        client=FakeClient(archive),
    )
    assert not summary.collected
    assert summary.quarantined
    assert list((tmp_path / "quarantine").glob("*.json"))


def test_only_checker_clean_collected_pack_is_promoted_with_inverse_variant(tmp_path):
    case = load_synthetic_case("data/synthetic/valid_modpack.json")
    case_path = tmp_path / "original_real" / "full-pack-one-v1.json"
    write_pretty_json(case_path, case)
    write_pretty_json(
        tmp_path / "metadata_cache" / "full_pack_collection.json",
        {
            "mode": "offline",
            "target_source_packs": 1,
            "collected": [
                {
                    "project_id": "pack1",
                    "slug": "pack-one",
                    "version_id": "v1",
                    "source_url": "https://modrinth.com/modpack/pack-one/version/v1",
                    "collected_at": "2026-01-01T00:00:00+00:00",
                    "source_manifest_sha256": "abc123",
                    "manifest_file_count": 2,
                    "resolved_mod_count": 2,
                    "unresolved_mod_count": 0,
                    "metadata_coverage_rate": 1.0,
                    "selected_mod_count": 2,
                    "pack_size_category": "small",
                    "required_edge_count": 1,
                    "maximum_required_depth": 1,
                    "normalized_case_path": str(case_path),
                    "provenance_path": str(
                        tmp_path / "original_real" / "full-pack-one-v1.provenance.json"
                    ),
                }
            ],
            "quarantined": {},
            "skipped": [],
        },
    )

    specs = _write_collected_real_cases(tmp_path)

    assert [spec.source_type.value for spec in specs] == [
        "original_real",
        "modified_real",
    ]
    assert specs[0].ground_truth_method.value == "original_control"
    assert specs[1].ground_truth_method.value == "inverse_injection"
    assert specs[1].known_valid_repair[0].action_type.value == "add_dependency"
    assert len(load_synthetic_case(case_path).config.selected_mods) == 2
    assert (
        len(
            load_synthetic_case(
                tmp_path / specs[1].fixture_path
            ).config.selected_mods
        )
        == 1
    )


@pytest.mark.parametrize("version_like", ["0.1.3", "1.1.1+1.17"])
def test_version_like_url_segment_uses_project_version_fallback(version_like):
    project_id = "projABCD"
    raw_version = {
        "id": "realABCD",
        "project_id": project_id,
        "version_number": version_like,
        "game_versions": ["1.20.1"],
        "loaders": ["fabric"],
        "dependencies": [],
        "files": [{"filename": "example.jar", "hashes": {}}],
    }
    client = ResolutionClient({f"/project/{project_id}/version": [raw_version]})
    item = {
        "path": "mods/example.jar",
        "downloads": [
            f"https://cdn.modrinth.com/data/{project_id}/versions/{version_like}/example.jar"
        ],
        "hashes": {},
    }

    resolved, record = resolve_modrinth_file(client, item)

    assert resolved == raw_version
    assert record.method == FileResolutionMethod.PROJECT_VERSION_MATCH
    assert not any(path.startswith("/version/") for path, _ in client.requests)


def test_valid_global_version_id_is_resolved_and_recorded():
    raw_version = {"id": "realABCD", "project_id": "projABCD"}
    client = ResolutionClient({"/version/realABCD": raw_version})
    item = {
        "path": "mods/example.jar",
        "downloads": [
            "https://cdn.modrinth.com/data/projABCD/versions/realABCD/example.jar"
        ],
        "hashes": {},
    }

    resolved, record = resolve_modrinth_file(client, item)

    assert resolved == raw_version
    assert record.method == FileResolutionMethod.GLOBAL_VERSION_LOOKUP


def test_hash_fallback_and_cache_reuse_do_not_fetch_jar():
    raw_version = {"id": "hashABCD", "project_id": "projABCD"}
    client = ResolutionClient({"/version_file/deadbeef": raw_version})
    item = {
        "path": "mods/example.jar",
        "downloads": ["https://example.invalid/example.jar"],
        "hashes": {"sha1": "deadbeef"},
    }
    cache = {}

    first, first_record = resolve_modrinth_file(client, item, resolution_cache=cache)
    request_count = len(client.requests)
    second, second_record = resolve_modrinth_file(client, item, resolution_cache=cache)

    assert first == second == raw_version
    assert first_record.method == second_record.method == FileResolutionMethod.FILE_HASH
    assert len(client.requests) == request_count
    assert "Reused" in second_record.messages[0]
    assert all(not path.endswith(".jar") for path, _ in client.requests)


def test_batch_lookup_keeps_successful_individual_results():
    client = ResolutionClient(
        {
            "/version/goodABCD": {"id": "goodABCD", "project_id": "projABCD"},
        }
    )

    values = _get_many_by_ids(
        client,
        "/versions",
        ["goodABCD", "bad0ABCD"],
        fallback_prefix="/version",
    )

    assert [value["id"] for value in values] == ["goodABCD"]


def test_fully_unresolved_file_has_auditable_record():
    client = ResolutionClient({})
    item = {
        "path": "mods/unknown.jar",
        "downloads": ["https://example.invalid/unknown.jar"],
        "hashes": {"sha1": "missing"},
    }

    resolved, record = resolve_modrinth_file(client, item)

    assert resolved is None
    assert record.method == FileResolutionMethod.UNRESOLVED
    assert not record.successful
    assert record.messages
