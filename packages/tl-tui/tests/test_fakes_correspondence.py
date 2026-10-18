"""The fake client's correspondence reads follow the real client's rules (P1-I5)."""

from __future__ import annotations

from datetime import date

import pytest
from fakes import FakeClient
from tl_core.auth.errors import ForbiddenError
from tl_mod_correspondence import views
from tl_mod_correspondence.errors import ClockNotFoundError, ItemNotFoundError
from tl_mod_correspondence.handlers.clocks import SweepClocks
from tl_tui.client import ClientInterface

P = "P123"


def _clock(
    key: str, due: str, state: str = "running", effective: str = "running"
) -> views.ClockView:
    return views.ClockView(
        id=f"CLK-{key}", key=key, item_id="I1", item_number="GEN-0001", label="Reply", kind="reply",
        start_on="2026-10-01", duration_days=14, day_type="calendar", calendar="P123-default@1",
        warn_days=[3], due_on=due, state=state, effective_state=effective, days_left=1,
        warned_level=None, paused_on=None, closed_on=None, closed_reason=None, owner=None,
        clause_id=None, restarts=0,
    )  # fmt: skip


@pytest.fixture
def fake() -> FakeClient:
    client = FakeClient()
    client.add_clock(P, _clock("GEN-0001-C02", "2026-10-20"))
    client.add_clock(P, _clock("GEN-0001-C01", "2026-10-15", effective="expired"))
    client.add_clock(P, _clock("GEN-0001-C03", "2026-10-10", state="met", effective="met"))
    return client


def test_the_fake_still_satisfies_the_protocol(fake: FakeClient) -> None:
    as_protocol: ClientInterface = fake
    assert as_protocol.list_clocks(P)


def test_clocks_are_soonest_due_first_and_the_filters_apply(fake: FakeClient) -> None:
    assert [c.key for c in fake.list_clocks(P)] == ["GEN-0001-C01", "GEN-0001-C02"]
    assert [c.key for c in fake.list_clocks(P, open_only=False)][0] == "GEN-0001-C03"
    assert [c.key for c in fake.list_clocks(P, overdue_only=True)] == ["GEN-0001-C01"]
    assert [c.key for c in fake.list_clocks(P, due_to=date(2026, 10, 16))] == ["GEN-0001-C01"]


def test_an_unknown_item_or_clock_is_the_modules_error(fake: FakeClient) -> None:
    with pytest.raises(ItemNotFoundError):
        fake.get_correspondence(P, "GEN-9999")
    with pytest.raises(ClockNotFoundError):
        fake.get_clock(P, "nope")


def test_a_controllers_command_is_refused_for_anyone_else(fake: FakeClient) -> None:
    fake.is_corr_controller = False
    with pytest.raises(ForbiddenError):
        fake.correspondence_command(
            "SweepClocks", SweepClocks(actor="alice", scope=f"project:{P}", source="user")
        )
