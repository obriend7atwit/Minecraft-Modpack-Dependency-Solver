"""Compatibility imports for weight profiles now owned by the solver package."""

from modpack_solver.solver.profiles import (
    WeightProfile,
    get_default_profile,
    get_preservation_profile,
    get_weight_profile,
    list_weight_profiles,
)

__all__ = [
    "WeightProfile",
    "get_default_profile",
    "get_preservation_profile",
    "get_weight_profile",
    "list_weight_profiles",
]
