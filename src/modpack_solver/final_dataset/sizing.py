"""Shared final-dataset modpack size categories."""

from enum import Enum


class PackSizeCategory(str, Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    HUGE = "huge"


def classify_pack_size(selected_mod_count: int) -> PackSizeCategory:
    """Classify a pack using the capstone's fixed publication boundaries."""

    if selected_mod_count < 0:
        raise ValueError("selected_mod_count cannot be negative.")
    if selected_mod_count <= 30:
        return PackSizeCategory.SMALL
    if selected_mod_count <= 80:
        return PackSizeCategory.MEDIUM
    if selected_mod_count <= 199:
        return PackSizeCategory.LARGE
    return PackSizeCategory.HUGE
