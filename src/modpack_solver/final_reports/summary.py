"""Measured Markdown summary for the final evaluation."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from modpack_solver.final_reports.models import FinalEvaluationRun, FinalEvaluationSystem


def write_final_summary(run: FinalEvaluationRun, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    unique = {}
    for result in run.results:
        unique.setdefault(result.case_id, result)
    source_counts = Counter(result.source_type.value for result in unique.values())
    size_counts = Counter(result.pack_size_category.value for result in unique.values())
    modification_counts = Counter(result.modification_type.value for result in unique.values())
    complete_controls = sum(
        result.source_type.value == "original_real" and bool(result.collection_method)
        for result in unique.values()
    )
    complete_variants = sum(
        result.source_type.value == "modified_real" and bool(result.collection_method)
        for result in unique.values()
    )
    reduced_controls = source_counts.get("original_real", 0) - complete_controls
    reduced_variants = source_counts.get("modified_real", 0) - complete_variants
    family_count = len({result.source_family_id for result in unique.values()})
    required_edges = [result.required_edge_count for result in unique.values()]
    depths = [result.maximum_required_depth for result in unique.values()]
    metrics = {metric.system: metric for metric in run.metrics}
    baseline = metrics.get(FinalEvaluationSystem.BASELINE)
    default = metrics.get(FinalEvaluationSystem.WEIGHTED_DEFAULT)
    preservation = metrics.get(FinalEvaluationSystem.WEIGHTED_PRESERVATION)
    weighted_failures = [
        result for result in run.results
        if result.system != FinalEvaluationSystem.BASELINE and result.failure_category
    ]

    lines = [
        "# Final Evaluation Summary",
        "",
        "## Dataset Overview",
        "",
        f"The final manifest contains {len(unique)} offline-reproducible cases. Automated validation passed "
        f"{run.validation.passed_cases} of {run.validation.total_cases} checked cases.",
        "",
        f"The cases represent {family_count} distinct source families. Required-edge counts range from "
        f"{min(required_edges, default=0)} to {max(required_edges, default=0)}, and maximum dependency depth "
        f"reaches {max(depths, default=0)}.",
        "",
        "Source counts: " + _counts(source_counts) + ".",
        "",
        "Size counts: " + _counts(size_counts) + ".",
        "",
        "## Input Types",
        "",
        "The final application accepts existing project JSON, built-in/final-dataset cases, basic `.mrpack` manifests, "
        "Modrinth URLs backed by normalized cache entries, and project ID/slug lists.",
        "",
        "## Real-World Modrinth Coverage",
        "",
        f"The scored corpus includes {complete_controls} complete cached Modrinth manifest controls and "
        f"{complete_variants} paired inverse-injected variants, plus {reduced_controls} reduced real-data controls "
        f"and {reduced_variants} reduced variants. Complete-manifest means the normalized metadata covers the "
        "pack's full Modrinth file list; it does not mean the project redistributes an official pack export. "
        "All complete-manifest cases remain pending manual review.",
        "",
        "## Error Injection Method",
        "",
        f"Modified cases are labeled and logged. Modification counts are {_counts(modification_counts)}. Injection "
        "operates on copied cases, records the change, and is rechecked through the normal graph/checker/solver pipeline.",
        "",
        "## Baselines",
        "",
        _metric_summary("One-pass baseline", baseline),
        "",
        _preservation_summary("One-pass baseline", baseline),
        "",
        "The baseline applies checker suggestions once in order. It does not search, backtrack, or compare weighted alternatives.",
        "",
        "## Weighted Solver Results",
        "",
        _metric_summary("Default weighted profile", default),
        "",
        _preservation_summary("Default weighted profile", default),
        "",
        _metric_summary("Preservation-focused profile", preservation),
        "",
        _preservation_summary("Preservation-focused profile", preservation),
        "",
        "Raw costs should only be interpreted within a profile because each profile uses a different weight scale.",
        "",
        "Cascading and reference results: "
        + _advanced_metric_summary(default),
        "",
        "## Results by Pack Size",
        "",
        "Small, medium, large, and huge results are exported in the case-category table and pack-size charts. "
        "Large results include controlled metadata and cached complete-manifest cases; huge results are controlled "
        "generated metadata stress cases.",
        "",
        "## Results by Source Type",
        "",
        "Source types remain separate in the exported tables and charts so synthetic/custom results are not presented as real-pack evidence.",
        "",
        "## Large and Huge Modpack Results",
        "",
        f"The manifest includes {size_counts.get('large', 0)} large and {size_counts.get('huge', 0)} huge cases. "
        "They test graph/checker/solver scaling but do not establish full ecosystem coverage.",
        "",
        "## Explanation Review",
        "",
        f"Structured weighted-explanation completeness was {_explanation(default)} for the default profile and "
        f"{_explanation(preservation)} for the preservation profile. This is an automated field-completeness check, not a human-readability score.",
        "",
        "Default-profile explanation checks: "
        + _explanation_detail(default)
        + ".",
        "",
        _human_explanation_review(),
        "",
        "## Review Status",
        "",
        _manual_review_overview(run),
        "",
        "## Failure Analysis",
        "",
        (
            "No weighted case-results were assigned a failure category."
            if not weighted_failures
            else f"{len(weighted_failures)} weighted case-results were assigned a failure category; see failure_analysis.csv."
        ),
        "",
        "## Key Findings",
        "",
        _key_finding(baseline, default, preservation),
        "",
        "## Limitations",
        "",
        "Results describe metadata compatibility, not guaranteed launch-time behavior. Support is Fabric/Modrinth-focused. "
        "The `.mrpack` reader does not install or regenerate packs, and live API data may change after this offline snapshot.",
        "",
        "## Reproducibility Notes",
        "",
        "Normal tests, demos, validation, and final evaluation run offline. New case expectations use controls, "
        "inverse injections, or reference enumeration rather than weighted-solver output. Live collection is optional "
        "and must be explicitly enabled.",
        "",
        "## Generated Files",
        "",
        f"The run generated {len(run.generated_files)} JSON, CSV, Markdown, LaTeX, and PNG artifacts under `{run.output_dir}`.",
    ]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def _metric_summary(label, metric) -> str:
    if metric is None:
        return f"{label}: no results were generated."
    return (
        f"{label}: {metric.successful_repairs}/{metric.repairable_cases} expected repairs succeeded "
        f"({metric.repair_success_rate:.2%}); average successful-repair preservation was "
        f"{metric.average_preservation_rate:.2%}; median runtime was {metric.median_runtime_seconds * 1000:.3f} ms."
    )


def _preservation_summary(label, metric) -> str:
    if metric is None:
        return f"{label}: common-denominator preservation was not measured."
    return (
        f"{label}: {metric.full_preservation_repairs}/{metric.repairable_cases} expected-repair cases "
        f"were repaired with full preservation ({metric.full_preservation_rate:.2%}). Preserved original "
        f"mods across the same expected-repair denominator were "
        f"{metric.preserved_mod_fraction_all_expected_repairs:.2%}; failed repairs contribute zero to this strict measure."
    )


def _advanced_metric_summary(metric) -> str:
    if metric is None:
        return "not measured."
    cascade = (
        f"{metric.successful_cascading_repairs}/{metric.cascading_cases} repairable cascading cases succeeded"
        if metric.cascading_cases
        else "no repairable cascading cases were evaluated"
    )
    oracle = (
        f"{metric.optimal_plan_agreements} optimal-plan agreements among solver-comparable oracle cases "
        f"from {metric.oracle_verified_cases} exhaustively verified cases"
    )
    no_solution = (
        f"{metric.correct_no_solution_cases}/{metric.no_solution_cases} no-solution outcomes were correct"
    )
    return f"{cascade}; {oracle}; {no_solution}."


def _explanation(metric) -> str:
    if metric is None or metric.explanation_completeness_rate is None:
        return "not measured"
    return f"{metric.explanation_completeness_rate:.2%}"


def _explanation_detail(metric) -> str:
    if metric is None:
        return "not measured"
    values = (
        ("dependency-chain accuracy", metric.dependency_chain_explanation_accuracy),
        ("cascading-step accuracy", metric.cascading_step_explanation_accuracy),
        ("global-plan-reason accuracy", metric.global_plan_reason_accuracy),
    )
    return "; ".join(
        f"{label}={value:.2%}" if value is not None else f"{label}=not applicable"
        for label, value in values
    )


def _key_finding(baseline, default, preservation) -> str:
    if not all((baseline, default, preservation)):
        return "A full three-system comparison was not available for this run."
    return (
        f"On this dataset, the default weighted solver changed repair success by "
        f"{(default.repair_success_rate - baseline.repair_success_rate) * 100:+.2f} percentage points relative to "
        f"the one-pass baseline. The preservation profile changed average preservation by "
        f"{(preservation.average_preservation_rate - default.average_preservation_rate) * 100:+.2f} percentage points "
        "relative to the default profile. These observations apply only to the evaluated corpus."
    )


def _human_explanation_review() -> str:
    review_dir = Path("data/final_dataset/manual_review")
    records = []
    for path in review_dir.glob("*.json") if review_dir.exists() else []:
        try:
            import json

            records.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    reviewed = [
        record for record in records if record.get("explanation_understandable") is not None
    ]
    understandable = sum(
        record.get("explanation_understandable") is True for record in reviewed
    )
    return (
        f"Human understandability review: {understandable}/{len(reviewed)} explicitly reviewed "
        f"records were marked understandable; {len(records) - len(reviewed)} queued records have no human judgment."
    )


def _manual_review_overview(run: FinalEvaluationRun) -> str:
    review_dir = Path("data/final_dataset/manual_review")
    statuses = Counter()
    for path in review_dir.glob("*.json") if review_dir.exists() else []:
        try:
            import json

            status = json.loads(path.read_text(encoding="utf-8")).get(
                "review_status", "not_started"
            )
        except (OSError, ValueError):
            status = "invalid_record"
        statuses[str(status)] += 1
    total = sum(statuses.values())
    human = statuses["human_reviewed"] + statuses["publication_ready"]
    publication = statuses["publication_ready"]
    return (
        f"Automated validation: {run.validation.passed_cases}/{run.validation.total_cases} scored cases passed. "
        f"Human review: {human}/{total} queued records are explicitly human-reviewed. "
        f"Publication-ready review: {publication}/{total} records meet the strict publication-ready status. "
        "Complete-manifest cases remain pending human publication review unless their records explicitly prove otherwise."
    )


def _counts(counter: Counter) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(counter.items())) or "none"
