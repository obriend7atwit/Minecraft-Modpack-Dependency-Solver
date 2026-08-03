from __future__ import annotations

import pytest
from pydantic import ValidationError

from modpack_solver.models import RepairAction, RepairActionType
from modpack_solver.solver.costs import RepairWeights, action_cost, plan_cost


def test_default_repair_weights_match_planned_values() -> None:
    weights = RepairWeights()

    assert weights.add_required_dependency == 1
    assert weights.upgrade_dependency == 2
    assert weights.downgrade_dependency == 3
    assert weights.upgrade_selected_mod == 4
    assert weights.downgrade_selected_mod == 5
    assert weights.remove_selected_mod == 10
    assert weights.change_minecraft_version == 20
    assert weights.change_loader == 25


def test_negative_repair_weight_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RepairWeights(remove_selected_mod=-1)


def test_action_cost_maps_each_action_type() -> None:
    weights = RepairWeights()

    assert action_cost(RepairAction(action_type=RepairActionType.ADD_DEPENDENCY, target_mod_id="a"), weights) == 1
    assert action_cost(RepairAction(action_type=RepairActionType.UPGRADE_DEPENDENCY, target_mod_id="a"), weights) == 2
    assert action_cost(RepairAction(action_type=RepairActionType.DOWNGRADE_DEPENDENCY, target_mod_id="a"), weights) == 3
    assert action_cost(RepairAction(action_type=RepairActionType.UPGRADE_MOD, target_mod_id="a"), weights) == 4
    assert action_cost(RepairAction(action_type=RepairActionType.DOWNGRADE_MOD, target_mod_id="a"), weights) == 5
    assert action_cost(RepairAction(action_type=RepairActionType.REMOVE_MOD, target_mod_id="a"), weights) == 10
    assert action_cost(RepairAction(action_type=RepairActionType.CHANGE_MINECRAFT_VERSION, target_mod_id="a"), weights) == 20
    assert action_cost(RepairAction(action_type=RepairActionType.CHANGE_LOADER, target_mod_id="a"), weights) == 25


def test_plan_cost_equals_sum_of_action_costs() -> None:
    weights = RepairWeights()
    actions = [
        RepairAction(action_type=RepairActionType.ADD_DEPENDENCY, target_mod_id="example-library"),
        RepairAction(action_type=RepairActionType.UPGRADE_MOD, target_mod_id="example-storage"),
        RepairAction(action_type=RepairActionType.REMOVE_MOD, target_mod_id="example-conflict"),
    ]

    assert plan_cost(actions, weights) == sum(action_cost(action, weights) for action in actions)


def test_custom_weights_are_honored() -> None:
    weights = RepairWeights(add_required_dependency=9, upgrade_selected_mod=12)

    assert action_cost(RepairAction(action_type=RepairActionType.ADD_DEPENDENCY, target_mod_id="a"), weights) == 9
    assert action_cost(RepairAction(action_type=RepairActionType.UPGRADE_MOD, target_mod_id="a"), weights) == 12
