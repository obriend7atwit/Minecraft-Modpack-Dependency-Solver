"""Generate or inspect final-dataset manual review packets."""

from __future__ import annotations

import argparse

from modpack_solver.final_dataset.manual_review import (
    format_case_review_packet,
    generate_review_queue,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="data/final_dataset/manifest.json")
    parser.add_argument("--review-dir", default="data/final_dataset/manual_review")
    parser.add_argument("--output-dir", default="results/final/review")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--summary", action="store_true")
    mode.add_argument("--case-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = generate_review_queue(
        manifest_path=args.manifest,
        review_dir=args.review_dir,
        output_dir=args.output_dir,
    )
    if args.case_id:
        print(
            format_case_review_packet(
                args.case_id,
                manifest_path=args.manifest,
                review_dir=args.review_dir,
            )
        )
        return 0
    print("MANUAL REVIEW SUMMARY")
    print(f"Total queued: {summary.total_queued}")
    print(f"Automated evidence ready: {summary.automated_evidence_ready}")
    print(f"Human reviewed: {summary.human_reviewed}")
    print(f"Publication ready: {summary.publication_ready}")
    print(f"Rejected: {summary.rejected}")
    print(f"Remaining human review: {summary.remaining_review_count}")
    print(f"Outputs: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
