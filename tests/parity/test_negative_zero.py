"""A pset number stored as -0.0 reads back as 0.0 on both adapters (P0-I5 review ruling)."""

from __future__ import annotations

import math
from collections.abc import Callable

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core.projection.pset import typed_columns

INSERT = text(
    "INSERT INTO cur_pset_values (record_id, scope, path, pset, property_name, layer, value_type, "
    "value_text, value_num, value_bool, value_json, last_seq, updated_at) VALUES "
    "('r', 'company', 'p.x', 'p', 'x', 'standard', :value_type, :value_text, :value_num, "
    ":value_bool, :value_json, 1, '2026-10-09T12:00:00+00:00')"
)


@pytest.mark.parametrize("value", [-0.0, 0.0, 0, -1.5])
def test_a_negative_zero_is_stored_as_zero(new_db: Callable[[], DbTarget], value: float) -> None:
    target = new_db()
    create_schema(target)
    columns = typed_columns(value)
    with open_uow(target) as uow:
        uow.conn().execute(INSERT, columns)
    with open_uow(target, readonly=True) as uow:
        stored = uow.conn().execute(text("SELECT value_num FROM cur_pset_values")).scalar_one()
    assert stored == value
    assert math.copysign(1.0, stored) == math.copysign(1.0, abs(value) if value == 0 else value)
