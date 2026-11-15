"""The author-only draft rule (P2-FORMS CR1): a draft is read by its author alone, on every path.

Readers: the author, another user, a document controller, an admin, an agent, a viewer with no
actor (the default), and the system viewer.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from forms_world import MARKER, SCOPE, World, answer
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.services import feed_queries, queries
from tl_core.services.errors import RecordNotFoundError
from tl_core.util import new_ulid

SUBMISSION = "forms.Submission"
AUTHOR = cf.Viewer(actor="user:uma", level=0, account="user:uma")
OTHER_USER = cf.Viewer(actor="user:rob", level=0, account="user:rob")
VERA = cf.Viewer(actor="user:vera", level=0, account="user:vera")
CONTROLLER = cf.Viewer(actor="user:dora", level=1, account="user:dora")
ADMIN = cf.Viewer(actor="user:ada", level=1, account="user:ada")
AGENT = cf.Viewer(actor="agent:bot", level=0, account="")
NOBODY = cf.LOWEST
STRANGERS = {"rob": OTHER_USER, "dora": CONTROLLER, "ada": ADMIN, "agent": AGENT, "nobody": NOBODY}


def hidden(world: World, record: str, viewer: cf.Viewer) -> bool:
    with open_uow(world.db, readonly=True) as uow:
        return cf.is_hidden(uow.conn(), record, viewer)


def draft_of(world: World, who: str = "uma", **more: Any) -> str:
    return str(world.save(who, world.template(), **more).stream_id)


def test_a_draft_is_read_by_its_author_alone(world: World) -> None:
    draft = draft_of(world)
    assert not hidden(world, draft, AUTHOR)
    for name, viewer in STRANGERS.items():
        assert hidden(world, draft, viewer), name
    assert not hidden(world, draft, cf.Viewer(actor="system", level=1, system=True))


def read(world: World, record: str, viewer: cf.Viewer) -> str:
    """What reading one record by id gives: what a record that never existed gives, for a hidden
    one (the id is cut out of the text)."""
    with open_uow(world.db, readonly=True) as uow, cf.use_viewer(viewer):
        try:
            found = queries.get_record_by_id(uow, record)
            history = queries.record_history(uow, record)
        except RecordNotFoundError as exc:
            return str(exc).replace(record, "<id>")
    return f"{found is None} {len(history)}"


def test_a_hidden_draft_answers_like_a_record_that_never_existed(world: World) -> None:
    draft = draft_of(world)
    ghost = new_ulid()
    assert read(world, draft, AUTHOR) != read(world, ghost, AUTHOR)
    for name, viewer in STRANGERS.items():
        assert read(world, draft, viewer) == read(world, ghost, viewer), name
    for name, viewer in STRANGERS.items():
        with open_uow(world.db, readonly=True) as uow, pytest.raises(RecordNotFoundError) as one:
            cf.require_visible(uow.conn(), draft, viewer)
        assert str(one.value) == f"no record {draft!r}", name


def test_the_filter_runs_before_the_limit_of_a_page(world: World) -> None:
    tpl = world.template()
    for _ in range(3):  # the oldest three are another author's drafts
        world.save("rob", tpl)
    kept = [str(world.submit("uma", tpl).stream_id) for _ in range(5)]
    sql = f"SELECT id FROM cur_forms_submission WHERE scope = '{SCOPE}' ORDER BY id"
    with open_uow(world.db, readonly=True) as uow:
        page = cf.visible_rows(uow.conn(), sql, {}, limit=5, viewer=VERA)
        assert [str(r.id) for r in page] == kept  # not the two a page cut before the filter gives
        mixed = cf.visible_rows(uow.conn(), sql, {}, limit=5, viewer=OTHER_USER)
        assert len(mixed) == 5  # his own three drafts count for him: the first five of the eight
        wide = cf.visible_rows(uow.conn(), sql, {}, limit=50, viewer=AUTHOR)
        assert [str(r.id) for r in wide] == kept  # the author reads her five, not his three
        assert len(cf.visible_rows(uow.conn(), sql, {}, limit=50, viewer=OTHER_USER)) == 8


def test_a_list_and_a_count_leave_out_another_authors_drafts(world: World) -> None:
    tpl = world.template()
    mine = str(world.save("uma", tpl).stream_id)
    sent = str(world.submit("uma", tpl).stream_id)
    for viewer, expected in ((AUTHOR, {mine, sent}), (OTHER_USER, {sent}), (NOBODY, {sent})):
        with cf.use_viewer(viewer), open_uow(world.db, readonly=True) as uow:
            rows = queries.list_records(uow, SCOPE, record_type=SUBMISSION)
        assert {str(r["id"]) for r in rows} == expected


def test_the_events_of_a_draft_stream_are_hidden_from_everyone_but_its_author(
    world: World,
) -> None:
    draft = draft_of(world, answers=[answer("topic", MARKER)])
    rows = world.rows("SELECT event_id, stream_id, stream_type, payload FROM events")
    own = {r["event_id"] for r in rows if r["stream_id"] == draft}
    assert own
    with open_uow(world.db, readonly=True) as uow:
        conn = uow.conn()
        assert cf.hidden_row_ids(conn, rows, AUTHOR) & own == set()
        assert cf.hidden_event_streams(conn, [(draft, SUBMISSION)], AUTHOR) == set()
        for name, viewer in STRANGERS.items():
            assert own <= cf.hidden_row_ids(conn, rows, viewer), name
            assert cf.hidden_event_streams(conn, [(draft, SUBMISSION)], viewer) == {draft}, name
        assert cf.hidden_row_ids(conn, rows, cf.Viewer(actor="system", system=True)) == set()
        everything = uow.ledger.read_after(0, scope=SCOPE, limit=1000)
        with cf.use_viewer(OTHER_USER):
            shown = cf.filter_events(conn, everything)
        assert draft not in {e.stream_id for e in shown}
        assert MARKER not in json.dumps([e.payload for e in shown], default=str)


def test_a_draft_makes_no_card_and_the_submit_card_names_no_answer(world: World) -> None:
    tpl = world.template()
    draft = str(world.save("uma", tpl, answers=[answer("topic", MARKER)]).stream_id)
    assert world.rows("SELECT * FROM cur_feed_items WHERE scope = :s", s=SCOPE) == []
    world.call("uma", "DiscardFormDraft", submission_id=draft)
    assert world.rows("SELECT * FROM cur_feed_items WHERE scope = :s", s=SCOPE) == []
    sub = str(world.submit("uma", tpl, answers=[answer("topic", MARKER)]).stream_id)
    cards = world.rows("SELECT * FROM cur_feed_items WHERE scope = :s", s=SCOPE)
    assert [c["event_type"] for c in cards if "Submission" in c["event_type"]] == [
        "Submission.Submitted"
    ]
    assert not [c for c in cards if MARKER in str(c)]
    assert not [c for c in cards if c["event_type"] in ("Record.Created", "Record.Updated")]
    with open_uow(world.db, readonly=True) as uow:
        with cf.use_viewer(AUTHOR):
            page = feed_queries.list_feed(uow, SCOPE, record_id=sub)
        assert [i.item_type for i in page.items] and not [i for i in page.items if MARKER in str(i)]


def test_the_same_row_after_a_submit_is_read_per_class(world: World) -> None:
    tpl = world.template()
    draft = str(world.save("uma", tpl).stream_id)
    assert hidden(world, draft, OTHER_USER)
    world.submit("uma", draft_id=draft)
    for viewer in (AUTHOR, OTHER_USER, CONTROLLER, AGENT, NOBODY):
        assert not hidden(world, draft, viewer)  # internal class, no subject


def test_the_author_of_a_restricted_or_privileged_form_completes_and_reads_it(
    world: World,
) -> None:
    for cls in ("restricted", "privileged"):
        tpl = world.template(answer_class=cls)
        sub = str(world.submit("uma", tpl).stream_id)  # a plain user: completes the submit
        assert world.state(sub) == "Submitted"
        assert not hidden(world, sub, AUTHOR)
        for viewer in (OTHER_USER, AGENT, NOBODY):
            assert hidden(world, sub, viewer), cls
        assert hidden(world, sub, ADMIN) or cls == "restricted"
        draft = str(world.save("uma", tpl).stream_id)
        assert not hidden(world, draft, AUTHOR) and hidden(world, draft, OTHER_USER)
        world.submit("uma", draft_id=draft)  # a draft continues and submits


def test_a_restricted_submission_is_read_per_class_once_submitted(world: World) -> None:
    tpl = world.template(answer_class="restricted")
    draft = str(world.save("dora", tpl).stream_id)  # a controller fills it: she may read the class
    assert hidden(world, draft, ADMIN)  # a draft: its author only
    assert not hidden(world, draft, CONTROLLER)
    world.submit("dora", draft_id=draft)
    for viewer in (AUTHOR, OTHER_USER, AGENT, NOBODY):  # the class governs now (not her)
        assert hidden(world, draft, viewer)
    assert not hidden(world, draft, CONTROLLER) and not hidden(world, draft, ADMIN)


def test_a_discarded_draft_stays_the_authors(world: World) -> None:
    draft = draft_of(world)
    world.call("uma", "DiscardFormDraft", submission_id=draft)
    assert world.state(draft) == "Discarded"
    assert not hidden(world, draft, AUTHOR)
    for viewer in STRANGERS.values():
        assert hidden(world, draft, viewer)


def test_a_returned_submission_is_not_a_draft(world: World) -> None:
    tpl = world.template()
    sub = str(world.submit("uma", tpl).stream_id)
    world.call("bea", "ReturnFormSubmission", submission_id=sub, note="again")
    assert world.state(sub) == "Returned"
    for viewer in (AUTHOR, OTHER_USER, CONTROLLER, AGENT, NOBODY):
        assert not hidden(world, sub, viewer)


def test_the_system_viewer_reads_a_draft_and_the_default_does_not(world: World) -> None:
    draft = draft_of(world)
    with open_uow(world.db, readonly=True) as uow:
        with cf.system_view():
            assert queries.get_record_by_id(uow, draft) is not None
        assert queries.get_record_by_id(uow, draft) is None  # the default viewer is the lowest


def test_the_actor_bind_parameter_is_given_only_when_the_sql_names_it() -> None:
    sql = cf.hidden_sql(AUTHOR)
    assert sql is not None and f":{cf.ACTOR_PARAM}" in sql
    assert cf.params_for(sql, AUTHOR)[cf.ACTOR_PARAM] == "user:uma"
    assert cf.params_for("SELECT 1", AUTHOR) == {}


# --- the seam (S3 review F1): a refusal of the stored arguments never echoes them ---------------


def _nested(world: World, args: dict[str, Any]) -> Exception:
    from tl_core.services.nested import run_nested_command

    with open_uow(world.db) as uow, pytest.raises(Exception) as caught:
        run_nested_command(
            uow,
            command_type="SubmitForm",
            args=args,
            actor="user:uma",
            scope=SCOPE,
            source="mcp:forms-bot",
        )
    return caught.value


def test_a_failed_accept_of_a_stored_form_command_gives_a_fixed_text(world: World) -> None:
    """The accept path: a module's refusal is recorded as its class and a fixed sentence."""
    from tl_adapters.db import open_uow as unit
    from tl_core.services.proposals import accept_or_fail, propose
    from tl_mod_forms.commands import SubmitForm

    tpl = world.template()
    command = SubmitForm(
        actor="agent:forms-bot",
        source="mcp:forms-bot",
        scope=SCOPE,
        template_id=tpl,
        answers=[answer(MARKER, "x")],  # a question the template does not have
    )
    with unit(world.db) as uow:
        made = propose(
            uow, tool="propose_form_submission", agent="agent:forms-bot", command=command,
            summary="File it",
        )  # fmt: skip
    decided = accept_or_fail(
        lambda readonly=False: unit(world.db, readonly=readonly),
        proposal_id=made.proposal_id,
        by="user:rob",
    )
    assert decided.status == "failed" and MARKER not in str(decided.reason)
    assert decided.reason is not None and decided.reason.endswith("the module refused the command")


def test_a_marker_in_a_pydantic_refusal_on_the_seam_path_is_not_echoed(world: World) -> None:
    from tl_core.services.nested import MSG_ARGS, NestedCommandError

    for args in (
        {"template_id": "t", "answers": [MARKER]},
        {"template_id": "t", "answers": MARKER},
        {"template_id": MARKER * 20, "answers": []},
        {"template_id": "t", "answers": [], "subject_id": MARKER * 20},
        {"template_id": "t", "answers": [], MARKER: "x"},  # an unknown key
        {"template_id": "t", "answers": [{"q": "a", "value": MARKER}] * 500},
    ):
        error = _nested(world, args)
        assert isinstance(error, NestedCommandError), args
        assert str(error) == MSG_ARGS and MARKER not in repr(error), args
