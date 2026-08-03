"""Solver-state helpers and immutable configuration mutations."""

from __future__ import annotations

from dataclasses import dataclass

from modpack_solver.models import ModpackConfig, ModVersion, RepairAction, SelectedMod


@dataclass(frozen=True)
class SolverState:
    """One candidate repair state inside the weighted search frontier."""

    config: ModpackConfig
    actions: tuple[RepairAction, ...] = ()
    total_cost: int = 0
    added_mod_ids: frozenset[str] = frozenset()
    removed_mod_ids: frozenset[str] = frozenset()


def canonical_state_key(config: ModpackConfig) -> tuple:
    """Return a stable key for de-duplicating equivalent selected configurations."""

    return (
        config.minecraft_version,
        config.loader,
        tuple(
            sorted(
                (
                    selected.mod_id,
                    selected.version_id or "",
                    selected.version_number or "",
                )
                for selected in config.selected_mods
            )
        ),
    )


def add_selected_mod(
    config: ModpackConfig,
    version: ModVersion,
) -> ModpackConfig:
    """Return a new config with one selected mod added."""

    existing_mod_ids = {selected.mod_id for selected in config.selected_mods}
    if version.mod_id in existing_mod_ids:
        raise ValueError(f"Mod '{version.mod_id}' is already selected.")

    updated = list(config.selected_mods) + [_selected_mod_from_version(version)]
    return _config_with_selected_mods(config, updated)


def remove_selected_mod(
    config: ModpackConfig,
    mod_id: str,
) -> ModpackConfig:
    """Return a new config with a selected mod removed."""

    updated = [selected.model_copy(deep=True) for selected in config.selected_mods if selected.mod_id != mod_id]
    if len(updated) == len(config.selected_mods):
        raise ValueError(f"Mod '{mod_id}' is not selected.")
    return _config_with_selected_mods(config, updated)


def replace_selected_mod_version(
    config: ModpackConfig,
    mod_id: str,
    new_version: ModVersion,
) -> ModpackConfig:
    """Return a new config with one selected mod moved to another version."""

    if new_version.mod_id != mod_id:
        raise ValueError(
            f"Replacement version '{new_version.version_id}' does not belong to mod '{mod_id}'."
        )

    updated = [selected.model_copy(deep=True) for selected in config.selected_mods if selected.mod_id != mod_id]
    if len(updated) == len(config.selected_mods):
        raise ValueError(f"Mod '{mod_id}' is not selected.")

    updated.append(_selected_mod_from_version(new_version))
    return _config_with_selected_mods(config, updated)


def deduplicate_selected_mod(
    config: ModpackConfig,
    mod_id: str,
) -> ModpackConfig:
    """Return a new config that keeps one deterministic selection for a duplicate mod."""

    matching = [selected.model_copy(deep=True) for selected in config.selected_mods if selected.mod_id == mod_id]
    if len(matching) <= 1:
        raise ValueError(f"Mod '{mod_id}' does not have duplicate selections.")

    keep = sorted(matching, key=_selected_mod_sort_key)[0]
    updated = [selected.model_copy(deep=True) for selected in config.selected_mods if selected.mod_id != mod_id]
    updated.append(keep)
    return _config_with_selected_mods(config, updated)


def count_original_mods_preserved(
    original: ModpackConfig,
    candidate: ModpackConfig,
) -> int:
    """Count how many original mod IDs remain selected."""

    original_mod_ids = {selected.mod_id for selected in original.selected_mods}
    candidate_mod_ids = {selected.mod_id for selected in candidate.selected_mods}
    return len(original_mod_ids.intersection(candidate_mod_ids))


def count_removed_original_mods(
    original: ModpackConfig,
    candidate: ModpackConfig,
) -> int:
    """Count how many originally selected mod IDs are no longer selected."""

    original_mod_ids = {selected.mod_id for selected in original.selected_mods}
    candidate_mod_ids = {selected.mod_id for selected in candidate.selected_mods}
    return len(original_mod_ids.difference(candidate_mod_ids))


def count_version_changes(
    original: ModpackConfig,
    candidate: ModpackConfig,
) -> int:
    """Count how many original selected mods remain but changed version selection."""

    original_map = {selected.mod_id: _selected_version_token(selected) for selected in original.selected_mods}
    candidate_map = {selected.mod_id: _selected_version_token(selected) for selected in candidate.selected_mods}
    changed = 0
    for mod_id, original_token in original_map.items():
        candidate_token = candidate_map.get(mod_id)
        if candidate_token is None:
            continue
        if candidate_token != original_token:
            changed += 1
    return changed


def _config_with_selected_mods(config: ModpackConfig, selected_mods: list[SelectedMod]) -> ModpackConfig:
    return ModpackConfig(
        minecraft_version=config.minecraft_version,
        loader=config.loader,
        selected_mods=_sorted_selected_mods(selected_mods),
    )


def _selected_mod_from_version(version: ModVersion) -> SelectedMod:
    return SelectedMod(
        mod_id=version.mod_id,
        version_id=version.version_id,
        version_number=version.version_number,
    )


def _selected_version_token(selected: SelectedMod) -> tuple[str, str]:
    return (
        selected.version_id or "",
        selected.version_number or "",
    )


def _sorted_selected_mods(selected_mods: list[SelectedMod]) -> list[SelectedMod]:
    return [
        selected.model_copy(deep=True)
        for selected in sorted(selected_mods, key=_selected_mod_sort_key)
    ]


def _selected_mod_sort_key(selected: SelectedMod) -> tuple[str, str, str]:
    return (
        selected.mod_id,
        selected.version_id or "",
        selected.version_number or "",
    )
