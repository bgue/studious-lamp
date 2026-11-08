"""INS-A4 twin: a hidden record leaves no trace in what the lowest-clearance viewer reads.

P2-INS-T04.

World A is the S1 world with a restricted record linked both ways to the IWP and carrying an event
of its own; world B is the same S1 world without that record. For the lowest-clearance viewer the
activity page of A must equal the page of B, row for row, page for page. A controller, who may read
the restricted record, must see more rows in A, which pins that the twin holds because of the
filter and not because the world is empty. SQLite only: ``sw.build`` is SQLite by default.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

ACCEPT = Path(__file__).resolve().parents[4] / "dev" / "accept" / "P2-INS"
sys.path.insert(0, str(ACCEPT))
import s1_world as sw  # noqa: E402  # pyright: ignore[reportMissingImports]
from tl_adapters.db import open_uow  # noqa: E402
from tl_core import confidentiality as cf  # noqa: E402
from tl_core.insights.activity import record_activity  # noqa: E402
from tl_core.insights.types import ActivityPage  # noqa: E402

CONTROLLER = cf.Viewer("user:controller", 1, "user:controller")
Normal = tuple[Any, ...]


@pytest.fixture(scope="module")
def pair(tmp_path_factory: pytest.TempPathFactory) -> tuple[sw.World, sw.World]:
    """World A: the S1 world with the restricted record. World B: the S1 world alone."""
    world_a = sw.build(tmp_path_factory.mktemp("twin_a"))
    sw.add_hidden(world_a)
    world_b = sw.build(tmp_path_factory.mktemp("twin_b"))
    return world_a, world_b


def read(world: sw.World, viewer: cf.Viewer = cf.LOWEST, **kw: Any) -> ActivityPage:
    with open_uow(world.w.db, readonly=True) as uow, cf.use_viewer(viewer):
        return record_activity(uow, world.iwp, **kw)


def norm(page: ActivityPage) -> list[Normal]:
    """A row without its seq, its ids or its payload: what the viewer reads of it."""
    return [
        (r.kind, r.event.event_type, r.event.actor, r.related, r.from_key, r.decided_by, r.note)
        for r in page.rows
    ]


def paged(
    world: sw.World, viewer: cf.Viewer, limit: int = 5
) -> tuple[list[list[Normal]], list[bool]]:
    """Every page of the read at ``limit``: its normalised rows, and whether it is the last."""
    pages: list[list[Normal]] = []
    ends: list[bool] = []
    cursor: int | None = None
    for _ in range(100):
        page = read(world, viewer, before_seq=cursor, limit=limit)
        pages.append(norm(page))
        ends.append(page.next_before_seq is None)
        if page.next_before_seq is None:
            return pages, ends
        cursor = page.next_before_seq
    pytest.fail("the paged read did not end within 100 pages")


def test_the_lowest_viewer_reads_a_world_with_a_hidden_link_like_its_twin(
    pair: tuple[sw.World, sw.World],
) -> None:
    world_a, world_b = pair
    low_a, low_b = read(world_a), read(world_b)
    assert len(low_a.rows) == len(low_b.rows) > 0
    assert norm(low_a) == norm(low_b)  # the full list, row for row
    assert norm(read(world_a, related=False)) == norm(read(world_b, related=False))
    pages_a, ends_a = paged(world_a, cf.LOWEST)
    pages_b, ends_b = paged(world_b, cf.LOWEST)
    assert [len(p) for p in pages_a] == [len(p) for p in pages_b]  # the same page lengths
    assert ends_a == ends_b and ends_a[-1] is True  # next_before_seq is None on the same pages
    assert pages_a == pages_b
    assert sum(len(p) for p in pages_a) == len(low_b.rows)


def test_the_controller_sees_the_extra_rows_and_the_twin_is_the_filter(
    pair: tuple[sw.World, sw.World],
) -> None:
    world_a, world_b = pair
    ctl_a = norm(read(world_a, CONTROLLER))
    ctl_b = norm(read(world_b, CONTROLLER))
    low_a = norm(read(world_a))
    extra = Counter(ctl_a) - Counter(ctl_b)
    assert len(ctl_a) > len(ctl_b) and sum(extra.values()) >= 1  # the restricted record's rows
    assert (
        Counter(low_a) - Counter(ctl_a) == Counter()
    )  # the lowest read is a subset of the controller's
    assert norm(read(world_b, CONTROLLER)) == norm(read(world_b))  # B has no hidden record to show
