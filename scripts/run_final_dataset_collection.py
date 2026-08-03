"""Collect or replay final dataset metadata and deterministic offline cases."""

from __future__ import annotations

import argparse
from pathlib import Path

from modpack_solver.final_dataset.cache import ModrinthCacheMode
from modpack_solver.final_dataset.collector import collect_final_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="data/final_dataset")
    parser.add_argument("--cache-dir")
    parser.add_argument("--manifest")
    parser.add_argument("--mode", choices=[mode.value for mode in ModrinthCacheMode], default="offline")
    parser.add_argument("--max-packs", type=int)
    parser.add_argument("--include-popular", action="store_true")
    parser.add_argument("--include-custom", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-large", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-huge", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--generate-dense-stress", action="store_true")
    parser.add_argument("--generate-cascading", action="store_true")
    parser.add_argument("--generate-search-stress", action="store_true")
    parser.add_argument("--collect-full-modpacks", action="store_true")
    parser.add_argument("--target-source-packs", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = collect_final_dataset(
        output_dir=Path(args.output_dir),
        cache_dir=Path(args.cache_dir) if args.cache_dir else None,
        manifest_path=Path(args.manifest) if args.manifest else None,
        mode=ModrinthCacheMode(args.mode),
        max_packs=args.max_packs,
        include_popular=args.include_popular,
        include_custom=args.include_custom,
        include_large=args.include_large,
        include_huge=args.include_huge,
        dry_run=args.dry_run,
        force_refresh=args.force_refresh,
        generate_dense_stress=args.generate_dense_stress,
        generate_cascading=args.generate_cascading,
        generate_search_stress=args.generate_search_stress,
        collect_full_modpacks=args.collect_full_modpacks,
        target_source_packs=args.target_source_packs,
    )
    print("FINAL DATASET COLLECTION")
    print(f"Mode: {summary.mode.value}")
    print(f"Manifest: {summary.manifest_path}")
    print(f"Cases available: {summary.total_cases}")
    print(f"Cases added: {summary.cases_added}")
    print(f"Live resources cached: {summary.cached_resources_added}")
    print(f"Full source packs collected: {summary.full_source_packs_collected}")
    print(f"Full source packs quarantined: {summary.full_source_packs_quarantined}")
    if summary.skipped:
        print("Skipped:")
        for item in summary.skipped:
            print(f"  - {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
