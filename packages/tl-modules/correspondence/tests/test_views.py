"""The reads: the register with its sources, items, clocks, threads, parties (P1-I5-S6)."""

from __future__ import annotations

import pytest
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_mod_correspondence import views
from tl_mod_correspondence.errors import ItemNotFoundError, PartyNotFoundError, ThreadNotFoundError
from tl_mod_correspondence.testing import BASE, PROJECT, CorrWorld, frozen_today
from tl_mod_documents.handlers.transmittals import (
    CreateTransmittal,
    Recipient,
    handle_create_transmittal,
)
from tl_mod_documents.testing import DocumentsWorld

MONDAY = "2026-10-19"
CONTROLLER = cf.Viewer(actor="user:ctl", level=1, account="user:ctl")
PLAIN = cf.Viewer(actor="user:ann", level=0, account="user:ann")


def read(world: CorrWorld, fn, *args, **kw):  # type: ignore[no-untyped-def]
    with open_uow(world.db, readonly=True) as uow:
        return fn(uow.conn(), *args, **kw)


def test_the_register_lists_items_newest_first_and_filters(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        a = world.receive("First", received_on="2026-10-12")
        b = world.receive("Second", received_on="2026-10-15")
        world.triage(b.stream_id)
        c = world.draft("Third")
    lines = read(world, views.register, PROJECT)
    assert [ln.number for ln in lines] == [c.key, b.key, a.key] or [ln.number for ln in lines][
        :2
    ] == [b.key, a.key]
    assert {ln.number for ln in read(world, views.register, PROJECT, state="Received")} == {a.key}
    assert {ln.number for ln in read(world, views.register, PROJECT, direction="out")} == {c.key}
    assert {ln.number for ln in read(world, views.register, PROJECT, domain="general")} == {b.key}
    waiting = read(world, views.register, PROJECT, awaiting_response=True)
    assert {ln.number for ln in waiting} == {b.key}
    assert read(world, views.register, "project:P999") == []
    assert len(read(world, views.register, PROJECT, limit=1)) == 1


def test_the_i2_transmittal_appears_in_the_register_as_a_document_control_item(
    world: CorrWorld, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    docs = DocumentsWorld(world.db, tmp_path / "docs")
    docs.issued_document("ISO-1234")
    rev = docs.revision("ISO-1234", "A")
    with frozen_today(MONDAY):
        world.receive("A letter", received_on=MONDAY)
    with open_uow(world.db) as uow:
        handle_create_transmittal(
            uow,
            CreateTransmittal(
                **BASE,
                subject="Isometrics for construction",
                purpose="for_construction",
                recipients=[Recipient(name="Site document control", organisation=None, email=None)],
                revision_ids=[rev.id],
            ),
        )
    lines = read(world, views.register, PROJECT)
    [trn] = [ln for ln in lines if ln.kind == "transmittal"]
    assert (trn.number, trn.domain, trn.subtype, trn.direction) == (
        "P123-TRN-0001",
        "document_control",
        "transmittal",
        "out",
    )
    assert trn.subject == "Isometrics for construction"
    assert trn.counterparty == "Site document control"
    assert [ln.number for ln in read(world, views.register, PROJECT, include_sources=False)] == [
        "P123-COR-0001"
    ]
    only = read(world, views.register, PROJECT, domain="document_control")
    assert [ln.kind for ln in only] == ["transmittal"]
    assert read(world, views.register, PROJECT, domain="general", subtype="letter") == []


def test_an_item_view_holds_its_fields_clocks_and_links_by_number(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        first = world.receive("Programme")
        reply = world.draft(
            "Answer", responds_to_id=first.stream_id, domain="general", subtype="letter"
        )
        world.issue(reply.stream_id)
        view = read(world, views.item_view, PROJECT, reply.key)
    assert (view.number, view.state, view.delivery, view.domain) == (
        reply.key,
        "Issued",
        "stub",
        "general",
    )
    assert view.responds_to_number == first.key and view.thread_number == "P123-THR-0001"
    [clock] = view.clocks
    assert (clock.state, clock.effective_state, clock.days_left, clock.due_on) == (
        "running",
        "running",
        14,
        "2026-11-02",
    )
    assert view.to[0].name == "Meridian Energy"
    with pytest.raises(ItemNotFoundError):
        read(world, views.item_view, PROJECT, "P123-COR-9999")


def test_a_hidden_item_is_not_found_with_the_text_of_a_missing_one(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        secret = world.receive("Commercial terms")
        with cf.use_viewer(CONTROLLER):
            world.set_class(secret.stream_id, "restricted")
    with cf.use_viewer(PLAIN):
        with pytest.raises(ItemNotFoundError) as hidden:
            read(world, views.item_view, PROJECT, secret.key)
        with pytest.raises(ItemNotFoundError) as missing:
            read(world, views.item_view, PROJECT, "P123-COR-9999")
        assert str(hidden.value).replace(secret.key or "", "X") == str(missing.value).replace(
            "P123-COR-9999", "X"
        )
        assert read(world, views.register, PROJECT) == []
        assert read(world, views.thread_views, PROJECT) == []
        assert read(world, views.clock_views, PROJECT) == []
        with pytest.raises(ItemNotFoundError):
            read(world, views.suggestion_for_item, PROJECT, secret.key)
        with pytest.raises(ThreadNotFoundError):
            read(world, views.thread_view, PROJECT, "P123-THR-0001")
    with cf.use_viewer(CONTROLLER):
        assert [ln.number for ln in read(world, views.register, PROJECT)] == [secret.key]
        assert len(read(world, views.thread_views, PROJECT)) == 1


def test_a_privileged_item_is_read_only_by_the_accounts_named_on_it(world: CorrWorld) -> None:
    from tl_core.auth import accounts
    from tl_core.auth.password import prepare_password

    for name in ("ctl", "amy"):
        with open_uow(world.db) as uow:
            accounts.create_account(
                uow,
                username=name,
                display_name=name,
                kind="person",
                roles=["document_controller"] if name == "ctl" else ["user"],
                password=prepare_password("a-long-enough-password-1", username=name),
                by="system:test",
            )
    with frozen_today(MONDAY):
        item = world.receive("Counsel's advice")
        with cf.use_viewer(CONTROLLER):
            world.set_class(item.stream_id, "privileged", grant=["user:amy"], actor="user:ctl")
    amy = cf.Viewer(actor="user:amy", level=0, account="user:amy")
    with cf.use_viewer(amy):
        view = read(world, views.item_view, PROJECT, item.key)
        assert sorted(c.account for c in view.clearances) == ["user:amy", "user:ctl"]
    with cf.use_viewer(CONTROLLER):  # ctl is named too: the setter always is
        assert read(world, views.item_view, PROJECT, item.key).confidentiality == "privileged"
    other = cf.Viewer(actor="user:bo", level=1, account="user:bo")
    with cf.use_viewer(other), pytest.raises(ItemNotFoundError):
        read(world, views.item_view, PROJECT, item.key)
    with cf.use_viewer(cf.LOWEST), pytest.raises(ItemNotFoundError):
        read(world, views.item_view, PROJECT, item.key)


def test_clock_views_count_days_left_overdue_and_paused(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        item = world.forge_item()
        running = world.start_clock(item).stream_id  # due 2 Nov
        paused = world.start_clock(item, label="Paused one").stream_id
        world.pause(paused)
        working = world.start_clock(
            item, label="Working", duration_days=5, day_type="working", warn_days=[]
        ).stream_id
    on = {"2026-10-26": 7, "2026-11-02": 0, "2026-11-04": -2}
    for day, left in on.items():
        with frozen_today(day):
            got = {v.id: v for v in read(world, views.clock_views, PROJECT)}
        assert got[running].days_left == left
    with frozen_today("2026-11-04"):
        got = {v.id: v for v in read(world, views.clock_views, PROJECT)}
        assert got[running].effective_state == "expired" and got[running].state == "running"
        assert got[paused].state == "paused" and got[paused].days_left == 14
        assert got[working].due_on == "2026-10-26"
        late = got[working].days_left
        assert late is not None
        assert late < 0
        overdue = read(world, views.clock_views, PROJECT, overdue_only=True)
        assert {v.id for v in overdue} == {running, working}
        one = read(world, views.clock_view_by_id, PROJECT, running)
        assert one.item_number == "P123-COR-0001"
    assert [v.id for v in read(world, views.clock_views, PROJECT, due_to="2026-10-27")] == [working]


def test_a_clock_whose_calendar_is_gone_is_shown_with_its_stored_figures_and_the_problem(
    world: CorrWorld,
) -> None:
    with frozen_today(MONDAY):
        item = world.forge_item()
        cid = world.start_clock(item).stream_id
    world.rows("SELECT 1")  # (the calendar of a clock cannot be removed; damage the row instead)
    with open_uow(world.db) as uow:
        from sqlalchemy import text

        uow.conn().execute(
            text("UPDATE cur_correspondence_response_clock SET calendar = 'gone@1' WHERE id = :i"),
            {"i": cid},
        )
    with frozen_today(MONDAY):
        [view] = read(world, views.clock_views, PROJECT)
    assert view.problem is not None and view.days_left is None and view.due_on == "2026-11-02"


def test_threads_parties_clauses_and_domains(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        a = world.receive("Programme")
        world.receive("RE: Programme")
    thread = read(world, views.thread_view, PROJECT, "P123-THR-0001")
    assert thread.item_count == 2 and [ln.number for ln in thread.items] == [a.key, "P123-COR-0002"]
    assert [t.number for t in read(world, views.thread_views, PROJECT)] == ["P123-THR-0001"]
    party = world.party(contacts=[{"name": "Pat"}])
    got = read(world, views.party_view, PROJECT, "MER")
    assert got.id == party.stream_id and [c.name for c in got.contacts] == ["Pat"]
    with pytest.raises(PartyNotFoundError):
        read(world, views.party_view, PROJECT, "NOPE")
    world.clause()
    assert [c.clause_number for c in read(world, views.clause_views, PROJECT)] == ["20.1"]
    domains = views.domain_views(PROJECT)
    assert [d.code for d in domains] == ["document_control", "general"]
    general = domains[1]
    assert general.item_source is None and "general-letter" in general.templates
    [clock] = [c for s in general.subtypes if s.code == "letter" for c in s.clocks]
    assert (clock.trigger, clock.duration_days, clock.warn_days) == ("issue", 14, [7, 3, 1])


def test_the_suggestion_views(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.receive("Transmittal 7 for review", body="Drawings and revision list.")
    got = read(world, views.suggestion_for_item, PROJECT, made.key)
    assert (got.domain, got.subtype) == ("document_control", "transmittal")
    again = views.suggestion_for_text(PROJECT, "Minutes of the meeting")
    assert again.subtype == "minutes" and again.domain == "general"
