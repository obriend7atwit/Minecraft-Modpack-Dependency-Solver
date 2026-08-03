# Repository Guidance

## Purpose

This is a Master's capstone project: **A Weighted Dependency Solver for Diagnosing and Repairing Minecraft Modpacks**. The central contribution is an explainable, minimum-disruption dependency repair algorithm for Fabric/Modrinth metadata.

## Preserve

- Keep models, metadata/import parsing, graph construction, checking, solving, explanations, UI, and evaluation separate.
- Preserve the default and preservation-focused repair weights, compatibility rules, final dataset, metadata cache, and archived numerical results unless a documented defect requires a change.
- Keep `.mrpack`, JSON, Modrinth URL, and project-list inputs working.
- Treat `results/final/` as immutable published evidence; direct test and exploratory output to `.artifacts/` or pytest temporary paths.
- Keep normal tests offline. Live API access must be explicitly enabled.
- Distinguish complete cached metadata, reduced real-derived cases, controlled injections/generated cases, and human-reviewed evidence.

## Development

```powershell
uv sync --extra dev --extra research
uv run pytest
uv run modpack-solver --smoke-test
uv run python scripts/run_final_evaluation.py --offline --validate-only
```

The package uses the `src/` layout. Do not add root import shims or `sitecustomize.py`. Runtime code should not depend on `pytest` or reporting/chart packages.

Use typed, focused functions and add deterministic tests for behavior changes. Prefer clarity over optimization. The GUI must call core APIs rather than duplicate solver logic, and long metadata/analysis work must not block the Tkinter event loop.

## Scope

Fabric and Modrinth are the supported ecosystem. Do not add automatic downloading, installation, launching, repaired-pack generation, Forge/CurseForge, crash-log NLP, or a heavy GUI framework unless the project scope is explicitly changed.

Metadata compatibility never guarantees that Minecraft will launch. Do not describe generated or modified cases as official public modpacks, and do not mark cases publication-ready without complete affirmative human review records.
