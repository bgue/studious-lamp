"""The read views of forms as the five kinds of reader (ADR-0016; P2-FORMS T03): the lowest
clearance by default, a reader of each class, the author, an admin and the system viewer. A
restricted submission and a draft are absent from every list and its count, and their detail is
``None`` exactly as an id that never existed gives. Filtering runs before the limit."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from forms_world import SCOPE, World, answer, two_fields
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.util import new_ulid
from tl_mod_forms import views

NOW = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)
SYSTEM = cf.Viewer(actor="system", level=1, system=True)
#: The readers and what each may read: (viewer, is it a reader of a restricted record).
READERS: dict[str, cf.Viewer] = {
    "nobody (the default)": cf.LOWEST,
    "vera (a viewer, internal)": cf.Viewer(actor="user:vera", level=0, account="user:vera"),
    "rob (another user)": cf.Viewer(actor="user:rob", level=0, account="user:rob"),
    "uma (the author)": cf.Viewer(actor="user:uma", level=0, account="user:uma"),
    "dora (a document controller)": cf.Viewer(actor="user:dora", level=1, account="user:dora"),
    "ada (an admin)": cf.Viewer(actor="user:ada", level=1, account="user:ada"),
    "system": SYSTEM,
}


def make_template(world: World, title: str, **more: Any) -> str:
    made = world.call("ada", "DraftFormTemplate", title=title, fields=two_fields(), **more)
    world.call("ada", "PublishFormTemplate", template_id=made.stream_id)
    return str(made.stream_id)


def listed(world: World, viewer: cf.Viewer | None = None, **kw: Any) -> views.Page[Any]:
    with open_uow(world.db, readonly=True) as uow:
        if viewer is None:
            return views.submission_list(uow.conn(), SCOPE, **kw)
        return views.submission_list(uow.conn(), SCOPE, viewer=viewer, **kw)


def detail(world: World, ref: str, viewer: cf.Viewer | None = None) -> Any:
    with open_uow(world.db, readonly=True) as uow:
        if viewer is None:
            return views.submission_detail(uow.conn(), SCOPE, ref)
        return views.submission_detail(uow.conn(), SCOPE, ref, viewer=viewer)


def fixture_world(world: World) -> dict[str, str]:
    """An internal submission (I), a restricted one by the author (R) and the author's draft (D)."""
    internal = make_template(world, "Open")
    restricted = make_template(world, "Secret", answer_class="restricted")
    return {
        "I": str(world.submit("uma", internal, answers=[answer("topic", "Open")]).stream_id),
        "R": str(world.submit("uma", restricted, answers=[answer("topic", "Secret")]).stream_id),
        "D": str(world.save("uma", internal, answers=[answer("topic", "Draft")]).stream_id),
    }


#: Which of I, R and D each reader may read.
EXPECTED: dict[str, set[str]] = {
    "nobody (the default)": {"I"},
    "vera (a viewer, internal)": {"I"},
    "rob (another user)": {"I"},
    "uma (the author)": {"I", "R", "D"},
    "dora (a document controller)": {"I", "R"},
    "ada (an admin)": {"I", "R"},
    "system": {"I", "R", "D"},
}


def test_the_five_readers_see_exactly_what_the_rules_give(world: World) -> None:
    subs = fixture_world(world)
    ghost = new_ulid()
    for name, viewer in READERS.items():
        page = listed(world, viewer)
        seen = {letter for letter, sid in subs.items() if sid in {r.id for r in page.rows}}
        assert seen == EXPECTED[name], name
        assert page.total == len(EXPECTED[name]), name
        for letter, sid in subs.items():
            found = detail(world, sid, viewer)
            if letter in EXPECTED[name]:
                assert found is not None and found.row.id == sid, (name, letter)
            else:
                assert found is None, (name, letter)
                assert found == detail(world, ghost, viewer), (name, letter)


def test_a_hidden_submission_is_absent_from_every_filter_of_the_list(world: World) -> None:
    subs = fixture_world(world)
    template_r = world.submission(subs["R"])["template_id"]
    for name, viewer in READERS.items():
        if name in EXPECTED and "R" in EXPECTED[name]:
            continue
        by_template = {r.id for r in listed(world, viewer, template_id=template_r).rows}
        by_state = {r.id for r in listed(world, viewer, state="Submitted").rows}
        assert subs["R"] not in by_template and subs["R"] not in by_state, name
        assert subs["D"] not in {r.id for r in listed(world, viewer, state="Draft").rows}, name


def test_a_draft_is_not_read_by_a_controller_or_an_admin(world: World) -> None:
    subs = fixture_world(world)
    for name in ("dora (a document controller)", "ada (an admin)", "rob (another user)"):
        assert detail(world, subs["D"], READERS[name]) is None, name
        assert subs["D"] not in {r.id for r in listed(world, READERS[name]).rows}, name


def test_the_default_viewer_is_the_lowest_clearance(world: World) -> None:
    subs = fixture_world(world)
    default = listed(world)
    explicit = listed(world, cf.LOWEST)
    assert [r.id for r in default.rows] == [r.id for r in explicit.rows]
    assert default.total == explicit.total == 1
    assert subs["R"] not in {r.id for r in default.rows}
    assert detail(world, subs["R"]) is None and detail(world, subs["D"]) is None
    assert detail(world, subs["I"]) is not None


def test_the_filter_runs_before_the_limit_and_the_count(world: World) -> None:
    tpl_secret = make_template(world, "Secret", answer_class="restricted")
    tpl_open = make_template(world, "Open")
    hidden = [world.submit("uma", tpl_secret).stream_id for _ in range(3)]
    shown = [world.submit("uma", tpl_open).stream_id for _ in range(5)]
    assert len(hidden) + len(shown) == 8
    readable = {str(s) for s in shown}
    first = listed(world, cf.LOWEST, limit=5)
    assert len(first.rows) == 5 and first.total == 5
    assert {r.id for r in first.rows} == readable
    page_two = listed(world, cf.LOWEST, limit=3, offset=3)
    assert len(page_two.rows) == 2 and page_two.total == 5
    assert {r.id for r in page_two.rows} <= readable
    past_the_end = listed(world, cf.LOWEST, limit=3, offset=5)
    assert past_the_end.rows == [] and past_the_end.total == 5
    assert len(listed(world, READERS["ada (an admin)"], limit=5).rows) == 5
    assert listed(world, READERS["ada (an admin)"]).total == 8


def test_the_template_list_and_the_form_for_read_the_same_way(world: World) -> None:
    subs = fixture_world(world)
    with open_uow(world.db, readonly=True) as uow:
        conn = uow.conn()
        assert views.form_for(conn, subs["R"], now=NOW) is None
        assert views.form_for(conn, subs["D"], now=NOW) is None
        assert views.form_for(conn, subs["D"], now=NOW, viewer=READERS["uma (the author)"]) is None
    with open_uow(world.db, readonly=True) as uow:
        assert views.template_list(uow.conn()).total == 2


def test_views_source_holds_no_intake_body_no_code_hash_and_no_write() -> None:
    """The repo-style check: the read module names no intake body, no code hash, no write."""
    source = Path(views.__file__).read_text(encoding="utf-8")
    for banned in ("forms_intake_body", "code_hash", "INSERT", "UPDATE", "DELETE"):
        assert banned not in source, banned
