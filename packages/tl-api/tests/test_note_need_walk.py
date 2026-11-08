"""``POST /insights/needs`` (P2-INS-S2): the one telemetry write, closed to agents, rate limited."""

from __future__ import annotations

from typing import Any

import pytest
from harness import Harness
from sqlalchemy import text
from test_checks_walk import FAKE_ID, Seed, seed  # pyright: ignore[reportMissingImports]
from tl_api.routes import insights as routes
from tl_core.auth.provider import AGENT_ACTIONS, agent_may

BODY = {"request_kind": "check", "trigger": "request", "record_type": "awp.IWP"}


@pytest.fixture
def harness(parity_harness: Harness) -> Harness:
    return parity_harness


@pytest.fixture
def seeded(harness: Harness) -> Seed:
    routes.NEED_LIMITER._seen.clear()  # pyright: ignore[reportPrivateUsage]
    return seed(harness)


def stored(h: Harness) -> list[Any]:
    with h.backend(True) as uow:
        return list(uow.conn().execute(text("SELECT * FROM telemetry_need ORDER BY recorded_at")))


def post(h: Harness, s: Seed, who: str, body: dict[str, Any] | None = None) -> Any:
    return h.client_for(None).post(
        "/insights/needs",
        json=BODY if body is None else body,
        headers={"Authorization": f"Bearer {s.tokens[who]}"},
    )


def test_the_action_is_in_no_agent_allow_list() -> None:
    assert routes.NEED_ACTION not in AGENT_ACTIONS and not agent_may(routes.NEED_ACTION)


def test_an_agent_token_is_refused_and_nothing_is_written(harness: Harness, seeded: Seed) -> None:
    answer = post(harness, seeded, "bot")
    assert answer.status_code == 403 and answer.json()["error"] == "forbidden"
    assert stored(harness) == []


def test_a_human_gets_204_then_429_past_30_in_the_window(harness: Harness, seeded: Seed) -> None:
    for n in range(30):
        assert post(harness, seeded, "bob").status_code == 204, n
    over = post(harness, seeded, "bob")
    assert over.status_code == 429 and over.json()["error"] == "rate_limited"
    assert len(stored(harness)) == 30
    assert post(harness, seeded, "amy").status_code == 204  # the window is per actor


def test_the_role_comes_from_the_token_and_the_body_cannot_say(
    harness: Harness, seeded: Seed
) -> None:
    for who in ("bob", "ctl", "boss"):
        assert post(harness, seeded, who).status_code == 204
    assert [r.viewer_role for r in stored(harness)] == ["user", "document_controller", "admin"]
    for extra in ({"viewer_role": "admin"}, {"actor": "user:boss"}, {"text": "a weld is bad"}):
        assert post(harness, seeded, "bob", {**BODY, **extra}).status_code == 422
    assert len(stored(harness)) == 3


def test_a_bad_value_is_422_and_writes_nothing(harness: Harness, seeded: Seed) -> None:
    for bad in ({"request_kind": "guess"}, {"trigger": "free text"}):
        assert post(harness, seeded, "bob", {**BODY, **bad}).status_code == 422, bad
    assert stored(harness) == []


def test_a_hidden_record_id_is_dropped_and_answers_like_a_readable_one(
    harness: Harness, seeded: Seed
) -> None:
    assert (
        post(harness, seeded, "bob", {**BODY, "record_id": seeded.ids["open"]}).status_code == 204
    )
    hidden = post(harness, seeded, "bob", {**BODY, "record_id": seeded.ids["restricted"]})
    missing = post(harness, seeded, "bob", {**BODY, "record_id": FAKE_ID})
    assert hidden.status_code == missing.status_code == 204 and hidden.text == missing.text == ""
    rows = stored(harness)
    assert [r.record_id for r in rows] == [seeded.ids["open"], None, None]
    assert rows[0].scope and rows[1].scope is None
    assert {r.why for r in rows} == {None} and {r.outcome for r in rows} == {"shown"}


def test_a_screen_opening_carries_no_record(harness: Harness, seeded: Seed) -> None:
    body = {**BODY, "trigger": "screen:insights.checks", "record_id": seeded.ids["open"]}
    assert post(harness, seeded, "bob", body).status_code == 422
    assert (
        post(harness, seeded, "bob", {**BODY, "trigger": "screen:insights.checks"}).status_code
        == 204
    )
    assert stored(harness)[0].record_id is None
