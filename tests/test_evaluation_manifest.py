from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest

from modpack_solver.evaluation import load_evaluation_manifest
from modpack_solver.metadata.synthetic import load_synthetic_case


MANIFEST_PATH = Path("data/evaluation/manifest.json")
VALID_FIXTURE = Path("data/synthetic/valid_modpack.json")


def test_default_manifest_loads() -> None:
    specs = load_evaluation_manifest(MANIFEST_PATH)

    assert specs


def test_manifest_contains_between_20_and_25_entries() -> None:
    specs = load_evaluation_manifest(MANIFEST_PATH)

    assert 20 <= len(specs) <= 25


def test_case_ids_are_unique() -> None:
    specs = load_evaluation_manifest(MANIFEST_PATH)

    case_ids = [spec.case_id for spec in specs]
    assert len(case_ids) == len(set(case_ids))


def test_every_fixture_exists_and_loads_as_synthetic_case() -> None:
    specs = load_evaluation_manifest(MANIFEST_PATH)

    for spec in specs:
        fixture_path = Path(spec.fixture)
        assert fixture_path.exists()
        case = load_synthetic_case(fixture_path)
        assert case.projects
        assert case.versions


def test_invalid_enum_values_fail_clearly() -> None:
    with _workspace_temp_dir() as raw_tmp_path:
        tmp_path = Path(raw_tmp_path)
        manifest_path = _write_manifest(
            tmp_path,
            [
                {
                    "case_id": "bad-enum",
                    "name": "Bad enum",
                    "fixture": "fixtures/case.json",
                    "source_type": "not_real",
                    "expected_initial_status": "compatible",
                    "expected_solver_status": "already_compatible",
                }
            ],
        )

        with pytest.raises(ValueError, match="Invalid evaluation manifest entry"):
            load_evaluation_manifest(manifest_path)


def test_duplicate_ids_fail_clearly() -> None:
    with _workspace_temp_dir() as raw_tmp_path:
        tmp_path = Path(raw_tmp_path)
        manifest_path = _write_manifest(
            tmp_path,
            [
                _valid_entry("duplicate-id", "fixtures/case.json"),
                _valid_entry("duplicate-id", "fixtures/case.json"),
            ],
        )

        with pytest.raises(ValueError, match="Duplicate evaluation case ID"):
            load_evaluation_manifest(manifest_path)


def test_invalid_cost_ranges_fail() -> None:
    with _workspace_temp_dir() as raw_tmp_path:
        tmp_path = Path(raw_tmp_path)
        manifest_path = _write_manifest(
            tmp_path,
            [
                {
                    **_valid_entry("bad-cost", "fixtures/case.json"),
                    "expected_min_cost": 5,
                    "expected_max_cost": 1,
                }
            ],
        )

        with pytest.raises(ValueError, match="Invalid evaluation manifest entry"):
            load_evaluation_manifest(manifest_path)


def test_invalid_preservation_rates_fail() -> None:
    with _workspace_temp_dir() as raw_tmp_path:
        tmp_path = Path(raw_tmp_path)
        manifest_path = _write_manifest(
            tmp_path,
            [
                {
                    **_valid_entry("bad-preservation", "fixtures/case.json"),
                    "expected_min_preservation_rate": 1.5,
                }
            ],
        )

        with pytest.raises(ValueError, match="Invalid evaluation manifest entry"):
            load_evaluation_manifest(manifest_path)


def test_relative_paths_resolve_from_manifest_location() -> None:
    with _workspace_temp_dir() as raw_tmp_path:
        tmp_path = Path(raw_tmp_path)
        manifest_dir = tmp_path / "nested"
        fixture_dir = tmp_path / "fixtures"
        fixture_dir.mkdir(parents=True)
        fixture_path = fixture_dir / "case.json"
        fixture_path.write_text(VALID_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

        manifest_path = manifest_dir / "manifest.json"
        manifest_dir.mkdir(parents=True)
        manifest_path.write_text(
            json.dumps([_valid_entry("relative-path", "../fixtures/case.json")], indent=2),
            encoding="utf-8",
        )

        specs = load_evaluation_manifest(manifest_path)

        assert Path(specs[0].fixture) == fixture_path.resolve()


def _write_manifest(tmp_path: Path, entries: list[dict]) -> Path:
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    (fixture_dir / "case.json").write_text(VALID_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return manifest_path


def _valid_entry(case_id: str, fixture: str) -> dict:
    return {
        "case_id": case_id,
        "name": case_id,
        "fixture": fixture,
        "source_type": "synthetic",
        "expected_initial_status": "compatible",
        "expected_solver_status": "already_compatible",
    }


@contextmanager
def _workspace_temp_dir():
    root = Path(".test-artifacts") / "pytest-temp"
    root.mkdir(parents=True, exist_ok=True)
    path = root / uuid.uuid4().hex
    path.mkdir()
    yield path
