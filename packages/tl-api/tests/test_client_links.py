"""HTTP client: links, trace, workflow, schema and reference (P0-I4-T47)."""

from __future__ import annotations

from typing import Any

import pytest
from harness import SCOPE, Harness
from tl_api.client import ApiClient
from tl_core.links.expected import missing_expected_links
from tl_core.links.provider import get_vocabulary
from tl_core.links.vocabulary import default_relation
from tl_core.numbering.detect import suggest_chips
from tl_core.services import link_queries, link_trace, psets
from tl_core.services.errors import (
    DuplicateLinkError,
    GuardFailedError,
    InvalidLinkTransitionError,
    RecordNotFoundError,
    SelfLinkError,
    UnknownRelationError,
    UnknownTransitionError,
)
from tl_core.services.links import (
    AcceptLink,
    AddLink,
    DeclineLink,
    FlagLink,
    RepinLink,
    RetractLink,
    SuggestLink,
    VerifyLink,
)
from tl_core.services.workflow import TransitionWorkflow, workflow_status
from tl_core.workflow.engine import GuardResult


def common(**extra: Any) -> dict[str, Any]:
    return {"actor": "user:ignored", "source": "tui", "scope": SCOPE, **extra}


def graph(h: Harness) -> dict[str, str]:
    """A requires B requires C, and a lone D."""
    ids = {k: h.create_record(k, f"Record {k}").stream_id for k in "ABCD"}
    api = h.api()
    api.add_link(AddLink(**common(from_id=ids["A"], to_id=ids["B"], relation="requires")))
    api.add_link(AddLink(**common(from_id=ids["B"], to_id=ids["C"], relation="requires")))
    return ids


def test_link_reads_equal_the_embedded_answers(harness: Harness) -> None:
    ids = graph(harness)
    api = harness.api()
    with harness.backend(True) as uow:
        assert api.links_of(ids["B"]) == link_queries.links_of(uow, ids["B"])
        assert len(api.links_of(ids["B"])) == 2
        assert api.trace(ids["A"]) == link_trace.trace(uow, ids["A"])
        assert api.trace(ids["C"], depth=1, direction="in") == link_trace.trace(
            uow, ids["C"], depth=1, direction="in"
        )
        assert api.expected_links(ids["D"]) == missing_expected_links(uow, ids["D"])
        assert api.search_linkable(SCOPE, "record b") == link_queries.search_linkable(
            uow, SCOPE, "record b"
        )
        wanted = link_queries.search_linkable(uow, SCOPE, "", exclude_id=ids["A"], limit=2)
        assert api.search_linkable(SCOPE, "", exclude_id=ids["A"], limit=2) == wanted
        assert api.link_counts(list(ids.values())) == link_queries.link_counts(
            uow, list(ids.values())
        )


def test_link_counts_send_large_lists_in_chunks(harness: Harness) -> None:
    ids = graph(harness)
    many = [f"missing-{n}" for n in range(450)] + [ids["B"]]
    counts = harness.api().link_counts(many)
    assert len(counts) == 451
    assert counts[ids["B"]].active_out == 1 and counts[ids["B"]].active_in == 1
    assert counts["missing-7"].active == 0
    assert harness.api().link_counts([]) == {}


def test_reference_reads_equal_the_embedded_answers(harness: Harness) -> None:
    known = harness.create_record("P123-REC-0001", "Known")
    api = harness.api()
    text = "see P123-REC-0001 and P123-REC-0099"
    with harness.backend(True) as uow:
        assert api.detect_keys(SCOPE, text) == suggest_chips(uow, SCOPE, text)
        assert api.detect_keys(SCOPE, text, linked_to=known.stream_id) == suggest_chips(
            uow, SCOPE, text, linked_to=known.stream_id
        )
        assert api.form_metadata(SCOPE, "core.Record") == psets.form_metadata(
            uow, SCOPE, "core.Record"
        )
        assert api.conformance(known.stream_id) == psets.conformance(uow, known.stream_id)
    vocabulary = get_vocabulary()
    assert [r.code for r in api.relations()] == list(vocabulary.codes())
    first = api.relations()[0]
    expected = vocabulary.get(first.code)
    assert (first.label, first.inverse_code, first.inverse_label) == (
        expected.label,
        expected.inverse_code,
        expected.inverse_label,
    )
    assert api.default_relation("core.Record", "core.Record") == default_relation(
        "core.Record", "core.Record"
    )


def test_unknown_records_raise_record_not_found(harness: Harness) -> None:
    api = harness.api()
    for call in (
        lambda: api.links_of("01NOSUCHRECORD"),
        lambda: api.trace("01NOSUCHRECORD"),
        lambda: api.expected_links("01NOSUCHRECORD"),
        lambda: api.workflow_status("01NOSUCHRECORD"),
        lambda: api.conformance("01NOSUCHRECORD"),
    ):
        with pytest.raises(RecordNotFoundError):
            call()


