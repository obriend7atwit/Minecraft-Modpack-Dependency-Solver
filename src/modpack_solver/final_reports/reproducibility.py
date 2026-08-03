"""Generate an auditable environment, dataset, command, and checksum freeze."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import platform
from pathlib import Path
import subprocess
import sys

from modpack_solver.solver.profiles import get_weight_profile
from modpack_solver.final_dataset.manifest import load_final_dataset_manifest
from modpack_solver.solver import SearchLimits


FINAL_COMMANDS = [
    "uv run pytest",
    "uv run python scripts/run_final_evaluation.py --offline --manifest data/final_dataset/manifest.json --output-dir .artifacts/final-evaluation --runtime-repetitions 3",
    "uv run python scripts/run_search_scaling_experiment.py --offline --output-dir .artifacts/search-scaling --runtime-repetitions 3",
    "uv run python scripts/run_manual_review.py --summary",
    "uv run modpack-solver --smoke-test",
    "uv run pytest -m stress",
]


def generate_reproducibility_freeze(
    *,
    output_dir: str | Path = "results/final",
    manifest_path: str | Path = "data/final_dataset/manifest.json",
    test_result: str = "not recorded",
    legacy_evaluation_result: str = "not recorded",
    expanded_evaluation_result: str = "not recorded",
) -> dict:
    """Write reproducibility metadata without copying API caches or mod files."""

    root = Path.cwd()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    manifest_file = Path(manifest_path)
    manifest = load_final_dataset_manifest(manifest_file)
    final_run = _load_json(output / "evaluation" / "final_results.json", {})
    git_commit, clean, git_note = _git_state(root)
    collection_index = Path("data/final_dataset/metadata_cache/full_pack_collection.json")
    review_counts = Counter(case.review_status for case in manifest.cases)
    record = {
        "evaluation_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit_hash": git_commit,
        "working_tree_clean": clean,
        "git_status_note": git_note,
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "operating_system": platform.platform(),
        "architecture": platform.machine(),
        "python_executable": sys.executable,
        "package_lock_file": "uv.lock",
        "package_lock_sha256": file_sha256(Path("uv.lock")),
        "dataset_name": manifest.dataset_name,
        "dataset_version": manifest.dataset_version,
        "manifest_path": manifest_file.as_posix(),
        "manifest_sha256": file_sha256(manifest_file),
        "manifest_v1_sha256": file_sha256(Path("data/final_dataset/manifest_v1.json")),
        "cache_index_path": collection_index.as_posix(),
        "cache_index_sha256": file_sha256(collection_index),
        "case_count": len(manifest.cases),
        "source_family_count": len({case.source_family_id for case in manifest.cases}),
        "review_status_counts": dict(sorted(review_counts.items())),
        "commands": FINAL_COMMANDS,
        "runtime_repetitions": final_run.get("runtime_repetitions", 3),
        "warmup_runs": final_run.get("warmup_runs", 1),
        "timer": final_run.get("timer", "time.perf_counter"),
        "timing_scope": final_run.get("timing_scope", "algorithm_only"),
        "search_limits": SearchLimits().model_dump(mode="json"),
        "weight_profiles": {
            profile_id: get_weight_profile(profile_id).weights.model_dump(mode="json")
            for profile_id in ("default", "preservation")
        },
        "test_result": test_result,
        "legacy_evaluation_result": legacy_evaluation_result,
        "expanded_evaluation_result": expanded_evaluation_result,
        "metadata_cache_location": "data/final_dataset/metadata_cache",
        "metadata_cache_copied": False,
        "mod_jars_frozen": False,
    }
    json_path = output / "reproducibility.json"
    json_path.write_text(
        json.dumps(record, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    checksum_paths = _checksum_targets(output)
    checksum_lines = [
        f"{file_sha256(path)}  {path.as_posix()}" for path in checksum_paths
    ]
    (output / "checksums.sha256").write_text(
        "\n".join(checksum_lines) + "\n", encoding="utf-8"
    )
    _write_markdown(output / "REPRODUCIBILITY.md", record, len(checksum_paths))
    return record


def file_sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_state(root: Path) -> tuple[str | None, bool | None, str]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        clean = not bool(status.strip())
        note = "Working tree was clean." if clean else "Working tree had uncommitted changes."
        return commit, clean, note
    except (OSError, subprocess.CalledProcessError) as exc:
        return None, None, f"Git state could not be read in this workspace: {type(exc).__name__}. Commit before publication and regenerate this record."


def _checksum_targets(output: Path) -> list[Path]:
    explicit = [
        Path("uv.lock"),
        Path("data/final_dataset/manifest.json"),
        Path("data/final_dataset/manifest_v1.json"),
        Path("data/final_dataset/search_scaling_manifest.json"),
        Path("data/final_dataset/seed_modpacks.json"),
        Path("data/final_dataset/seed_projects.json"),
        Path("data/final_dataset/metadata_cache/full_pack_collection.json"),
        output / "evaluation" / "final_results.json",
        output / "evaluation" / "final_results.csv",
        output / "search_scaling" / "search_scaling_results.json",
        output / "search_scaling" / "search_scaling_results.csv",
        output / "reports" / "final_evaluation_summary.md",
        output / "reports" / "implementation_report.md",
        output / "review" / "manual_review_summary.csv",
        output / "review" / "manual_review_summary.md",
        output / "exclusions" / "excluded_manifest_review.csv",
        output / "exclusions" / "excluded_manifest_review.md",
    ]
    paper = list((output / "paper").glob("*")) if (output / "paper").exists() else []
    valid_suffixes = {".json", ".csv", ".md", ".tex", ".png"}
    return sorted(
        {
            path
            for path in explicit + paper
            if path.exists() and path.is_file() and path.suffix.lower() in valid_suffixes
        },
        key=lambda path: path.as_posix(),
    )


def _load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_markdown(path: Path, record: dict, checksum_count: int) -> None:
    clean_value = (
        "unknown" if record["working_tree_clean"] is None else str(record["working_tree_clean"]).lower()
    )
    commands = "\n".join(f"- `{command}`" for command in record["commands"])
    warning = ""
    if record["working_tree_clean"] is not True:
        warning = (
            "\n> Publication warning: the Git commit/clean state is not proven. Commit the final files and regenerate this freeze before citing immutable results.\n"
        )
    text = f"""# Final Reproducibility Record

