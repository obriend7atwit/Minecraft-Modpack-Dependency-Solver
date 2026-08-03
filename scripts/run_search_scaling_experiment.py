"""Run the separate deterministic search-state scaling supplement."""

from __future__ import annotations

import argparse

from modpack_solver.final_dataset.search_scaling import (
    generate_search_scaling_dataset,
    run_search_scaling_experiment,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        default="data/final_dataset/search_scaling_manifest.json",
    )
    parser.add_argument("--output-dir", default="results/final/search_scaling")
    parser.add_argument("--runtime-repetitions", type=int, default=3)
    parser.add_argument("--offline", action="store_true", default=True)
    parser.add_argument("--regenerate", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.regenerate:
        generate_search_scaling_dataset("data/final_dataset")
    run = run_search_scaling_experiment(
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        runtime_repetitions=args.runtime_repetitions,
        offline=True,
    )
    print("SEARCH SCALING EXPERIMENT")
    for item in run.results:
        print(
            f"{item.case_id}: status={item.observed_status.value}, "
            f"states={item.states_expanded}, median={item.median_runtime_seconds * 1000:.3f} ms, "
            f"target={item.target_min_states}-{item.target_max_states}, correct={item.outcome_correct}"
        )
    print(f"All outcomes correct: {run.all_outcomes_correct}")
    print(f"All target ranges met: {run.all_target_ranges_met}")
    print(f"Outputs: {args.output_dir}")
    return 0 if run.all_outcomes_correct and run.all_target_ranges_met else 1


if __name__ == "__main__":
    raise SystemExit(main())
