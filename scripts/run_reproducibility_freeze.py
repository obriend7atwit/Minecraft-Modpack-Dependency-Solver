"""Freeze final environment, command, dataset, and result metadata."""

import argparse

from modpack_solver.final_reports.reproducibility import generate_reproducibility_freeze


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="results/final")
    parser.add_argument("--manifest", default="data/final_dataset/manifest.json")
    parser.add_argument("--test-result", default="not recorded")
    parser.add_argument("--legacy-result", default="not recorded")
    parser.add_argument("--expanded-result", default="not recorded")
    args = parser.parse_args()
    record = generate_reproducibility_freeze(
        output_dir=args.output_dir,
        manifest_path=args.manifest,
        test_result=args.test_result,
        legacy_evaluation_result=args.legacy_result,
        expanded_evaluation_result=args.expanded_result,
    )
    print(f"Dataset: {record['dataset_version']} ({record['case_count']} cases)")
    print(f"Manifest SHA-256: {record['manifest_sha256']}")
    print(f"Git commit: {record['git_commit_hash'] or 'unavailable'}")
    print(f"Working tree clean: {record['working_tree_clean']}")


if __name__ == "__main__":
    main()
