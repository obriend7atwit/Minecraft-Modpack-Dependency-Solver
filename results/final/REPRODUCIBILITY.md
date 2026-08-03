# Final Reproducibility Record

Generated at `2026-07-21T18:09:06.394722+00:00` from dataset `2.0.0`.

> Publication warning: the Git commit/clean state is not proven. Commit the final files and regenerate this freeze before citing immutable results.

| Field | Recorded value |
| --- | --- |
| Git commit | `unavailable` |
| Working tree clean | `unknown` |
| Python | `3.14.3` (CPython) |
| Operating system | `Windows-11-10.0.26200-SP0` |
| Architecture | `AMD64` |
| Main manifest SHA-256 | `a02a919357a73f0f35904874cb8cd61617c2d4a3dfbf539036f29db0bf52abdc` |
| Version 1 manifest SHA-256 | `7ec9981fdfdbf44361cf4b61931efcf310b7a61db785803e5786be773f35a3e5` |
| Cases / source families | 158 / 89 |
| Timing | 1 warm-up, 3 measured repetitions, `time.perf_counter`, algorithm_only |
| Tests | 353 passed, 1 live test skipped, 1 stress test deselected |
| Legacy evaluation | 25/25 strict evaluation passed; 64/64 manifest_v1 regression passed |
| Expanded evaluation | 158/158 validation passed; baseline 91/104; weighted default 104/104; preservation 104/104 |

Git note: Git state could not be read in this workspace: CalledProcessError. Commit before publication and regenerate this record.

## Commands

- `uv run pytest`
- `uv run python run_evaluation.py`
- `uv run python run_final_evaluation.py --offline --manifest data/final_dataset/manifest_v1.json --output-dir results/final_v1_regression --runtime-repetitions 1`
- `uv run python run_final_evaluation.py --offline --manifest data/final_dataset/manifest.json --output-dir results/final --runtime-repetitions 3`
- `uv run python run_search_scaling_experiment.py --offline --output-dir results/final/search_scaling --runtime-repetitions 3`
- `uv run python run_manual_review.py --summary`
- `uv run python final_gui.py --smoke-test`
- `uv run python demo_final_system_readable.py`
- `uv run pytest -m stress`

## Checksums

`checksums.sha256` records 37 dataset, configuration, result, table, and figure files. The metadata cache is referenced by its collection-index hash rather than duplicated. No mod JARs are copied or frozen.
