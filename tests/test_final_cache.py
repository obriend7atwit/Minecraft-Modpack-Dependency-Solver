import pytest

from modpack_solver.final_dataset import cache
from modpack_solver.final_dataset.cache import (
    ModrinthCacheMode,
    fetch_or_load_project,
    load_cached_json,
    save_cached_json,
)


def test_cache_save_load_round_trip(tmp_path):
    path = save_cached_json(tmp_path / "nested" / "data.json", {"b": 2, "a": 1})
    assert load_cached_json(path) == {"a": 1, "b": 2}


def test_offline_missing_cache_fails_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_fetch_json", lambda *args, **kwargs: pytest.fail("network called"))
    with pytest.raises(FileNotFoundError, match="No cached"):
        fetch_or_load_project("missing", cache_dir=tmp_path, mode=ModrinthCacheMode.OFFLINE)


def test_live_fetch_is_cached_and_not_repeated(tmp_path, monkeypatch):
    calls = []

    def fake_fetch(path, params=None):
        calls.append(path)
        return {"id": "project-id", "slug": "demo", "title": "Demo"}

    monkeypatch.setattr(cache, "_fetch_json", fake_fetch)
    first = fetch_or_load_project("demo", cache_dir=tmp_path, mode=ModrinthCacheMode.LIVE)
    second = fetch_or_load_project("demo", cache_dir=tmp_path, mode=ModrinthCacheMode.LIVE)
    assert first == second
    assert calls == ["/project/demo"]
    assert (tmp_path / "collection_index.json").exists()


def test_live_fetch_can_force_refresh(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(cache, "_fetch_json", lambda *args, **kwargs: calls.append(1) or {"id": "id"})
    fetch_or_load_project("demo", cache_dir=tmp_path, mode=ModrinthCacheMode.LIVE)
    fetch_or_load_project("demo", cache_dir=tmp_path, mode=ModrinthCacheMode.LIVE, force_refresh=True)
    assert len(calls) == 2
