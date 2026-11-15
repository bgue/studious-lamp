"""`forms_intake_body` is operational: a rebuild keeps it and no projector writes it."""

from __future__ import annotations

import importlib
import inspect

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow, rebuild_projections
from tl_core.ledger import NewEvent
from tl_core.util import new_ulid
from tl_mod_forms.module import projectors
from tl_mod_forms.names import INTAKE_BODY_TABLE, INTAKE_ITEM

SCOPE = "project:P123"


def _receive(db: DbTarget) -> str:
    """Append a received intake item through the ledger; returns its id."""
    item = new_ulid()
    envelope = NewEvent(
        event_type="Record.Created",
        payload={
            "record_type": INTAKE_ITEM,
            "key": "II-" + item[-6:],
            "title": "item",
            "description": None,
            "psets": {},
        },
    )
    received = NewEvent(
        event_type="IntakeItem.Received",
        payload={
            "record_id": item,
            "item_id": item,
            "code_id": new_ulid(),
            "template_id": new_ulid(),
            "template_version": 1,
            "template_hash": "ab" * 32,
            "body_mac": "cd" * 32,
            "body_bytes": 20,
            "received_at": "2026-12-01T09:00:00Z",
            "feed_policy": "none",
        },
    )
    with open_uow(db) as uow:
        uow.append(
            stream_id=item,
            stream_type=INTAKE_ITEM,
            scope=SCOPE,
            expected_version=0,
            events=[envelope, received],
            actor="svc:intake",
            source="test",
            correlation_id=new_ulid(),
        )
    return item


def _insert(db: DbTarget, item_id: str, body: str) -> None:
    with open_uow(db) as uow:
        uow.conn().execute(
            text(
                f"INSERT INTO {INTAKE_BODY_TABLE} (item_id, code_id, salt, body, received_at) "
                "VALUES (:i, :c, :s, :b, :r)"
            ),
            {"i": item_id, "c": new_ulid(), "s": "0f" * 16, "b": body, "r": "2026-12-01T09:00:00Z"},
        )


def _rows(db: DbTarget) -> list[tuple[str, str]]:
    with open_uow(db) as uow:
        found = uow.conn().execute(
            text(f"SELECT item_id, body FROM {INTAKE_BODY_TABLE} ORDER BY item_id")
        )
        return [(str(r[0]), str(r[1])) for r in found]


def _items(db: DbTarget) -> int:
    with open_uow(db) as uow:
        return int(
            uow.conn().execute(text("SELECT COUNT(*) FROM cur_forms_intake_item")).scalar_one()
        )


def test_a_body_row_survives_a_rebuild_while_the_item_rows_are_rebuilt(db: DbTarget) -> None:
    item = _receive(db)
    _insert(db, item, '{"claim_name":"Sam"}')
    before = _rows(db)
    assert len(before) == 1 and _items(db) == 1
    rebuild_projections(db)
    assert _rows(db) == before
    assert _items(db) == 1


def test_a_body_row_with_no_item_event_survives_too(db: DbTarget) -> None:
    _insert(db, new_ulid(), "{}")
    before = _rows(db)
    rebuild_projections(db)
    assert _rows(db) == before


@pytest.mark.parametrize("module", ["template", "submission", "intake_code", "intake_item"])
def test_no_projector_writes_or_clears_the_body_table(module: str) -> None:
    source = inspect.getsource(importlib.import_module(f"tl_mod_forms.projectors.{module}"))
    for verb in ("INSERT INTO", "UPDATE", "DELETE FROM"):
        assert f"{verb} {{INTAKE_BODY_TABLE}}" not in source, verb
        assert f"{verb} forms_intake_body" not in source, verb


def test_every_reset_leaves_the_body_table_alone(db: DbTarget) -> None:
    _insert(db, new_ulid(), "{}")
    with open_uow(db) as uow:
        for projector in projectors():
            projector.reset(uow.conn())
    assert len(_rows(db)) == 1
