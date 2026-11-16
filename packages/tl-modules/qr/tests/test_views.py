"""The read views of scan codes (P2-QR T01; pinned by S2): newest first, at most 100, counted by
state, exported as CSV or JSON lines; a hidden record's codes are filtered before the LIMIT and
before the count; no row holds a code or its hash."""

from __future__ import annotations

import csv
import dataclasses
import io
import json
from datetime import timedelta
from typing import Any

from qr_world import World
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.util import utcnow
from tl_mod_qr import service
from tl_mod_qr.codes import code_hash, grouped
from tl_mod_qr.views import CodeRow, code_counts, codes_for_record, export_rows

FIELDS = [
    "id",
    "label_text",
    "size",
    "issued_by",
    "issued_at",
    "expires_on",
    "state",
    "revoked_at",
    "replaced_by_id",
]
CLEARED = cf.Viewer(actor="user:dora", level=1, account="user:dora")
LOW = cf.Viewer(actor="user:vera", level=0, account="user:vera")


def issue(world: World, target: str, who: str = "uma", **more: Any) -> service.IssuedCode:
    return world.serve(service.issue, who, "IssueScanCode", target_id=target, **more)


def rows_for(world: World, record: str, viewer: cf.Viewer = cf.LOWEST) -> list[CodeRow]:
    with open_uow(world.db, readonly=True) as uow:
        return codes_for_record(uow.conn(), record, viewer=viewer)


def counts(world: World, viewer: cf.Viewer = cf.LOWEST) -> dict[str, int]:
    with open_uow(world.db, readonly=True) as uow:
        return code_counts(uow.conn(), viewer=viewer)


def test_a_code_row_holds_the_register_fields_and_never_the_code_or_its_hash() -> None:
    assert [f.name for f in dataclasses.fields(CodeRow)] == FIELDS


def test_codes_of_a_record_come_newest_first_with_their_state(world: World) -> None:
    target = world.record()
    first = issue(world, target, label_text="Pump", size="card")
    second = issue(world, target)
    world.call("ada", "RevokeScanCode", code_id=first.result.stream_id, reason="lost")
    rows = rows_for(world, target)
    assert [r.id for r in rows] == [second.result.stream_id, first.result.stream_id]
    assert [r.state for r in rows] == ["live", "revoked"]
    old = rows[1]
    assert (old.label_text, old.size, old.issued_by) == ("Pump", "card", "user:uma")
    assert old.revoked_at is not None and old.replaced_by_id is None
    assert rows[0].revoked_at is None and rows[0].expires_on is None
    assert rows_for(world, world.record(key="EMPTY")) == []


def test_a_rotated_code_names_its_replacement(world: World) -> None:
    target = world.record()
    first = issue(world, target)
    fresh = world.serve(
        service.rotate, "uma", "RotateScanCode", code_id=first.result.stream_id, reason="worn"
    )
    newest, oldest = rows_for(world, target)
    assert oldest.replaced_by_id == newest.id == fresh.result.stream_id


def test_a_row_and_its_text_hold_neither_the_code_nor_its_hash(world: World) -> None:
    target = world.record()
    made = issue(world, target, label_text="Pump")
    (row,) = rows_for(world, target)
    dump = repr(row) + str(dataclasses.asdict(row))
    for needle in (made.code, grouped(made.code), code_hash(made.code)):
        assert needle not in dump


def test_at_most_one_hundred_rows_newest_first(world: World) -> None:
    world.cap(100)  # the default per-record cap is 20 (qr.codes_per_record_max)
    target = world.record()
    made = [issue(world, target) for _ in range(100)]
    for old in made[:5]:  # five rotations: 105 rows, 100 of them live
        world.serve(
            service.rotate,
            "uma",
            "RotateScanCode",
            code_id=old.result.stream_id,
            reason="worn",
        )
    rows = rows_for(world, target)
    assert len(rows) == 100
    assert [r.issued_at for r in rows] == sorted((r.issued_at for r in rows), reverse=True)
    assert counts(world) == {"live": 100, "revoked": 5, "expired": 0}


def test_counts_by_state(world: World) -> None:
    target = world.record()
    gone, aged, _kept = (issue(world, target) for _ in range(3))
    world.call("ada", "RevokeScanCode", code_id=gone.result.stream_id, reason="lost")
    with open_uow(world.db) as uow:
        uow.conn().execute(
            text("UPDATE cur_qr_scan_code SET expires_on = :d WHERE id = :i"),
            {"d": (utcnow().date() - timedelta(days=1)).isoformat(), "i": aged.result.stream_id},
        )
    assert counts(world) == {"live": 1, "revoked": 1, "expired": 1}
    assert {r.state for r in rows_for(world, target)} == {"live", "revoked", "expired"}


def test_a_hidden_record_gives_no_rows_and_no_count_to_a_reader_who_may_not_read_it(
    world: World,
) -> None:
    secret = world.hidden_record()
    open_record = world.record(key="OPEN-1")
    for _ in range(3):
        issue(world, secret, who="dora")
    issue(world, open_record)
    for viewer in (cf.LOWEST, LOW, cf.Viewer(actor="agent:bot", level=0, account="")):
        assert rows_for(world, secret, viewer) == []
        assert counts(world, viewer) == {"live": 1, "revoked": 0, "expired": 0}
    assert len(rows_for(world, secret, CLEARED)) == 3
    assert counts(world, CLEARED) == {"live": 4, "revoked": 0, "expired": 0}


def test_the_hidden_filter_runs_before_the_limit(world: World) -> None:
    """A hidden record's codes, newer than every visible one, never push a visible one out."""
    secret = world.hidden_record()
    open_record = world.record(key="OPEN-2")
    issue(world, open_record)
    for _ in range(3):
        issue(world, secret, who="dora")
    assert len(rows_for(world, open_record)) == 1
    assert counts(world)["live"] == 1


def test_export_csv_and_jsonl_carry_the_fields_and_nothing_secret(world: World) -> None:
    target = world.record()
    made = issue(world, target, label_text='Pump, "P-101"')
    rows = rows_for(world, target)
    as_csv = export_rows(rows, "csv")
    parsed = list(csv.DictReader(io.StringIO(as_csv)))
    assert list(parsed[0]) == FIELDS
    assert parsed[0]["label_text"] == 'Pump, "P-101"' and parsed[0]["state"] == "live"
    as_json = export_rows(rows, "jsonl")
    lines = as_json.splitlines()
    assert len(lines) == 1 and list(json.loads(lines[0])) == FIELDS
    assert json.loads(lines[0])["id"] == made.result.stream_id
    for dump in (as_csv, as_json):
        for needle in (made.code, grouped(made.code), code_hash(made.code)):
            assert needle not in dump
    assert export_rows([], "jsonl") == ""
