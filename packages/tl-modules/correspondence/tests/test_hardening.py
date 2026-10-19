"""Cases the provided tests of the first wave leave open (found by the mutation run, P1-I5).

Each test names the rule it pins. They run against the merged code of T07a, T07c and T07f.
"""

from __future__ import annotations

import pytest
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.ledger.types import ConcurrencyError
from tl_core.services.errors import RecordNotFoundError
from tl_mod_correspondence import catalog, registry
from tl_mod_correspondence import domains as dm
from tl_mod_correspondence.errors import (
    ClauseNotFoundError,
    ClearanceError,
    InvalidClauseError,
    InvalidItemError,
    LetterRenderError,
)
from tl_mod_correspondence.handlers.confidentiality import GrantClearance, handle_grant_clearance
from tl_mod_correspondence.handlers.models import Recipient
from tl_mod_correspondence.testing import BASE, PROJECT, CorrWorld, frozen_today
from tl_mod_documents.handlers.documents import RegisterDocument, handle_register_document

MONDAY = "2026-10-19"


def stored(world: CorrWorld, file_id: str) -> bytes:
    assert world.files is not None
    with open_uow(world.db, readonly=True) as uow:
        opened = world.files.open_file(uow, PROJECT, file_id, actor="user:u")
        try:
            return opened.data.read()
        finally:
            opened.data.close()


