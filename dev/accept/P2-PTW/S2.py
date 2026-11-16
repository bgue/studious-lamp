"""Acceptance for P2-PTW S2: the ten permit commands, the issue guards and the hooks (SQLite).

Run: ``uv run python dev/accept/P2-PTW/S2.py``. One ``PASS <check>`` line per check, then
``S2 ok``. The clock is fixed (07:00 UTC on 2026-12-01).
"""

from __future__ import annotations

import sys
import tempfile
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages/tl-modules/permits/tests"))
from permit_world import World  # noqa: E402
from tl_adapters.db import as_target, create_schema  # noqa: E402
from tl_core import confidentiality as cf  # noqa: E402
from tl_core.auth.errors import ForbiddenError  # noqa: E402
from tl_core.modules import hook_failures, load_modules  # noqa: E402
from tl_core.services.errors import RecordNotFoundError  # noqa: E402
from tl_mod_permits.errors import (  # noqa: E402
    PermitBlockedError,
    PermitStateError,
    StaleVersionError,
)
from tl_mod_permits.handlers import permit as handlers  # noqa: E402
from tl_mod_permits.handlers.permit import MSG_SELF_APPROVE  # noqa: E402
from tl_mod_permits.module import COMMANDS, PROPOSABLE  # noqa: E402

HOT = ["fire_watch", "extinguisher", "combustibles_cleared", "spark_containment"]


def passed(name: str) -> None:
    print(f"PASS {name}")


def refused(error: type[BaseException], call: Callable[[], Any]) -> str:
    try:
        call()
    except error as exc:
        return str(exc)
    raise AssertionError(f"expected {error.__name__}")


def main() -> None:
    db = as_target(str(Path(tempfile.mkdtemp()) / "s2.db"))
    create_schema(db)
    w = World(db)
    w.people()
    clocked: Any = handlers
    clocked.now = lambda: w.at  # the one clock of the handlers

    assert len(COMMANDS) == 10 and [p.tool for p in PROPOSABLE] == ["propose_permit"]
    assert all(c.meta == {"delegation": "excluded:reserved"} for c in COMMANDS)
    spec = next(s for s in load_modules() if s.name == "permits")
    assert not hook_failures().get("permits") and len(spec.cli_groups) == 3
    passed("ten commands, one proposable row, three groups, no hook failure")

    permit = w.approved("hot_work")
    assert w.row(permit)["approved_by"] == "user:sue"
    assert refused(ForbiddenError, lambda: w.call("rob", "ApprovePermit", permit=w.request("sue")))
    mine = w.request("sue")
    assert refused(ForbiddenError, lambda: w.call("sue", "ApprovePermit", permit=mine)) == (
        MSG_SELF_APPROVE
    )
    passed("approver differs from requester")

    def issue(**more: Any) -> Any:
        return w.call("pam", "IssuePermit", permit=permit, precautions=HOT, **more)

    assert "gas_test_missing" in refused(PermitBlockedError, issue)
    w.gas_test(permit, result="fail")
    assert refused(PermitBlockedError, issue).endswith("gas_test_failed")
    w.at += timedelta(minutes=1)
    w.gas_test(permit)
    issue()
    row = w.row(permit)
    assert w.state(permit) == "Active" and str(row["valid_until"])[:16] == "2026-12-01T18:00"
    passed("issue refused by each gas blocker, passes when clean, valid to shift end")

    w.at = w.at.replace(hour=19)
    w.gas_test(permit)
    w.call("rob", "RevalidatePermit", permit=permit)
    assert w.row(permit)["revalidation_count"] == 1
    assert str(w.row(permit)["valid_until"])[:16] == "2026-12-02T06:00"
    passed("a lapsed permit is revalidated with a fresh passing test")

    w.call("uma", "SuspendPermit", permit=permit, reason="Gas alarm")
    assert refused(ForbiddenError, lambda: w.call("uma", "ResumePermit", permit=permit))
    w.at += timedelta(hours=5)
    assert "gas_test_stale" in refused(
        PermitBlockedError, lambda: w.call("pam", "ResumePermit", permit=permit)
    )
    w.gas_test(permit)
    w.call("pam", "ResumePermit", permit=permit)
    passed("suspend by any user, resume re-runs the issue guards")

    assert refused(PermitStateError, lambda: w.call("pam", "ClosePermit", permit=permit)).endswith(
        "it needs Handed back"
    )
    w.call("rob", "HandBackPermit", permit=permit, handback_note="Site clear")
    w.call("pam", "ClosePermit", permit=permit)
    assert w.state(permit) == "Closed"
    assert refused(
        PermitStateError, lambda: w.call("pam", "CancelPermit", permit=permit, reason="x")
    )
    passed("hand back, close, and a closed permit takes nothing")

    version = w.version(mine)
    assert refused(
        StaleVersionError,
        lambda: w.call(
            "pam", "CancelPermit", permit=mine, reason="x", expected_version=version + 5
        ),
    )
    w.call("pam", "CancelPermit", permit=mine, reason="Work moved", expected_version=version)
    assert w.state(mine) == "Cancelled"
    passed("expected_version and cancel")

    secret = w.hidden_record()
    hid = w.request("dora", for_record_id=secret)
    text_hidden = refused(RecordNotFoundError, lambda: w.call("sue", "ApprovePermit", permit=hid))
    text_missing = refused(
        RecordNotFoundError,
        lambda: w.call("sue", "ApprovePermit", permit="01JXXXXXXXXXXXXXXXXXXXXXXX"),
    )
    assert text_hidden == text_missing == "no record with that id"
    gas = w.gas_test(hid)
    cleared = cf.Viewer(actor="user:dora", level=1, account="user:dora")
    from tl_adapters.db import open_uow

    with open_uow(w.db, readonly=True) as uow:
        assert cf.is_hidden(uow.conn(), hid) and cf.is_hidden(uow.conn(), gas)
        assert not cf.is_hidden(uow.conn(), gas, cleared)
    passed("a hidden permit and its gas test read as missing")
    print("S2 ok")


if __name__ == "__main__":
    main()
