"""Shadow enrichment values stay out of the event surfaces (second security review, re-check
finding 1): the change feed filter (so `/events`, `/stream`, `tl events`) and the feed cards."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from tl_core.changefeed.filters import ANY, SubscriptionFilter
from tl_core.feed.cards import disposition
from tl_core.ledger import Event

# the thread test of the filter touches the context only for a thread event
CTX: Any = None
NOW = datetime(2026, 10, 19, tzinfo=UTC)


def event(state: str) -> Event:
    return Event(
        event_id="E" * 26, seq=5, scope="project:P123", stream_id="V1",
        stream_type="core.EnrichmentValue", stream_version=1, event_type="Enrichment.Proposed",
        payload={"acceptance_state": state, "value": "alpha"}, actor="svc:enricher-e",
        source="enricher:e@1", correlation_id="C" * 26, causation_id=None,
        recorded_at=NOW, effective_at=NOW,
        schema_version=1,
        prev_hash="0", hash="1",
    )  # fmt: skip


@pytest.mark.parametrize("flt", [ANY, SubscriptionFilter(), SubscriptionFilter.of(scope=None)])
def test_a_default_filter_hides_a_shadow_proposal_and_shows_the_others(
    flt: SubscriptionFilter,
) -> None:
    assert not flt.matches(event("shadow"))
    assert flt.matches(event("proposed"))


def test_only_an_explicit_show_shadow_lets_it_through() -> None:
    assert SubscriptionFilter.of(show_shadow=True).matches(event("shadow"))


def test_the_event_api_filter_follows_the_callers_role() -> None:
    from tl_api.routes.events import build_filter
    from tl_core.auth.types import Principal

    def principal(roles: list[str], kind: str = "person") -> Principal:
        return Principal.model_validate(
            {
                "actor": f"user:{roles[0]}", "account_id": "A" * 26, "kind": kind,
                "roles": roles, "via": "session",
            }
        )  # fmt: skip

    admin = build_filter(CTX, None, None, None, principal(["admin"]))
    user = build_filter(CTX, None, None, None, principal(["user"]))
    agent = build_filter(CTX, None, None, None, principal(["admin"], kind="agent"))
    assert admin.matches(event("shadow"))
    assert not user.matches(event("shadow")) and not agent.matches(event("shadow"))


def test_a_shadow_proposal_makes_no_feed_card() -> None:
    assert disposition(None, event("shadow")) == "ignore"
    assert disposition(None, event("proposed")) == "start"
