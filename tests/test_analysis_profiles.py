from __future__ import annotations

import pytest

from modpack_solver.analysis import (
    get_default_profile,
    get_preservation_profile,
    get_weight_profile,
    list_weight_profiles,
)
from modpack_solver.solver import RepairWeights


def test_default_profile_matches_current_default_weights() -> None:
    assert get_default_profile().weights == RepairWeights()


def test_preservation_profile_uses_removal_cost_20() -> None:
    assert get_preservation_profile().weights.remove_selected_mod == 20


def test_profiles_have_unique_ids() -> None:
    profile_ids = [profile.profile_id for profile in list_weight_profiles()]
    assert len(profile_ids) == len(set(profile_ids))


def test_profile_lookup_works() -> None:
    assert get_weight_profile("default").profile_id == "default"
    assert get_weight_profile("preservation").profile_id == "preservation"


def test_unknown_profile_fails_clearly() -> None:
    with pytest.raises(ValueError, match="Unknown weight profile"):
        get_weight_profile("surprise")


def test_returned_profiles_do_not_share_mutable_data() -> None:
    first = get_default_profile()
    second = get_default_profile()
    first.weights.remove_selected_mod = 99

    assert second.weights.remove_selected_mod == 10


def test_custom_values_do_not_replace_global_defaults() -> None:
    custom = get_preservation_profile()
    custom.weights.upgrade_selected_mod = 99

    assert get_preservation_profile().weights.upgrade_selected_mod == 5
    assert RepairWeights().upgrade_selected_mod == 4
