"""Final dataset migration, deterministic custom cases, and optional live caching."""

from __future__ import annotations

import json
import os
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from modpack_solver.evaluation import load_evaluation_manifest
from modpack_solver.final_dataset.cache import (
    ModrinthCacheMode,
    fetch_or_load_project,
    fetch_or_load_project_versions,
    save_cached_json,
)
from modpack_solver.final_dataset.export import write_pretty_json
from modpack_solver.final_dataset.complexity import calculate_case_complexity
from modpack_solver.final_dataset.manifest import load_final_dataset_manifest
from modpack_solver.final_dataset.models import (
    FinalCaseSourceType,
    FinalDatasetCaseSpec,
    FinalDatasetManifest,
    GroundTruthMethod,
    ModificationType,
)
from modpack_solver.final_dataset.sizing import classify_pack_size
from modpack_solver.graph import build_graph_from_synthetic_case
from modpack_solver.metadata.synthetic import load_synthetic_case
from modpack_solver.models import (
    Dependency,
    DependencyType,
    MetadataSource,
    ModProject,
    ModVersion,
    ModpackConfig,
    IssueType,
    RepairActionType,
    SelectedMod,
    SyntheticCase,
)
from modpack_solver.solver import SolverStatus
from modpack_solver.solver.checker import check_graph


class CollectionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ModrinthCacheMode
    manifest_path: str
    total_cases: int = 0
    cases_added: int = 0
    cached_resources_added: int = 0
    full_source_packs_collected: int = 0
    full_source_packs_quarantined: int = 0
    skipped: list[str] = Field(default_factory=list)
    source_type_counts: dict[str, int] = Field(default_factory=dict)
    size_category_counts: dict[str, int] = Field(default_factory=dict)


