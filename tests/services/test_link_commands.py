"""Link command handlers against a real SQLite ledger (P0-I3-T02; brief 7.1, 7.3)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from tl_adapters.sqlite.uow import create_schema, open_uow, rebuild_projections
from tl_core.ledger import ConcurrencyError, Event
from tl_core.services.commands import Command, CommandResult, CreateRecord
from tl_core.services.errors import (
    CrossScopeLinkError,
    DuplicateLinkError,
    InvalidLinkTransitionError,
    LinkNotFoundError,
    NoChangesError,
    RecordNotFoundError,
    RecordVoidedError,
    SelfLinkError,
    SuggestionDeclinedError,
    UnknownRelationError,
)
from tl_core.services.links import (
    AcceptLink,
    AddLink,
    DeclineLink,
    FlagLink,
    MarkPinsStale,
    RepinLink,
    RetractLink,
    SuggestLink,
    VerifyLink,
    handle_accept_link,
    handle_add_link,
    handle_decline_link,
    handle_flag_link,
    handle_mark_pins_stale,
    handle_repin_link,
    handle_retract_link,
    handle_suggest_link,
    handle_verify_link,
)
from tl_core.services.records import handle_create_record
from tl_core.uow import UnitOfWork

P1 = "project:P123"
Handler = Callable[[UnitOfWork, Any], CommandResult]


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "tl.db"
    create_schema(path)
    return path


def run(db: Path, handler: Handler, cmd: Command) -> CommandResult:
    with open_uow(db) as uow:
        return handler(uow, cmd)


def record(db: Path, key: str, scope: str = P1) -> str:
    cmd = CreateRecord(
        actor="u", source="t", scope=scope, record_type="core.Record", title=key, key=key
    )
    return run(db, handle_create_record, cmd).stream_id


def common(**kw: Any) -> dict[str, Any]:
    return {"actor": "user:u-1", "source": "test", "scope": P1, **kw}


def add(db: Path, from_id: str, to_id: str, **kw: Any) -> str:
    cmd = AddLink(**common(from_id=from_id, to_id=to_id, **kw))
    return run(db, handle_add_link, cmd).stream_id


def suggest(db: Path, from_id: str, to_id: str, **kw: Any) -> str:
    cmd = SuggestLink(**common(from_id=from_id, to_id=to_id, **kw))
    return run(db, handle_suggest_link, cmd).stream_id


def row(db: Path, link_id: str) -> dict[str, Any]:
    with open_uow(db, readonly=True) as uow:
        found = uow.conn().execute(
            text("SELECT * FROM cur_links WHERE link_id = :i"), {"i": link_id}
        )
        return dict(found.mappings().one())


def events(db: Path) -> list[Event]:
    with open_uow(db, readonly=True) as uow:
        return uow.ledger.read_after(0, limit=10_000)


def count_events(db: Path) -> int:
    return len(events(db))


@pytest.fixture
def pair(db: Path) -> tuple[str, str]:
    return record(db, "A"), record(db, "B")


# --- AddLink -----------------------------------------------------------------------------------


def test_add_creates_an_active_link_with_one_event(db: Path, pair: tuple[str, str]) -> None:
    a, b = pair
    result = run(
        db,
        handle_add_link,
        AddLink(**common(from_id=a, to_id=b, relation="requires", pin="C", note="why")),
    )
    assert result.key is None
    assert result.version == 1
    (event,) = result.events
    assert event.event_type == "Link.Added"
    assert event.stream_id == result.stream_id
    assert event.stream_type == "core.Link"
    assert event.scope == P1
    assert event.actor == "user:u-1"
    assert event.source == "test"
    assert event.payload == {
        "link_id": result.stream_id,
        "from_ref": a,
        "to_ref": b,
        "relation": "requires",
        "pin": "C",
        "source": "manual",
        "note": "why",
    }
    found = row(db, result.stream_id)
    assert (found["status"], found["from_id"], found["to_id"]) == ("active", a, b)
    assert (found["relation"], found["pin"], found["note"], found["source"]) == (
        "requires",
        "C",
        "why",
        "manual",
    )


def test_add_without_a_relation_uses_the_default(db: Path, pair: tuple[str, str]) -> None:
    link_id = add(db, *pair)
    assert row(db, link_id)["relation"] == "references"


def test_add_records_how_the_link_arose(db: Path, pair: tuple[str, str]) -> None:
    link_id = add(db, *pair, link_source="tray")
    assert row(db, link_id)["source"] == "tray"
    with pytest.raises(ValidationError):
        AddLink(**common(from_id="a", to_id="b", link_source="telepathy"))


def test_add_updates_the_counts_of_both_records(db: Path, pair: tuple[str, str]) -> None:
    a, b = pair
    add(db, a, b)
    with open_uow(db, readonly=True) as uow:
        counts = {
            r.record_id: (r.active_out, r.active_in)
            for r in uow.conn().execute(text("SELECT * FROM cur_link_counts"))
        }
    assert counts == {a: (1, 0), b: (0, 1)}


def test_add_refuses_an_unknown_relation(db: Path, pair: tuple[str, str]) -> None:
    with pytest.raises(UnknownRelationError, match="unknown relation 'friends_with'"):
        add(db, *pair, relation="friends_with")
    assert count_events(db) == 2  # only the two records


def test_add_refuses_an_inverse_relation_code(db: Path, pair: tuple[str, str]) -> None:
    with pytest.raises(UnknownRelationError, match="swapped"):
        add(db, *pair, relation="referenced_by")


def test_add_refuses_a_missing_or_foreign_from_record(db: Path, pair: tuple[str, str]) -> None:
    a, b = pair
    other = record(db, "O", scope="project:OTHER")
    for from_id in ("NOPE", other):
        with pytest.raises(RecordNotFoundError):
            add(db, from_id, b)
    with pytest.raises(RecordNotFoundError):
        add(db, a, "NOPE")


def test_add_refuses_a_link_to_itself(db: Path, pair: tuple[str, str]) -> None:
    with pytest.raises(SelfLinkError):
        add(db, pair[0], pair[0])


def test_add_refuses_a_voided_end(db: Path, pair: tuple[str, str]) -> None:
    a, b = pair
    with open_uow(db) as uow:
        uow.conn().execute(text("UPDATE cur_core_record SET voided = 1 WHERE id = :i"), {"i": b})
    with pytest.raises(RecordVoidedError):
        add(db, a, b)
    with pytest.raises(RecordVoidedError):
        add(db, b, a)


def test_add_allows_a_company_target_but_not_another_project(db: Path) -> None:
    a = record(db, "A")
    company = record(db, "C", scope="company")
    elsewhere = record(db, "E", scope="project:OTHER")
    link_id = add(db, a, company)
    assert row(db, link_id)["scope"] == P1  # the scope of the from record
    with pytest.raises(CrossScopeLinkError):
        add(db, a, elsewhere)


def test_add_refuses_a_live_duplicate_whatever_its_status(db: Path, pair: tuple[str, str]) -> None:
    a, b = pair
    first = add(db, a, b, relation="requires")
    with pytest.raises(DuplicateLinkError, match="requires"):
        add(db, a, b, relation="requires")
    run(db, handle_flag_link, FlagLink(**common(link_id=first, status="stale", reason="r")))
    with pytest.raises(DuplicateLinkError, match="stale"):
        add(db, a, b, relation="requires")
    suggested = suggest(db, a, b, relation="blocks")
    with pytest.raises(DuplicateLinkError, match="suggested"):
        add(db, a, b, relation="blocks")
    assert suggested


def test_add_allows_other_relations_the_reverse_direction_and_a_re_add_after_retraction(
    db: Path, pair: tuple[str, str]
) -> None:
    a, b = pair
    first = add(db, a, b, relation="requires")
    add(db, a, b, relation="blocks")
    add(db, b, a, relation="requires")
    run(db, handle_retract_link, RetractLink(**common(link_id=first, reason="mistake")))
    again = add(db, a, b, relation="requires")
    assert again != first
    assert row(db, first)["status"] == "retracted"
    assert row(db, again)["status"] == "active"


def test_add_shares_a_given_correlation_id(db: Path, pair: tuple[str, str]) -> None:
    result = run(
        db,
        handle_add_link,
        AddLink(**common(from_id=pair[0], to_id=pair[1], correlation_id="CORR-1")),
    )
    assert result.events[0].correlation_id == "CORR-1"


# --- SuggestLink -------------------------------------------------------------------------------


def test_suggest_creates_a_suggested_link_with_confidence(db: Path, pair: tuple[str, str]) -> None:
    result = run(
        db,
        handle_suggest_link,
        SuggestLink(**common(from_id=pair[0], to_id=pair[1], confidence=0.82, note="in the text")),
    )
    (event,) = result.events
    assert event.event_type == "Link.Suggested"
    assert event.payload["confidence"] == 0.82
    assert event.payload["source"] == "key_detected"
    found = row(db, result.stream_id)
    assert (found["status"], found["source"], found["confidence"]) == (
        "suggested",
        "key_detected",
        0.82,
    )


def test_suggest_rejects_a_confidence_outside_zero_to_one() -> None:
    for bad in (-0.1, 1.5):
        with pytest.raises(ValidationError):
            SuggestLink(**common(from_id="a", to_id="b", confidence=bad))


def test_a_declined_suggestion_is_remembered(db: Path, pair: tuple[str, str]) -> None:
    a, b = pair
    link_id = suggest(db, a, b)
    run(db, handle_decline_link, DeclineLink(**common(link_id=link_id, reason="unrelated")))
    before = count_events(db)
    with pytest.raises(SuggestionDeclinedError):
        suggest(db, a, b)
    assert count_events(db) == before
    other_relation = suggest(db, a, b, relation="blocks")  # a different relation is a new question
    assert row(db, other_relation)["status"] == "suggested"
    manual = add(db, a, b)  # a person may still link them by hand
    assert row(db, manual)["status"] == "active"


# --- accept, decline ---------------------------------------------------------------------------


def test_accept_activates_a_suggestion(db: Path, pair: tuple[str, str]) -> None:
    link_id = suggest(db, *pair)
    result = run(db, handle_accept_link, AcceptLink(**common(link_id=link_id, note="checked")))
    assert result.stream_id == link_id
    assert result.version == 2
    (event,) = result.events
    assert event.event_type == "Link.Accepted"
    assert event.payload == {"link_id": link_id, "note": "checked"}
    assert (row(db, link_id)["status"], row(db, link_id)["note"]) == ("active", "checked")


def test_accept_needs_a_suggestion(db: Path, pair: tuple[str, str]) -> None:
    link_id = add(db, *pair)
    with pytest.raises(InvalidLinkTransitionError, match="Link.Accepted"):
        run(db, handle_accept_link, AcceptLink(**common(link_id=link_id)))
    assert row(db, link_id)["version"] == 1


def test_decline_retracts_and_remembers(db: Path, pair: tuple[str, str]) -> None:
    link_id = suggest(db, *pair)
    result = run(db, handle_decline_link, DeclineLink(**common(link_id=link_id, reason="no")))
    assert result.events[0].event_type == "Link.Declined"
    found = row(db, link_id)
    assert (found["status"], found["declined"], found["reason"]) == ("retracted", 1, "no")


def test_decline_needs_a_suggestion(db: Path, pair: tuple[str, str]) -> None:
    link_id = add(db, *pair)
    with pytest.raises(InvalidLinkTransitionError):
        run(db, handle_decline_link, DeclineLink(**common(link_id=link_id)))


# --- repin, verify, flag, retract ----------------------------------------------------------------


def test_repin_sets_the_pin(db: Path, pair: tuple[str, str]) -> None:
    link_id = add(db, *pair, pin="B")
    result = run(db, handle_repin_link, RepinLink(**common(link_id=link_id, pin="C")))
    assert result.events[0].event_type == "Link.Repinned"
    assert result.events[0].payload == {"link_id": link_id, "pin": "C"}
    assert row(db, link_id)["pin"] == "C"
    run(db, handle_repin_link, RepinLink(**common(link_id=link_id, pin=None)))
    assert row(db, link_id)["pin"] is None


def test_repin_to_the_same_pin_of_an_active_link_changes_nothing(
    db: Path, pair: tuple[str, str]
) -> None:
    link_id = add(db, *pair, pin="B")
    with pytest.raises(NoChangesError):
        run(db, handle_repin_link, RepinLink(**common(link_id=link_id, pin="B")))
    assert row(db, link_id)["version"] == 1


def test_repin_restores_a_stale_link_even_to_the_same_pin(db: Path, pair: tuple[str, str]) -> None:
    link_id = add(db, *pair, pin="B")
    run(db, handle_flag_link, FlagLink(**common(link_id=link_id, status="stale", reason="rev C")))
    run(db, handle_repin_link, RepinLink(**common(link_id=link_id, pin="B")))
    assert row(db, link_id)["status"] == "active"


def test_repin_of_a_broken_link_is_refused(db: Path, pair: tuple[str, str]) -> None:
    link_id = add(db, *pair)
    run(db, handle_flag_link, FlagLink(**common(link_id=link_id, status="broken", reason="gone")))
    with pytest.raises(InvalidLinkTransitionError):
        run(db, handle_repin_link, RepinLink(**common(link_id=link_id, pin="C")))


def test_verify_records_who(db: Path, pair: tuple[str, str]) -> None:
    link_id = add(db, *pair)
    result = run(
        db,
        handle_verify_link,
        VerifyLink(**common(actor="user:qa", link_id=link_id, note="covers all welds")),
    )
    assert result.events[0].event_type == "Link.Verified"
    assert result.events[0].payload == {"link_id": link_id, "note": "covers all welds"}
    found = row(db, link_id)
    assert (found["status"], found["verified_by"]) == ("active", "user:qa")
    assert found["verified_at"] is not None


def test_verify_needs_an_active_link(db: Path, pair: tuple[str, str]) -> None:
    link_id = suggest(db, *pair)
    with pytest.raises(InvalidLinkTransitionError):
        run(db, handle_verify_link, VerifyLink(**common(link_id=link_id)))


def test_flag_sets_stale_or_broken_with_a_reason(db: Path, pair: tuple[str, str]) -> None:
    link_id = add(db, *pair)
    result = run(
        db, handle_flag_link, FlagLink(**common(link_id=link_id, status="stale", reason="rev C"))
    )
    assert result.events[0].event_type == "Link.Flagged"
    assert result.events[0].payload == {"link_id": link_id, "status": "stale", "reason": "rev C"}
    assert (row(db, link_id)["status"], row(db, link_id)["reason"]) == ("stale", "rev C")
    run(db, handle_flag_link, FlagLink(**common(link_id=link_id, status="broken", reason="gone")))
    assert row(db, link_id)["status"] == "broken"


def test_flag_to_the_current_status_or_a_suggestion_is_refused(
    db: Path, pair: tuple[str, str]
) -> None:
    link_id = add(db, *pair)
    run(db, handle_flag_link, FlagLink(**common(link_id=link_id, status="stale", reason="r")))
    with pytest.raises(InvalidLinkTransitionError, match="already stale"):
        run(db, handle_flag_link, FlagLink(**common(link_id=link_id, status="stale", reason="r")))
    suggestion = suggest(db, pair[0], pair[1], relation="blocks")
    with pytest.raises(InvalidLinkTransitionError):
        run(
            db, handle_flag_link, FlagLink(**common(link_id=suggestion, status="stale", reason="r"))
        )


def test_flag_and_retract_need_a_reason_and_a_valid_status() -> None:
    with pytest.raises(ValidationError):
        FlagLink(**common(link_id="x", status="stale", reason="  "))
    with pytest.raises(ValidationError):
        FlagLink(**common(link_id="x", status="retracted", reason="r"))
    with pytest.raises(ValidationError):
        RetractLink(**common(link_id="x", reason=""))


def test_retract_ends_the_link_but_keeps_the_row(db: Path, pair: tuple[str, str]) -> None:
    link_id = add(db, *pair)
    result = run(db, handle_retract_link, RetractLink(**common(link_id=link_id, reason="oops")))
    assert result.events[0].event_type == "Link.Retracted"
    found = row(db, link_id)
    assert (found["status"], found["reason"], found["declined"]) == ("retracted", "oops", 0)
    with pytest.raises(InvalidLinkTransitionError):
        run(db, handle_retract_link, RetractLink(**common(link_id=link_id, reason="again")))
    with pytest.raises(InvalidLinkTransitionError):
        run(db, handle_verify_link, VerifyLink(**common(link_id=link_id)))
    with open_uow(db, readonly=True) as uow:
        total = uow.conn().execute(text("SELECT COUNT(*) FROM cur_links")).scalar_one()
    assert total == 1


def test_a_suggestion_can_be_retracted(db: Path, pair: tuple[str, str]) -> None:
    link_id = suggest(db, *pair)
    run(db, handle_retract_link, RetractLink(**common(link_id=link_id, reason="withdrawn")))
    assert row(db, link_id)["status"] == "retracted"
    assert row(db, link_id)["declined"] == 0


# --- existing-link lookups -----------------------------------------------------------------------


def test_an_unknown_link_or_a_link_of_another_scope_is_not_found(
    db: Path, pair: tuple[str, str]
) -> None:
    link_id = add(db, *pair)
    with pytest.raises(LinkNotFoundError):
        run(db, handle_verify_link, VerifyLink(**common(link_id="NOPE")))
    with pytest.raises(LinkNotFoundError):
        run(db, handle_verify_link, VerifyLink(**common(link_id=link_id, scope="project:OTHER")))


def test_expected_version_is_checked_when_given(db: Path, pair: tuple[str, str]) -> None:
    link_id = add(db, *pair)
    with pytest.raises(ConcurrencyError):
        run(db, handle_verify_link, VerifyLink(**common(link_id=link_id, expected_version=5)))
    result = run(db, handle_verify_link, VerifyLink(**common(link_id=link_id, expected_version=1)))
    assert result.version == 2
    result = run(db, handle_verify_link, VerifyLink(**common(link_id=link_id)))  # None: current
    assert result.version == 3


# --- MarkPinsStale -------------------------------------------------------------------------------


def test_mark_pins_stale_flags_links_pinned_to_an_older_revision(db: Path) -> None:
    doc, a, b, c, d = (record(db, k) for k in ("DOC", "A", "B", "C", "D"))
    old = add(db, a, doc, pin="B")
    older = add(db, b, doc, pin="A")
    current = add(db, c, doc, pin="C")
    floating = add(db, d, doc)
    elsewhere = add(db, doc, a, relation="requires", pin="A")  # points away from the document
    result = run(
        db,
        handle_mark_pins_stale,
        MarkPinsStale(**common(record_id=doc, current_pin="C", correlation_id="REV-C")),
    )
    assert result.stream_id == doc
    assert result.key == "DOC"
    assert [e.event_type for e in result.events] == ["Link.Flagged", "Link.Flagged"]
    assert [e.stream_id for e in result.events] == [old, older]  # creation order
    assert {e.correlation_id for e in result.events} == {"REV-C"}
    assert result.events[0].payload == {
        "link_id": old,
        "status": "stale",
        "reason": "revision C issued",
    }
    assert row(db, old)["status"] == row(db, older)["status"] == "stale"
    for untouched in (current, floating, elsewhere):
        assert row(db, untouched)["status"] == "active"


def test_mark_pins_stale_skips_links_that_are_not_active(db: Path) -> None:
    doc, a = record(db, "DOC"), record(db, "A")
    link_id = add(db, a, doc, pin="A")
    run(db, handle_flag_link, FlagLink(**common(link_id=link_id, status="broken", reason="r")))
    with pytest.raises(NoChangesError):
        run(db, handle_mark_pins_stale, MarkPinsStale(**common(record_id=doc, current_pin="B")))


def test_mark_pins_stale_with_nothing_to_flag_changes_nothing(db: Path) -> None:
    doc = record(db, "DOC")
    before = count_events(db)
    with pytest.raises(NoChangesError):
        run(db, handle_mark_pins_stale, MarkPinsStale(**common(record_id=doc, current_pin="B")))
    assert count_events(db) == before


def test_mark_pins_stale_needs_a_record_in_the_scope(db: Path) -> None:
    doc = record(db, "DOC", scope="project:OTHER")
    with pytest.raises(RecordNotFoundError):
        run(db, handle_mark_pins_stale, MarkPinsStale(**common(record_id=doc, current_pin="B")))
    with pytest.raises(RecordNotFoundError):
        run(db, handle_mark_pins_stale, MarkPinsStale(**common(record_id="NOPE", current_pin="B")))


# --- replay -------------------------------------------------------------------------------------


def test_the_projection_rebuilds_from_the_ledger(db: Path) -> None:
    a, b, c = record(db, "A"), record(db, "B"), record(db, "C")
    first = suggest(db, a, b)
    run(db, handle_accept_link, AcceptLink(**common(link_id=first)))
    second = add(db, b, c, pin="A")
    run(db, handle_flag_link, FlagLink(**common(link_id=second, status="stale", reason="r")))
    run(db, handle_retract_link, RetractLink(**common(link_id=first, reason="x")))
    before = (row(db, first), row(db, second))
    assert rebuild_projections(db) == count_events(db)
    assert (row(db, first), row(db, second)) == before
