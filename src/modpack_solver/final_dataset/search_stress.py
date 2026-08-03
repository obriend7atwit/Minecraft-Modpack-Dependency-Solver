"""Small candidate-choice cases that exercise bounded weighted search."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from modpack_solver.final_dataset.models import GroundTruthMethod
from modpack_solver.final_dataset.repair_trace import replay_repair_plan
from modpack_solver.models import (
    Dependency,
    DependencyType,
    MetadataSource,
    ModProject,
    ModVersion,
    ModpackConfig,
    RepairAction,
    RepairActionType,
    SelectedMod,
    SyntheticCase,
)
from modpack_solver.solver.common import SolverStatus
from modpack_solver.solver.costs import RepairWeights, action_cost


class SearchStressCategory(str):
    CANDIDATE_EXPLOSION = "candidate_explosion"
    PROFILE_SENSITIVE = "profile_sensitive"
    NO_SOLUTION = "no_solution"
    TIE_BREAKING = "tie_breaking"


class SearchStressDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    display_name: str
    category: str
    case: SyntheticCase
    known_valid_repair: list[RepairAction] = Field(default_factory=list)
    expected_solver_status: SolverStatus
    ground_truth_method: GroundTruthMethod = GroundTruthMethod.REFERENCE_ENUMERATION
    expensive: bool = False


def build_search_stress_cases() -> list[SearchStressDefinition]:
    definitions = []
    for index in range(1, 5):
        definitions.append(_candidate_explosion(index))
        definitions.append(_profile_sensitive(index))
        definitions.append(_no_solution(index))
        definitions.append(_tie_breaking(index))
    return definitions


def build_bounded_extreme_case(decision_mod_count: int = 8) -> SyntheticCase:
    """Build an intentionally over-depth candidate product for marked stress tests."""

    if decision_mod_count < 7:
        raise ValueError("decision_mod_count must be at least 7.")
    projects = []
    versions = []
    selected = []
    for index in range(decision_mod_count):
        mod_id = f"bounded-extreme-{index:02d}"
        project = _project(mod_id)
        bad = _version(
            mod_id,
            "1.0.0",
            "bad",
            game_versions=["1.19.4"],
        )
        projects.append(project)
        versions.extend(
            [
                bad,
                _version(mod_id, "2.0.0", "good-a"),
                _version(mod_id, "3.0.0", "good-b"),
            ]
        )
        selected.append(bad)
    return _case(projects, versions, selected)


def _candidate_explosion(index: int) -> SearchStressDefinition:
    prefix = f"search-candidate-{index:02d}"
    versions = []
    projects = [_project(f"{prefix}-decision"), _project(f"{prefix}-anchor")]
    decision = projects[0].mod_id
    anchor = projects[1].mod_id
    bad = _version(decision, "1.0.0", "v1-bad", game_versions=["1.19.4"])
    versions.append(bad)
    valid = _version(decision, "2.0.0", "v2-valid")
    versions.append(valid)
    helper_ids = []
    for candidate_number in range(3, 7):
        dependencies = []
        if candidate_number in {3, 5}:
            helper_id = f"{prefix}-helper-{candidate_number}"
            helper_ids.append(helper_id)
            projects.append(_project(helper_id))
            versions.append(_version(helper_id, "1.0.0", "v1"))
            dependencies.append(_dependency(helper_id, DependencyType.REQUIRED))
        if candidate_number == 4:
            dependencies.append(_dependency(anchor, DependencyType.INCOMPATIBLE))
        versions.append(
            _version(
                decision,
                f"{candidate_number}.0.0",
                f"v{candidate_number}",
                dependencies=dependencies,
            )
        )
    anchor_version = _version(anchor, "1.0.0", "v1")
    versions.append(anchor_version)
    case = _case(projects, versions, [bad, anchor_version])
    repair = [_action(RepairActionType.UPGRADE_MOD, valid)]
    _verify_repair(case, repair)
    return SearchStressDefinition(
        case_id=prefix,
        display_name=f"Candidate explosion {index}",
        category=SearchStressCategory.CANDIDATE_EXPLOSION,
        case=case,
        known_valid_repair=repair,
        expected_solver_status=SolverStatus.SOLUTION_FOUND,
        expensive=index == 4,
    )


def _profile_sensitive(index: int) -> SearchStressDefinition:
    prefix = f"search-profile-{index:02d}"
    mod_ids = [f"{prefix}-{name}" for name in ("a", "b", "c", "d")]
    projects = [_project(mod_id) for mod_id in mod_ids]
    a, b, c, d = mod_ids
    b1 = _version(b, "1.0.0", "v1")
    c1 = _version(c, "1.0.0", "v1")
    d1 = _version(d, "1.0.0", "v1")
    a1 = _version(
        a,
        "1.0.0",
        "v1",
        dependencies=[_dependency(b, DependencyType.INCOMPATIBLE, b1.version_id)],
    )
    a2 = _version(
        a,
        "2.0.0",
        "v2",
        dependencies=[_dependency(c, DependencyType.INCOMPATIBLE, c1.version_id)],
    )
    c2 = _version(
        c,
        "2.0.0",
        "v2",
        dependencies=[_dependency(d, DependencyType.INCOMPATIBLE, d1.version_id)],
    )
    d2 = _version(d, "2.0.0", "v2")
    case = _case(projects, [a1, a2, b1, c1, c2, d1, d2], [a1, b1, c1, d1])
    preservation_repair = [
        _action(RepairActionType.UPGRADE_MOD, a2),
        _action(RepairActionType.UPGRADE_MOD, c2),
        _action(RepairActionType.UPGRADE_MOD, d2),
    ]
    _verify_repair(case, preservation_repair)
    return SearchStressDefinition(
        case_id=prefix,
        display_name=f"Profile-sensitive chain {index}",
        category=SearchStressCategory.PROFILE_SENSITIVE,
        case=case,
        known_valid_repair=preservation_repair,
        expected_solver_status=SolverStatus.SOLUTION_FOUND,
    )


def _no_solution(index: int) -> SearchStressDefinition:
    prefix = f"search-unsat-{index:02d}"
    a, b, d, e = [f"{prefix}-{name}" for name in ("a", "b", "d", "e")]
    projects = [_project(mod_id) for mod_id in (a, b, d, e)]
    a1 = _version(a, "1.0.0", "v1", dependencies=[_dependency(b, DependencyType.REQUIRED)])
    b1 = _version(
        b,
        "1.0.0",
        "fabric",
        dependencies=[
            _dependency(d, DependencyType.REQUIRED),
            _dependency(e, DependencyType.INCOMPATIBLE),
        ],
    )
    b2 = _version(b, "2.0.0", "forge", loaders=["forge"])
    d1 = _version(d, "1.0.0", "v1", dependencies=[_dependency(e, DependencyType.REQUIRED)])
    e1 = _version(e, "1.0.0", "v1")
    case = _case(projects, [a1, b1, b2, d1, e1], [a1, d1, e1])
    return SearchStressDefinition(
        case_id=prefix,
        display_name=f"Unsatisfiable dependency core {index}",
        category=SearchStressCategory.NO_SOLUTION,
        case=case,
        expected_solver_status=SolverStatus.NO_SOLUTION,
    )


def _tie_breaking(index: int) -> SearchStressDefinition:
    prefix = f"search-tie-{index:02d}"
    a, b = f"{prefix}-a", f"{prefix}-b"
    projects = [_project(a), _project(b)]
    b1 = _version(b, "1.0.0", "v1")
    b2 = _version(b, "2.0.0", "v2")
    a1 = _version(
        a,
        "1.0.0",
        "v1",
        dependencies=[_dependency(b, DependencyType.INCOMPATIBLE, b1.version_id)],
    )
    a2 = _version(a, "2.0.0", "v2")
    case = _case(projects, [a1, a2, b1, b2], [a1, b1])
    deterministic_repair = [_action(RepairActionType.UPGRADE_MOD, b2)]
    _verify_repair(case, deterministic_repair)
    return SearchStressDefinition(
        case_id=prefix,
        display_name=f"Deterministic equal-cost tie {index}",
        category=SearchStressCategory.TIE_BREAKING,
        case=case,
        known_valid_repair=deterministic_repair,
        expected_solver_status=SolverStatus.SOLUTION_FOUND,
    )


def _project(mod_id: str) -> ModProject:
    return ModProject(
        mod_id=mod_id,
        name=mod_id.replace("-", " ").title(),
        slug=mod_id,
        source=MetadataSource.SYNTHETIC,
    )


def _version(
    mod_id: str,
    version_number: str,
    suffix: str,
    *,
    game_versions: list[str] | None = None,
    loaders: list[str] | None = None,
    dependencies: list[Dependency] | None = None,
) -> ModVersion:
    return ModVersion(
        version_id=f"{mod_id}-{suffix}",
        mod_id=mod_id,
        version_number=version_number,
        game_versions=game_versions or ["1.20.1"],
        loaders=loaders or ["fabric"],
        dependencies=dependencies or [],
    )


def _dependency(
    target: str,
    dependency_type: DependencyType,
    target_version_id: str | None = None,
) -> Dependency:
    return Dependency(
        target_mod_id=target,
        target_version_id=target_version_id,
        dependency_type=dependency_type,
        source=MetadataSource.SYNTHETIC,
    )


def _case(
    projects: list[ModProject],
    versions: list[ModVersion],
    selected_versions: list[ModVersion],
) -> SyntheticCase:
    return SyntheticCase(
        config=ModpackConfig(
            minecraft_version="1.20.1",
            loader="fabric",
            selected_mods=[
                SelectedMod(
                    mod_id=version.mod_id,
                    version_id=version.version_id,
                    version_number=version.version_number,
                )
                for version in selected_versions
            ],
        ),
        projects=projects,
        versions=versions,
    )


def _action(action_type: RepairActionType, version: ModVersion) -> RepairAction:
    action = RepairAction(
        action_type=action_type,
        target_mod_id=version.mod_id,
        target_version_id=version.version_id,
        target_version_number=version.version_number,
        reason="Reference-enumerated controlled search case.",
    )
    action.cost = action_cost(action, RepairWeights())
    return action


def _verify_repair(case: SyntheticCase, actions: list[RepairAction]) -> None:
    if not replay_repair_plan(case, actions).final_compatible:
        raise ValueError("Search-stress known repair did not restore compatibility.")
