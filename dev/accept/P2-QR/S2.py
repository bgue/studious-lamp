"""Acceptance for P2-QR-S2: issue, resolve, rotate and revoke a scan code, a hidden target, and a
code that is written nowhere. Exit 0, one ``PASS <check>`` line per check, then ``S2 ok``. SQLite
only; no network.

Run: ``uv run python dev/accept/P2-QR/S2.py``.
"""

from __future__ import annotations

import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tl_adapters.db import as_target, create_schema, open_uow
from tl_core import confidentiality as cf
from tl_core.qr import registry
from tl_core.services.errors import RecordNotFoundError
from tl_core.settings import resolver

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "tl-modules" / "qr" / "tests"))

from qr_world import BASE, SECRET, FakeProvider, World, providers_of  # noqa: E402
from tl_mod_qr import service  # noqa: E402
from tl_mod_qr.codes import code_hash, grouped  # noqa: E402
from tl_mod_qr.errors import MSG_BASE, MSG_CAP, MSG_UNKNOWN, QrRuleError  # noqa: E402
from tl_mod_qr.resolve import resolve  # noqa: E402

USER = cf.Viewer(actor="user:uma", level=0, account="user:uma")
NOW = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)


def passed(name: str) -> None:
    print(f"PASS {name}")


def need(ok: bool, what: str) -> None:
    if not ok:
        raise SystemExit(f"FAIL {what}")


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="qr-s2-"))
    target = as_target(str(work / "tl.db"))
    create_schema(target)
    world = World(target)
    world.people()
    fake = FakeProvider()
    registry.load_scan_cards = lambda *a, **k: providers_of(fake, FakeProvider(SECRET))  # type: ignore[assignment]
    real = resolver.value_of

    def value_of(conn: Any, key: str, **kwargs: Any) -> Any:
        return world.public if key == service.BASE_URL else real(conn, key, **kwargs)

    service.value_of = value_of  # type: ignore[attr-defined]

    def lookup(code: str, viewer: cf.Viewer = USER) -> object:
        with open_uow(target, readonly=True) as uow:
            return resolve(uow.conn(), code, viewer, NOW)

    record = world.record()
    try:
        world.serve(service.issue, "uma", "IssueScanCode", target_id=record)
    except QrRuleError as exc:
        need(str(exc) == MSG_BASE, "fixed message while the public address is empty")
    else:
        raise SystemExit("FAIL issue without the public address")
    passed("issue refused while api.public_base_url is empty")

    world.base(BASE)
    first = world.serve(service.issue, "uma", "IssueScanCode", target_id=record, label_text="P-1")
    (row,) = world.rows("SELECT * FROM cur_qr_scan_code")
    need(row["code_hash"] == code_hash(first.code), "the register holds the hash")
    passed("issue returns the code once and stores its hash")

    need(lookup(first.code) is not None, "a live code resolves")
    need(lookup(grouped(first.code).lower()) is not None, "a typed code resolves")
    passed("a live code resolves to its card, typed or scanned")

    fresh = world.serve(
        service.rotate, "uma", "RotateScanCode", code_id=first.result.stream_id, reason="worn"
    )
    need(lookup(first.code) is None and lookup(fresh.code) is not None, "rotate swaps the code")
    passed("rotate: the old code misses, the new one hits")

    world.call("ada", "RevokeScanCode", code_id=fresh.result.stream_id, reason="lost")
    need(lookup(fresh.code) is None, "a revoked code misses")
    passed("revoke: the code misses")

    world.cap(1)
    world.serve(service.issue, "uma", "IssueScanCode", target_id=record)
    try:
        world.serve(service.issue, "uma", "IssueScanCode", target_id=record)
    except QrRuleError as exc:
        need(str(exc) == MSG_CAP, "fixed cap message")
    else:
        raise SystemExit("FAIL the cap")
    passed("the per-record cap refuses the next live code")

    answers: set[str] = set()
    for pick in (world.hidden_record, lambda: world.record("awp.IWP", "NOCARD-1")):
        try:
            world.serve(service.issue, "uma", "IssueScanCode", target_id=pick())
        except RecordNotFoundError as exc:
            answers.add(str(exc))
    for missing in ("01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",):
        try:
            world.serve(service.issue, "uma", "IssueScanCode", target_id=missing)
        except RecordNotFoundError as exc:
            answers.add(str(exc))
    need(answers == {MSG_UNKNOWN}, "hidden, card-less and missing targets answer alike")
    passed("a hidden, card-less or missing target answers one text")

    everything = "\n".join(
        str(v) for r in world.rows("SELECT * FROM events") for v in r.values()
    ) + "\n".join(str(v) for r in world.rows("SELECT * FROM cur_qr_scan_code") for v in r.values())
    need(
        not any(c in everything for c in (first.code, fresh.code, grouped(first.code))),
        "no code in the ledger",
    )
    passed("no code in any event or row")
    print("S2 ok")


if __name__ == "__main__":
    main()
