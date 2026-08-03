from collections import Counter

from modpack_solver.final_dataset.manifest import (
    load_final_dataset_manifest,
    resolve_final_case_path,
)
from modpack_solver.final_dataset.sizing import classify_pack_size


MANIFEST = "data/final_dataset/manifest.json"


def test_final_manifest_loads_with_unique_existing_fixtures():
    manifest = load_final_dataset_manifest(MANIFEST)
    assert len(manifest.cases) >= 60
    assert len({case.case_id for case in manifest.cases}) == len(manifest.cases)
    assert all(resolve_final_case_path(case, MANIFEST).exists() for case in manifest.cases)


def test_manifest_size_categories_match_counts():
    manifest = load_final_dataset_manifest(MANIFEST)
    assert all(case.pack_size_category == classify_pack_size(case.selected_mod_count) for case in manifest.cases)
    counts = Counter(case.pack_size_category.value for case in manifest.cases)
    assert counts["large"] > 0
    assert counts["huge"] > 0


def test_modified_real_cases_reference_original_and_have_logs():
    manifest = load_final_dataset_manifest(MANIFEST)
    modified = [case for case in manifest.cases if case.source_type.value == "modified_real"]
    assert modified
    assert all(case.original_case_id for case in modified)
    assert all((resolve_final_case_path(case, MANIFEST).exists()) for case in modified)
    manifest_dir = __import__("pathlib").Path(MANIFEST).resolve().parent
    assert all((manifest_dir / case.injection_log).resolve().exists() for case in modified)


def test_final_manifest_has_expected_source_and_size_coverage():
    manifest = load_final_dataset_manifest(MANIFEST)
    sources = {case.source_type.value for case in manifest.cases}
    sizes = {case.pack_size_category.value for case in manifest.cases}
    assert {"synthetic", "original_real", "modified_real", "custom_modpack"} <= sources
    assert {"small", "medium", "large", "huge"} <= sizes
