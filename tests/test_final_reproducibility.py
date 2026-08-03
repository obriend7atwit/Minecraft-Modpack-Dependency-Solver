import json
from pathlib import Path

from modpack_solver.final_reports.reproducibility import (
    file_sha256,
    generate_reproducibility_freeze,
)


def test_manifest_hash_is_stable():
    path = Path("data/final_dataset/manifest.json")
    assert file_sha256(path) == file_sha256(path)
    assert len(file_sha256(path) or "") == 64


def test_reproducibility_record_contains_environment_commands_and_checksums(tmp_path):
    output = tmp_path / "final"
    record = generate_reproducibility_freeze(
        output_dir=output,
        test_result="focused tests passed",
        legacy_evaluation_result="not run in unit test",
        expanded_evaluation_result="not run in unit test",
    )

    saved = json.loads((output / "reproducibility.json").read_text(encoding="utf-8"))
    assert saved["manifest_sha256"] == record["manifest_sha256"]
    assert saved["python_version"]
    assert saved["commands"]
    assert saved["runtime_repetitions"] >= 1
    assert saved["weight_profiles"]["default"]
    checksums = (output / "checksums.sha256").read_text(encoding="utf-8")
    assert "data/final_dataset/manifest.json" in checksums
    markdown = (output / "REPRODUCIBILITY.md").read_text(encoding="utf-8")
    assert "No mod JARs" in markdown
