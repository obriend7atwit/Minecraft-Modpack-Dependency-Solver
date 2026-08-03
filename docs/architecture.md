# Architecture

## Runtime Pipeline

All inputs are converted to the typed models in `models.py`; downstream graph and solver code never consumes raw API or archive structures directly.

```text
.mrpack / JSON / Modrinth URL / project list
                |
                v
        importers + metadata cache
                |
                v
           SyntheticCase
                |
                v
        NetworkX graph builder
                |
                v
      deterministic compatibility checker
                |
                v
       baseline or weighted plan search
                |
                v
      explanation + text/JSON exports
```

## Package Boundaries

- `models.py` defines stable projects, versions, dependencies, configurations, issues, and repair actions.
- `metadata/` normalizes Modrinth responses, loads synthetic cases, and provides small cache helpers.
- `importers/` handles JSON, `.mrpack`, Modrinth URLs, and project lists without modifying or installing packs.
- `graph/` creates the inspectable compatibility graph and graph summaries.
- `solver/checker.py` evaluates compatibility rules.
- `solver/baseline.py` provides the one-pass comparison method.
- `solver/weighted.py` performs bounded, deterministic complete-plan search using costs from `solver/costs.py`.
- `solver/explanations.py` translates issues and solver decisions into structured explanations.
- `final_gui/` coordinates the end-user workflow; it calls core APIs and contains no duplicate solver logic.
- `final_dataset/`, `evaluation/`, `analysis/`, and `final_reports/` support corpus validation and reproducible research outputs.

The normal GUI imports the models, importers, metadata cache, graph, solver, explanations, and export modules. It does not import evaluation dashboards or dataset review views. Research scripts under `scripts/` use the final dataset and reporting modules and should write exploratory results to `.artifacts/`.

## Data and Evidence

- `data/synthetic/` contains deterministic rule-focused inputs.
- `data/evaluation/` retains the earlier evaluation manifest and reduced cached-real fixtures still covered by regression tests and referenced by manifests.
- `data/experiments/` contains controlled profile experiment inputs.
- `data/final_dataset/` is the current versioned 158-case corpus. Its `metadata_cache/` is required for offline URL, project-list, and complete-manifest workflows.
- `results/final/` is the sole authoritative archived result snapshot and must not be overwritten during testing.

Complete cached manifests, reduced real-derived examples, modified controls, synthetic/generated topology cases, and quarantined cases are separate evidence categories. Metadata compatibility does not prove launch-time compatibility. Automated validation does not constitute human review.

## Interfaces

`uv run modpack-solver` and `python -m modpack_solver` launch the Tkinter GUI. The default screen presents input, analysis, concise results, exports, and an optional advanced details area. `uv run modpack-solver --smoke-test` runs the same orchestration without creating a window.

Research and review operations remain command-line tools in `scripts/`. Live Modrinth access is always explicit; normal tests, validation, and archived evaluation are offline.
