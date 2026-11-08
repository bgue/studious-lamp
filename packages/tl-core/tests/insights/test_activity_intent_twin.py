"""An intent that names a hidden record reads as "not available" (P2-INT-T04).

``record_activity`` hands the event to every reader, so its intent passes ``redact_events``: a
reference the viewer cannot read is "not available", byte for byte as an intent that was stored as "not available".
Runs on every adapter the root conftest offers (SQLite; Postgres under ``--adapters sqlite,postgres``).
"""

from __future__ import annotations

import sys
from pathlib import Path

ACCEPT = Path(__file__).resolve().parents[4] / "dev" / "accept" / "P2-INS"
sys.path.insert(0, str(ACCEPT))
import pytest  # noqa: E402
import s1_world as sw  # noqa: E402  # pyright: ignore[reportMissingImports]
from tl_adapters.db import open_uow  # noqa: E402
from tl_core import confidentiality as cf  # noqa: E402
from tl_core.insights.activity import record_activity  # noqa: E402
from tl_core.intent import NOT_AVAILABLE, Intent, IntentRef, IntentToward, intent_scope  # noqa: E402

CONTROLLER = cf.Viewer("user:controller", 1, "user:controller")


def intent_of(target: str, where: str) -> Intent:
    if where == "toward":
        return Intent(toward=IntentToward(target=target, condition="done"))
    return Intent(next=[IntentRef(command="UpdateRecord", target=target)])


def unavailable(where: str) -> Intent:
    """The intent as an unreadable reference is stored for nobody: the text, no target."""
    if where == "toward":
        return Intent(toward=IntentToward(target=NOT_AVAILABLE))
    return Intent(next=[IntentRef(text=NOT_AVAILABLE)])


def made(built: sw.World, key: str, intent: Intent) -> str:
    """A record created with ``intent``."""
    with cf.system_view(), intent_scope(intent):
        return sw.make_record(built.w, key, "has intent")


def read_intent(built: sw.World, record: str, viewer: cf.Viewer) -> str:
    with open_uow(built.w.db, readonly=True) as uow, cf.use_viewer(viewer):
        rows = record_activity(uow, record, related=False).rows
    found = [r.event.intent for r in rows if r.event.intent is not None]
    assert len(found) == 1
    return found[0].model_dump_json()


@pytest.mark.parametrize("where", ["toward", "next"])
def test_a_hidden_target_reads_as_not_available(
    db: str | Path, tmp_path: Path, where: str
) -> None:
    built = sw.build(tmp_path, db)
    hidden = sw.add_hidden(built)
    rec_a = made(built, f"P123-INT-{where}-A", intent_of(hidden, where))
    rec_b = made(built, f"P123-INT-{where}-B", unavailable(where))
    named = read_intent(built, rec_a, cf.LOWEST)
    unnamed = read_intent(built, rec_b, cf.LOWEST)
    assert NOT_AVAILABLE in named and hidden not in named
    assert named == unnamed  # byte for byte
    assert hidden in read_intent(built, rec_a, CONTROLLER)  # a reader of the record sees its id
    with open_uow(built.w.db, readonly=True) as uow, cf.use_viewer(cf.LOWEST):
        page = record_activity(uow, rec_a, revisions_only=True)
    assert page.rows and hidden not in "".join(r.event.model_dump_json() for r in page.rows)
