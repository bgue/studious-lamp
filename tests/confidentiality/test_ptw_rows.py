"""Permit confidentiality rows (P2-PTW S2): a permit is hidden through the record the work is for,
a gas test through its permit (the second hop), an isolation through its own point record.

Rows are made through the permit commands and the ledger events S3 will one day write (a gas test
and an isolation have no command yet); a restricted record through the correspondence module's own
command. Five readers: nobody (the default), an agent, a viewer, an ordinary user and the foreman
who asked for the permit; the cleared reader sees all of it.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core import confidentiality as cf
from tl_core.modules import load_modules
from tl_core.services import queries
from tl_core.services.errors import RecordNotFoundError
from tl_core.util import new_ulid

_PERMITS_TESTS = (
    Path(__file__).resolve().parents[2] / "packages" / "tl-modules" / "permits" / "tests"
)
if str(_PERMITS_TESTS) not in sys.path:
    sys.path.insert(0, str(_PERMITS_TESTS))

from permit_world import SCOPE, World  # noqa: E402
from tl_mod_permits.handlers import permit as permit_handlers  # noqa: E402
from tl_mod_permits.names import GAS_TEST, ISOLATION, PERMIT  # noqa: E402

READERS = {
    "nobody": cf.LOWEST,
    "agent": cf.Viewer(actor="agent:bot", level=0, account=""),
    "viewer": cf.Viewer(actor="user:vera", level=0, account="user:vera"),
    "user": cf.Viewer(actor="user:uma", level=0, account="user:uma"),
    "foreman": cf.Viewer(actor="user:rob", level=0, account="user:rob"),
}
CLEARED = cf.Viewer(actor="user:dora", level=1, account="user:dora")
MISSING = "no record with that id"


@pytest.fixture
def world(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> World:
    target = new_db()
    create_schema(target)
    made = World(target)
    made.people()
    monkeypatch.setattr(permit_handlers, "now", lambda: made.at)
    return made


def hidden(world: World, record: str, viewer: cf.Viewer) -> bool:
    with open_uow(world.db, readonly=True) as uow:
        return cf.is_hidden(uow.conn(), record, viewer)


def listed(world: World, viewer: cf.Viewer, record_type: str) -> list[str]:
    with open_uow(world.db, readonly=True) as uow, cf.use_viewer(viewer):
        return [r["id"] for r in queries.list_records(uow, SCOPE, record_type=record_type)]


def secret_set(world: World) -> tuple[str, str, str, str]:
    """A permit for a restricted record, its gas test, an open permit and its gas test."""
    secret = world.hidden_record()
    iwp = world.record("awp.IWP", "IWP-1")
    hid = world.request("dora", "hot_work", for_record_id=secret)
    open_ = world.request("rob", "hot_work", for_record_id=iwp)
    return hid, world.gas_test(hid), open_, world.gas_test(open_)


def test_the_three_rows_are_the_last_three_subject_links() -> None:
    assert cf.SUBJECT_LINKS[-3:] == (
        ("permits.Permit", "cur_permits_permit", "id", "for_record_id"),
        ("permits.Isolation", "cur_permits_isolation", "id", "point_record_id"),
        ("permits.GasTest", "cur_permits_gas_test", "id", "permit_id"),
    )
    assert {r[0] for r in cf.SUBJECT_LINKS[-3:]} == {PERMIT, ISOLATION, GAS_TEST}


def test_a_permit_and_its_gas_test_on_a_restricted_record_are_absent_for_five_readers(
    world: World,
) -> None:
    hid, hid_gas, open_, open_gas = secret_set(world)
    ghost = new_ulid()
    with open_uow(world.db, readonly=True) as uow:
        rows = [
            dict(r)
            for r in uow.conn()
            .execute(text("SELECT event_id, stream_id, stream_type, payload FROM events"))
            .mappings()
        ]
    own = {r["event_id"] for r in rows if r["stream_id"] in (hid, hid_gas)}
    assert own
    for name, viewer in READERS.items():
        for record in (hid, hid_gas):
            assert hidden(world, record, viewer), (name, record)
        for record in (open_, open_gas):
            assert not hidden(world, record, viewer), (name, record)
        assert listed(world, viewer, PERMIT) == [open_], name
        assert listed(world, viewer, GAS_TEST) == [open_gas], name
        with open_uow(world.db, readonly=True) as uow, cf.use_viewer(viewer):
            for record in (hid, hid_gas):
                assert queries.get_record_by_id(uow, record) is None
                assert queries.record_history(uow, record) == queries.record_history(uow, ghost)
            assert cf.hidden_row_ids(uow.conn(), rows) & own == own, name
            feed = [r for r in rows if r["event_id"] not in cf.hidden_row_ids(uow.conn(), rows)]
            assert not {r["stream_id"] for r in feed} & {hid, hid_gas}, name
    for record in (hid, hid_gas):
        assert not hidden(world, record, CLEARED)
    assert sorted(listed(world, CLEARED, PERMIT)) == sorted([hid, open_])
    assert sorted(listed(world, CLEARED, GAS_TEST)) == sorted([hid_gas, open_gas])


def test_an_isolation_with_no_point_record_is_its_own_subject(world: World) -> None:
    free = world.isolation()
    for viewer in READERS.values():
        assert not hidden(world, free, viewer)


def test_a_hidden_permit_and_a_missing_id_answer_alike_on_approve_and_request(
    world: World,
) -> None:
    hid, _gas, _open, _og = secret_set(world)
    answers = set()
    for record in (hid, new_ulid()):
        with pytest.raises(RecordNotFoundError) as caught:
            world.call("sue", "ApprovePermit", permit=record)
        answers.add(str(caught.value))
    with pytest.raises(RecordNotFoundError) as caught:
        world.request("sue", for_record_id=world.hidden_record())
    answers.add(str(caught.value))
    assert answers == {MISSING}
    assert world.state(hid) == "Requested"


def test_the_hidden_sql_is_under_the_join_limit_with_the_permit_rows(world: World) -> None:
    assert "permits" in {spec.name for spec in load_modules()}
    for viewer in (*READERS.values(), CLEARED):
        sql = cf.hidden_sql(viewer)
        assert sql is not None
        assert max(part.count("JOIN") for part in sql.split(" UNION ALL ")) < 64, viewer
        statement = f"SELECT x.id FROM cur_core_record x WHERE x.id IN ({sql})"
        with open_uow(world.db, readonly=True) as uow:
            conn = uow.conn()
            conn.execute(text(f"EXPLAIN {statement}"), cf.params_for(sql, viewer)).all()
            conn.execute(text(statement), cf.params_for(sql, viewer)).all()
