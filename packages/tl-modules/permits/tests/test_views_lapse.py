"""The SQL lapse filter of the views and ``rules.effective_state`` agree on the boundaries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from tl_core.ledger import iso_utc
from tl_mod_permits import rules, views

NOW = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize("state", ["Active", "Suspended", "Requested"])
@pytest.mark.parametrize(
    "valid_until",
    [None, NOW, NOW - timedelta(seconds=1), NOW + timedelta(seconds=1), NOW - timedelta(days=9)],
)
def test_the_sql_filter_and_effective_state_agree(state: str, valid_until: datetime | None) -> None:
    engine = create_engine("sqlite://")
    statement = text(
        f"SELECT {views._SHOWN} FROM (SELECT :state AS state) w, (SELECT :vu AS valid_until) p"
    )
    params = {
        "state": state,
        "vu": None if valid_until is None else iso_utc(valid_until),
        "now": iso_utc(NOW),
    }
    with engine.connect() as conn:
        shown = conn.execute(statement, params).scalar_one()
    assert shown == rules.effective_state(state, valid_until, NOW)