Generated at `{record['evaluation_timestamp_utc']}` from dataset `{record['dataset_version']}`.
{warning}
| Field | Recorded value |
| --- | --- |
| Git commit | `{record['git_commit_hash'] or 'unavailable'}` |
| Working tree clean | `{clean_value}` |
| Python | `{record['python_version']}` ({record['python_implementation']}) |
| Operating system | `{record['operating_system']}` |
| Architecture | `{record['architecture']}` |
| Main manifest SHA-256 | `{record['manifest_sha256']}` |
| Version 1 manifest SHA-256 | `{record['manifest_v1_sha256']}` |
| Cases / source families | {record['case_count']} / {record['source_family_count']} |
| Timing | {record['warmup_runs']} warm-up, {record['runtime_repetitions']} measured repetitions, `{record['timer']}`, {record['timing_scope']} |
| Tests | {record['test_result']} |
| Legacy evaluation | {record['legacy_evaluation_result']} |
| Expanded evaluation | {record['expanded_evaluation_result']} |

Git note: {record['git_status_note']}

## Commands

{commands}

## Checksums

`checksums.sha256` records {checksum_count} dataset, configuration, result, table, and figure files. The metadata cache is referenced by its collection-index hash rather than duplicated. No mod JARs are copied or frozen.
"""
    path.write_text(text, encoding="utf-8")