def collect_final_dataset(
    *,
    output_dir: str | Path = "data/final_dataset",
    cache_dir: str | Path | None = None,
    manifest_path: str | Path | None = None,
    mode: ModrinthCacheMode = ModrinthCacheMode.OFFLINE,
    max_packs: int | None = None,
    include_popular: bool = False,
    include_custom: bool = True,
    include_large: bool = True,
    include_huge: bool = True,
    dry_run: bool = False,
    force_refresh: bool = False,
    generate_dense_stress: bool = False,
    generate_cascading: bool = False,
    generate_search_stress: bool = False,
    collect_full_modpacks: bool = False,
    target_source_packs: int = 20,
) -> CollectionSummary:
    """Create/replay the final dataset and optionally refresh seed metadata."""

    mode = ModrinthCacheMode(mode)
    output = Path(output_dir)
    cache = Path(cache_dir) if cache_dir else output / "metadata_cache"
    manifest_file = Path(manifest_path) if manifest_path else output / "manifest.json"
    existing_count = 0
    if manifest_file.exists():
        existing_count = len(load_final_dataset_manifest(manifest_file).cases)

    generated_expanded = bool(
        generate_dense_stress or generate_cascading or generate_search_stress
    )
    if not dry_run and generated_expanded:
        legacy_path = output / "manifest_v1.json"
        if not legacy_path.exists():
            if not manifest_file.exists():
                raise FileNotFoundError(
                    "A v1 manifest is required before generating the expanded corpus."
                )
            current = load_final_dataset_manifest(manifest_file)
            if current.dataset_version != "1.0.0":
                raise FileNotFoundError(
                    "manifest_v1.json is missing and the current manifest is not v1."
                )
            shutil.copyfile(manifest_file, legacy_path)
        from modpack_solver.final_dataset.expanded_corpus import generate_expanded_corpus

        generate_expanded_corpus(
            output_dir=output,
            legacy_manifest_path=legacy_path,
            generate_dense=generate_dense_stress,
            generate_cascading=generate_cascading,
            generate_search=(
                generate_search_stress
                or generate_dense_stress
                or generate_cascading
            ),
        )

    if not dry_run and not generated_expanded and (not manifest_file.exists() or force_refresh):
        _create_seed_dataset(
            output,
            manifest_file,
            include_custom=include_custom,
            include_large=include_large,
            include_huge=include_huge,
        )
        _seed_offline_metadata_cache(output, cache)

    cached_added = 0
    full_collected = 0
    full_quarantined = 0
    skipped: list[str] = []
    if mode == ModrinthCacheMode.LIVE:
        seeds = _load_live_seeds(output, include_popular=include_popular)
        if max_packs is not None:
            seeds = seeds[:max_packs]
        for seed in seeds:
            identifier = seed.get("slug") or seed.get("id")
            if not identifier:
                skipped.append("Skipped seed without slug or ID.")
                continue
            try:
                fetch_or_load_project(
                    identifier,
                    cache_dir=cache,
                    mode=mode,
                    force_refresh=force_refresh,
                )
                fetch_or_load_project_versions(
                    identifier,
                    cache_dir=cache,
                    mode=mode,
                    force_refresh=force_refresh,
                )
                cached_added += 1
            except Exception as exc:
                skipped.append(f"{identifier}: {type(exc).__name__}: {exc}")
    if collect_full_modpacks:
        from modpack_solver.final_dataset.modrinth_pack_collector import (
            collect_full_modrinth_packs,
        )

        pack_summary = collect_full_modrinth_packs(
            output_dir=output,
            cache_dir=cache,
            mode=mode,
            target_source_packs=target_source_packs,
        )
        full_collected = len(pack_summary.collected)
        full_quarantined = len(pack_summary.quarantined)
        skipped.extend(pack_summary.skipped)
        if (
            not dry_run
            and manifest_file.exists()
            and (output / "manifest_v1.json").exists()
            and load_final_dataset_manifest(manifest_file).dataset_version.startswith("2.")
        ):
            from modpack_solver.final_dataset.expanded_corpus import (
                generate_expanded_corpus,
            )

            generate_expanded_corpus(
                output_dir=output,
                legacy_manifest_path=output / "manifest_v1.json",
                generate_dense=True,
                generate_cascading=True,
                generate_search=True,
            )

    if not manifest_file.exists():
        return CollectionSummary(
            mode=mode,
            manifest_path=str(manifest_file),
            skipped=[*skipped, "Dry run: manifest was not written."],
        )

    manifest = load_final_dataset_manifest(manifest_file)
    source_counts = Counter(case.source_type.value for case in manifest.cases)
    size_counts = Counter(case.pack_size_category.value for case in manifest.cases)
    return CollectionSummary(
        mode=mode,
        manifest_path=str(manifest_file),
        total_cases=len(manifest.cases),
        cases_added=max(0, len(manifest.cases) - existing_count),
        cached_resources_added=cached_added,
        full_source_packs_collected=full_collected,
        full_source_packs_quarantined=full_quarantined,
        skipped=skipped,
        source_type_counts=dict(sorted(source_counts.items())),
        size_category_counts=dict(sorted(size_counts.items())),
    )


