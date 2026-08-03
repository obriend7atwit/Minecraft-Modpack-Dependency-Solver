# Manual Review

Each top-level JSON file is a human review form; `evidence/` contains machine-generated objective packets. Null values mean that no human review claim has been made. Status and queue summaries are exported to `results/final/review/`.

The `full-*.json` forms cover the complete-manifest controls and their paired injected variants. Review should confirm source provenance, environment metadata, warning interpretation, the removed dependency, and the replayed inverse action before those cases are used in publication claims.

Use `uv run python scripts/run_manual_review.py --summary` to refresh the queue, or `uv run python scripts/run_manual_review.py --case-id CASE_ID` to print a compact packet. Automated evidence never sets subjective fields. `publication_ready` requires every judgment to be true plus a reviewer and ISO-8601 timestamp.
