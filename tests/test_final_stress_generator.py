from modpack_solver.final_dataset.repair_trace import replay_repair_plan
from modpack_solver.final_dataset.stress_generator import (
    StressCaseConfig,
    build_valid_stress_case,
    inject_missing_required_selection,
    inject_selected_version_mismatch,
)
from modpack_solver.final_dataset.topology import DependencyTopology
from modpack_solver.models import IssueType
from modpack_solver.solver.checker import check_synthetic_case


def _control():
    return build_valid_stress_case(
        StressCaseConfig(
            case_id="stress-injection-test",
            selected_mod_count=20,
            topology=DependencyTopology.LAYERED_DAG,
            target_required_edge_count=32,
            target_maximum_depth=4,
            target_branching_factor=3,
            candidate_versions_per_choice_mod=3,
            choice_mod_fraction=0.2,
            seed=77,
        )
    )


def test_missing_injection_is_immutable_and_inverse_repair_succeeds():
    control = _control()
    original = control.model_dump(mode="json")
    variant = inject_missing_required_selection(control)
    issues = {issue.issue_type for issue in check_synthetic_case(variant.case).issues}
    assert control.model_dump(mode="json") == original
    assert IssueType.MISSING_DEPENDENCY in issues
    assert replay_repair_plan(variant.case, variant.known_valid_repair).final_compatible


def test_version_injection_has_known_inverse_repair():
    variant = inject_selected_version_mismatch(_control())
    issues = {issue.issue_type for issue in check_synthetic_case(variant.case).issues}
    assert IssueType.MINECRAFT_VERSION_MISMATCH in issues
    assert replay_repair_plan(variant.case, variant.known_valid_repair).final_compatible
