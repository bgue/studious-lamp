"""``next_before_seq`` is never the seq of an event the viewer may not read (P2-FIX-CONF F4).

One round of candidates is scanned, so the last candidate of the batch can be the hidden event of
a linked restricted record; the cursor must then be a visible seq (or none), not that one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ACCEPT = Path(__file__).resolve().parents[4] / "dev" / "accept" / "P2-INS"
sys.path.insert(0, str(ACCEPT))
import s1_world as sw  # noqa: E402  # pyright: ignore[reportMissingImports]
from tl_adapters.db import open_uow  # noqa: E402
from tl_core import confidentiality as cf  # noqa: E402
from tl_core.insights import activity  # noqa: E402
from tl_core.insights.activity import record_activity  # noqa: E402

CONTROLLER = cf.Viewer("user:controller", 1, "user:controller")


def test_the_cursor_is_never_a_hidden_seq(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    built = sw.build(tmp_path)
    sw.add_hidden(built)
    with open_uow(built.w.db, readonly=True) as uow:
        with cf.use_viewer(CONTROLLER):
            everyone = {r.event.seq for r in record_activity(uow, built.iwp, limit=200).rows}
        with cf.use_viewer(cf.LOWEST):
            shown = {r.event.seq for r in record_activity(uow, built.iwp, limit=200).rows}
    hidden = everyone - shown
    assert hidden, "the world must have a hidden event among the candidates"
    monkeypatch.setattr(activity, "MAX_ROUNDS", 1)
    touched = False
    for limit in range(1, 40):
        with open_uow(built.w.db, readonly=True) as uow, cf.use_viewer(cf.LOWEST):
            page = record_activity(uow, built.iwp, limit=limit)
        assert page.next_before_seq not in hidden, limit
        touched = touched or page.next_before_seq is not None
    assert touched
