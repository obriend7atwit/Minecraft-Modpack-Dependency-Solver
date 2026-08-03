"""Run the final offline dataset comparison and generate publication artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from modpack_solver.final_dataset.validation import validate_final_dataset
from modpack_solver.final_reports import FinalEvaluationSystem, run_final_evaluation
from modpack_solver.final_reports.models import FinalEvaluationRun
from modpack_solver.final_reports.paper import generate_paper_outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="data/final_dataset/manifest.json")
    parser.add_argument("--output-dir", default="results/final")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", default=True)
    mode.add_argument("--allow-live", action="store_true")
    parser.add_argument("--max-cases", type=int)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--profile", action="append", choices=["default", "preservation"], default=[])
    parser.add_argument("--runtime-repetitions", type=int, default=3)
    parser.add_argument("--skip-charts", action="store_true")
    parser.add_argument("--show-details", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--paper-outputs-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.validate_only and args.paper_outputs_only:
        raise ValueError("--validate-only and --paper-outputs-only cannot be combined.")
    if args.validate_only:
        validation = validate_final_dataset(args.manifest, offline=True)
        print(
            f"Dataset validation: {validation.passed_cases}/{validation.total_cases} passed"
        )
        if validation.failures:
            for case_id, failures in validation.failures.items():
                print(f"  - {case_id}: {'; '.join(failures)}")
        return 0 if validation.passed else 1
    if args.paper_outputs_only:
        saved_path = Path(args.output_dir) / "evaluation" / "final_results.json"
        if not saved_path.exists():
            raise FileNotFoundError(
                f"Saved evaluation '{saved_path}' was not found; run the evaluation first."
            )
        run = FinalEvaluationRun.model_validate_json(
            saved_path.read_text(encoding="utf-8")
        )
        run.manifest_path = args.manifest
        outputs = generate_paper_outputs(run, args.output_dir)
        print(f"Generated {len(outputs)} paper outputs in {Path(args.output_dir) / 'paper'}")
        return 0
    profiles = args.profile or ["default", "preservation"]
    run = run_final_evaluation(
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        offline=not args.allow_live,
        allow_live=args.allow_live,
        max_cases=args.max_cases,
        case_ids=args.case_id or None,
        profile_ids=profiles,
        runtime_repetitions=args.runtime_repetitions,
        skip_charts=args.skip_charts,
    )
    print("FINAL EVALUATION COMPLETE")
    print()
    print(f"Dataset validation: {run.validation.passed_cases}/{run.validation.total_cases} passed")
    print(f"Case-results: {len(run.results)}")
    for metric in run.metrics:
        print(
            f"{metric.system.value}: repair={metric.repair_success_rate:.2%}, "
            f"preservation={metric.average_preservation_rate:.2%}, "
            f"median_runtime={metric.median_runtime_seconds * 1000:.3f} ms"
        )
    failed_weighted = [
        result
        for result in run.results
        if result.system != FinalEvaluationSystem.BASELINE and not result.passed
    ]
    print(f"Failed weighted case-results: {len(failed_weighted)}")
    print(f"Generated output: {run.output_dir}")
    if args.show_details and failed_weighted:
        for result in failed_weighted:
            print(f"  - {result.case_id} ({result.system.value}): {result.failure_detail}")
    return 0 if run.validation.passed and not failed_weighted else 1


if __name__ == "__main__":
    raise SystemExit(main())
