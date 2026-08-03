from __future__ import annotations

import pytest
from pydantic import ValidationError

from modpack_solver.models import (
    Dependency,
    DependencyType,
    MetadataSource,
    ModProject,
    ModVersion,
    ModpackConfig,
)


def test_models_validate_normal_inputs() -> None:
    dependency = Dependency(
        target_mod_id="example-library",
        dependency_type=DependencyType.REQUIRED,
        source=MetadataSource.SYNTHETIC,
    )
    project = ModProject(
        mod_id="example-machines",
        name="Example Machines",
        slug="example-machines",
        source=MetadataSource.SYNTHETIC,
    )
    version = ModVersion(
        version_id="example-machines-1.0.0",
        mod_id="example-machines",
        version_number="1.0.0",
        game_versions=["1.20.1"],
        loaders=["fabric"],
        dependencies=[dependency],
    )
    config = ModpackConfig(
        minecraft_version="1.20.1",
        loader="fabric",
        selected_mods=[{"mod_id": "example-machines", "version_id": "example-machines-1.0.0"}],
    )

    assert project.source == MetadataSource.SYNTHETIC
    assert version.dependencies[0].dependency_type == DependencyType.REQUIRED
    assert config.selected_mods[0].mod_id == "example-machines"


def test_invalid_dependency_type_fails_clearly() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Dependency(target_mod_id="example-library", dependency_type="broken-type")

    assert "dependency_type" in str(exc_info.value)
    assert "required" in str(exc_info.value)
