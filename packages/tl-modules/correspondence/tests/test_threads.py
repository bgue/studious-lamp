"""Threads, manual assignment and superseding an item (P1-I5-T08b)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.services.errors import NoChangesError, RecordNotFoundError
from tl_mod_correspondence import registry
from tl_mod_correspondence.errors import InvalidItemError, ItemStateError, ThreadNotFoundError
from tl_mod_correspondence.handlers import threads as th
from tl_mod_correspondence.testing import BASE, PROJECT, CorrWorld, frozen_today

MONDAY = "2026-10-19"
CONTROLLER = cf.Viewer(actor="user:ctl", level=1, account="user:ctl")


def thread_of(world: CorrWorld, number: str) -> registry.ThreadRow:
    item = world.item(number)
    assert item.thread_id is not None, number
    with open_uow(world.db, readonly=True) as uow:
        found = registry.get_thread(uow.conn(), item.thread_id)
    assert found is not None
    return found


def assigned(world: CorrWorld, item_id: str) -> list[dict[str, Any]]:
    return [p for n, p in world.events_of(item_id) if n == "Correspondence.ThreadAssigned"]


def test_a_new_item_with_no_match_opens_a_thread_of_its_own(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.receive("Revised programme", received_on=MONDAY)
    thread = thread_of(world, made.key or "")
    assert (thread.number, thread.subject_key, thread.state, thread.item_count) == (
        "P123-THR-0001",
        "revised programme",
        "open",
        1,
    )
    assert (thread.governing_item_id, thread.last_item_on) == (made.stream_id, MONDAY)
    [event] = assigned(world, made.stream_id)
    assert event["thread_id"] == thread.id and event["responds_to_id"] is None
    # the first item is counted by Defined: no ItemAdded for it
    assert [n for n, _ in world.events_of(thread.id)] == [
        "Record.Created",
        "CorrespondenceThread.Defined",
    ]


def test_an_item_with_the_same_subject_joins_the_open_thread(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        first = world.receive("Revised programme")
        second = world.receive("RE: Revised  Programme")
        other = world.receive("Something else entirely")
    assert world.item(second.key or "").thread_id == world.item(first.key or "").thread_id
    assert world.item(other.key or "").thread_id != world.item(first.key or "").thread_id
    [event] = assigned(world, second.stream_id)
    assert (event["matched_by"], event["responds_to_id"]) == ("subject", None)
    assert thread_of(world, first.key or "").item_count == 2
    assert thread_of(world, other.key or "").number == "P123-THR-0002"


def test_a_reply_header_joins_the_thread_of_the_message_it_answers(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        first = world.receive("Programme", message_id="<one@mail.example>", medium="email")
        reply = world.receive(
            "A different subject",
            in_reply_to="<one@mail.example>",
            message_id="<two@mail.example>",
            medium="email",
        )
    assert world.item(reply.key or "").thread_id == world.item(first.key or "").thread_id
    assert world.item(reply.key or "").responds_to_id == first.stream_id
    [event] = assigned(world, reply.stream_id)
    assert event["matched_by"] == "header" and event["responds_to_id"] == first.stream_id


def test_an_item_number_in_the_text_joins_the_thread_of_that_item(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        first = world.receive("Programme")
        later = world.receive(
            "Follow-up", body="Further to your letter p123-cor-0001 of last week."
        )
        self_ref = world.receive("Third", body="This is P123-COR-0003 and nothing else.")
    assert world.item(later.key or "").thread_id == world.item(first.key or "").thread_id
    assert world.item(later.key or "").responds_to_id == first.stream_id
    [event] = assigned(world, later.stream_id)
    assert event["matched_by"] == "reference_key"
    assert world.item(self_ref.key or "").thread_id != world.item(first.key or "").thread_id


def test_a_match_with_an_item_that_has_no_thread_opens_one_for_both(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        old = world.forge_item("P123-COR-0070", state="Received")
        assert world.item("P123-COR-0070").thread_id is None
        later = world.receive("Unrelated subject", body="Re our letter P123-COR-0070.")
    thread = thread_of(world, "P123-COR-0070")
    assert thread.governing_item_id == old and thread.item_count == 2
    assert world.item(later.key or "").thread_id == thread.id
    assert world.item(later.key or "").responds_to_id == old


def test_a_drafted_reply_joins_the_thread_of_the_item_it_answers(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        first = world.receive("Programme")
        reply = world.draft("Our answer", responds_to_id=first.stream_id)
    assert world.item(reply.key or "").thread_id == world.item(first.key or "").thread_id
    [event] = assigned(world, reply.stream_id)
    assert event["responds_to_id"] == first.stream_id


def test_a_thread_the_viewer_cannot_read_is_never_joined(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        secret = world.receive("Commercial terms")
        with cf.use_viewer(CONTROLLER):
            world.set_class(secret.stream_id, "restricted")
        plain = world.receive("Commercial terms")
        assert world.item(plain.key or "").thread_id is not None
        with cf.use_viewer(CONTROLLER):
            assert world.item(plain.key or "").thread_id != world.item(secret.key or "").thread_id


def test_threads_are_numbered_per_project(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        world.receive("One")
        other = world.receive("One", scope="project:P999")
    with open_uow(world.db, readonly=True) as uow:
        found = registry.list_threads(uow.conn(), "project:P999")
    assert [t.number for t in found] == ["P999-THR-0001"]
    assert other.key == "P999-COR-0001"


def test_a_person_assigns_an_item_to_a_thread_and_says_what_it_answers(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        first = world.receive("Programme")
        stray = world.receive("Different")
        thread = thread_of(world, first.key or "")
        done = world.assign(stray.stream_id, thread_id=thread.id, responds_to_id=first.stream_id)
    assert world.item(stray.key or "").thread_id == thread.id
    assert world.item(stray.key or "").responds_to_id == first.stream_id
    assert thread_of(world, first.key or "").item_count == 2
    assert assigned(world, stray.stream_id)[-1]["matched_by"] == "manual"
    assert {e.event_type for e in done.events} == {
        "CorrespondenceThread.ItemAdded",
        "Correspondence.ThreadAssigned",
    }


def test_assigning_without_a_thread_opens_a_new_one(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        first = world.receive("Programme")
        second = world.receive("RE: Programme")  # joins by subject
        done = world.assign(second.stream_id)
    assert world.item(second.key or "").thread_id != world.item(first.key or "").thread_id
    own = thread_of(world, second.key or "")
    assert own.governing_item_id == second.stream_id
    assert own.item_count == 1  # the item that opened it is counted by Defined, not added again
    assert [n for n, _ in world.events_of(own.id)] == [
        "Record.Created",
        "CorrespondenceThread.Defined",
    ]
    assert done.events[0].event_type == "Record.Created"


def test_assign_refuses_unknown_things_a_repeat_a_void_item_and_self_answers(
    world: CorrWorld,
) -> None:
    with frozen_today(MONDAY):
        first = world.receive("Programme")
        thread = thread_of(world, first.key or "")
        with pytest.raises(NoChangesError):
            world.assign(first.stream_id, thread_id=thread.id)
        with pytest.raises(ThreadNotFoundError):
            world.assign(first.stream_id, thread_id="01J000000000000000000000")
        with pytest.raises(RecordNotFoundError):
            world.assign(
                first.stream_id, thread_id=thread.id, responds_to_id="01J000000000000000000000"
            )
        with pytest.raises(InvalidItemError):
            world.assign(first.stream_id, thread_id=thread.id, responds_to_id=first.stream_id)
        with pytest.raises(RecordNotFoundError):
            world.assign("01J000000000000000000000")
        with pytest.raises(ValidationError):
            world.assign(first.stream_id, unknown=1)
        gone = world.draft("Mistake")
        world.void_draft(gone.stream_id)
        with pytest.raises(ItemStateError):
            world.assign(gone.stream_id, thread_id=thread.id)
        foreign = world.receive("Elsewhere", scope="project:P999")
        with pytest.raises(ThreadNotFoundError):
            world.assign(first.stream_id, thread_id=thread_of_scope(world, foreign.key or ""))


def thread_of_scope(world: CorrWorld, number: str) -> str:
    with open_uow(world.db, readonly=True) as uow:
        item = registry.find_item(uow.conn(), "project:P999", number)
    assert item is not None and item.thread_id is not None
    return item.thread_id


def test_superseding_marks_the_old_item_links_the_new_one_and_closes_the_old(
    world: CorrWorld,
) -> None:
    with frozen_today(MONDAY):
        old = world.draft("Letter with a mistake")
        new = world.draft("Corrected letter")
        done = world.supersede(old.stream_id, new.stream_id, "wrong figure in paragraph 2")
    item = world.item(old.key or "")
    assert item.superseded_by_id == new.stream_id and item.closed is True
    payload = [p for n, p in world.events_of(old.stream_id) if n == "Correspondence.Superseded"]
    assert payload == [{"superseded_by_id": new.stream_id, "reason": "wrong figure in paragraph 2"}]
    links = world.rows(
        "SELECT from_id, to_id, relation FROM cur_links WHERE relation = 'supersedes'"
    )
    assert links == [{"from_id": new.stream_id, "to_id": old.stream_id, "relation": "supersedes"}]
    assert {e.event_type for e in done.events} >= {"Correspondence.Superseded", "Link.Added"}
    with frozen_today(MONDAY), pytest.raises(ItemStateError):
        world.update(old.stream_id, body="more")


def test_superseding_refuses_itself_a_void_replacement_a_closed_item_and_a_blank_reason(
    world: CorrWorld,
) -> None:
    with frozen_today(MONDAY):
        old = world.draft("Old")
        new = world.draft("New")
        voided = world.draft("Void")
        world.void_draft(voided.stream_id)
        with pytest.raises(InvalidItemError):
            world.supersede(old.stream_id, old.stream_id)
        with pytest.raises(ItemStateError):
            world.supersede(old.stream_id, voided.stream_id)
        with pytest.raises(ValidationError):
            world.supersede(old.stream_id, new.stream_id, reason=" ")
        with pytest.raises(RecordNotFoundError):
            world.supersede(old.stream_id, "01J000000000000000000000")
        world.supersede(old.stream_id, new.stream_id)
        with pytest.raises(ItemStateError):
            world.supersede(old.stream_id, new.stream_id)
        assert world.item(PROJECT and new.key or "").superseded_by_id is None


def test_a_hidden_item_cannot_be_superseded_or_used_to_supersede(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        secret = world.draft("Secret")
        plain = world.draft("Plain")
        with cf.use_viewer(CONTROLLER):
            world.set_class(secret.stream_id, "restricted")
        with pytest.raises(RecordNotFoundError):
            world.supersede(plain.stream_id, secret.stream_id)
        with pytest.raises(RecordNotFoundError):
            world.supersede(secret.stream_id, plain.stream_id)


def test_threading_an_item_that_is_in_a_thread_already_adds_nothing(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.receive("Programme")
    before = [n for n, _ in world.events_of(made.stream_id)]
    thread = thread_of(world, made.key or "")
    with open_uow(world.db) as uow:
        item = registry.get_item(uow.conn(), made.stream_id)
        assert item is not None
        cmd = th.AssignThread(**BASE, stream_id=made.stream_id)
        assert th.assign_thread(uow, cmd, item) == []
        again = th.with_thread(uow, cmd, made)
    assert again.events == made.events
    assert [n for n, _ in world.events_of(made.stream_id)] == before
    assert thread_of(world, made.key or "").item_count == thread.item_count == 1


# --- moving an existing item never raises its class silently (ADR-0016 section 5) -------------


def _privileged_world(world: CorrWorld) -> tuple[str, str, str, str]:
    """A privileged item (thread and all) read by amy and ctl, and an internal item of bob's with
    a thread of its own. Returns (privileged id, its thread id, internal id, internal thread id)."""
    from tl_core.auth import accounts
    from tl_core.auth.password import prepare_password

    with open_uow(world.db) as uow:
        for name in ("u", "amy", "ctl"):
            accounts.create_account(
                uow, username=name, display_name=name, kind="person", roles=["user"],
                password=prepare_password("correct horse battery"), by="svc:test",
            )  # fmt: skip
    with frozen_today(MONDAY):
        secret = world.receive("Counsel advice", received_on=MONDAY)
        plain = world.receive("Site memo", received_on=MONDAY)
    with cf.use_viewer(CONTROLLER):
        world.set_class(secret.stream_id, "privileged", grant=["user:amy", "user:ctl"])
        secret_thread = world.item(secret.key or "").thread_id
    plain_thread = world.item(plain.key or "").thread_id
    assert secret_thread and plain_thread
    return secret.stream_id, secret_thread, plain.stream_id, plain_thread


def _unchanged(world: CorrWorld, item_id: str, events: list[tuple[str, dict[str, Any]]]) -> None:
    with cf.use_viewer(CONTROLLER):
        with open_uow(world.db, readonly=True) as uow:
            row = registry.get_item(uow.conn(), item_id)
        assert row is not None and row.confidentiality == "internal"
    assert world.events_of(item_id) == events


def test_a_plain_user_cannot_file_an_item_in_a_higher_class_thread(world: CorrWorld) -> None:
    from tl_core.auth.errors import ForbiddenError

    _, secret_thread, plain_id, _ = _privileged_world(world)
    before = world.events_of(plain_id)
    amy = cf.Viewer(actor="user:amy", level=0, account="user:amy")
    with cf.use_viewer(amy), pytest.raises(ForbiddenError, match="document_controller"):
        world.run(
            th.AssignThread, th.handle_assign_thread, stream_id=plain_id, thread_id=secret_thread
        )
    _unchanged(world, plain_id, before)


def test_a_plain_user_cannot_make_an_item_answer_a_higher_class_item(world: CorrWorld) -> None:
    from tl_core.auth.errors import ForbiddenError

    secret_id, _, plain_id, plain_thread = _privileged_world(world)
    before = world.events_of(plain_id)
    amy = cf.Viewer(actor="user:amy", level=0, account="user:amy")
    with cf.use_viewer(amy), pytest.raises(ForbiddenError):
        world.run(
            th.AssignThread,
            th.handle_assign_thread,
            stream_id=plain_id,
            thread_id=plain_thread,
            responds_to_id=secret_id,
        )
    _unchanged(world, plain_id, before)


def test_a_plain_user_may_still_move_an_item_to_a_thread_of_its_own_class(
    world: CorrWorld,
) -> None:
    with frozen_today(MONDAY):
        one = world.receive("Programme", received_on=MONDAY)
        two = world.receive("Site memo", received_on=MONDAY)
    thread = world.item(one.key or "").thread_id
    assert thread
    world.run(th.AssignThread, th.handle_assign_thread, stream_id=two.stream_id, thread_id=thread)
    assert world.item(two.key or "").thread_id == thread


def test_a_controllers_move_into_a_higher_class_thread_raises_the_class_on_record(
    world: CorrWorld,
) -> None:
    _, secret_thread, plain_id, _ = _privileged_world(world)
    with cf.use_viewer(CONTROLLER):
        world.run(
            th.AssignThread, th.handle_assign_thread, stream_id=plain_id, thread_id=secret_thread
        )
        events = world.events_of(plain_id)
        changed = [p for n, p in events if n == "Correspondence.ConfidentialityChanged"]
        with open_uow(world.db, readonly=True) as uow:
            row = registry.get_item(uow.conn(), plain_id)
            assert row is not None and row.confidentiality == "privileged"
            named = {c.account for c in registry.clearances_of(uow.conn(), plain_id)}
    assert [(p["from_class"], p["to_class"]) for p in changed] == [("internal", "privileged")]
    assert {"user:amy", "user:ctl", "user:u"} <= named
    amy = cf.Viewer(actor="user:amy", level=0, account="user:amy")
    with cf.use_viewer(amy), open_uow(world.db, readonly=True) as uow:
        assert registry.get_item(uow.conn(), plain_id) is not None
    nobody = cf.Viewer(actor="user:bob", level=0, account="user:bob")
    with cf.use_viewer(nobody), open_uow(world.db, readonly=True) as uow:
        assert registry.get_item(uow.conn(), plain_id) is None
