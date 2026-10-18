"""The commands together: the flow of the increment's demo, on a ledger (P1-I5).

Receive a letter, triage it to General, draft and issue a reply, watch the clock, record the
answer, close. Each step checks the events and the rows; the per-command rules have their own
tests next to the tickets that built them.
"""

from __future__ import annotations

import pytest
from tl_core.services.errors import RecordNotFoundError
from tl_mod_correspondence.errors import ItemStateError
from tl_mod_correspondence.testing import CorrWorld, frozen_today

MONDAY = "2026-10-19"


def test_the_demo_flow_receive_triage_issue_and_the_clock(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        received = world.receive("Revised programme", received_on=MONDAY)
        assert received.key == "P123-COR-0001"
        item = world.item("P123-COR-0001")
        assert (item.state, item.direction, item.confidentiality) == ("Received", "in", "internal")
        world.upload(received.stream_id, "original")
        triaged = world.triage(received.stream_id)
        item = world.item("P123-COR-0001")
        assert (item.state, item.domain, item.subtype, item.response_required) == (
            "Triaged",
            "general",
            "letter",
            True,
        )
        assert world.clocks("P123-COR-0001") == []  # the General letter clock starts on issue
        reply = world.draft(responds_to_id=received.stream_id)
        draft = world.item(reply.key or "")
        assert (draft.state, draft.direction, draft.domain, draft.subtype) == (
            "Draft",
            "out",
            "general",
            "letter",
        )
        assert draft.responds_to_id == received.stream_id
        issued = world.issue(reply.stream_id)
    assert triaged.events and issued.events
    letter = world.item(reply.key or "")
    assert (letter.state, letter.delivery, letter.issued_on) == ("Issued", "stub", MONDAY)
    assert letter.rendition_file_id is not None
    [clock] = world.clocks(reply.key or "")
    assert (clock.kind, clock.state, clock.due_on, clock.calendar) == (
        "response_from_them",
        "running",
        "2026-11-02",
        "P123-default@1",
    )
    assert clock.warn_days == [7, 3, 1]
    # issuing the reply answered the letter it replied to
    assert world.item("P123-COR-0001").state == "Responded"
    # one thread holds both
    assert letter.thread_id is not None
    assert world.item("P123-COR-0001").thread_id == letter.thread_id


def test_a_reply_is_the_answer_and_closing_cancels_what_is_left(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        first = world.receive(received_on=MONDAY)
        world.triage(first.stream_id)
        reply = world.draft(responds_to_id=first.stream_id)
        world.issue(reply.stream_id)
        [clock] = world.clocks(reply.key or "")
    with frozen_today("2026-10-23"):
        incoming = world.receive("Re: Reply: revised programme", received_on="2026-10-23")
        world.respond(reply.stream_id, incoming.stream_id)
        assert world.clock(clock.id).state == "met"
        world.triage(incoming.stream_id, response_required=False)
        world.close(incoming.stream_id)
    assert world.item(incoming.key or "").state == "Closed"
    with pytest.raises(ItemStateError):
        with frozen_today("2026-10-24"):
            world.update(incoming.stream_id, body="late edit")


def test_a_hidden_item_is_not_found_by_the_commands_that_name_it(world: CorrWorld) -> None:
    from tl_core import confidentiality as cf

    plain = cf.Viewer(actor="user:ann", level=0, account="user:ann")
    with frozen_today(MONDAY):
        secret = world.receive("Commercial terms")
        with cf.use_viewer(cf.Viewer(actor="user:ctl", level=1, account="user:ctl")):
            world.set_class(secret.stream_id, "restricted")
        with cf.use_viewer(plain):
            for act in (
                lambda: world.update(secret.stream_id, body="x"),
                lambda: world.triage(secret.stream_id),
                lambda: world.draft(responds_to_id=secret.stream_id),
                lambda: world.void(secret.stream_id),
                lambda: world.close(secret.stream_id),
                lambda: world.assign(secret.stream_id),
            ):
                with pytest.raises(RecordNotFoundError):
                    act()
