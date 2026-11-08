"""``GET /records/{id}/checks`` as five kinds of reader (P2-INS-S2).

The world is small and written straight into the current-state tables (the Checks read is a pure
read of them, and the walk of ``test_confidentiality_walk`` cannot seed on Postgres): an IWP with
findings that names a hidden record, and four correspondence items, one of each class (internal,
restricted, privileged for one person, a class nobody knows). Every record is asked for as each
reader; a hidden record answers exactly as an id that names nothing, and the read writes nothing
on either adapter.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from harness import Harness
from sqlalchemy import Connection, Engine, event, text
from test_confidentiality_walk import PASSWORD, _person  # pyright: ignore[reportMissingImports]
from tl_core.auth import accounts, sessions
from tl_core.util import new_ulid

_SEED = Path(__file__).resolve().parents[2] / "tl-core/tests/insights/test_checks.py"
_spec = importlib.util.spec_from_file_location("insights_world", _SEED)
assert _spec is not None and _spec.loader is not None
_world = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_world)
seed_world = _world.seed_world
SCOPE = _world.SCOPE
FAKE_ID = "01J000000000000000000000"

#: What each reader may read, by kind. ``iwp`` is not confidential; ``hidden`` is read by nobody.
MAY_READ = {
    "bob": {"open", "iwp", "corr"},
    "ctl": {"open", "restricted", "iwp", "corr"},
    "boss": {"open", "restricted", "iwp", "corr"},
    "amy": {"open", "privileged", "iwp", "corr"},
    "bot": {"open", "iwp", "corr"},
}


@dataclass
class Seed:
    ids: dict[str, str]
    tokens: dict[str, str]


def _item(conn: Connection, key: str, klass: str) -> str:
    rid = _world.record(conn, "correspondence.Correspondence", key)
    conn.execute(
        text(
            "INSERT INTO cur_correspondence_correspondence (id, scope, number, direction, medium, "
            "received_via, confidentiality, last_seq) VALUES (:i, :s, :k, 'in', 'letter', "
            "'manual', :c, 1)"
        ),
        {"i": rid, "s": SCOPE, "k": key, "c": klass},
    )
    return rid


def seed(h: Harness) -> Seed:
    with h.backend(False) as uow:
        for name, roles in (("bob", ["user"]), ("ctl", ["document_controller"]),
                            ("boss", ["admin"]), ("amy", ["user"])):  # fmt: skip
            _person(uow, name, roles)
        bot = accounts.create_account(
            uow, username="bot", display_name="Bot", kind="agent", roles=["user"], password=None,
            by="svc:test",
        )  # fmt: skip
        _, agent_token = accounts.issue_agent_token(
            uow, account_id=bot.account_id, label="walk",
            expires_at=datetime.now(UTC) + timedelta(days=1), by="svc:test",
        )  # fmt: skip
        conn = uow.conn()
        ids = seed_world(conn)  # iwp, corr (internal, with a clock), hidden (no module row), ...
        ids["open"] = _item(conn, "P123-COR-0101", "internal")
        ids["restricted"] = _item(conn, "P123-COR-0102", "restricted")
        ids["privileged"] = _item(conn, "P123-COR-0103", "privileged")
        ids["bogus"] = _item(conn, "P123-COR-0104", "bogus")
        conn.execute(
            text(
                "INSERT INTO cur_correspondence_clearance (clearance_id, scope, record_id, account,"
                " granted_by, granted_on, last_seq) VALUES (:c, :s, :r, 'user:amy', 'user:ctl',"
                " '2026-10-01', 1)"
            ),
            {"c": new_ulid(), "s": SCOPE, "r": ids["privileged"]},
        )
    tokens = {
        name: sessions.sign_in(h.backend, username=name, password=PASSWORD)[1]
        for name in ("bob", "ctl", "boss", "amy")
    }
    return Seed(ids, {**tokens, "bot": agent_token})


def hidden_markers(s: Seed, reader: str) -> tuple[list[str], list[str]]:
    """(texts, ids) of what the reader must never see in a response."""
    may = MAY_READ[reader]
    ids = [s.ids[k] for k in ("restricted", "privileged", "bogus", "hidden") if k not in may]
    return ["SECRET"], ids


@pytest.fixture
def harness(parity_harness: Harness) -> Harness:
    return parity_harness


@pytest.fixture
def seeded(harness: Harness) -> Seed:
    return seed(harness)


@pytest.mark.parametrize("reader", sorted(MAY_READ))
def test_checks_tell_each_reader_only_about_the_records_they_may_read(
    harness: Harness, seeded: Seed, reader: str
) -> None:
    client = harness.client_for(None)
    headers = {"Authorization": f"Bearer {seeded.tokens[reader]}"}
    tokens, hidden_ids = hidden_markers(seeded, reader)
    nothing = client.get(f"/records/{FAKE_ID}/checks", headers=headers)
    assert nothing.status_code == 404 and nothing.json()["error"] == "record_not_found"
    readable = 0
    for kind, record_id in sorted(seeded.ids.items()):
        found = client.get(f"/records/{record_id}/checks", headers=headers)
        if record_id in hidden_ids:  # hidden equals missing: status, body and headers
            assert found.status_code == 404, (reader, kind)
            assert found.text.replace(record_id, FAKE_ID) == nothing.text, (reader, kind)
            assert sorted(found.headers) == sorted(nothing.headers), (reader, kind)
            continue
        readable += 1
        assert found.status_code == 200, (reader, kind, found.text)
        assert isinstance(found.json(), list)
        for marker in [*tokens, *hidden_ids]:
            assert marker not in found.text, (reader, kind, marker)
    assert readable >= 2  # the reader reads some, so the test can fail


def test_the_checks_route_is_open_to_no_one_without_a_token(harness: Harness) -> None:
    assert harness.client_for(None).get(f"/records/{FAKE_ID}/checks").status_code == 401


def test_the_read_writes_nothing_on_either_adapter(harness: Harness, seeded: Seed) -> None:
    verbs: list[str] = []

    def listener(_c: Any, _cur: Any, statement: str, *_a: Any) -> None:
        verbs.append(statement.lstrip().split(None, 1)[0].upper())

    client = harness.client_for(None)
    headers = {"Authorization": f"Bearer {seeded.tokens['ctl']}"}
    event.listen(Engine, "before_cursor_execute", listener)
    try:
        for record_id in seeded.ids.values():
            client.get(f"/records/{record_id}/checks", headers=headers)
    finally:
        event.remove(Engine, "before_cursor_execute", listener)
    writes = {v for v in verbs if v in {"INSERT", "UPDATE", "DELETE", "REPLACE", "CREATE", "DROP"}}
    assert verbs and not writes, writes
    with harness.backend(True) as uow:
        assert uow.conn().execute(text("SELECT COUNT(*) FROM telemetry_need")).scalar_one() == 0


@pytest.mark.parametrize("reader", sorted(MAY_READ))
def test_the_iwp_answers_every_reader_with_findings_and_no_hidden_key(
    harness: Harness, seeded: Seed, reader: str
) -> None:
    answer = harness.client_for(None).get(
        f"/records/{seeded.ids['iwp']}/checks",
        headers={"Authorization": f"Bearer {seeded.tokens[reader]}"},
    )
    assert answer.status_code == 200
    found = answer.json()
    assert [f["source"] for f in found] == [
        "readiness", "readiness", "readiness", "constraints", "expected_links", "shortages",
    ]  # fmt: skip
    assert "Some blocking records are not available to you." in found[0]["text"]
    assert [r["record_id"] for r in found[0]["resolve_via"]] == [seeded.ids["doc"]]
    assert "SECRET" not in answer.text and seeded.ids["hidden"] not in answer.text
    # the clock hangs on a correspondence item, which every reader here may read
    (clock,) = (
        harness.client_for(None)
        .get(
            f"/records/{seeded.ids['corr']}/checks",
            headers={"Authorization": f"Bearer {seeded.tokens[reader]}"},
        )
        .json()
    )
    assert clock["source"] == "clocks" and clock["severity"] == "blocking"
