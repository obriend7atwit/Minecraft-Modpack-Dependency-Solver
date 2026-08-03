"""Launch the desktop modpack repair workflow or run its headless smoke test."""

from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="modpack-solver",
        description="Diagnose Fabric modpack metadata and recommend a minimum-disruption repair plan.",
    )
    parser.add_argument("--smoke-test", action="store_true", help="Run the display-free end-to-end workflow.")
    parser.add_argument("--allow-live", action="store_true", help="Allow cache-first requests to the Modrinth API.")
    parser.add_argument("--cache-dir", default="data/final_dataset/metadata_cache")
    parser.add_argument("--sample", help="Load a built-in JSON fixture when the GUI opens.")
    return parser


def run_smoke_test() -> int:
    from modpack_solver.final_gui.exports import build_json_repair_report, build_text_repair_report
    from modpack_solver.final_gui.presenter import analyze_loaded_case, build_result_summary, load_builtin_sample, load_dataset_case
    from modpack_solver.final_gui.state import FinalGuiState

    state = FinalGuiState()
    load_builtin_sample(state, "missing_required_dependency.json")
    analyze_loaded_case(state)
    summary = build_result_summary(state)
    text_report = build_text_repair_report(state)
    json_report = build_json_repair_report(state)
    if summary.status != "repair_found" or "WEIGHTED REPAIR PLAN" not in text_report or "solver_result" not in json_report:
        raise RuntimeError("The built-in repair workflow did not produce the expected output.")
    load_dataset_case(state, "real-fo-missing-fabric-api")
    analyze_loaded_case(state)
    if state.solver_result is None or state.explanation_report is None:
        raise RuntimeError("The final-dataset workflow did not complete.")
    print("Display-free GUI smoke test passed.")
    print("Built-in and final-dataset inputs completed graph, checker, solver, explanation, and export workflows.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.smoke_test:
        return run_smoke_test()
    from modpack_solver.final_gui.app import launch_final_gui

    launch_final_gui(offline=not args.allow_live, cache_dir=Path(args.cache_dir), sample=args.sample)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