def test_every_link_command_runs_over_http(harness: Harness) -> None:
    ids = {k: harness.create_record(k).stream_id for k in "ABC"}
    api = harness.api()
    added = api.add_link(AddLink(**common(from_id=ids["A"], to_id=ids["B"], relation="requires")))
    link_id = added.stream_id
    verified = api.verify_link(VerifyLink(**common(link_id=link_id, note="checked")))
    assert verified.events[0].event_type == "Link.Verified"
    flagged = api.flag_link(FlagLink(**common(link_id=link_id, status="stale", reason="moved")))
    assert flagged.events[0].event_type == "Link.Flagged"
    repinned = api.repin_link(RepinLink(**common(link_id=link_id, pin="B")))
    assert repinned.events[0].event_type == "Link.Repinned"
    retracted = api.retract_link(RetractLink(**common(link_id=link_id, reason="mistake")))
    assert retracted.events[0].event_type == "Link.Retracted"

    suggested = api.suggest_link(
        SuggestLink(**common(from_id=ids["A"], to_id=ids["C"], relation="requires"))
    )
    assert suggested.events[0].event_type == "Link.Suggested"
    accepted = api.accept_link(AcceptLink(**common(link_id=suggested.stream_id)))
    assert accepted.events[0].event_type == "Link.Accepted"
    again = api.suggest_link(
        SuggestLink(**common(from_id=ids["B"], to_id=ids["C"], relation="requires"))
    )
    declined = api.decline_link(DeclineLink(**common(link_id=again.stream_id, reason="no")))
    assert declined.events[0].event_type == "Link.Declined"
    assert all(e.actor == "user:alice" for r in (added, verified, accepted) for e in r.events)


def test_link_refusals_raise_the_embedded_exception_classes(harness: Harness) -> None:
    ids = {k: harness.create_record(k).stream_id for k in "AB"}
    api = harness.api()
    api.add_link(AddLink(**common(from_id=ids["A"], to_id=ids["B"], relation="requires")))
    with pytest.raises(DuplicateLinkError):
        api.add_link(AddLink(**common(from_id=ids["A"], to_id=ids["B"], relation="requires")))
    with pytest.raises(SelfLinkError):
        api.add_link(AddLink(**common(from_id=ids["A"], to_id=ids["A"], relation="requires")))
    with pytest.raises(UnknownRelationError):
        api.add_link(AddLink(**common(from_id=ids["A"], to_id=ids["B"], relation="friends_with")))
    with pytest.raises(InvalidLinkTransitionError):
        link = api.links_of(ids["A"])[0].link_id
        api.accept_link(AcceptLink(**common(link_id=link)))  # it is already active


def test_workflow_status_and_transitions(harness: Harness) -> None:
    sid = harness.create_record("W-1").stream_id
    api = harness.api()
    with harness.backend(True) as uow:
        assert api.workflow_status(sid) == workflow_status(uow, sid)
    status = api.workflow_status(sid)
    assert status.state == "Draft" and [o.transition for o in status.options] == ["submit"]
    moved = api.transition(
        TransitionWorkflow(**common(stream_id=sid, expected_version=1, transition="submit"))
    )
    assert moved.version == 2 and moved.events[0].event_type == "Workflow.Transitioned"
    assert api.workflow_status(sid).state == "Review"


def test_a_blocked_transition_raises_guard_failed_with_its_results(harness: Harness) -> None:
    sid = harness.create_record("W-2").stream_id
    api = harness.api()
    api.transition(
        TransitionWorkflow(**common(stream_id=sid, expected_version=1, transition="submit"))
    )
    with pytest.raises(GuardFailedError) as caught:
        api.transition(
            TransitionWorkflow(**common(stream_id=sid, expected_version=2, transition="approve"))
        )
    results = caught.value.results
    assert results and all(isinstance(r, GuardResult) for r in results)
    assert any(not r.passed for r in results)
    with pytest.raises(UnknownTransitionError):
        api.transition(
            TransitionWorkflow(**common(stream_id=sid, expected_version=2, transition="nonesuch"))
        )


def test_roles_reach_the_role_guards(harness: Harness) -> None:
    sid = harness.create_record("W-3").stream_id
    other = harness.create_record("W-4").stream_id
    api = harness.api()
    api.add_link(AddLink(**common(from_id=sid, to_id=other, relation="references")))
    version = 1
    for name in ("submit", "approve"):
        version = api.transition(
            TransitionWorkflow(**common(stream_id=sid, expected_version=version, transition=name))
        ).version

    def issue_allowed(**kw: Any) -> bool:
        options = api.workflow_status(sid, **kw).options
        return next(o for o in options if o.transition == "issue").allowed

    assert issue_allowed() is False
    assert issue_allowed(roles=["manager"]) is True


def test_a_client_built_for_another_actor_is_attributed_to_that_actor(harness: Harness) -> None:
    ids = {k: harness.create_record(k).stream_id for k in "AB"}
    result = harness.api("user:bob").add_link(
        AddLink(**common(from_id=ids["A"], to_id=ids["B"], relation="requires"))
    )
    assert result.events[0].actor == "user:bob"
    assert isinstance(harness.api(), ApiClient)
