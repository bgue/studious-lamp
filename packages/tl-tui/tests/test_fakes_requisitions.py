"""The fake client's requisition and work order reads follow the views' rules (P2-I4A T04c2)."""

from __future__ import annotations

import pytest
from fakes import FakeClient
from fakes_requisitions import PROJECT, seed_requisitions
from tl_core.services.errors import RecordNotFoundError
from tl_tui.client import ClientInterface


@pytest.fixture
def fake() -> FakeClient:
    client = FakeClient()
    seed_requisitions(client)
    return client


def test_the_fake_still_satisfies_the_protocol(fake: FakeClient) -> None:
    protocol: ClientInterface = fake
    assert protocol is fake


def test_the_seed_holds_five_requisitions_and_two_work_orders(fake: FakeClient) -> None:
    requisitions = fake.list_requisitions(PROJECT)
    assert len(requisitions.rows) == requisitions.total == 5
    orders = fake.list_work_orders(PROJECT)
    assert len(orders.rows) == orders.total == 2


def test_the_seed_has_the_kinds_the_acceptance_shape_names(fake: FakeClient) -> None:
    kinds = [row.kind for row in fake.list_requisitions(PROJECT).rows]
    assert sorted(kinds) == ["general", "labor", "labor", "material", "scaffold"]


def test_each_filter_narrows_and_the_total_equals_the_rows(fake: FakeClient) -> None:
    cases = {
        "kind": (fake.list_requisitions(PROJECT, kind="labor"), 2),
        "state": (fake.list_requisitions(PROJECT, state="Approved"), 1),
        "requester": (fake.list_requisitions(PROJECT, requester="user:uma"), 3),
        "for_key": (fake.list_requisitions(PROJECT, for_key=f"{PROJECT}-IWP-PIP-0001"), 2),
    }
    for name, (page, count) in cases.items():
        assert len(page.rows) == page.total == count, name
    rejected = fake.list_requisitions(PROJECT, state="Rejected")
    assert [row.kind for row in rejected.rows] == ["scaffold"]


def test_the_limit_clamps_the_rows_and_the_total_counts_them(fake: FakeClient) -> None:
    page = fake.list_requisitions(PROJECT, limit=2)
    assert len(page.rows) == page.total == 2
    assert [row.key for row in page.rows] == sorted(row.key for row in page.rows)


def test_an_unknown_key_gives_an_empty_list_not_an_error(fake: FakeClient) -> None:
    page = fake.list_requisitions(PROJECT, for_key=f"{PROJECT}-IWP-NOPE")
    assert page.rows == [] and page.total == 0


def test_get_requisition_carries_its_work_order_or_none(fake: FakeClient) -> None:
    approved = fake.get_requisition(PROJECT, f"{PROJECT}-REQ-0001")
    assert approved.work_order is not None
    assert approved.work_order.key == f"{PROJECT}-WO-0001"
    assert fake.get_requisition(PROJECT, f"{PROJECT}-REQ-0002").work_order is None


def test_a_missing_requisition_raises_record_not_found(fake: FakeClient) -> None:
    with pytest.raises(RecordNotFoundError, match="no requisition 'P123-REQ-9999'"):
        fake.get_requisition(PROJECT, f"{PROJECT}-REQ-9999")


def test_the_work_order_filters_narrow(fake: FakeClient) -> None:
    scheduled = fake.list_work_orders(PROJECT, state="Scheduled")
    assert len(scheduled.rows) == scheduled.total == 1
    assigned = fake.list_work_orders(PROJECT, assigned_to="user:uma")
    assert len(assigned.rows) == assigned.total == 1


def test_get_work_order_names_its_requisition_and_a_missing_key_raises(fake: FakeClient) -> None:
    order = fake.get_work_order(PROJECT, f"{PROJECT}-WO-0001")
    assert order.requisition_key == f"{PROJECT}-REQ-0001"
    with pytest.raises(RecordNotFoundError, match="no work order 'P123-WO-9999'"):
        fake.get_work_order(PROJECT, f"{PROJECT}-WO-9999")