def _create_seed_dataset(
    output: Path,
    manifest_path: Path,
    *,
    include_custom: bool,
    include_large: bool,
    include_huge: bool,
) -> None:
    for directory in (
        output / "original_real",
        output / "modified_real",
        output / "custom_modpacks",
        output / "metadata_cache",
        output / "injection_logs",
        output / "manual_review",
        output / "collection_logs",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    specs = _migrate_existing_evaluation_cases(manifest_path)
    if include_custom:
        sizes = [("small", 10), ("medium", 40)]
        if include_large:
            sizes.append(("large", 100))
        if include_huge:
            sizes.append(("huge", 220))
        for size_name, count in sizes:
            for scenario in (
                "valid",
                "missing_dependency",
                "minecraft_mismatch",
                "loader_mismatch",
                "hard_conflict",
                "duplicate",
                "optional",
                "multi_error",
            ):
                case = _build_scaled_case(size_name, count, scenario)
                case_id = f"custom-{size_name}-{scenario.replace('_', '-')}"
                fixture_path = output / "custom_modpacks" / f"{case_id}.json"
                write_pretty_json(fixture_path, case)
                spec = _case_spec_from_case(
                    case_id=case_id,
                    display_name=f"Custom {size_name} {scenario.replace('_', ' ')} case",
                    case=case,
                    fixture_path=_relative_path(fixture_path, manifest_path.parent),
                    source_type=FinalCaseSourceType.CUSTOM_MODPACK,
                    modification_type=_scenario_modification(scenario),
                    original_case_id=(None if scenario == "valid" else f"custom-{size_name}-valid"),
                    modification_description=(
                        None
                        if scenario == "valid"
                        else f"Deterministic custom {scenario.replace('_', ' ')} scenario generated offline."
                    ),
                )
                if spec.modification_type != ModificationType.NONE:
                    log_path = output / "injection_logs" / f"{case_id}.json"
                    _write_generic_injection_log(spec, log_path)
                    spec = spec.model_copy(
                        update={"injection_log": _relative_path(log_path, manifest_path.parent)}
                    )
                specs.append(spec)

        for scenario in (
            "embedded",
            "dependency_chain",
            "multiple_missing",
            "unresolved_selected",
            "unknown_dependency",
            "version_choice",
            "conflict_alternative",
        ):
            case = _build_special_case(scenario)
            case_id = f"custom-focused-{scenario.replace('_', '-')}"
            fixture_path = output / "custom_modpacks" / f"{case_id}.json"
            write_pretty_json(fixture_path, case)
            spec = _case_spec_from_case(
                case_id=case_id,
                display_name=f"Focused custom {scenario.replace('_', ' ')} case",
                case=case,
                fixture_path=_relative_path(fixture_path, manifest_path.parent),
                source_type=FinalCaseSourceType.CUSTOM_MODPACK,
                modification_type=ModificationType.MANUAL,
                modification_description=f"Focused deterministic {scenario.replace('_', ' ')} case generated offline.",
            )
            log_path = output / "injection_logs" / f"{case_id}.json"
            _write_generic_injection_log(spec, log_path)
            specs.append(
                spec.model_copy(update={"injection_log": _relative_path(log_path, manifest_path.parent)})
            )

    manifest = FinalDatasetManifest(
        dataset_name="Minecraft Modpack Solver Final Evaluation Dataset",
        dataset_version="1.0.0",
        generated_at=datetime.now(timezone.utc).isoformat(),
        description=(
            "Offline-reproducible evaluation cases combining the existing strict corpus, "
            "reduced cached Modrinth examples, and deterministic custom scale/error cases."
        ),
        cases=specs,
    )
    write_pretty_json(manifest_path, manifest)
    _write_seed_files(output)


def _migrate_existing_evaluation_cases(manifest_path: Path) -> list[FinalDatasetCaseSpec]:
    old_manifest = Path("data/evaluation/manifest.json").resolve()
    specs = []
    original_map = {
        "real-fo-missing-fabric-api": "real-fo-valid",
        "real-fo-wrong-minecraft": "real-fo-valid",
        "real-additive-missing-dependency": "real-additive-valid",
        "real-additive-loader-mismatch": "real-additive-valid",
    }
    modification_map = {
        "real-fo-missing-fabric-api": ModificationType.REMOVE_REQUIRED_DEPENDENCY,
        "real-fo-wrong-minecraft": ModificationType.CHANGE_MINECRAFT_VERSION,
        "real-additive-missing-dependency": ModificationType.REMOVE_REQUIRED_DEPENDENCY,
        "real-additive-loader-mismatch": ModificationType.CHANGE_LOADER,
    }
    for old_spec in load_evaluation_manifest(old_manifest):
        case = load_synthetic_case(old_spec.fixture)
        if old_spec.source_type.value == "cached_real":
            source_type = FinalCaseSourceType.ORIGINAL_REAL
        elif old_spec.source_type.value == "modified_real":
            source_type = FinalCaseSourceType.MODIFIED_REAL
        else:
            source_type = FinalCaseSourceType.SYNTHETIC
        modification = modification_map.get(old_spec.case_id, ModificationType.NONE)
        description = old_spec.notes if modification != ModificationType.NONE else None
        spec = _case_spec_from_case(
            case_id=old_spec.case_id,
            display_name=old_spec.name,
            case=case,
            fixture_path=_relative_path(Path(old_spec.fixture), manifest_path.parent),
            source_type=source_type,
            modification_type=modification,
            original_case_id=original_map.get(old_spec.case_id),
            modification_description=description,
            source_modpack_name=_source_pack_name(old_spec.case_id),
            dataset_notes=old_spec.notes,
        )
        if modification != ModificationType.NONE:
            log_path = manifest_path.parent / "injection_logs" / f"{old_spec.case_id}.json"
            _write_generic_injection_log(spec, log_path)
            spec = spec.model_copy(
                update={"injection_log": _relative_path(log_path, manifest_path.parent)}
            )
        specs.append(spec)
    return specs


def _case_spec_from_case(
    *,
    case_id: str,
    display_name: str,
    case: SyntheticCase,
    fixture_path: str,
    source_type: FinalCaseSourceType,
    modification_type: ModificationType,
    original_case_id: str | None = None,
    modification_description: str | None = None,
    source_modpack_name: str | None = None,
    dataset_notes: str | None = None,
) -> FinalDatasetCaseSpec:
    graph_result = build_graph_from_synthetic_case(case)
    report = check_graph(graph_result)
    expected_actions, repairable = _construction_expectation(case, report)
    if report.status.value != "incompatible":
        expected_status = SolverStatus.ALREADY_COMPATIBLE
    elif repairable:
        expected_status = SolverStatus.SOLUTION_FOUND
    else:
        expected_status = SolverStatus.NO_SOLUTION
    selected_count = len(case.config.selected_mods)
    metrics = calculate_case_complexity(case, graph_result)
    return FinalDatasetCaseSpec(
        case_id=case_id,
        display_name=display_name,
        source_type=source_type,
        source_family_id=original_case_id or case_id,
        ground_truth_method=(
            GroundTruthMethod.INVERSE_INJECTION
            if modification_type != ModificationType.NONE
            else GroundTruthMethod.ORIGINAL_CONTROL
        ),
        review_status="generated",
        source_modpack_name=source_modpack_name,
        original_case_id=original_case_id,
        modification_type=modification_type,
        modification_description=modification_description,
        fixture_path=fixture_path,
        minecraft_version=case.config.minecraft_version,
        loader=case.config.loader,
        selected_mod_count=selected_count,
        dependency_edge_count=metrics.total_dependency_edge_count,
        pack_size_category=classify_pack_size(selected_count),
        **metrics.model_dump(exclude={"selected_mod_count"}),
        expected_initial_status=report.status,
        expected_solver_status=expected_status,
        expected_issue_types=_stable_unique([issue.issue_type for issue in report.issues]),
        expected_action_types=expected_actions,
        expected_repairable=expected_status == SolverStatus.SOLUTION_FOUND,
        expected_final_compatible=expected_status != SolverStatus.NO_SOLUTION,
        manually_reviewed=source_type in {FinalCaseSourceType.ORIGINAL_REAL, FinalCaseSourceType.MODIFIED_REAL},
        review_notes=(
            "Reviewed as a reduced metadata example; it is not a complete official pack export."
            if source_type in {FinalCaseSourceType.ORIGINAL_REAL, FinalCaseSourceType.MODIFIED_REAL}
            else None
        ),
        license_or_terms_note=(
            "Contains normalized metadata only; verify Modrinth project terms before publication."
            if source_type in {FinalCaseSourceType.ORIGINAL_REAL, FinalCaseSourceType.MODIFIED_REAL}
            else None
        ),
        dataset_notes=dataset_notes,
    )


def _construction_expectation(case: SyntheticCase, report):
    actions = []
    repairable = True
    for issue in report.issues:
        if issue.severity != "error":
            continue
        if issue.issue_type == IssueType.MISSING_DEPENDENCY:
            target = issue.affected_mod_ids[-1] if issue.affected_mod_ids else ""
            if any(
                version.mod_id == target
                and case.config.minecraft_version in version.game_versions
                and case.config.loader in version.loaders
                for version in case.versions
            ):
                actions.append(RepairActionType.ADD_DEPENDENCY)
            else:
                repairable = False
        elif issue.issue_type in {
            IssueType.MINECRAFT_VERSION_MISMATCH,
            IssueType.LOADER_MISMATCH,
        }:
            target = issue.affected_mod_ids[0] if issue.affected_mod_ids else ""
            if any(
                version.mod_id == target
                and case.config.minecraft_version in version.game_versions
                and case.config.loader in version.loaders
                for version in case.versions
            ):
                actions.append(RepairActionType.UPGRADE_MOD)
            else:
                repairable = False
        elif issue.issue_type in {
            IssueType.HARD_CONFLICT,
            IssueType.DUPLICATE_MOD_VERSION,
        }:
            actions.append(RepairActionType.REMOVE_MOD)
        else:
            repairable = False
    return _stable_unique(actions), repairable


def _build_scaled_case(size_name: str, count: int, scenario: str) -> SyntheticCase:
    unique_count = count - 1 if scenario == "duplicate" else count
    projects = []
    versions = []
    selected = []
    for index in range(1, unique_count + 1):
        mod_id = f"custom-{size_name}-mod-{index:03d}"
        project = ModProject(
            mod_id=mod_id,
            name=f"Custom {size_name.title()} Mod {index:03d}",
            slug=mod_id,
            source=MetadataSource.SYNTHETIC,
        )
        version = ModVersion(
            version_id=f"{mod_id}-1.0.0",
            mod_id=mod_id,
            version_number="1.0.0",
            game_versions=["1.20.1"],
            loaders=["fabric"],
        )
        projects.append(project)
        versions.append(version)
        selected.append(SelectedMod(mod_id=mod_id, version_id=version.version_id))

    first = versions[0]
    if scenario == "valid":
        first.dependencies = [Dependency(target_mod_id=versions[1].mod_id, dependency_type=DependencyType.REQUIRED)]
    elif scenario in {"missing_dependency", "multi_error"}:
        helper = _extra_project(size_name, "required-helper")
        projects.append(helper[0])
        versions.append(helper[1])
        first.dependencies = [Dependency(target_mod_id=helper[0].mod_id, dependency_type=DependencyType.REQUIRED)]
    elif scenario == "minecraft_mismatch":
        first.game_versions = ["1.19.4"]
        first.version_number = "0.5.0"
        compatible = first.model_copy(
            update={
                "version_id": f"{first.mod_id}-1.0.0-compatible",
                "version_number": "1.0.0",
                "game_versions": ["1.20.1"],
            },
            deep=True,
        )
        versions.append(compatible)
    elif scenario == "loader_mismatch":
        first.loaders = ["forge"]
        first.version_number = "0.5.0"
        compatible = first.model_copy(
            update={
                "version_id": f"{first.mod_id}-1.0.0-fabric",
                "version_number": "1.0.0",
                "loaders": ["fabric"],
            },
            deep=True,
        )
        versions.append(compatible)
    elif scenario == "hard_conflict":
        first.dependencies = [
            Dependency(target_mod_id=versions[2].mod_id, dependency_type=DependencyType.INCOMPATIBLE)
        ]
    elif scenario == "duplicate":
        duplicate_version = first.model_copy(
            update={"version_id": f"{first.mod_id}-2.0.0", "version_number": "2.0.0"},
            deep=True,
        )
        versions.append(duplicate_version)
        selected.append(SelectedMod(mod_id=first.mod_id, version_id=duplicate_version.version_id))
    elif scenario == "optional":
        helper = _extra_project(size_name, "optional-helper")
        projects.append(helper[0])
        versions.append(helper[1])
        first.dependencies = [Dependency(target_mod_id=helper[0].mod_id, dependency_type=DependencyType.OPTIONAL)]

    if scenario == "multi_error":
        versions[1].dependencies = [
            Dependency(target_mod_id=versions[2].mod_id, dependency_type=DependencyType.INCOMPATIBLE)
        ]

    return SyntheticCase(
        config=ModpackConfig(minecraft_version="1.20.1", loader="fabric", selected_mods=selected),
        projects=projects,
        versions=versions,
    )


def _build_special_case(scenario: str) -> SyntheticCase:
    case = _build_scaled_case("focused", 6, "valid")
    first, second, third = case.versions[:3]
    if scenario == "embedded":
        helper = _extra_project("focused", "embedded-helper")
        case.projects.append(helper[0])
        case.versions.append(helper[1])
        first.dependencies = [Dependency(target_mod_id=helper[0].mod_id, dependency_type=DependencyType.EMBEDDED)]
    elif scenario == "dependency_chain":
        helper = _extra_project("focused", "chain-helper")
        case.projects.append(helper[0])
        case.versions.append(helper[1])
        first.dependencies = [Dependency(target_mod_id=second.mod_id, dependency_type=DependencyType.REQUIRED)]
        second.dependencies = [Dependency(target_mod_id=helper[0].mod_id, dependency_type=DependencyType.REQUIRED)]
    elif scenario == "multiple_missing":
        helpers = [_extra_project("focused", f"missing-{index}") for index in (1, 2)]
        for project, version in helpers:
            case.projects.append(project)
            case.versions.append(version)
        first.dependencies = [
            Dependency(target_mod_id=project.mod_id, dependency_type=DependencyType.REQUIRED)
            for project, _ in helpers
        ]
    elif scenario == "unresolved_selected":
        case.config.selected_mods.append(SelectedMod(mod_id="focused-unresolved", version_id="missing-version"))
    elif scenario == "unknown_dependency":
        first.dependencies = [Dependency(target_mod_id="focused-unknown-target", dependency_type=DependencyType.REQUIRED)]
    elif scenario == "version_choice":
        first.game_versions = ["1.19.4"]
        first.version_number = "0.5.0"
        case.versions.append(
            first.model_copy(
                update={
                    "version_id": f"{first.mod_id}-2.0.0",
                    "version_number": "2.0.0",
                    "game_versions": ["1.20.1"],
                    "dependencies": [],
                },
                deep=True,
            )
        )
    elif scenario == "conflict_alternative":
        first.dependencies = [Dependency(target_mod_id=second.mod_id, dependency_type=DependencyType.INCOMPATIBLE)]
        case.versions.append(
            first.model_copy(
                update={
                    "version_id": f"{first.mod_id}-2.0.0",
                    "version_number": "2.0.0",
                    "dependencies": [],
                },
                deep=True,
            )
        )
    return case


def _extra_project(prefix: str, suffix: str) -> tuple[ModProject, ModVersion]:
    mod_id = f"custom-{prefix}-{suffix}"
    project = ModProject(mod_id=mod_id, name=mod_id.replace("-", " ").title(), slug=mod_id, source=MetadataSource.SYNTHETIC)
    version = ModVersion(
        version_id=f"{mod_id}-1.0.0",
        mod_id=mod_id,
        version_number="1.0.0",
        game_versions=["1.20.1"],
        loaders=["fabric"],
    )
    return project, version


def _scenario_modification(scenario: str) -> ModificationType:
    return {
        "valid": ModificationType.NONE,
        "missing_dependency": ModificationType.REMOVE_REQUIRED_DEPENDENCY,
        "minecraft_mismatch": ModificationType.REPLACE_WITH_INCOMPATIBLE_VERSION,
        "loader_mismatch": ModificationType.REPLACE_WITH_INCOMPATIBLE_VERSION,
        "hard_conflict": ModificationType.ADD_CONFLICTING_MOD,
        "duplicate": ModificationType.DUPLICATE_MOD_VERSION,
        "optional": ModificationType.MANUAL,
        "multi_error": ModificationType.MULTI_ERROR,
    }[scenario]


def _write_generic_injection_log(spec: FinalDatasetCaseSpec, path: Path) -> None:
    write_pretty_json(
        path,
        {
            "case_id": spec.case_id,
            "original_case_id": spec.original_case_id,
            "modification_type": spec.modification_type.value,
            "modification_description": spec.modification_description,
            "expected_issue_types": [issue.value for issue in spec.expected_issue_types],
            "expected_action_types": [action.value for action in spec.expected_action_types],
            "manually_reviewed": spec.manually_reviewed,
        },
    )


def _seed_offline_metadata_cache(output: Path, cache: Path) -> None:
    source_files = [
        Path("data/evaluation/cached_real/fabulously_optimized_valid.json"),
        Path("data/evaluation/cached_real/additive_valid.json"),
    ]
    projects = {}
    versions_by_project = {}
    for source in source_files:
        case = load_synthetic_case(source)
        normalized_case_name = "fabulously-optimized" if "fabulously" in source.name else "additive"
        write_pretty_json(cache / "normalized" / "cases" / f"{normalized_case_name}.json", case)
        for project in case.projects:
            projects[project.mod_id] = project
        for version in case.versions:
            versions_by_project.setdefault(version.mod_id, {})[version.version_id] = version

    for project_id, project in projects.items():
        raw_project = {
            "id": project.mod_id,
            "slug": project.slug,
            "title": project.name,
            "description": project.description or "Cached reduced metadata used for offline evaluation.",
            "project_type": "mod",
        }
        aliases = [project.mod_id, project.slug] if project.slug else [project.mod_id]
        raw_versions = [
            _version_to_modrinth_raw(version)
            for version in sorted(versions_by_project.get(project_id, {}).values(), key=lambda item: item.version_id)
        ]
        for alias in aliases:
            save_cached_json(cache / "raw" / "projects" / f"{alias}.json", raw_project)
            save_cached_json(cache / "raw" / "versions" / f"{alias}.json", raw_versions)

    write_pretty_json(
        cache / "collection_index.json",
        {
            "note": "Seeded from reduced cached evaluation fixtures; no live request was made.",
            "entries": {
                f"seed:{project_id}": {"resource_id": project_id, "source": "reduced cached fixture"}
                for project_id in sorted(projects)
            },
        },
    )


def _version_to_modrinth_raw(version: ModVersion) -> dict:
    return {
        "id": version.version_id,
        "project_id": version.mod_id,
        "version_number": version.version_number,
        "game_versions": version.game_versions,
        "loaders": version.loaders,
        "version_type": version.version_type,
        "dependencies": [
            {
                "project_id": dependency.target_mod_id,
                "version_id": dependency.target_version_id,
                "dependency_type": dependency.dependency_type.value,
            }
            for dependency in version.dependencies
        ],
    }


def _write_seed_files(output: Path) -> None:
    write_pretty_json(
        output / "seed_modpacks.json",
        [
            {"slug": "fabulously-optimized", "evidence": "Existing reduced cached reference case"},
            {"slug": "additive", "evidence": "Existing reduced cached reference case"},
        ],
    )
    write_pretty_json(
        output / "seed_projects.json",
        [
            {"slug": "fabric-api", "project_id": "P7dR8mSH"},
            {"slug": "modmenu", "project_id": "mOgUt4GM"},
            {"slug": "sodium", "project_id": "AANobbMI"},
            {"slug": "lithium", "project_id": "gvQqBUqZ"},
            {"slug": "indium", "project_id": "Orvt0mRa"},
        ],
    )


def _load_live_seeds(output: Path, *, include_popular: bool) -> list[dict]:
    seeds = []
    for file_name in ("seed_projects.json", "seed_modpacks.json" if include_popular else ""):
        if not file_name:
            continue
        path = output / file_name
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                seeds.extend(item for item in payload if isinstance(item, dict))
    return seeds


def _source_pack_name(case_id: str) -> str | None:
    if case_id.startswith("real-fo-"):
        return "Fabulously Optimized (reduced cached example)"
    if case_id.startswith("real-additive-"):
        return "Additive (reduced cached example)"
    return None


def _relative_path(path: Path, base: Path) -> str:
    return Path(os.path.relpath(path.resolve(), base.resolve())).as_posix()


def _stable_unique(values):
    seen = set()
    ordered = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
