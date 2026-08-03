"""Typed domain models for metadata ingestion and future solver work."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class SolverBaseModel(BaseModel):
    """Shared Pydantic configuration for project models."""

    model_config = ConfigDict(extra="forbid")


class MetadataSource(str, Enum):
    SYNTHETIC = "synthetic"
    MODRINTH = "modrinth"
    LOCAL_FABRIC = "local_fabric"


class DependencyType(str, Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    INCOMPATIBLE = "incompatible"
    EMBEDDED = "embedded"


class IssueType(str, Enum):
    MISSING_DEPENDENCY = "missing_dependency"
    MINECRAFT_VERSION_MISMATCH = "minecraft_version_mismatch"
    LOADER_MISMATCH = "loader_mismatch"
    HARD_CONFLICT = "hard_conflict"
    OPTIONAL_DEPENDENCY_WARNING = "optional_dependency_warning"
    DUPLICATE_MOD_VERSION = "duplicate_mod_version"
    UNRESOLVED_SELECTED_MOD = "unresolved_selected_mod"
    UNKNOWN_DEPENDENCY_TARGET = "unknown_dependency_target"
    EMBEDDED_DEPENDENCY_INFO = "embedded_dependency_info"


class RepairActionType(str, Enum):
    ADD_DEPENDENCY = "add_dependency"
    UPGRADE_DEPENDENCY = "upgrade_dependency"
    DOWNGRADE_DEPENDENCY = "downgrade_dependency"
    UPGRADE_MOD = "upgrade_mod"
    DOWNGRADE_MOD = "downgrade_mod"
    REMOVE_MOD = "remove_mod"
    CHANGE_MINECRAFT_VERSION = "change_minecraft_version"
    CHANGE_LOADER = "change_loader"


class Dependency(SolverBaseModel):
    """Normalized dependency edge for a mod version."""

    target_mod_id: str
    dependency_type: DependencyType
    target_version_id: str | None = None
    raw_constraint: str | None = None
    source: MetadataSource | None = None


class ModProject(SolverBaseModel):
    mod_id: str
    name: str
    slug: str | None = None
    source: MetadataSource
    author: str | None = None
    description: str | None = None


class ModVersion(SolverBaseModel):
    """Normalized version metadata used by future compatibility logic."""

    version_id: str
    mod_id: str
    version_number: str
    game_versions: list[str]
    loaders: list[str]
    version_type: str | None = None
    dependencies: list[Dependency] = Field(default_factory=list)
    source: MetadataSource = MetadataSource.SYNTHETIC


class SelectedMod(SolverBaseModel):
    mod_id: str
    version_number: str | None = None
    version_id: str | None = None


class ModpackConfig(SolverBaseModel):
    minecraft_version: str
    loader: str
    selected_mods: list[SelectedMod] = Field(default_factory=list)


class CompatibilityIssue(SolverBaseModel):
    issue_type: IssueType
    message: str
    affected_mod_ids: list[str] = Field(default_factory=list)
    severity: str = "error"


class RepairAction(SolverBaseModel):
    action_type: RepairActionType
    target_mod_id: str
    target_version_id: str | None = None
    target_version_number: str | None = None
    cost: int = 0
    reason: str | None = None


class SyntheticCase(SolverBaseModel):
    """Container for a deterministic synthetic modpack scenario."""

    config: ModpackConfig
    projects: list[ModProject] = Field(default_factory=list)
    versions: list[ModVersion] = Field(default_factory=list)
