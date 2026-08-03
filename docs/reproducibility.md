# Reproducibility Notes

`results/final/` is the archived evidence snapshot from the completed evaluation. Its `reproducibility.json` records the Python version, search limits, weight profiles, dataset hashes, timing method, and original evaluation command set. One non-numerical privacy cleanup was made for public release: the absolute local `python_executable` path was shortened to `.venv\Scripts\python.exe`.

The archived `package_lock_sha256` identifies the dependency lock used for the original evaluation. The current `uv.lock` changed during GitHub cleanup because `pytest`, `matplotlib`, and the removed CLI framework were separated from normal runtime dependencies. The archived hash was intentionally not rewritten, and no final numerical result was regenerated.

Use the current commands in the root README and write reproduced output to `.artifacts/`. A new run is a reproduction attempt, not a replacement for the archived snapshot.
