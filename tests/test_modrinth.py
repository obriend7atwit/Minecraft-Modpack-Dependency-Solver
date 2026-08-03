from __future__ import annotations

from modpack_solver.metadata.modrinth import (
    normalize_modrinth_dependency,
    normalize_modrinth_version,
)
from modpack_solver.models import DependencyType, MetadataSource


def test_dependency_types_normalize_correctly() -> None:
    dependency_types = ["required", "optional", "incompatible", "embedded"]

    normalized = [
        normalize_modrinth_dependency(
            {
                "project_id": f"project-{dependency_type}",
                "dependency_type": dependency_type,
            }
        )
        for dependency_type in dependency_types
    ]

    assert [dependency.dependency_type for dependency in normalized] == [
        DependencyType.REQUIRED,
        DependencyType.OPTIONAL,
        DependencyType.INCOMPATIBLE,
        DependencyType.EMBEDDED,
    ]


def test_modrinth_dependency_normalization_uses_internal_model_shape() -> None:
    raw_dependency = {
        "project_id": "P7dR8mSH",
        "version_id": "AABBCCDD",
        "version_requirement": ">=1.0.0",
        "dependency_type": "required",
    }

    dependency = normalize_modrinth_dependency(raw_dependency)

    assert dependency.target_mod_id == "P7dR8mSH"
    assert dependency.target_version_id == "AABBCCDD"
    assert dependency.raw_constraint == ">=1.0.0"
    assert dependency.dependency_type == DependencyType.REQUIRED
    assert dependency.source == MetadataSource.MODRINTH


def test_modrinth_version_normalization_uses_internal_model_shape() -> None:
    raw_version = {
        "id": "IIJJKKLL",
        "project_id": "P7dR8mSH",
        "version_number": "0.100.1+1.21.1",
        "game_versions": ["1.21.1"],
        "loaders": ["fabric"],
        "version_type": "release",
        "dependencies": [
            {
                "project_id": "base-lib-id",
                "version_id": "base-lib-version-id",
                "dependency_type": "optional",
            }
        ],
    }

    version = normalize_modrinth_version(raw_version)

    assert version.version_id == "IIJJKKLL"
    assert version.mod_id == "P7dR8mSH"
    assert version.version_number == "0.100.1+1.21.1"
    assert version.game_versions == ["1.21.1"]
    assert version.loaders == ["fabric"]
    assert version.version_type == "release"
    assert version.source == MetadataSource.MODRINTH
    assert version.dependencies[0].dependency_type == DependencyType.OPTIONAL
