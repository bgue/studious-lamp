"""Link read queries: links_of, link_counts, search_linkable (P0-I3-T03b; brief 7.4)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from tl_adapters.sqlite.uow import create_schema, open_uow
from tl_core.ledger import NewEvent
from tl_core.links.provider import use_vocabulary
from tl_core.links.vocabulary import Relation, default_vocabulary
from tl_core.services.commands import CreateRecord
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.link_queries import (
    LinkCounts,
    LinkTarget,
    LinkView,
    link_counts,
    links_of,
    search_linkable,
)
from tl_core.services.records import handle_create_record
from tl_core.uow import UnitOfWork

P1 = "project:P123"


@pytest.fixture
def uow(tmp_path: Path) -> Iterator[UnitOfWork]:
    db = tmp_path / "tl.db"
    create_schema(db)
    with open_uow(db) as handle:
        yield handle


def record(uow: UnitOfWork, key: str, title: str | None = None, scope: str = P1, **kw: Any) -> str:
    rid = handle_create_record(
        uow,
        CreateRecord(
            actor="u",
            source="t",
            scope=scope,
            record_type="core.Record",
            title=title or f"title of {key}",
            key=key,
        ),
    ).stream_id
    if kw.get("voided"):
        uow.conn().execute(text("UPDATE cur_core_record SET voided = 1 WHERE id = :i"), {"i": rid})
    if "status" in kw:
        uow.conn().execute(
            text("UPDATE cur_core_record SET status = :s WHERE id = :i"),
            {"s": kw["status"], "i": rid},
        )
    return rid


def link(
    uow: UnitOfWork,
    link_id: str,
    from_id: str,
    to_id: str,
    relation: str = "references",
    *,
    suggested: bool = False,
    **extra: Any,
) -> None:
    payload: dict[str, Any] = {
        "link_id": link_id,
        "from_ref": from_id,
        "to_ref": to_id,
        "relation": relation,
        "pin": extra.pop("pin", None),
        "source": "key_detected" if suggested else "manual",
        "note": extra.pop("note", None),
        **({"confidence": 0.9} if suggested else {}),
    }
    uow.append(
        stream_id=link_id,
        stream_type="core.Link",
        scope=P1,
        expected_version=0,
        events=[
            NewEvent(event_type="Link.Suggested" if suggested else "Link.Added", payload=payload)
        ],
        actor="user:u-1",
        source="test",
        correlation_id="c",
    )


def later(uow: UnitOfWork, link_id: str, version: int, event_type: str, **payload: Any) -> None:
    uow.append(
        stream_id=link_id,
        stream_type="core.Link",
        scope=P1,
        expected_version=version,
        events=[NewEvent(event_type=event_type, payload={"link_id": link_id, **payload})],
        actor="user:qa",
        source="test",
        correlation_id="c",
    )


# --- links_of -------------------------------------------------------------------------------


def test_both_directions_are_resolved_with_labels_from_this_record(uow: UnitOfWork) -> None:
    weld = record(uow, "W-1", title="Weld one")
    ncr = record(uow, "NCR-1", title="Bevel damage", status="Open")
    link(uow, "L1", weld, ncr, "raised_against", pin="C", note="found at fit-up")
    from_weld = links_of(uow, weld)
    from_ncr = links_of(uow, ncr)
    assert len(from_weld) == len(from_ncr) == 1

    out = from_weld[0]
    assert isinstance(out, LinkView)
    assert (out.link_id, out.direction, out.relation, out.label) == (
        "L1",
        "out",
        "raised_against",
        "raised against",
    )
    assert (out.other_id, out.other_key, out.other_title) == (ncr, "NCR-1", "Bevel damage")
    assert (out.other_type, out.other_status, out.other_voided) == ("core.Record", "Open", False)
    assert (out.status, out.pin, out.note, out.source) == (
        "active",
        "C",
        "found at fit-up",
        "manual",
    )
    assert out.version == 1
    assert out.verified_by is None and out.confidence is None and out.declined is False

    inbound = from_ncr[0]
    assert (inbound.direction, inbound.relation, inbound.label) == (
        "in",
        "raised_against",
        "has raised",
    )
    assert (inbound.other_id, inbound.other_key) == (weld, "W-1")


def test_a_symmetric_relation_reads_the_same_both_ways(uow: UnitOfWork) -> None:
    a, b = record(uow, "A"), record(uow, "B")
    link(uow, "L1", a, b, "same_as")
    assert links_of(uow, a)[0].label == "same as"
    assert links_of(uow, b)[0].label == "same as"


def test_suggestions_carry_their_confidence_and_verification_shows(uow: UnitOfWork) -> None:
    a, b, c = record(uow, "A"), record(uow, "B"), record(uow, "C")
    link(uow, "L1", a, b, suggested=True)
    link(uow, "L2", a, c)
    later(uow, "L2", 1, "Link.Verified")
    by_id = {v.link_id: v for v in links_of(uow, a)}
    assert (by_id["L1"].status, by_id["L1"].confidence) == ("suggested", 0.9)
    assert by_id["L2"].verified_by == "user:qa"
    assert by_id["L2"].verified_at is not None
    assert by_id["L2"].version == 2


def test_retracted_links_are_left_out_unless_asked_for(uow: UnitOfWork) -> None:
    a, b, c = record(uow, "A"), record(uow, "B"), record(uow, "C")
    link(uow, "L1", a, b)
    link(uow, "L2", a, c, suggested=True)
    later(uow, "L1", 1, "Link.Retracted", reason="oops")
    later(uow, "L2", 1, "Link.Declined", reason="no")
    assert links_of(uow, a) == []
    everything = links_of(uow, a, include_retracted=True)
    assert {(v.link_id, v.status, v.declined, v.reason) for v in everything} == {
        ("L1", "retracted", False, "oops"),
        ("L2", "retracted", True, "no"),
    }


def test_a_voided_other_end_is_shown_as_voided(uow: UnitOfWork) -> None:
    a, b = record(uow, "A"), record(uow, "B", voided=True)
    link(uow, "L1", a, b)
    (view,) = links_of(uow, a)
    assert view.other_voided is True


def test_ordering_is_outbound_first_then_vocabulary_then_key(uow: UnitOfWork) -> None:
    me = record(uow, "ME")
    x, y, z, w = (record(uow, k) for k in ("X-1", "Y-1", "Z-1", "W-1"))
    link(uow, "L1", me, z, "requires")
    link(uow, "L2", me, y, "references")
    link(uow, "L3", me, x, "requires")
    link(uow, "L4", w, me, "blocks")
    link(uow, "L5", y, me, "references")
    order = [(v.direction, v.relation, v.other_key) for v in links_of(uow, me)]
    assert order == [
        ("out", "references", "Y-1"),
        ("out", "requires", "X-1"),
        ("out", "requires", "Z-1"),
        ("in", "references", "Y-1"),
        ("in", "blocks", "W-1"),
    ]


def test_a_relation_outside_the_vocabulary_still_displays_and_sorts_last(uow: UnitOfWork) -> None:
    a, b, c = record(uow, "A"), record(uow, "B"), record(uow, "C")
    vocabulary = default_vocabulary()
    vocabulary.add(Relation("inspects", "inspects", "inspected_by", "inspected by"))
    with use_vocabulary(vocabulary):
        link(uow, "L1", a, b, "inspects")
        link(uow, "L2", a, c, "references")
        assert [v.relation for v in links_of(uow, a)] == ["references", "inspects"]
        assert links_of(uow, b)[0].label == "inspected by"
    views = links_of(uow, a)  # the vocabulary no longer knows "inspects"
    assert [v.relation for v in views] == ["references", "inspects"]
    assert views[1].label == "inspects"


def test_a_record_without_links_gives_an_empty_list_and_an_unknown_one_raises(
    uow: UnitOfWork,
) -> None:
    a = record(uow, "A")
    assert links_of(uow, a) == []
    with pytest.raises(RecordNotFoundError):
        links_of(uow, "NOPE")


# --- link_counts ----------------------------------------------------------------------------


def test_counts_come_from_the_counts_table_with_zeros_for_the_rest(uow: UnitOfWork) -> None:
    a, b, c = record(uow, "A"), record(uow, "B"), record(uow, "C")
    link(uow, "L1", a, b)
    link(uow, "L2", c, a, suggested=True)
    link(uow, "L3", a, c)
    later(uow, "L3", 1, "Link.Flagged", status="stale", reason="r")
    counts = link_counts(uow, [a, b, "UNKNOWN"])
    assert set(counts) == {a, b, "UNKNOWN"}
    assert counts[a] == LinkCounts(record_id=a, active_out=1, active_in=0, stale=1, suggested=1)
    assert counts[b] == LinkCounts(record_id=b, active_in=1)
    assert counts["UNKNOWN"] == LinkCounts(record_id="UNKNOWN")
    assert counts[a].active == 1
    assert counts[b].active == 1


def test_counts_of_nothing_is_empty(uow: UnitOfWork) -> None:
    assert link_counts(uow, []) == {}


# --- search_linkable ------------------------------------------------------------------------


def keys(found: list[LinkTarget]) -> list[str | None]:
    return [t.key for t in found]


def test_search_matches_key_or_title_case_insensitively(uow: UnitOfWork) -> None:
    record(uow, "NCR-P123-0042", title="Bevel damage, spools ex Fab-A")
    record(uow, "NCR-P123-0039", title="Bevel prep out of tolerance")
    record(uow, "CAR-P123-0011", title="Fab-A bevel protection")
    record(uow, "W-12", title="Weld twelve")
    assert keys(search_linkable(uow, P1, "ncr")) == ["NCR-P123-0039", "NCR-P123-0042"]
    assert keys(search_linkable(uow, P1, "BEVEL")) == [
        "CAR-P123-0011",
        "NCR-P123-0039",
        "NCR-P123-0042",
    ]
    assert keys(search_linkable(uow, P1, "weld")) == ["W-12"]
    assert search_linkable(uow, P1, "zzz") == []


def test_every_word_must_match(uow: UnitOfWork) -> None:
    record(uow, "NCR-1", title="Bevel damage")
    record(uow, "NCR-2", title="Bevel prep")
    assert keys(search_linkable(uow, P1, "ncr bevel")) == ["NCR-1", "NCR-2"]
    assert keys(search_linkable(uow, P1, "ncr damage")) == ["NCR-1"]
    assert keys(search_linkable(uow, P1, "  ncr   damage ")) == ["NCR-1"]


def test_keys_that_start_with_the_first_word_come_first(uow: UnitOfWork) -> None:
    record(uow, "A-1", title="mentions ncr here")
    record(uow, "NCR-9", title="x")
    record(uow, "B-1", title="also ncr")
    assert keys(search_linkable(uow, P1, "ncr")) == ["NCR-9", "A-1", "B-1"]


def test_an_empty_query_lists_everything_by_key_and_respects_the_limit(uow: UnitOfWork) -> None:
    for key in ("C-3", "A-1", "B-2"):
        record(uow, key)
    assert keys(search_linkable(uow, P1, "")) == ["A-1", "B-2", "C-3"]
    assert keys(search_linkable(uow, P1, "", limit=2)) == ["A-1", "B-2"]


def test_search_covers_the_scope_and_company_but_not_other_projects(uow: UnitOfWork) -> None:
    record(uow, "MINE-1")
    record(uow, "CO-1", scope="company")
    record(uow, "THEIRS-1", scope="project:OTHER")
    found = search_linkable(uow, P1, "")
    assert keys(found) == ["CO-1", "MINE-1"]
    assert {t.scope for t in found} == {"company", P1}


def test_search_leaves_out_voided_records_the_excluded_record_and_other_types(
    uow: UnitOfWork,
) -> None:
    me = record(uow, "ME-1")
    record(uow, "GONE-1", voided=True)
    other = record(uow, "OTHER-1")
    uow.conn().execute(
        text("UPDATE cur_core_record SET type = 'x.Other' WHERE id = :i"), {"i": other}
    )
    assert keys(search_linkable(uow, P1, "", exclude_id=me)) == ["OTHER-1"]
    assert keys(search_linkable(uow, P1, "", record_type="core.Record")) == ["ME-1"]
    assert keys(search_linkable(uow, P1, "", record_type="x.Other")) == ["OTHER-1"]


def test_percent_and_underscore_in_a_query_are_literal(uow: UnitOfWork) -> None:
    record(uow, "A-1", title="100% done")
    record(uow, "A-2", title="plain")
    record(uow, "A_3", title="under_score")
    assert keys(search_linkable(uow, P1, "100%")) == ["A-1"]
    assert keys(search_linkable(uow, P1, "%")) == ["A-1"]
    assert keys(search_linkable(uow, P1, "a_3")) == ["A_3"]
    assert keys(search_linkable(uow, P1, "_")) == ["A_3"]


def test_a_target_carries_what_the_preview_line_needs(uow: UnitOfWork) -> None:
    ncr = record(uow, "NCR-1", title="Bevel damage", status="Open")
    w1, w2 = record(uow, "W-1"), record(uow, "W-2")
    link(uow, "L1", w1, ncr)
    link(uow, "L2", w2, ncr)
    link(uow, "L3", w2, ncr, "requires", suggested=True)  # a suggestion is not counted
    (target,) = search_linkable(uow, P1, "ncr")
    assert target == LinkTarget(
        id=ncr,
        key="NCR-1",
        type="core.Record",
        title="Bevel damage",
        status="Open",
        scope=P1,
        link_total=2,
    )