def test_updating_the_recipients_checks_the_parties_like_receiving_does(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.receive("Programme")
        with pytest.raises(InvalidItemError, match="not a party"):
            world.update(made.stream_id, to=[Recipient(party_id="01J000000000000000000000")])
        with pytest.raises(InvalidItemError, match="not a party"):
            world.update(made.stream_id, cc=[Recipient(party_id="01J000000000000000000000")])
        party = world.party()
        world.update(made.stream_id, to=[Recipient(party_id=party.stream_id)])
    assert world.item(made.key or "").to[0]["party_id"] == party.stream_id


def test_issuing_with_a_stale_version_is_a_conflict(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        draft = world.draft(domain="general", subtype="letter")
        with pytest.raises(ConcurrencyError):
            world.issue(draft.stream_id, expected_version=1)
        assert world.item(draft.key or "").state == "Draft"
        world.issue(draft.stream_id, expected_version=world.item(draft.key or "").version)


def test_the_letter_carries_the_issue_day_not_the_day_an_earlier_text_was_received(
    world: CorrWorld,
) -> None:
    with frozen_today(MONDAY):
        draft = world.draft(domain="general", subtype="letter")
        world.update(draft.stream_id, received_on="2026-09-01")
        world.issue(draft.stream_id, issued_on="2026-10-12", date_reason="posted earlier")
    item = world.item(draft.key or "")
    data = stored(world, item.rendition_file_id or "")
    assert b"2026-10-12" in data or b"12 October 2026" in data
    assert b"2026-10-19" not in data and b"19 October 2026" not in data


def test_a_letter_too_long_to_print_is_a_render_error_and_the_draft_stays(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        draft = world.draft(domain="general", subtype="letter", body="line\n" * 3000)
        with pytest.raises(LetterRenderError, match="pages"):
            world.issue(draft.stream_id)
    assert world.item(draft.key or "").state == "Draft"


def _two_templates() -> dm.DomainSet:
    base = catalog.domain_set()
    changed: list[dm.DomainDefinition] = []
    for definition in base.all():
        if definition.code == "general":
            first = next(t for t in definition.templates if t.subtype == "letter")
            second = first.model_copy(update={"code": "general-letter-b", "header": "SECOND"})
            definition = definition.model_copy(
                update={"templates": (first, second, *definition.templates[1:])}
            )
        changed.append(definition)
    return dm.DomainSet(changed)


def test_with_two_templates_for_a_subtype_the_first_is_used(world: CorrWorld) -> None:
    with frozen_today(MONDAY), catalog.use_domains(_two_templates()):
        draft = world.draft(domain="general", subtype="letter")
        world.issue(draft.stream_id)
        chosen = world.draft(domain="general", subtype="letter")
        world.issue(chosen.stream_id, template="general-letter-b")
    issued = [p for n, p in world.events_of(draft.stream_id) if n == "Correspondence.Issued"]
    assert issued[0]["template"] == "general-letter"
    other = [p for n, p in world.events_of(chosen.stream_id) if n == "Correspondence.Issued"]
    assert other[0]["template"] == "general-letter-b"


def test_a_contact_added_after_one_ended_takes_a_new_position(world: CorrWorld) -> None:
    party = world.party(contacts=[{"name": "Ann", "email": "ann@meridian.example"}])
    world.end_contact(party.stream_id, 1)
    world.add_contact(party.stream_id, name="Bob", email="bob@meridian.example")
    world.add_contact(party.stream_id, name="Cy", email="cy@meridian.example")
    with open_uow(world.db, readonly=True) as uow:
        everyone = registry.contacts_of(uow.conn(), party.stream_id, include_ended=True)
    assert [(c.position, c.name) for c in everyone] == [(1, "Ann"), (2, "Bob"), (3, "Cy")]


def test_a_clause_of_another_project_is_not_found_to_retire(world: CorrWorld) -> None:
    foreign = world.clause("CT-9", "1", scope="project:P999")
    with pytest.raises(ClauseNotFoundError):
        world.retire_clause(foreign.stream_id)  # this world's scope is P123
    with open_uow(world.db, readonly=True) as uow:
        row = registry.get_clause(uow.conn(), foreign.stream_id)
    assert row is not None and row.is_active


def test_a_contract_document_of_another_project_is_refused(world: CorrWorld) -> None:
    with open_uow(world.db) as uow:
        document = handle_register_document(
            uow,
            RegisterDocument(
                **{**BASE, "scope": "project:P999"},
                number="CON-0001",
                title="Contract",
                doc_type="ISO",
                discipline="PIP",
            ),
        )
    with pytest.raises(InvalidClauseError, match="not a document"):
        world.clause("CT-1", "30", contract_document_id=document.stream_id)
    assert PROJECT == "project:P123"


# --- ADR-0016 section 2: the lock-out clause ----------------------------------------------------

CTL = cf.Viewer(actor="user:ctl", level=1, account="user:ctl")
ANN = cf.Viewer(actor="user:ann", level=0, account="user:ann")


def _privileged(world: CorrWorld) -> str:
    """An item only user:boss (a person who is about to leave) is named on."""
    with frozen_today(MONDAY):
        made = world.receive("Counsel's advice")
    with cf.use_viewer(CTL):
        world.set_class(made.stream_id, "privileged", grant=["user:boss"])
    return made.stream_id


def _people(world: CorrWorld) -> None:
    from tl_core.auth import accounts
    from tl_core.auth.password import prepare_password

    with open_uow(world.db) as uow:
        for name in ("u", "boss", "ann", "ctl", "newcomer"):
            accounts.create_account(
                uow, username=name, display_name=name, kind="person", roles=["user"],
                password=prepare_password("correct horse battery"), by="svc:test",
            )  # fmt: skip


def test_a_controller_not_named_on_a_privileged_item_can_still_name_a_reader(
    world: CorrWorld,
) -> None:
    _people(world)
    item = _privileged(world)
    with cf.use_viewer(cf.Viewer(actor="user:other", level=1, account="user:other")):
        # the item does not exist for this controller...
        with open_uow(world.db, readonly=True) as uow:
            assert registry.get_item(uow.conn(), item) is None
        # ...but the clearance commands work by id
        world.grant(item, "user:newcomer")
        world.withdraw(item, "user:boss")
    with cf.use_viewer(cf.Viewer(actor="user:newcomer", level=0, account="user:newcomer")):
        with open_uow(world.db, readonly=True) as uow:
            found = registry.get_item(uow.conn(), item)
        assert found is not None and found.subject == "Counsel's advice"


def test_the_lock_out_path_is_for_a_controller_and_checks_the_scope_and_the_class(
    world: CorrWorld,
) -> None:
    _people(world)
    item = _privileged(world)
    with cf.use_viewer(ANN):  # a plain viewer gets what it got before: no such item
        with pytest.raises(RecordNotFoundError):
            world.grant(item, "user:newcomer")
    with cf.use_viewer(CTL):
        with pytest.raises(RecordNotFoundError):
            world.grant("01J000000000000000000000", "user:newcomer")  # unknown
        with pytest.raises(RecordNotFoundError):
            world.run(GrantClearance, handle_grant_clearance, stream_id=item,
                      account="user:newcomer", reason="x", scope="project:P999")  # fmt: skip
        plain = world.receive("An ordinary letter").stream_id
        with pytest.raises(ClearanceError, match="not privileged"):
            world.grant(plain, "user:newcomer")
    # an unnamed controller cannot change the class: that needs to read the item
    with cf.use_viewer(cf.Viewer(actor="user:other", level=1, account="user:other")):
        with pytest.raises(RecordNotFoundError):
            world.set_class(item, "internal")


def test_a_post_that_tags_a_hidden_item_cannot_be_reacted_to_edited_or_retracted_by_a_stranger(
    world: CorrWorld,
) -> None:
    from tl_core.services.errors import PostNotFoundError
    from tl_core.services.feed import EditPost, PostToFeed, handle_edit_post, handle_post
    from tl_core.services.feed_actions import (
        ReactToPost,
        RetractPost,
        handle_react_to_post,
        handle_retract_post,
    )

    with frozen_today(MONDAY):
        secret = world.receive("Commercial terms")
    with cf.use_viewer(CTL):
        world.set_class(secret.stream_id, "restricted")
    base = {"actor": "user:ctl", "source": "test", "scope": PROJECT}
    with cf.use_viewer(CTL), open_uow(world.db) as uow:
        post = handle_post(uow, PostToFeed(**base, body=f"see #{secret.key} for terms")).stream_id
    plain = {"actor": "user:ann", "source": "test", "scope": PROJECT}
    attempts = [
        (handle_react_to_post, ReactToPost(**plain, post_id=post, reaction="ack")),
        (handle_edit_post, EditPost(**plain, post_id=post, body="rewritten")),
        (handle_retract_post, RetractPost(**plain, post_id=post, reason="x")),
    ]
    for handler, command in attempts:
        with cf.use_viewer(ANN), open_uow(world.db) as uow:
            with pytest.raises(PostNotFoundError):  # not "forbidden: written by user:ctl"
                handler(uow, command)  # type: ignore[operator]
    with cf.use_viewer(CTL), open_uow(world.db) as uow:  # one who may read the item can react
        assert handle_react_to_post(uow, ReactToPost(**base, post_id=post, reaction="ack")).events


# --- the sweep reads every clock, as the system, and says what it could not judge ---------------


def test_the_sweep_expires_the_clock_of_an_item_the_runner_may_not_read(world: CorrWorld) -> None:
    _people(world)
    item = _privileged(world)
    boss = cf.Viewer(actor="user:boss", level=0, account="user:boss")
    with cf.use_viewer(boss), frozen_today(MONDAY):
        clock = world.start_clock(item).stream_id  # due 2 Nov
    with cf.use_viewer(ANN), frozen_today("2026-11-10"):  # a runner with the lowest clearance
        done = world.sweep()
    assert [e.event_type for e in done.events] == ["ResponseClock.Expired"]
    with cf.system_view():
        assert world.clock(clock).state == "expired"


def test_the_sweep_pages_through_more_clocks_than_a_page_and_reports_the_ones_it_skipped(
    world: CorrWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tl_mod_correspondence import catalog
    from tl_mod_correspondence.errors import CalendarUnavailableError
    from tl_mod_correspondence.handlers import clocks as handlers_clocks

    monkeypatch.setattr(handlers_clocks, "SWEEP_PAGE", 2)
    with frozen_today(MONDAY):
        item = world.forge_item()
        ids = [world.start_clock(item, label=f"Clock {n}").stream_id for n in range(5)]
    real = catalog.calendar_for
    broken = ids[3]

    def calendar_for(ref: str, scope: str):  # type: ignore[no-untyped-def]
        if scope == PROJECT and world.clock(broken).calendar == ref and calling_for[0] == broken:
            raise CalendarUnavailableError("gone")
        return real(ref, scope)

    calling_for = [""]
    original_figures = handlers_clocks.figures_of

    def figures_of(uow, clock):  # type: ignore[no-untyped-def]
        calling_for[0] = clock.id
        return original_figures(uow, clock)

    monkeypatch.setattr(handlers_clocks, "figures_of", figures_of)
    monkeypatch.setattr(catalog, "calendar_for", calendar_for)
    with open_uow(world.db) as uow, frozen_today("2026-11-10"):
        events, skipped = handlers_clocks.sweep_clocks(uow, handlers_clocks.SweepClocks(**BASE))
    assert len(events) == 4 and skipped == [broken]


# --- a contractual time bar is moved or ended by a controller ------------------------------------


def test_restarting_or_cancelling_a_time_bar_is_a_controllers_act(world: CorrWorld) -> None:
    from tl_core.auth.errors import ForbiddenError

    with frozen_today(MONDAY):
        item = world.forge_item()
        bar = world.start_clock(item, kind="time_bar", label="Notice of claim").stream_id
        courtesy = world.start_clock(item, label="Reply expected").stream_id
        # a plain person may restart and cancel an ordinary clock
        world.restart(courtesy, reason="they asked for a week")
        world.cancel(courtesy, reason="no longer needed")
        for act in (world.restart, world.cancel):
            with cf.use_viewer(ANN), pytest.raises(ForbiddenError, match="time bar"):
                act(bar, reason="please")
        # pausing it is still anyone's; a controller may restart and cancel it
        world.pause(bar)
        world.resume(bar)
        with cf.use_viewer(CTL):
            world.restart(bar, reason="the notice was served again")
            world.cancel(bar, reason="withdrawn by the contractor")
    with cf.system_view():
        assert world.clock(bar).state == "cancelled"
