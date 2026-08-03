"""Hand-constructed cascading repair cases with independent known plans."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from modpack_solver.final_dataset.models import GroundTruthMethod
from modpack_solver.final_dataset.repair_trace import RepairTrace, replay_repair_plan
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


class CascadingCaseDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    display_name: str
    description: str
    case: SyntheticCase
    known_valid_repair: list[RepairAction] = Field(default_factory=list)
    expected_solver_status: SolverStatus
    ground_truth_method: GroundTruthMethod
    trace: RepairTrace | None = None


class _CaseBuilder:
    def __init__(self, case_id: str) -> None:
        self.case_id = case_id
        self.projects: dict[str, ModProject] = {}
        self.versions: list[ModVersion] = []
        self.selected: list[SelectedMod] = []

    def version(
        self,
        mod_id: str,
        version_number: str = "1.0.0",
        *,
        suffix: str | None = None,
        game_versions: list[str] | None = None,
        loaders: list[str] | None = None,
        dependencies: list[tuple[str, DependencyType]] | None = None,
        select: bool = False,
    ) -> ModVersion:
        self.projects.setdefault(
            mod_id,
            ModProject(
                mod_id=mod_id,
                name=mod_id.replace("-", " ").title(),
                slug=mod_id,
                source=MetadataSource.SYNTHETIC,
            ),
        )
        version = ModVersion(
            version_id=f"{mod_id}-{suffix or version_number}",
            mod_id=mod_id,
            version_number=version_number,
            game_versions=game_versions or ["1.20.1"],
            loaders=loaders or ["fabric"],
            dependencies=[
                Dependency(
                    target_mod_id=target,
                    dependency_type=dependency_type,
                    source=MetadataSource.SYNTHETIC,
                )
                for target, dependency_type in (dependencies or [])
            ],
        )
        self.versions.append(version)
        if select:
            self.selected.append(
                SelectedMod(
                    mod_id=mod_id,
                    version_id=version.version_id,
                    version_number=version.version_number,
                )
            )
        return version

    def select_again(self, version: ModVersion) -> None:
        self.selected.append(
            SelectedMod(
                mod_id=version.mod_id,
                version_id=version.version_id,
                version_number=version.version_number,
            )
        )

    def build(self) -> SyntheticCase:
        return SyntheticCase(
            config=ModpackConfig(
                minecraft_version="1.20.1",
                loader="fabric",
                selected_mods=self.selected,
            ),
            projects=sorted(self.projects.values(), key=lambda item: item.mod_id),
            versions=sorted(self.versions, key=lambda item: (item.mod_id, item.version_id)),
        )


def build_cascading_cases() -> list[CascadingCaseDefinition]:
    """Return the twelve required deterministic cascading scenarios."""

    definitions = [
        _missing_dependency_chain(),
        _dependency_conflict(),
        _version_then_dependency(),
        _version_then_transitive_chain(),
        _global_candidate_choice(),
        _shared_dependency_fan_in(),
        _diamond_dependency(),
        _cycle_closure(),
        _intermediate_loader_choice(),
        _cascading_conflict_alternative(),
        _cascading_no_solution(),
        _multi_error_cascade(),
    ]
    return [_attach_trace(definition) for definition in definitions]


def _missing_dependency_chain() -> CascadingCaseDefinition:
    builder = _CaseBuilder("cascade-01-missing-chain")
    builder.version("cascade-a", dependencies=[("cascade-b", DependencyType.REQUIRED)], select=True)
    b = builder.version("cascade-b", dependencies=[("cascade-c", DependencyType.REQUIRED)])
    c = builder.version("cascade-c", dependencies=[("cascade-d", DependencyType.REQUIRED)])
    d = builder.version("cascade-d")
    return _repairable(
        builder,
        "Missing dependency chain",
        "Adding each missing dependency reveals the next required library.",
        [_add(b), _add(c), _add(d)],
    )


def _dependency_conflict() -> CascadingCaseDefinition:
    builder = _CaseBuilder("cascade-02-add-conflict")
    builder.version("conflict-a", dependencies=[("conflict-b", DependencyType.REQUIRED)], select=True)
    b = builder.version(
        "conflict-b",
        dependencies=[("conflict-d", DependencyType.INCOMPATIBLE)],
    )
    builder.version("conflict-d", select=True)
    return _repairable(
        builder,
        "Dependency addition reveals conflict",
        "Adding the required library reveals its conflict with an existing selection.",
        [_add(b), _remove("conflict-d")],
    )


def _version_then_dependency() -> CascadingCaseDefinition:
    builder = _CaseBuilder("cascade-03-version-dependency")
    builder.version(
        "version-a",
        "1.0.0",
        suffix="v1",
        game_versions=["1.19.4"],
        select=True,
    )
    compatible = builder.version(
        "version-a",
        "2.0.0",
        suffix="v2",
        dependencies=[("version-b", DependencyType.REQUIRED)],
    )
    dependency = builder.version("version-b")
    return _repairable(
        builder,
        "Version repair reveals dependency",
        "The compatible mod version adds a new required library.",
        [_change(compatible, RepairActionType.UPGRADE_MOD), _add(dependency)],
    )


def _version_then_transitive_chain() -> CascadingCaseDefinition:
    builder = _CaseBuilder("cascade-04-version-transitive")
    builder.version(
        "transitive-a",
        "1.0.0",
        suffix="v1",
        game_versions=["1.19.4"],
        select=True,
    )
    compatible = builder.version(
        "transitive-a",
        "2.0.0",
        suffix="v2",
        dependencies=[("transitive-b", DependencyType.REQUIRED)],
    )
    b = builder.version(
        "transitive-b",
        dependencies=[
            ("transitive-c", DependencyType.REQUIRED),
            ("transitive-d", DependencyType.REQUIRED),
        ],
    )
    c = builder.version("transitive-c")
    d = builder.version("transitive-d")
    return _repairable(
        builder,
        "Version repair reveals transitive chain",
        "Changing the root version reveals a dependency whose addition exposes two more missing libraries.",
        [
            _change(compatible, RepairActionType.UPGRADE_MOD),
            _add(b),
            _add(c),
            _add(d),
        ],
    )


def _global_candidate_choice() -> CascadingCaseDefinition:
    builder = _CaseBuilder("cascade-05-global-choice")
    builder.version("choice-a", dependencies=[("choice-b", DependencyType.REQUIRED)], select=True)
    builder.version("choice-d", select=True)
    builder.version("choice-c")
    builder.version("choice-e")
    builder.version(
        "choice-b",
        "1.0.0",
        suffix="v1",
        dependencies=[
            ("choice-c", DependencyType.REQUIRED),
            ("choice-e", DependencyType.REQUIRED),
            ("choice-d", DependencyType.INCOMPATIBLE),
        ],
    )
    better = builder.version("choice-b", "2.0.0", suffix="v2")
    return _repairable(
        builder,
        "Global candidate choice",
        "One equally cheap first add creates a costly cascade; the other completes the repair.",
        [_add(better)],
    )


def _shared_dependency_fan_in() -> CascadingCaseDefinition:
    builder = _CaseBuilder("cascade-06-shared-fan-in")
    for mod_id in ("fan-a", "fan-b", "fan-c"):
        builder.version(mod_id, dependencies=[("fan-library", DependencyType.REQUIRED)], select=True)
    library = builder.version("fan-library")
    return _repairable(
        builder,
        "Shared dependency fan-in",
        "Three missing relationships are resolved by one shared-library addition.",
        [_add(library)],
    )


def _diamond_dependency() -> CascadingCaseDefinition:
    builder = _CaseBuilder("cascade-07-diamond")
    builder.version(
        "diamond-a",
        dependencies=[
            ("diamond-b", DependencyType.REQUIRED),
            ("diamond-c", DependencyType.REQUIRED),
        ],
        select=True,
    )
    builder.version("diamond-b", dependencies=[("diamond-d", DependencyType.REQUIRED)], select=True)
    builder.version("diamond-c", dependencies=[("diamond-d", DependencyType.REQUIRED)], select=True)
    d = builder.version("diamond-d")
    return _repairable(
        builder,
        "Diamond dependency",
        "Two branches converge on one missing dependency, which is added only once.",
        [_add(d)],
    )


def _cycle_closure() -> CascadingCaseDefinition:
    builder = _CaseBuilder("cascade-08-cycle")
    builder.version("cycle-a", dependencies=[("cycle-b", DependencyType.REQUIRED)], select=True)
    b = builder.version("cycle-b", dependencies=[("cycle-a", DependencyType.REQUIRED)])
    return _repairable(
        builder,
        "Required cycle closure",
        "Adding the missing member closes a valid required cycle without recursive traversal.",
        [_add(b)],
    )


def _intermediate_loader_choice() -> CascadingCaseDefinition:
    builder = _CaseBuilder("cascade-09-loader-choice")
    builder.version("loader-a", dependencies=[("loader-b", DependencyType.REQUIRED)], select=True)
    builder.version("loader-b", "1.0.0", suffix="forge", loaders=["forge"])
    fabric = builder.version(
        "loader-b",
        "2.0.0",
        suffix="fabric",
        dependencies=[("loader-c", DependencyType.REQUIRED)],
    )
    c = builder.version("loader-c")
    return _repairable(
        builder,
        "Intermediate loader choice",
        "The Forge distractor is rejected; the Fabric candidate reveals another dependency.",
        [_add(fabric), _add(c)],
    )


def _cascading_conflict_alternative() -> CascadingCaseDefinition:
    builder = _CaseBuilder("cascade-10-conflict-alternative")
    builder.version(
        "alternative-a",
        "1.0.0",
        suffix="v1",
        game_versions=["1.19.4"],
        select=True,
    )
    builder.version(
        "alternative-a",
        "2.0.0",
        suffix="v2",
        dependencies=[("alternative-c", DependencyType.INCOMPATIBLE)],
    )
    preferred = builder.version(
        "alternative-a",
        "3.0.0",
        suffix="v3",
        dependencies=[("alternative-b", DependencyType.REQUIRED)],
    )
    b = builder.version("alternative-b")
    builder.version("alternative-c", select=True)
    return _repairable(
        builder,
        "Cascading conflict alternative",
        "Complete plans are compared: one version conflicts, while another needs a library.",
        [_change(preferred, RepairActionType.UPGRADE_MOD), _add(b)],
    )


def _cascading_no_solution() -> CascadingCaseDefinition:
    builder = _CaseBuilder("cascade-11-no-solution")
    builder.version("unsat-a", dependencies=[("unsat-b", DependencyType.REQUIRED)], select=True)
    builder.version(
        "unsat-b",
        "1.0.0",
        suffix="fabric",
        dependencies=[
            ("unsat-d", DependencyType.REQUIRED),
            ("unsat-e", DependencyType.INCOMPATIBLE),
        ],
    )
    builder.version("unsat-b", "2.0.0", suffix="forge", loaders=["forge"])
    builder.version(
        "unsat-d",
        dependencies=[("unsat-e", DependencyType.REQUIRED)],
        select=True,
    )
    builder.version("unsat-e", select=True)
    return CascadingCaseDefinition(
        case_id=builder.case_id,
        display_name="Cascading no-solution",
        description=(
            "Every usable required-library choice either conflicts with or requires the "
            "same selected mod, so no supported complete plan exists."
        ),
        case=builder.build(),
        expected_solver_status=SolverStatus.NO_SOLUTION,
        ground_truth_method=GroundTruthMethod.REFERENCE_ENUMERATION,
    )


def _multi_error_cascade() -> CascadingCaseDefinition:
    builder = _CaseBuilder("cascade-12-multi-error")
    builder.version("multi-a", dependencies=[("multi-b", DependencyType.REQUIRED)], select=True)
    b = builder.version("multi-b", dependencies=[("multi-c", DependencyType.REQUIRED)])
    c = builder.version("multi-c")
    builder.version(
        "multi-x",
        "1.0.0",
        suffix="v1",
        game_versions=["1.19.4"],
        select=True,
    )
    x2 = builder.version("multi-x", "2.0.0", suffix="v2")
    builder.version(
        "multi-d",
        dependencies=[("multi-e", DependencyType.INCOMPATIBLE)],
        select=True,
    )
    builder.version("multi-e", select=True)
    z1 = builder.version("multi-z", "1.0.0", suffix="v1", select=True)
    z2 = builder.version("multi-z", "2.0.0", suffix="v2")
    builder.select_again(z2)
    return _repairable(
        builder,
        "Multi-error cascade",
        "Four initial errors plus a revealed transitive dependency require five actions.",
        [
            _add(b),
            _add(c),
            _change(x2, RepairActionType.UPGRADE_MOD),
            _remove("multi-e"),
            _remove(z1.mod_id),
        ],
    )


def _repairable(
    builder: _CaseBuilder,
    display_name: str,
    description: str,
    actions: list[RepairAction],
) -> CascadingCaseDefinition:
    return CascadingCaseDefinition(
        case_id=builder.case_id,
        display_name=display_name,
        description=description,
        case=builder.build(),
        known_valid_repair=actions,
        expected_solver_status=SolverStatus.SOLUTION_FOUND,
        ground_truth_method=GroundTruthMethod.INVERSE_INJECTION,
    )


def _attach_trace(definition: CascadingCaseDefinition) -> CascadingCaseDefinition:
    if not definition.known_valid_repair:
        return definition
    trace = replay_repair_plan(definition.case, definition.known_valid_repair)
    if not trace.final_compatible:
        raise ValueError(f"Known repair for '{definition.case_id}' is not compatible.")
    return definition.model_copy(update={"trace": trace}, deep=True)


def _add(version: ModVersion) -> RepairAction:
    return _action(RepairActionType.ADD_DEPENDENCY, version.mod_id, version)


def _change(version: ModVersion, action_type: RepairActionType) -> RepairAction:
    return _action(action_type, version.mod_id, version)


def _remove(mod_id: str) -> RepairAction:
    return _action(RepairActionType.REMOVE_MOD, mod_id)


def _action(
    action_type: RepairActionType,
    mod_id: str,
    version: ModVersion | None = None,
) -> RepairAction:
    action = RepairAction(
        action_type=action_type,
        target_mod_id=mod_id,
        target_version_id=version.version_id if version else None,
        target_version_number=version.version_number if version else None,
        reason="Hand-constructed independent cascading repair.",
    )
    action.cost = action_cost(action, RepairWeights())
    return action
