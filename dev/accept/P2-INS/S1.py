"""P2-INS-S1 acceptance: the activity read on a SQLite tmp db. Final line: ``S1 ok``."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import s1_world as sw  # noqa: E402
from tl_adapters.db import open_uow  # noqa: E402
from tl_core import confidentiality as cf  # noqa: E402
from tl_core.insights.activity import record_activity  # noqa: E402
from tl_core.services import queries  # noqa: E402


def check(name: str, cond: bool) -> None:
    sys.exit(f"FAIL {name}") if not cond else print(f"PASS {name}")


def page(w: sw.World, viewer: cf.Viewer = cf.LOWEST, **kw: object):  # noqa: ANN201
    with open_uow(w.w.db, readonly=True) as uow, cf.use_viewer(viewer):
        return record_activity(uow, w.iwp, **kw)  # type: ignore[arg-type]


root = Path(tempfile.mkdtemp())
world = sw.build(root)
sw.upload(world)
sw.propose_link(world, accept=True)
sw.propose_link(world, accept=False)
rows = page(world).rows
kinds = {r.kind for r in rows}
check(
    "every kind appears",
    kinds == {"change", "move", "link", "file", "post", "proposal", "constraint", "check"},
)
check(
    "newest first", [r.event.seq for r in rows] == sorted((r.event.seq for r in rows), reverse=True)
)
check("link events of both ends", len({r.event.stream_id for r in rows if r.kind == "link"}) >= 3)
with open_uow(world.w.db, readonly=True) as uow, cf.use_viewer(cf.LOWEST):
    history = queries.record_history(uow, world.iwp)
check(
    "revisions_only is record_history",
    [r.event for r in reversed(page(world, revisions_only=True).rows)] == history,
)
related = [r for r in rows if r.related]
check(
    "a related row names its record",
    bool(related) and {r.from_key for r in related} == {"P123-IWP-PIP-0002"},
)
check("related=False has none", not any(r.related for r in page(world, related=False).rows))
hidden = sw.add_hidden(world)
controller = cf.Viewer("user:controller", 1, "user:controller")
low, ctl = page(world).rows, page(world, controller).rows
check(
    "the hidden far end is no row",
    not any(r.from_id == hidden for r in low) and not any(hidden in r.event.stream_id for r in low),
)
check("a controller reads it", any(r.from_id == hidden for r in ctl))
check(
    "hidden leaves no gap",
    [r.event.seq for r in low]
    == [
        r.event.seq
        for r in ctl
        if r.from_id != hidden
        and hidden not in str(r.event.payload)
        and r.event.stream_id != hidden
        and r.event.seq in {x.event.seq for x in low}
    ],
)
print("S1 ok")
