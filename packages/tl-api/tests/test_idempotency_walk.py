"""Idempotency keys at the HTTP edge, walked as five kinds of reader (P2-X1-T07).

Five readers: the confidentiality walk's accounts (a plain user, a document controller, an admin,
a person named on privileged items, and an agent). Each files ``CreateRecord`` with key K. The
record's class then rises above what every reader may read, so the same reader's replay of K must
show nothing of the record and answer as for a record that never existed. ``CreateRecord`` refuses
extension types over HTTP, so the class comes from a test-only source on ``core.Record`` (the
pattern of ``seed_week`` in the confidentiality walk).

The cross-actor cases: the same key value sent by another actor neither replays the first answer
nor collides with it. The other-body case uses another record key, so the duplicate-record-key rule
is not what is tested there.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from harness import ALICE, BOB, SCOPE, Harness
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_api_walk import FAKE_ID, MAY_READ, Seed, seed  # pyright: ignore[reportMissingImports]
from tl_core import confidentiality as cf
from tl_core import modules as core_modules
from tl_core.modules import ConfidentialSource

KEY = "walk-key-5e2b91"
CLASS_TABLE = "walk_idem_class"


@pytest.fixture
def harness(parity_harness: Harness) -> Harness:
    return parity_harness


@pytest.fixture
def seeded(harness: Harness, tmp_path: Path) -> Seed:
    return seed(harness, tmp_path)


@pytest.fixture
def classed(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    """``core.Record`` rows carry a class in ``CLASS_TABLE`` (a test-only source, as seed_week)."""
    with open_uow(harness.target or harness.db) as uow:
        uow.conn().execute(
            text(f"CREATE TABLE {CLASS_TABLE} (id TEXT PRIMARY KEY, cls TEXT NOT NULL)")
        )
    source = ConfidentialSource(
        record_types=frozenset({"core.Record"}),
        table=CLASS_TABLE,
        id_column="id",
        class_column="cls",
    )
    real = core_modules.confidential_sources
    monkeypatch.setattr(cf, "confidential_sources", lambda: [*real(), source])


def body(title: str = "Valve", key: str = "REC-1", **extra: Any) -> dict[str, Any]:
    return {"scope": SCOPE, "record_type": "core.Record", "title": title, "key": key, **extra}


def post(h: Harness, body_: dict[str, Any], header: str | None = None, actor: str = ALICE) -> Any:
    headers = {} if header is None else {"Idempotency-Key": header}
    return h.client_for(actor).post("/commands/CreateRecord", json=body_, headers=headers)


def scalar(harness: Harness, sql: str) -> int:
    with harness.backend(True) as uow:
        return int(uow.conn().execute(text(sql)).scalar_one())


def set_class(harness: Harness, record_id: str, cls: str) -> None:
    with open_uow(harness.target or harness.db) as uow:
        found = (
            uow.conn()
            .execute(text(f"SELECT 1 FROM {CLASS_TABLE} WHERE id = :i"), {"i": record_id})
            .first()
        )
        if found is None:
            uow.conn().execute(
                text(f"INSERT INTO {CLASS_TABLE} (id, cls) VALUES (:i, :c)"),
                {"i": record_id, "c": cls},
            )
        else:
            uow.conn().execute(
                text(f"UPDATE {CLASS_TABLE} SET cls = :c WHERE id = :i"),
                {"i": record_id, "c": cls},
            )


#: The four people. The agent reader files through MCP only (see the agent test below).
PEOPLE = [reader for reader in sorted(MAY_READ) if reader != "bot"]


@pytest.mark.parametrize("reader", PEOPLE)
def test_a_replay_after_the_clearance_drops_shows_nothing_of_the_record(
    harness: Harness, seeded: Seed, classed: None, reader: str
) -> None:
    client = harness.client_for(None)
    auth = {"Authorization": f"Bearer {seeded.tokens[reader]}"}
    keyed = {**auth, "Idempotency-Key": KEY}
    title = f"walk-title-{reader}-7d1f"
    request = body(title=title, key=f"WALK-{reader}")

    first = client.post("/commands/CreateRecord", json=request, headers=keyed)
    assert first.status_code == 200, first.text
    record_id = first.json()["stream_id"]

    set_class(harness, record_id, "internal")  # every reader may read it while K is filed
    visible = client.post("/commands/CreateRecord", json=request, headers=keyed)
    assert visible.status_code == 200, visible.text
    assert visible.json() == first.json(), reader

    # the clearance drops: no reader is named on a privileged item, so the record reads as absent
    set_class(harness, record_id, "privileged")
    replay = client.post("/commands/CreateRecord", json=request, headers=keyed)
    assert title not in replay.text, (reader, replay.text)

    hidden = client.get(f"/records/{record_id}/actions", headers=auth)
    nothing = client.get(f"/records/{FAKE_ID}/actions", headers=auth)
    assert hidden.status_code == nothing.status_code, (reader, hidden.text)
    assert hidden.text.replace(record_id, FAKE_ID) == nothing.text, (reader, hidden.text)
    assert title not in hidden.text, (reader, hidden.text)
    assert replay.status_code == nothing.status_code, (reader, replay.text)


def test_another_actor_with_the_same_key_and_other_body_gets_its_own_record_not_a_409(
    harness: Harness,
) -> None:
    alice = post(harness, body(key="REC-A"), KEY, actor=ALICE)
    assert alice.status_code == 200, alice.text
    bobs = post(harness, body(key="REC-OTHER", title="Pump"), KEY, actor=BOB)
    assert bobs.status_code != 409, bobs.text
    assert bobs.status_code == 200, bobs.text
    assert bobs.json()["stream_id"] != alice.json()["stream_id"]
    assert scalar(harness, "SELECT COUNT(*) FROM idempotency_key") == 2


def test_another_actor_with_the_same_key_and_same_title_gets_its_own_record_not_a_409(
    harness: Harness,
) -> None:
    # the record key differs: a second "REC-SAME" would be the duplicate-record-key rule (409
    # duplicate_key), which is not idempotency and is not tested here
    alice = post(harness, body(key="REC-A"), KEY, actor=ALICE)
    assert alice.status_code == 200, alice.text
    bobs = post(harness, body(key="REC-B"), KEY, actor=BOB)
    assert bobs.status_code != 409, bobs.text
    assert bobs.status_code == 200, bobs.text
    assert bobs.json()["stream_id"] != alice.json()["stream_id"]


def test_an_agent_cannot_file_create_record_over_http_so_its_keyed_filing_is_the_mcp_path(
    harness: Harness, seeded: Seed
) -> None:
    client = harness.client_for(None)
    headers = {"Authorization": f"Bearer {seeded.tokens['bot']}", "Idempotency-Key": KEY}
    refused = client.post("/commands/CreateRecord", json=body(key="WALK-bot"), headers=headers)
    assert refused.status_code == 403, refused.text
    assert refused.json()["error"] == "agent_must_propose"
    assert scalar(harness, "SELECT COUNT(*) FROM idempotency_key") == 0
