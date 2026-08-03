"""Named repair-weight profiles shared by the application and experiments."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from modpack_solver.solver.costs import RepairWeights


class WeightProfile(BaseModel):
    """A named, reproducible repair-weight configuration."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    display_name: str
    description: str
    weights: RepairWeights


def get_default_profile() -> WeightProfile:
    return WeightProfile(
        profile_id="default",
        display_name="Default",
        description=(
            "Current solver defaults. Lower raw cost means less disruption within this profile, "
            "but raw costs should not be compared directly across profiles."
        ),
        weights=RepairWeights(),
    )


def get_preservation_profile() -> WeightProfile:
    return WeightProfile(
        profile_id="preservation",
        display_name="Preservation-focused",
        description=(
            "Keeps add-dependency costs low while raising selected-mod version-change and removal "
            "costs. Raw costs use a different scale from the default profile."
        ),
        weights=RepairWeights(
            add_required_dependency=1,
            upgrade_dependency=2,
            downgrade_dependency=3,
            upgrade_selected_mod=5,
            downgrade_selected_mod=6,
            remove_selected_mod=20,
            change_minecraft_version=20,
            change_loader=25,
        ),
    )


def list_weight_profiles() -> list[WeightProfile]:
    return [get_default_profile(), get_preservation_profile()]


def get_weight_profile(profile_id: str) -> WeightProfile:
    for profile in list_weight_profiles():
        if profile.profile_id == profile_id:
            return profile
    known = ", ".join(profile.profile_id for profile in list_weight_profiles())
    raise ValueError(f"Unknown weight profile '{profile_id}'. Known profiles: {known}.")
