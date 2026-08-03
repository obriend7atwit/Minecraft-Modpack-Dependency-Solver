import pytest

from modpack_solver.final_dataset.cascading import build_cascading_cases
from modpack_solver.final_dataset.repair_trace import replay_repair_plan
from modpack_solver.models import RepairAction, RepairActionType


def test_replay_records_before_and_after_reports():
    definition = build_cascading_cases()[0]
    trace = replay_repair_plan(definition.case, definition.known_valid_repair)
    assert trace.original_report == trace.steps[0].report_before
    assert trace.steps[-1].report_after == trace.final_report
    assert trace.final_compatible


def test_replay_rejects_unapplicable_action():
    definition = build_cascading_cases()[0]
    with pytest.raises(ValueError, match="could not be applied"):
        replay_repair_plan(
            definition.case,
            [
                RepairAction(
                    action_type=RepairActionType.REMOVE_MOD,
                    target_mod_id="not-selected",
                )
            ],
        )
