"""``GET /records/{id}/actions``: what the caller may do on a record now (P1-UX2-S1).

The ledger is the hidden world of ADR-0016 (an RFI anybody reads, a privileged RFI, a restricted
early warning, a restricted document...). The route answers by the caller's own roles, answers a
record the caller may not read exactly as a missing one, and offers an agent nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from harness import Harness
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from tl_mod_correspondence.confseed import TOKENS, Hidden, seed_hidden_world

PASSWORD = "correct horse battery"
FAKE_ID = "01J000000000000000000000"
ROLES = {
    "bob": ["user"],
    "amy": ["user"],  # named on the privileged RFI
    "ctl": ["document_controller"],
    "boss": ["admin"],
}


@pytest.fixture
def harness(parity_harness: Harness) -> Harness:
    return parity_harness


class World:
    def __init__(self, harness: Harness, hidden: Hidden, tokens: dict[str, str]) -> None:
        self.harness = harness
        self.hidden = hidden
        self.tokens = tokens

    def client(self, who: str | None) -> TestClient:
        client = self.harness.client_for(None)
        if who is not None:
            client.headers.update({"Authorization": f"Bearer {self.tokens[who]}"})
        return client

    def actions(self, who: str | None, record_id: str) -> tuple[int, dict[str, object]]:
        found = self.client(who).get(f"/records/{record_id}/actions")
        return found.status_code, found.json()


@pytest.fixture
def world(harness: Harness, tmp_path: Path) -> World:
    with harness.backend(False) as uow:
        for name, roles in ROLES.items():
            accounts.create_account(
                uow,
                username=name,
                display_name=name.title(),
                kind="person",
                roles=roles,
                password=prepare_password(PASSWORD),
                by="svc:test",
            )
        bot = accounts.create_account(
            uow,
            username="bot",
            display_name="Bot",
            kind="agent",
            roles=["user"],
            password=None,
            by="svc:test",
        )
        _, agent_token = accounts.issue_agent_token(
            uow,
            account_id=bot.account_id,
            label="actions",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            by="svc:test",
        )
    tokens = {
        name: sessions.sign_in(harness.backend, username=name, password=PASSWORD)[1]
        for name in ROLES
    }
    tokens["bot"] = agent_token
    hidden = seed_hidden_world(harness.target or harness.db, harness.service, tmp_path)
    return World(harness, hidden, tokens)


def commands(body: dict[str, object]) -> list[str]:
    found = body["actions"]
    assert isinstance(found, list)
    return [a["command"] for a in found]  # pyright: ignore[reportUnknownVariableType]


def test_a_reader_is_told_what_they_may_do_with_the_label_in_plain_words(world: World) -> None:
    rfi = world.hidden.ids["open_rfi"]  # an answered RFI: the answer is judged
    status, body = world.actions("bob", rfi)
    assert status == 200
    assert body["record_id"] == rfi and body["state"] == "Answered"
    assert body["actions"] == [{"command": "ReviewTechnicalAnswer", "label": "Review answer"}]


def test_the_offers_follow_the_roles_of_the_caller(world: World) -> None:
    waiting = world.hidden.ids["secret_rfi"]  # awaiting its answer; amy and ctl are named
    assert world.actions("bob", waiting)[0] == 404
    assert commands(world.actions("amy", waiting)[1]) == ["AnswerTechnical", "CloseTechnical"]
    assert commands(world.actions("ctl", waiting)[1]) == ["AnswerTechnical", "CloseTechnical"]
    assert world.actions("boss", waiting)[0] == 404  # an admin is not named on it
    # the early warning is a controller's: a plain user does not even know it is there
    notice = world.hidden.ids["commercial"]
    assert world.actions("bob", notice)[0] == 404
    assert commands(world.actions("ctl", notice)[1]) == ["AssessCommercial"]
    assert commands(world.actions("boss", notice)[1]) == ["AssessCommercial"]


def test_an_answered_rfi_is_escalated_by_a_controller_until_it_has_been(world: World) -> None:
    """The seed already raised an early warning from the open RFI, so a controller is not offered
    to escalate it again; the plain user never was."""
    rfi = world.hidden.ids["open_rfi"]
    for who in ("bob", "ctl", "boss"):
        assert commands(world.actions(who, rfi)[1]) == ["ReviewTechnicalAnswer"], who


def test_a_hidden_record_answers_exactly_like_a_missing_one(world: World) -> None:
    ids = world.hidden.ids
    cases = {
        "bob": ["restricted", "privileged", "bogus", "document", "commercial", "secret_rfi"],
        "amy": ["restricted", "bogus", "document", "commercial"],
        "ctl": ["bogus"],
        "boss": ["privileged", "bogus", "secret_rfi"],
        "bot": ["restricted", "privileged", "bogus", "document", "commercial", "secret_rfi"],
    }
    for who, kinds in cases.items():
        client = world.client(who)
        missing = client.get(f"/records/{FAKE_ID}/actions")
        assert missing.status_code == 404 and missing.json()["error"] == "record_not_found"
        for kind in kinds:
            hidden = client.get(f"/records/{ids[kind]}/actions")
            assert hidden.status_code == missing.status_code, (who, kind)
            assert hidden.text.replace(ids[kind], FAKE_ID) == missing.text, (who, kind)
            assert sorted(hidden.headers) == sorted(missing.headers), (who, kind)
            assert hidden.headers["content-type"] == missing.headers["content-type"]
            for token in TOKENS.values():
                assert token not in hidden.text, (who, kind, token)


def test_an_agent_is_offered_nothing_on_a_record_it_may_read(world: World) -> None:
    status, body = world.actions("bot", world.hidden.ids["open_rfi"])
    assert status == 200
    assert body["state"] == "Answered" and body["actions"] == []


def test_an_agent_cannot_tell_a_hidden_record_from_a_missing_one_by_the_agent_rule(
    world: World,
) -> None:
    """Visibility is judged before the agent rule: a hidden record is a 404, not an empty list."""
    assert world.actions("bot", world.hidden.ids["restricted"])[0] == 404
    assert world.actions("bot", FAKE_ID)[0] == 404


def test_without_a_token_the_route_answers_401(world: World) -> None:
    anonymous = world.client(None).get(f"/records/{world.hidden.ids['open_rfi']}/actions")
    assert anonymous.status_code == 401
    assert world.hidden.ids["open_rfi"] not in anonymous.text


def test_a_record_of_a_type_with_no_hook_is_offered_nothing(world: World) -> None:
    plain = world.harness.create_record("PLAIN-1", "A plain record")
    status, body = world.actions("bob", plain.stream_id)
    assert status == 200 and body["actions"] == []


def test_the_route_is_in_the_contract(world: World) -> None:
    spec = world.harness.app.openapi()
    op = spec["paths"]["/records/{record_id}/actions"]["get"]
    assert op["operationId"] == "get_record_actions"
    ok = op["responses"]["200"]["content"]["application/json"]["schema"]
    assert ok["$ref"].endswith("/RecordActions")
    assert {"RecordActions", "ActionOffer"} <= set(spec["components"]["schemas"])
