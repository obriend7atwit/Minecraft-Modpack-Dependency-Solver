from __future__ import annotations

from modpack_solver.models import ModVersion, ModpackConfig, SelectedMod
from modpack_solver.solver.state import (
    add_selected_mod,
    canonical_state_key,
    count_original_mods_preserved,
    count_removed_original_mods,
    count_version_changes,
    remove_selected_mod,
    replace_selected_mod_version,
)


def _base_config() -> ModpackConfig:
    return ModpackConfig(
        minecraft_version="1.20.1",
        loader="fabric",
        selected_mods=[
            SelectedMod(mod_id="example-storage", version_id="example-storage-1.0.0", version_number="1.0.0"),
            SelectedMod(mod_id="example-machines", version_id="example-machines-1.0.0", version_number="1.0.0"),
        ],
    )


def _library_version() -> ModVersion:
    return ModVersion(
        version_id="example-library-1.0.0",
        mod_id="example-library",
        version_number="1.0.0",
        game_versions=["1.20.1"],
        loaders=["fabric"],
    )


def _storage_upgrade() -> ModVersion:
    return ModVersion(
        version_id="example-storage-2.0.0",
        mod_id="example-storage",
        version_number="2.0.0",
        game_versions=["1.20.1"],
        loaders=["fabric"],
    )


def test_canonical_state_key_is_stable() -> None:
    config = _base_config()

    assert canonical_state_key(config) == canonical_state_key(config.model_copy(deep=True))


def test_selected_mod_order_does_not_change_canonical_key() -> None:
    config_a = _base_config()
    config_b = ModpackConfig(
        minecraft_version="1.20.1",
        loader="fabric",
        selected_mods=list(reversed(config_a.selected_mods)),
    )

    assert canonical_state_key(config_a) == canonical_state_key(config_b)


def test_different_versions_produce_different_keys() -> None:
    config = _base_config()
    changed = replace_selected_mod_version(config, "example-storage", _storage_upgrade())

    assert canonical_state_key(config) != canonical_state_key(changed)


def test_add_selected_mod_does_not_mutate_original_config() -> None:
    config = _base_config()
    original_dump = config.model_dump()

    updated = add_selected_mod(config, _library_version())

    assert config.model_dump() == original_dump
    assert any(selected.mod_id == "example-library" for selected in updated.selected_mods)


def test_remove_selected_mod_does_not_mutate_original_config() -> None:
    config = _base_config()
    original_dump = config.model_dump()

    updated = remove_selected_mod(config, "example-machines")

    assert config.model_dump() == original_dump
    assert all(selected.mod_id != "example-machines" for selected in updated.selected_mods)


def test_replace_selected_mod_version_does_not_mutate_original_config() -> None:
    config = _base_config()
    original_dump = config.model_dump()

    updated = replace_selected_mod_version(config, "example-storage", _storage_upgrade())

    assert config.model_dump() == original_dump
    assert any(selected.version_id == "example-storage-2.0.0" for selected in updated.selected_mods)


def test_original_mod_preservation_count_is_correct() -> None:
    original = _base_config()
    candidate = add_selected_mod(original, _library_version())

    assert count_original_mods_preserved(original, candidate) == 2


def test_removed_original_mod_count_is_correct() -> None:
    original = _base_config()
    candidate = remove_selected_mod(original, "example-machines")

    assert count_removed_original_mods(original, candidate) == 1


def test_version_change_count_is_correct() -> None:
    original = _base_config()
    candidate = replace_selected_mod_version(original, "example-storage", _storage_upgrade())

    assert count_version_changes(original, candidate) == 1
