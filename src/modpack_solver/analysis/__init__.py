"""Week 9 analysis helpers for solver evaluation and result generation."""

from modpack_solver.analysis.baseline import apply_baseline_suggestions, baseline_suggestions_for_case
from modpack_solver.analysis.charts import (
    ChartOutput,
    generate_all_charts,
    generate_baseline_vs_weighted_chart,
    generate_failure_category_chart,
    generate_preservation_chart,
    generate_repair_success_chart,
    generate_runtime_chart,
)
from modpack_solver.analysis.failures import FailureCategory, classify_failure
from modpack_solver.analysis.models import (
    BaselineExecutionResult,
    ExperimentCaseResult,
    ExperimentSummary,
    ExperimentSystem,
    GroupMetrics,
    RuntimeMeasurements,
    SearchLimitExperimentResult,
    Week9AnalysisResult,
)
from modpack_solver.analysis.profiles import (
    WeightProfile,
    get_default_profile,
    get_preservation_profile,
    get_weight_profile,
    list_weight_profiles,
)
from modpack_solver.analysis.runner import (
    build_grouped_metrics,
    measure_runtime,
    run_baseline_experiment,
    run_profile_experiment,
    run_search_limit_experiment,
    run_week9_analysis,
    summarize_experiment_results,
)
from modpack_solver.analysis.tables import (
    escape_latex,
    format_percent,
    generate_analysis_tables,
    write_markdown_summary,
)

__all__ = [
    "BaselineExecutionResult",
    "ChartOutput",
    "ExperimentCaseResult",
    "ExperimentSummary",
    "ExperimentSystem",
    "FailureCategory",
    "GroupMetrics",
    "RuntimeMeasurements",
    "SearchLimitExperimentResult",
    "Week9AnalysisResult",
    "WeightProfile",
    "apply_baseline_suggestions",
    "baseline_suggestions_for_case",
    "build_grouped_metrics",
    "classify_failure",
    "escape_latex",
    "format_percent",
    "generate_all_charts",
    "generate_analysis_tables",
    "generate_baseline_vs_weighted_chart",
    "generate_failure_category_chart",
    "generate_preservation_chart",
    "generate_repair_success_chart",
    "generate_runtime_chart",
    "get_default_profile",
    "get_preservation_profile",
    "get_weight_profile",
    "list_weight_profiles",
    "measure_runtime",
    "run_baseline_experiment",
    "run_profile_experiment",
    "run_search_limit_experiment",
    "run_week9_analysis",
    "summarize_experiment_results",
    "write_markdown_summary",
]
