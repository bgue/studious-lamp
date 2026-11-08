"""The requisitions module spec: record types, projectors, no command yet (P2-I4A S1)."""

from __future__ import annotations

from tl_mod_requisitions.module import REQUISITIONS_COMMANDS, projectors, spec
from tl_mod_requisitions.names import RECORD_TYPES, TABLES


def test_spec_registers_five_record_types_and_two_projectors() -> None:
    found = spec()
    assert found.name == "requisitions"
    assert found.record_types == RECORD_TYPES and len(RECORD_TYPES) == 5
    assert [p.name for p in projectors()] == ["requisitions_requisition", "requisitions_work_order"]


def test_no_command_and_one_table_per_type() -> None:
    assert REQUISITIONS_COMMANDS == ()
    assert set(TABLES) == RECORD_TYPES
    assert all(t.startswith("cur_requisitions_") for t in TABLES.values())
