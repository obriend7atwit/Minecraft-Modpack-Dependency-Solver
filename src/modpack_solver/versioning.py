"""Version comparison helpers for the synthetic weighted solver.

The current implementation targets simple synthetic version strings such as
`1.0.0`, `1.1.0`, and `2.0.0`. More complex Minecraft-specific version naming
still remains future work.
"""

from __future__ import annotations

from enum import Enum

from packaging.version import InvalidVersion, Version


class VersionDirection(str, Enum):
    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"
    SAME = "same"
    UNKNOWN = "unknown"


def compare_versions(
    current: str,
    candidate: str,
) -> VersionDirection:
    """Compare two version strings using packaging when possible."""

    current_version = _parse_version(current)
    candidate_version = _parse_version(candidate)
    if current_version is None or candidate_version is None:
        return VersionDirection.UNKNOWN
    if candidate_version > current_version:
        return VersionDirection.UPGRADE
    if candidate_version < current_version:
        return VersionDirection.DOWNGRADE
    return VersionDirection.SAME


def version_sort_key(version_number: str) -> tuple[int, object, str]:
    """Return a deterministic sort key for version strings."""

    parsed = _parse_version(version_number)
    if parsed is not None:
        return (0, parsed, version_number)
    return (1, version_number.lower(), version_number)


def _parse_version(value: str) -> Version | None:
    try:
        return Version(value)
    except InvalidVersion:
        return None
