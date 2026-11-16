"""Acceptance for P2-PTW S3: the six isolation and gas test commands (SQLite).

Run: ``uv run python dev/accept/P2-PTW/S3.py``. One ``PASS <check>`` line per check, then
``S3 ok``. The clock is fixed (07:00 UTC on 2026-12-01).
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
from tl_core.auth.errors import ForbiddenError  # noqa: E402
from tl_core.modules import hook_failures  # noqa: E402
from tl_core.services.errors import RecordNotFoundError  # noqa: E402
from tl_mod_permits.errors import (  # noqa: E402
    GasTestRuleError,
    IsolationInUseError,
    IsolationRuleError,
    IsolationStateError,
    PermitBlockedError,
)
from tl_mod_permits.handlers import common  # noqa: E402
from tl_mod_permits.handlers import permit as permit_handlers  # noqa: E402
from tl_mod_permits.handlers.isolation import MSG_HIDDEN_PERMIT, MSG_SELF_VERIFY  # noqa: E402
from tl_mod_permits.module import COMMANDS  # noqa: E402

ISO: dict[str, Any] = {
    "point_text": "Pump P-101 breaker",
    "energy": "electrical",
    "method": "Lock and tag",
    "lock_number": "L-12",
    "tag_number": "T-12",
}


def passed(name: str) -> None:
    print(f"PASS {name}")


def refused(error: type[BaseException], call: Callable[[], Any]) -> str:
    try:
        call()
    except error as exc:
        return str(exc)
    raise AssertionError(f"expected {error.__name__}")


def main() -> None:
    db = as_target(str(Path(tempfile.mkdtemp()) / "s3.db"))
    create_schema(db)
    w = World(db)
    w.people()
    w.person("dan", ("user", "document_controller"), grant="superuser")
    clocked: Any = common
    clocked.now = lambda: w.at  # the one clock of the S3 handlers
    clocked_permit: Any = permit_handlers
    clocked_permit.now = lambda: w.at

    assert len(COMMANDS) == 16 and not hook_failures().get("permits")
    assert all(c.meta == {"delegation": "excluded:reserved"} for c in COMMANDS)
    passed("sixteen commands, all excluded:reserved, no hook failure")

    first = str(w.call("uma", "ApplyIsolation", **ISO).stream_id)
    key = w.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=first)
    assert w.state(first) == "Applied" and key == "P123-ISL-0001"
    assert refused(ForbiddenError, lambda: w.call("uma", "VerifyIsolation", isolation=first))
    own = str(w.call("sue", "ApplyIsolation", **ISO).stream_id)
    assert refused(ForbiddenError, lambda: w.call("sue", "VerifyIsolation", isolation=own)) == (
        MSG_SELF_VERIFY
    )
    w.call("sue", "VerifyIsolation", isolation=first)
    assert w.state(first) == "Verified"
    assert refused(
        IsolationStateError, lambda: w.call("pam", "VerifyIsolation", isolation=first)
    ).endswith("needs Applied")
    passed("apply, verify by another controller, the applier cannot verify")

    permit = w.approved("isolation")
    ticks = ["points_listed", "locks_tags_applied", "zero_energy_proven"]
    assert "isolation_missing" in refused(
        PermitBlockedError, lambda: w.call("pam", "IssuePermit", permit=permit, precautions=ticks)
    )
    w.call("uma", "LinkIsolation", permit=permit, isolation=first)
    assert refused(
        IsolationRuleError, lambda: w.call("uma", "LinkIsolation", permit=permit, isolation=first)
    )
    w.call("pam", "IssuePermit", permit=permit, precautions=ticks)
    assert w.state(permit) == "Active"
    assert refused(
        IsolationRuleError, lambda: w.call("uma", "UnlinkIsolation", permit=permit, isolation=first)
    )
    passed("link feeds the issue guards; no link change while the permit is live")

    named = refused(IsolationInUseError, lambda: w.call("uma", "RemoveIsolation", isolation=first))
    assert named.endswith("P123-PTW-0001")
    w.call("rob", "HandBackPermit", permit=permit, handback_note="Site clear")
    w.call("pam", "ClosePermit", permit=permit)
    w.call("uma", "RemoveIsolation", isolation=first)
    assert w.state(first) == "Removed"
    assert refused(
        IsolationStateError, lambda: w.call("uma", "LinkIsolation", permit=permit, isolation=first)
    )
    passed("remove is refused while a permit in use needs it, allowed after Closed")

    secret = w.hidden_record()
    shared = str(w.call("uma", "ApplyIsolation", **ISO).stream_id)
    for _ in range(3):
        hid = w.request("dora", "general", for_record_id=secret)
        w.call("dan", "ApprovePermit", permit=hid)
        w.link(hid, shared)
    text_three = refused(
        IsolationInUseError, lambda: w.call("uma", "RemoveIsolation", isolation=shared)
    )
    assert text_three.endswith(MSG_HIDDEN_PERMIT) and "PTW" not in text_three
    gone = refused(
        RecordNotFoundError, lambda: w.call("sue", "VerifyIsolation", isolation="X" * 26)
    )
    assert gone == "no record with that id"
    passed("a hidden dependent permit is only 'a permit you cannot see'")

    hot = w.approved("hot_work")
    w.call("uma", "RecordGasTest", permit=hot, instrument_text="MX6", o2_pct="20.9")
    w.at += timedelta(minutes=1)
    w.issue(hot)
    assert w.state(hot) == "Active"
    refused(
        GasTestRuleError,
        lambda: w.call(
            "uma",
            "RecordGasTest",
            permit=hot,
            instrument_text="MX6",
            o2_pct="20.9",
            taken_at=w.at + timedelta(minutes=5),
        ),
    )
    passed("a gas test dated in the future is refused")

    w.call("uma", "RecordGasTest", permit=hot, instrument_text="MX6", co_ppm="25")
    assert w.state(hot) == "Active"
    w.call("uma", "RecordGasTest", permit=hot, instrument_text="MX6", co_ppm="25.1")
    assert w.state(hot) == "Suspended"
    general = w.active("general")
    w.call("uma", "RecordGasTest", permit=general, instrument_text="MX6", lel_pct="50")
    assert w.state(general) == "Active"
    passed("a reading at the limit passes, over it fails and stops a gas-test permit only")

    assert "gas_test_failed" in refused(
        PermitBlockedError, lambda: w.call("pam", "ResumePermit", permit=hot)
    )
    w.at += timedelta(minutes=1)
    w.call("uma", "RecordGasTest", permit=hot, instrument_text="MX6", co_ppm="2")
    w.call("pam", "ResumePermit", permit=hot)
    assert w.state(hot) == "Active"
    passed("a suspended permit resumes only after a fresh pass")
    print("S3 ok")


if __name__ == "__main__":
    main()
