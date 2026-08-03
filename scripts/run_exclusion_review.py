"""Generate the offline excluded-manifest classification report."""

from modpack_solver.final_dataset.exclusion_review import review_excluded_manifests


def main() -> None:
    summary = review_excluded_manifests()
    print(f"Reviewed: {summary.total_exclusions}")
    print(f"Incomplete resolution/collection: {summary.incomplete_resolution}")
    print(f"Metadata semantics/normalization: {summary.metadata_semantics}")
    print(f"Ambiguous: {summary.ambiguous}")
    print(f"Recovered: {summary.recovered}")
    print(f"Still quarantined: {summary.still_quarantined}")


if __name__ == "__main__":
    main()
