"""A permit is hidden when the record it is for is; a refusal never names that record."""

from __future__ import annotations

import pytest
from permit_world import IWP, World
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.services.errors import RecordNotFoundError
from tl_core.util import new_ulid

CLEARED = cf.Viewer(actor="user:dora", level=1, account="user:dora")


def hidden(world: World, record: str, viewer: cf.Viewer | None = None) -> bool:
    with open_uow(world.db, readonly=True) as uow:
        return cf.is_hidden(uow.conn(), record, viewer)


def test_a_permit_for_a_restricted_record_is_hidden_from_the_default_viewer(
    world: World,
) -> None:
    secret = world.hidden_record()
    permit = world.request("dora", for_record_id=secret)
    assert hidden(world, permit) and not hidden(world, permit, CLEARED)
    with pytest.raises(RecordNotFoundError, match="no record with that id"):
        world.call("sue", "ApprovePermit", permit=permit)
    assert world.state(permit) == "Requested"


def test_the_refusal_for_a_hidden_for_record_id_does_not_name_it(world: World) -> None:
    secret = world.hidden_record()
    with pytest.raises(RecordNotFoundError) as hid:
        world.request("uma", for_record_id=secret)
    with pytest.raises(RecordNotFoundError) as gone:
        world.request("uma", for_record_id=new_ulid())
    assert secret not in str(hid.value)
    assert str(hid.value) == "no record with that id"
    assert str(gone.value) == str(hid.value)


def test_a_permit_with_no_or_an_open_record_falls_back_to_its_own_class(world: World) -> None:
    free = world.request()
    mine = world.request(for_record_id=world.record(IWP, "IWP-1"))
    for permit in (free, mine):
        assert not hidden(world, permit)


def test_a_gas_test_is_hidden_through_its_permit(world: World) -> None:
    secret = world.hidden_record()
    permit = world.request("dora", "hot_work", for_record_id=secret)
    gas = world.gas_test(permit)
    assert hidden(world, gas) and not hidden(world, gas, CLEARED)
