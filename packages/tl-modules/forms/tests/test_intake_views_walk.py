"""The intake queue read by five readers (P2-FORMS I03, CR1): a hidden code and its items look
missing to every reader who may not read its context, and a code with no context is listed."""

from __future__ import annotations

import time
from typing import Any

import pytest
from forms_world import SCOPE, World
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.util import new_ulid
from tl_mod_forms import intake_views as views

PERSON = cf.Viewer(actor="user:rob", level=0, account="user:rob")  # an internal reader
CONTROLLER = cf.Viewer(actor="user:dora", level=1, account="user:dora")  # restricted, named
ADMIN = cf.Viewer(actor="user:ada", level=1, account="user:ada")  # restricted, not named
SYSTEM = cf.Viewer(actor="system", level=1, account="", system=True)
READERS: dict[str, cf.Viewer] = {
    "lowest": cf.LOWEST,
    "person": PERSON,
    "controller": CONTROLLER,
    "admin": ADMIN,
    "system": SYSTEM,
}
#: The contexts each reader may read: restricted, privileged (named only), open, and no context.
SEES: dict[str, set[str]] = {
    "lowest": {"open", "none"},
    "person": {"open", "none"},
    "controller": {"restricted", "privileged", "open", "none"},
    "admin": {"restricted", "open", "none"},
    "system": {"restricted", "privileged", "open", "none"},
}


@pytest.fixture
def queue(world: World) -> dict[str, Any]:
    """One code per context kind, each with one item: the code ids and the item ids by name."""
    tpl = world.intake_template()
    contexts = {
        "restricted": world.hidden_record("restricted"),
        "privileged": world.hidden_record("privileged"),
        "open": world.record("awp.IWP", "IWP-2"),
        "none": None,
    }
    codes = {name: world.stage_code(tpl, context_id=ctx) for name, ctx in contexts.items()}
    items = {name: world.stage_item(code) for name, code in codes.items()}
    return {"codes": codes, "items": items}


@pytest.mark.parametrize("who", list(READERS))
def test_hidden_codes_and_items_are_absent_for_each_reader(
    world: World, queue: dict[str, Any], who: str
) -> None:
    viewer = READERS[who]
    codes, items = queue["codes"], queue["items"]
    shown_codes = {codes[name] for name in SEES[who]}
    shown_items = {items[name] for name in SEES[who]}
    with open_uow(world.db, readonly=True) as uow:
        conn = uow.conn()
        page = views.code_list(conn, SCOPE, viewer=viewer)
        assert {r.id for r in page.rows} == shown_codes and page.total == len(shown_codes)
        assert {r.pending for r in page.rows} == {1}
        queued = views.item_list(conn, SCOPE, viewer=viewer)
        assert {r.id for r in queued.rows} == shown_items and queued.total == len(shown_items)
        assert views.pending_count(conn, SCOPE, viewer=viewer) == len(shown_items)
        for name, item in items.items():
            detail = views.item_detail(conn, SCOPE, item, viewer=viewer)
            answers = views.item_answers(conn, SCOPE, item, viewer=viewer)
            if name in SEES[who]:
                assert detail is not None and answers is not None, name
            else:
                absent = new_ulid()
                assert detail is None and answers is None, name
                assert repr(detail) == repr(views.item_detail(conn, SCOPE, absent, viewer=viewer))
                assert repr(answers) == repr(views.item_answers(conn, SCOPE, absent, viewer=viewer))


def test_a_code_with_no_context_is_listed_because_the_module_does_not_hide_it(
    world: World, queue: dict[str, Any]
) -> None:
    """The module leaves a code with no context to the entry points' word checks: every reader
    gets it here, and the item of it too."""
    with open_uow(world.db, readonly=True) as uow:
        for viewer in READERS.values():
            ids = {r.id for r in views.code_list(uow.conn(), SCOPE, viewer=viewer).rows}
            assert queue["codes"]["none"] in ids
            assert queue["items"]["none"] in {
                r.id for r in views.item_list(uow.conn(), SCOPE, viewer=viewer).rows
            }


def test_the_filter_runs_before_the_limit(world: World) -> None:
    """Eight items, three of them hidden from the lowest reader, and a page of five: the five
    shown are the first five the reader may read, not the first five of all eight."""
    tpl = world.intake_template()
    hidden_code = world.stage_code(tpl, context_id=world.hidden_record("restricted"))
    open_code = world.stage_code(tpl, context_id=world.record("awp.IWP", "IWP-3"))
    hidden_items: list[str] = []
    shown_items: list[str] = []
    for _ in range(3):  # the hidden ones are the oldest: they would fill a page first
        hidden_items.append(world.stage_item(hidden_code))
        time.sleep(0.002)  # ULIDs of one millisecond may not sort: keep the creation order exact
    for _ in range(5):
        shown_items.append(world.stage_item(open_code))
        time.sleep(0.002)
    with open_uow(world.db, readonly=True) as uow:
        conn = uow.conn()
        page = views.item_list(conn, SCOPE, limit=5, viewer=cf.LOWEST)
        assert [r.id for r in page.rows] == shown_items and page.total == 5
        assert set(hidden_items).isdisjoint(r.id for r in page.rows)
        second = views.item_list(conn, SCOPE, limit=3, offset=3, viewer=cf.LOWEST)
        assert [r.id for r in second.rows] == shown_items[3:] and second.total == 5
        codes = views.code_list(conn, SCOPE, limit=1, viewer=cf.LOWEST)
        assert codes.total == 1 and codes.rows[0].id == open_code
