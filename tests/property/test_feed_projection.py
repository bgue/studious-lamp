"""Feed projection determinism (P0-I6-S4): a rebuild gives the same cur_feed_items as the live run,
event cards included, and the cards equal an independent reading of the aggregation rules.

Run with ``pytest tests/property -k projection``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from tl_adapters._unit import BaseUnitOfWork
from tl_adapters.db import (
    DbTarget,
    create_schema,
    make_engine,
    make_ledger,
    read_tx,
    rebuild_projections,
    write_tx,
)
from tl_core.ledger import Event, NewEvent
from tl_core.projection.defaults import default_registry
from tl_core.services.commands import CreateRecord, UpdateRecord
from tl_core.services.errors import ServiceError
from tl_core.services.feed import EditPost, PostToFeed, handle_edit_post, handle_post
from tl_core.services.records import handle_create_record, handle_update_record

T0 = datetime(2026, 10, 9, 9, 0, 0, tzinfo=UTC)
SCOPES = ["project:P1", "project:P2"]
ACTORS = ["user:jo", "user:al", "agent:bot"]
WINDOW = timedelta(seconds=600)
PLUMBING = {"Numbering.Allocated", "Link.Suggested"}

op = st.tuples(
    # Weighted towards bursts of one actor in one scope, so windows and their edges are exercised.
    st.sampled_from(["create"] * 4 + ["update"] * 2 + ["post", "edit", "retract", "react"]),
    st.sampled_from(ACTORS[:1] * 3 + ACTORS),
    st.sampled_from(SCOPES[:1] * 3 + SCOPES),
    st.sampled_from([0, 1, 30, 300, 300, 599, 600, 600, 601, 1200]),  # seconds since the last op
    st.integers(min_value=0, max_value=5),  # picks a record, post or body
)


def body_for(pick: int, keys: list[str]) -> str:
    tag = f"#{keys[pick % len(keys)]} " if keys else ""
    return [f"{tag}note", "stop #hold @party:fab-a", f"{tag}#area:A12 #bevel", "plain", "#fyi"][
        pick % 5
    ] + f" {pick}"


def run(path: DbTarget, ops: list[tuple[str, str, str, int, int]]) -> None:
    create_schema(path)
    engine = make_engine(path)
    clock = {"now": T0}
    ledger = make_ledger(engine, clock=lambda: clock["now"])
    records: dict[str, list[tuple[str, int, str]]] = {s: [] for s in SCOPES}  # id, version, key
    posts: dict[str, list[tuple[str, int]]] = {s: [] for s in SCOPES}  # id, version
    try:
        for kind, actor, scope, gap, pick in ops:
            clock["now"] += timedelta(seconds=gap)
            try:
                with BaseUnitOfWork(
                    ledger, default_registry(), None, lambda: write_tx(engine), readonly=False
                ) as uow:
                    common: dict[str, Any] = {"actor": actor, "source": "t", "scope": scope}
                    if kind == "create":
                        result = handle_create_record(
                            uow, CreateRecord(**common, record_type="core.Record", title="t")
                        )
                        records[scope].append((result.stream_id, 1, result.key or ""))
                    elif kind == "update" and records[scope]:
                        rid, version, key = records[scope][pick % len(records[scope])]
                        handle_update_record(
                            uow,
                            UpdateRecord(
                                **common,
                                stream_id=rid,
                                expected_version=version,
                                changes={"title": f"v{version}{pick}"},
                            ),
                        )
                        index = records[scope].index((rid, version, key))
                        records[scope][index] = (rid, version + 1, key)
                    elif kind == "post":
                        keys = [k for _, _, k in records[scope]]
                        result = handle_post(uow, PostToFeed(**common, body=body_for(pick, keys)))
                        posts[scope].append((result.stream_id, 1))
                    elif kind == "edit" and posts[scope]:
                        pid, version = posts[scope][pick % len(posts[scope])]
                        keys = [k for _, _, k in records[scope]]
                        result = handle_edit_post(
                            uow, EditPost(**common, post_id=pid, body=body_for(pick + 1, keys))
                        )
                        posts[scope][posts[scope].index((pid, version))] = (pid, result.version)
                    elif kind in ("retract", "react") and posts[scope]:
                        pid, version = posts[scope][pick % len(posts[scope])]
                        is_react = kind == "react"
                        payload: dict[str, Any] = {"post_id": pid}
                        if is_react:
                            payload |= {"reaction": ["ack", "+1"][pick % 2], "on": pick % 3 != 0}
                        else:
                            payload["reason"] = "r"
                        uow.append(
                            stream_id=pid,
                            stream_type="core.ActivityPost",
                            scope=scope,
                            expected_version=version,
                            events=[
                                NewEvent(
                                    event_type="Feed.Reacted" if is_react else "Feed.Retracted",
                                    payload=payload,
                                )
                            ],
                            actor=actor,
                            source="t",
                            correlation_id="c",
                        )
                        posts[scope][posts[scope].index((pid, version))] = (pid, version + 1)
            except ServiceError:
                continue
    finally:
        engine.dispose()


def dump(path: DbTarget) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    engine = make_engine(path)
    try:
        with read_tx(engine) as conn:
            items = conn.execute(text("SELECT * FROM cur_feed_items ORDER BY item_id")).all()
            tags = conn.execute(text("SELECT * FROM cur_feed_tags ORDER BY tag_row_id")).all()
        return [tuple(r) for r in items], [tuple(r) for r in tags]
    finally:
        engine.dispose()


def oracle(events: list[Event]) -> dict[str, list[tuple[str, str, int, int]]]:
    """Cards per scope from the ledger, written straight from the rules (no shared code)."""
    cards: dict[str, list[tuple[str, str, int, int]]] = {}
    state: dict[str, dict[str, Any] | None] = {}
    for e in events:
        t = e.event_type
        if t in PLUMBING or t.startswith("Webhook."):
            continue
        current = state.get(e.scope)
        if t.startswith("Feed."):
            state[e.scope] = None
            continue
        if (
            current is not None
            and current["actor"] == e.actor
            and current["type"] == t
            and timedelta(0) <= e.recorded_at - current["first"] <= WINDOW
        ):
            current["count"] += 1
            current["last"] = e.seq
            cards[e.scope][-1] = (current["id"], t, current["count"], e.seq)
        else:
            state[e.scope] = {
                "id": f"card:{e.event_id}",
                "actor": e.actor,
                "type": t,
                "first": e.recorded_at,
                "count": 1,
                "last": e.seq,
            }
            cards.setdefault(e.scope, []).append((f"card:{e.event_id}", t, 1, e.seq))
    return cards


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(ops=st.lists(op, min_size=1, max_size=40))
def test_feed_projection_rebuild_equals_live_and_cards_follow_the_rules(
    new_db: Callable[[], DbTarget],
    ops: list[tuple[str, str, str, int, int]],
) -> None:
    path = new_db()
    run(path, ops)
    live = dump(path)

    engine = make_engine(path)
    try:
        ledger = make_ledger(engine)
        events = ledger.read_after(0, limit=100_000)
        with read_tx(engine) as conn:
            found = conn.execute(
                text(
                    "SELECT scope, item_id, event_type, event_count, seq, open_scope "
                    "FROM cur_feed_items WHERE item_type = 'card' ORDER BY seq"
                )
            ).all()
    finally:
        engine.dispose()

    expected = oracle(events)
    actual: dict[str, list[tuple[str, str, int, int]]] = {}
    for r in found:
        actual.setdefault(r.scope, []).append((r.item_id, r.event_type, r.event_count, r.seq))
    assert actual == {scope: sorted(rows, key=lambda c: c[3]) for scope, rows in expected.items()}
    for scope in SCOPES:
        assert sum(1 for r in found if r.scope == scope and r.open_scope) <= 1

    rebuild_projections(path)
    assert dump(path) == live
    rebuild_projections(path, types=["feed"])
    assert dump(path) == live
