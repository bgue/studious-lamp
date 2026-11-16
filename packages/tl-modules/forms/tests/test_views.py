"""The read views of templates and submissions, and ``form_for`` (P2-FORMS T03): lists, filters,
order, limits, detail, and the form a record offers. Each test builds its own world."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from typing import Any

import pytest
from forms_world import SCOPE, World, answer, two_fields
from sqlalchemy import event
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.forms.types import FormBinding
from tl_core.util import new_ulid
from tl_mod_forms import views
from tl_mod_forms.names import SUBMISSION

NOW = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)
AUTHOR = cf.Viewer(actor="user:uma", level=0, account="user:uma")
LOWEST = cf.LOWEST


def make_template(
    world: World, title: str, *, publish: bool = True, fields: list[dict[str, Any]] | None = None,
    **more: Any,
) -> str:  # fmt: skip
    """A template with its own title (the world's helper fixes the title)."""
    made = world.call(
        "ada", "DraftFormTemplate", title=title, fields=fields or two_fields(), **more
    )
    if publish:
        world.call("ada", "PublishFormTemplate", template_id=made.stream_id)
    return str(made.stream_id)


def submit_as(world: World, who: str, template: str, **more: Any) -> str:
    return str(world.submit(who, template, **more).stream_id)


def ids(page: views.Page[Any]) -> set[str]:
    return {r.id for r in page.rows}


def with_conn(world: World, fn: Any) -> Any:
    with open_uow(world.db, readonly=True) as uow:
        return fn(uow.conn())


# --- templates ---------------------------------------------------------------------------------


def test_template_list_orders_by_title_version_and_id(world: World) -> None:
    gamma = make_template(world, "Gamma")
    alpha = make_template(world, "Alpha")
    beta = make_template(world, "Beta")
    page = with_conn(world, lambda c: views.template_list(c))
    assert [r.id for r in page.rows] == [alpha, beta, gamma]
    assert page.total == 3
    row = page.rows[0]
    assert row.state == "Published" and row.key is not None and row.title == "Alpha"


def test_template_list_covers_all_three_states(world: World) -> None:
    make_template(world, "Draft one", publish=False)
    make_template(world, "Live one")
    retired = make_template(world, "Old one")
    world.call("ada", "RetireFormTemplate", template_id=retired)
    states = with_conn(world, lambda c: views.template_list(c)).rows
    assert sorted(r.state for r in states) == ["Draft", "Published", "Retired"]
    for state in ("Draft", "Published", "Retired"):
        page = with_conn(world, lambda c, s=state: views.template_list(c, state=s))
        assert [r.state for r in page.rows] == [state] and page.total == 1


def test_template_list_filters_by_intake(world: World) -> None:
    make_template(world, "Plain")
    public = make_template(
        world, "Public", intake="public", purpose="request", accepts_as=["SubmitForm"]
    )
    page = with_conn(world, lambda c: views.template_list(c, intake="public"))
    assert [r.id for r in page.rows] == [public] and page.total == 1


def test_template_list_rejects_an_unknown_state_or_intake(world: World) -> None:
    for kwargs in ({"state": "Open"}, {"intake": "private"}):
        with pytest.raises(ValueError) as caught:
            with_conn(world, lambda c, k=kwargs: views.template_list(c, **k))
        assert str(caught.value) == "unknown state"


def test_template_list_clamps_the_limit_and_pages_by_offset(world: World) -> None:
    for title in ("A", "B", "C"):
        make_template(world, title)
    small = with_conn(world, lambda c: views.template_list(c, limit=0))
    assert len(small.rows) == 1 and small.total == 3
    assert views._clamp(9999) == views.MAX_LIMIT == 500
    assert views._clamp(0) == views.MIN_LIMIT == 1
    second = with_conn(world, lambda c: views.template_list(c, limit=1, offset=1))
    assert [r.title for r in second.rows] == ["B"] and second.total == 3


def test_template_detail_decodes_fields_and_accepts_as(world: World) -> None:
    tid = make_template(
        world, "Public", intake="public", purpose="request", accepts_as=["SubmitForm"]
    )
    detail = with_conn(world, lambda c: views.template_detail(c, tid))
    assert detail is not None
    assert [f["id"] for f in detail.fields] == ["topic", "count"]
    assert detail.accepts_as == ["SubmitForm"]
    assert detail.row.field_count == 2
    assert with_conn(world, lambda c: views.template_detail(c, "no-such-id")) is None


def test_template_detail_of_a_draft_and_a_template_without_accepts(world: World) -> None:
    tid = make_template(world, "Plain", publish=False)
    detail = with_conn(world, lambda c: views.template_detail(c, tid))
    assert detail is not None and detail.row.state == "Draft" and detail.accepts_as == []


# --- submissions -------------------------------------------------------------------------------


def test_submission_rows_carry_no_answers(world: World) -> None:
    names = {f.name for f in dataclasses.fields(views.SubmissionRow)}
    assert "answers" not in names and "review_note" not in names
    tpl = make_template(world, "Form")
    submit_as(world, "uma", tpl)
    page = with_conn(world, lambda c: views.submission_list(c, SCOPE, viewer=LOWEST))
    assert page.total == 1 and not hasattr(page.rows[0], "answers")


def test_submission_list_filters_by_state_template_subject_and_author(world: World) -> None:
    tpl_a = make_template(world, "A")
    tpl_b = make_template(world, "B")
    here = world.record("awp.IWP", "IWP-1")
    first = submit_as(world, "uma", tpl_a, subject_id=here)
    second = submit_as(world, "rob", tpl_b)
    draft = str(world.save("uma", tpl_a).stream_id)

    def listing(**kw: Any) -> set[str]:
        return ids(with_conn(world, lambda c: views.submission_list(c, SCOPE, **kw)))

    assert listing(viewer=AUTHOR, state="Draft") == {draft}
    assert listing(viewer=AUTHOR, state="Submitted") == {first, second}
    assert listing(template_id=tpl_a, viewer=AUTHOR) == {first, draft}
    assert listing(template_id=tpl_b) == {second}
    assert listing(subject_id=here) == {first}
    assert listing(author=world.submission(second)["author"]) == {second}
    with pytest.raises(ValueError):
        listing(state="Open")


def test_submission_list_orders_submitted_first_then_id_and_drafts_last(world: World) -> None:
    tpl = make_template(world, "Form")
    draft = str(world.save("uma", tpl).stream_id)
    sent = submit_as(world, "uma", tpl)
    page = with_conn(world, lambda c: views.submission_list(c, SCOPE, viewer=AUTHOR))
    assert [r.id for r in page.rows] == [sent, draft]
    assert page.rows[-1].submitted_on is None and page.rows[-1].key is None


def test_submission_detail_by_key_and_by_id_decodes_answers(world: World) -> None:
    tpl = make_template(world, "Form")
    sent = submit_as(world, "uma", tpl, answers=[answer("topic", "Ladders")])
    key = world.key(sent)
    assert key is not None
    by_key = with_conn(world, lambda c: views.submission_detail(c, SCOPE, key, viewer=LOWEST))
    by_id = with_conn(world, lambda c: views.submission_detail(c, SCOPE, sent, viewer=LOWEST))
    assert by_key is not None and by_id is not None and by_key == by_id
    assert by_id.row.id == sent and by_id.answers[0]["q"] == "topic"
    assert by_id.review_note is None and by_id.void_reason is None


def test_a_draft_has_no_key_and_its_detail_is_read_by_id(world: World) -> None:
    tpl = make_template(world, "Form")
    draft = str(world.save("uma", tpl, answers=[answer("topic", "Wip")]).stream_id)
    assert world.key(draft) is None
    detail = with_conn(world, lambda c: views.submission_detail(c, SCOPE, draft, viewer=AUTHOR))
    assert detail is not None and detail.row.key is None and detail.row.state == "Draft"
    assert detail.answers[0]["value"] == "Wip"
    assert with_conn(world, lambda c: views.submission_detail(c, SCOPE, "nope")) is None


# --- form_for ----------------------------------------------------------------------------------


class FakeSource:
    """A form source injected through the registry's loader (no entry points)."""

    record_type = SUBMISSION
    view_word = "forms.view"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def binding(self, conn: Any, record_id: str, viewer: cf.Viewer, now: datetime) -> FormBinding:
        self.calls.append(record_id)
        return FormBinding(record_type=SUBMISSION, key="K", available=False, reason="closed")


def test_form_for_returns_the_binding_of_the_source_of_the_type(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = FakeSource()
    monkeypatch.setattr(views, "load_form_sources", lambda *a, **k: {SUBMISSION: source})
    tpl = make_template(world, "Form")
    sent = submit_as(world, "uma", tpl)
    binding = with_conn(world, lambda c: views.form_for(c, sent, now=NOW, viewer=LOWEST))
    assert binding == FormBinding(record_type=SUBMISSION, key="K", available=False, reason="closed")
    assert source.calls == [sent]


def test_form_for_with_no_source_for_the_type_is_none(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(views, "load_form_sources", lambda *a, **k: {})
    iwp = world.record("awp.IWP", "IWP-1")
    assert with_conn(world, lambda c: views.form_for(c, iwp, now=NOW)) is None
    assert with_conn(world, lambda c: views.form_for(c, new_ulid(), now=NOW)) is None


def test_form_for_a_hidden_record_is_none_and_never_reaches_the_source(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = FakeSource()
    monkeypatch.setattr(views, "load_form_sources", lambda *a, **k: {SUBMISSION: source})
    tpl = make_template(world, "Secret", answer_class="restricted")
    sent = submit_as(world, "uma", tpl)
    draft = str(world.save("uma", make_template(world, "Plain")).stream_id)
    assert with_conn(world, lambda c: views.form_for(c, sent, now=NOW)) is None
    assert with_conn(world, lambda c: views.form_for(c, draft, now=NOW)) is None
    assert source.calls == []
    assert with_conn(world, lambda c: views.form_for(c, draft, now=NOW, viewer=AUTHOR)) is not None
    assert source.calls == [draft]


# --- the shape of the reads ---------------------------------------------------------------------


def test_a_list_runs_two_statements_the_rows_and_the_count(world: World) -> None:
    make_template(world, "Form")
    statements: list[str] = []

    def count(conn: Any) -> None:
        def record(*args: Any) -> None:
            statements.append(str(args[2]))

        event.listen(conn, "before_cursor_execute", record)
        try:
            views.template_list(conn)
            views.submission_list(conn, SCOPE)
        finally:
            event.remove(conn, "before_cursor_execute", record)

    with_conn(world, count)
    assert len(statements) == 4  # two statements for each list, no more
    assert all(s.lstrip().upper().startswith("SELECT") for s in statements)
