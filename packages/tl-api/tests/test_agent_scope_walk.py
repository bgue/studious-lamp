"""P2-X2-T04: the agent scope walks at the HTTP edge and in the proposing service (parity harness).

(A) an agent with no module word on ``project:P1`` is refused the same as an agent filing on a
scope that does not exist (140: hidden and missing look alike); a refused filing writes nothing.
(B) a full queue answers one fixed text with no digit, and that text maps to 429 ``queue_full``.
(C) the held count and the stopped list, read as five kinds of reader (an admin without a
clearance row, a plain user, a document controller, the person named on the privileged item, and
the lowest reader), name no hidden record and count none; the count is the same with limit 1 and
limit 200 (141). Over HTTP, the admin sees the same list, and the agent gets 403 on every stop
route. The expected counts come from a control agent that never filed the privileged proposal.

Over HTTP an ``agent:`` token is refused by ``agent_must_propose`` before any scope is looked at
(``tl_api.auth.refuse_agent_writes``), so the filing refusals and the cap are exercised at the
proposing service (``proposals.propose``), the path the HTTP routes and MCP tools share.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from harness import Harness, ensure_agent
from sqlalchemy import text
from test_auth_review import AGENT_MAY_NOT
from tl_api.errors import body_for
from tl_api.tokens import add_token
from tl_core import confidentiality as cf
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from tl_core.services import agent_stop, proposals
from tl_core.services.agent_scope import QUEUE_CAP_SETTING, QUEUE_FULL_TEXT
from tl_core.services.commands import CreateRecord
from tl_core.services.errors import QueueFullError, RecordNotFoundError
from tl_core.services.settings import ChangeSetting, handle_change_setting
from tl_mod_correspondence.confseed import TOKENS, seed_hidden_world
from tl_mod_documents.derivation.publish import PublishDerivedTags

PASSWORD = "correct horse battery"
ADA = "user:ada"
BARE = "agent:bare"  # an agent with no explicit grant: no module word on any scope
TRIAGE = "agent:triage"  # granted by ensure_agent (the word on P123, P1, P2, P999)
CONTROL = "agent:zcontrol"  # granted; never files the privileged proposal (the world without it)
NOPE = "project:NOPE"  # a scope that does not exist (not in PROJECTS)
P1 = "project:P1"
TOOL = "create_record"
COUNTS = {
    "events": "SELECT COUNT(*) FROM events",
    "keys": "SELECT COUNT(*) FROM idempotency_key",
    "proposals": "SELECT COUNT(*) FROM cur_proposals",
}
PEOPLE = (
    ("ada", ("admin",)),
    ("uma", ("user",)),
    ("dora", ("user", "document_controller")),
    ("amy", ("user",)),
)


@pytest.fixture
def harness(parity_harness: Harness) -> Harness:
    return parity_harness


class Cast:
    """The people and the agent accounts; the HTTP clients are kept (copied from the stop test)."""

    def __init__(self, harness: Harness) -> None:
        self.harness = harness
        self.clients: dict[str, TestClient] = {}
        for name, roles in PEOPLE:
            self.person(name, roles)
        with harness.backend() as uow:
            for name in ("bare", "triage", "zcontrol"):
                accounts.create_account(
                    uow, username=name, display_name=name.title(), kind="agent", roles=["user"],
                    password=None, by="svc:test",
                )  # fmt: skip
        for agent in (BARE, TRIAGE, CONTROL):
            token = add_token(harness.settings.tokens_path, agent)
            self.clients[agent] = self._client(token)

    def _client(self, token: str) -> TestClient:
        client = self.harness.client_for(None)
        client.headers.update({"Authorization": f"Bearer {token}"})
        return client

    def person(self, name: str, roles: tuple[str, ...]) -> None:
        with self.harness.backend() as uow:
            accounts.create_account(
                uow, username=name, display_name=name.title(), kind="person", roles=list(roles),
                password=prepare_password(PASSWORD, username=name), by="svc:test",
            )  # fmt: skip
        _, token = sessions.sign_in(self.harness.backend, username=name, password=PASSWORD)
        self.clients[name] = self._client(token)


@pytest.fixture
def cast(harness: Harness) -> Cast:
    return Cast(harness)


def counts(harness: Harness) -> dict[str, int]:
    with harness.backend(True) as uow:
        conn = uow.conn()
        return {name: int(conn.execute(text(sql)).scalar_one()) for name, sql in COUNTS.items()}


def propose_create(harness: Harness, agent: str, scope: str, key: str) -> Any:
    """File one ``CreateRecord`` as ``agent`` through the proposing service (the shared path)."""
    command = CreateRecord(
        actor=agent, source="mcp:triage", scope=scope, record_type="core.Record",
        title=f"walk {key}", key=key,
    )  # fmt: skip
    with harness.backend(readonly=False) as uow:
        return proposals.propose(uow, tool=TOOL, agent=agent, command=command, summary="create")


def file_proposal(harness: Harness, agent: str, derived_id: str) -> str:
    """One pending proposal of ``agent`` carrying ``derived_id`` (written as the system)."""
    command = PublishDerivedTags(
        actor=agent, source="mcp:triage", scope="project:P123", derived_id=derived_id,
        expected_content_rev=1,
    )  # fmt: skip
    with harness.backend(readonly=False) as uow, cf.system_view():
        return proposals.propose(
            uow, tool="propose_import_tags", agent=agent, command=command, summary="publish"
        ).proposal_id


def set_cap(harness: Harness, scope: str, value: int) -> None:
    with harness.backend(readonly=False) as uow:
        handle_change_setting(
            uow,
            ChangeSetting(
                actor=ADA,
                source="test",
                scope=scope,
                key=QUEUE_CAP_SETTING,
                layer=scope,
                value=value,
                reason="test",
                accept_risk=True,
            ),
        )


def body(scope: str, key: str) -> dict[str, Any]:
    return {"scope": scope, "record_type": "core.Record", "title": "walk", "key": key}


# --- (A) a refusal looks like a missing scope


def test_a_bare_agents_refused_filing_answers_as_a_scope_that_does_not_exist(
    harness: Harness, cast: Cast
) -> None:
    bare = cast.clients[BARE]
    before = counts(harness)
    on_p1 = bare.post("/commands/CreateRecord", json=body(P1, "WALK-A1"))
    on_nope = bare.post("/commands/CreateRecord", json=body(NOPE, "WALK-A1"))
    # the HTTP route refuses every agent write before the scope is read: the same answer
    assert on_p1.status_code == on_nope.status_code == 403, on_p1.text
    assert on_p1.json() == on_nope.json()
    assert on_p1.json()["error"] == "agent_must_propose"

    # the proposing service: the bare agent's refusal is the missing-scope text, word for word
    with pytest.raises(RecordNotFoundError) as refused_p1:
        propose_create(harness, BARE, P1, "WALK-A1")
    with pytest.raises(RecordNotFoundError) as refused_nope:
        propose_create(harness, BARE, NOPE, "WALK-A1")
    assert type(refused_p1.value) is type(refused_nope.value)
    assert str(refused_p1.value).replace(P1, NOPE) == str(refused_nope.value)
    assert P1 in str(refused_p1.value) and NOPE in str(refused_nope.value)
    assert counts(harness) == before  # no event, no idempotency row, no proposal, no budget use


def test_the_same_filing_passes_once_the_word_is_granted(harness: Harness) -> None:
    ensure_agent(harness, TRIAGE)
    made = propose_create(harness, TRIAGE, P1, "WALK-A2")
    assert made.proposal_id


# --- (B) the queue cap answers one fixed text


@pytest.mark.parametrize(("scope", "limit"), [("project:P1", 2), ("project:P2", 3)])
def test_a_full_queue_answers_the_fixed_text_with_no_digit(
    harness: Harness, scope: str, limit: int
) -> None:
    ensure_agent(harness, TRIAGE)
    set_cap(harness, scope, limit)
    for n in range(limit):
        propose_create(harness, TRIAGE, scope, f"WALK-B-{scope}-{n}")
    before = counts(harness)
    with pytest.raises(QueueFullError) as full:
        propose_create(harness, TRIAGE, scope, f"WALK-B-{scope}-full")
    assert str(full.value) == QUEUE_FULL_TEXT
    assert re.search(r"\d", str(full.value)) is None
    assert counts(harness) == before

    # the HTTP mapping of the same refusal: 429 queue_full, the fixed text, nothing else
    status, error = body_for(full.value)  # type: ignore[misc]
    assert status == 429
    assert error.error == "queue_full"
    assert error.message == QUEUE_FULL_TEXT
    assert re.search(r"\d", error.model_dump_json()) is None


# --- (C) the held count and the stopped list, five readers


def stop_world(harness: Harness, cast: Cast, tmp_path: Path) -> dict[str, Any]:
    """TRIAGE files an open, a plain and a privileged proposal; CONTROL files an open and a plain
    one (the world that never had the privileged proposal). Both are stopped, TRIAGE first."""
    hidden = seed_hidden_world(harness.target or harness.db, harness.service, tmp_path)
    ensure_agent(harness, TRIAGE)
    ensure_agent(harness, CONTROL)
    filed = {
        "triage_open": file_proposal(harness, TRIAGE, hidden.ids["open"]),
        "triage_plain": file_proposal(harness, TRIAGE, "NOSUCH"),
        "triage_privileged": file_proposal(harness, TRIAGE, hidden.ids["privileged"]),
        "control_open": file_proposal(harness, CONTROL, hidden.ids["open"]),
        "control_plain": file_proposal(harness, CONTROL, "NOSUCH"),
    }
    ada = cast.clients["ada"]
    assert (
        ada.post("/admin/agents/stop", json={"agent": TRIAGE, "reason": "review"}).status_code
        == 200
    )
    assert (
        ada.post("/admin/agents/stop", json={"agent": CONTROL, "reason": "review"}).status_code
        == 200
    )
    return {"hidden": hidden, "filed": filed}


READERS = (
    ("admin", "user:ada", {"held": 2}),  # an admin without a clearance row: not named
    ("user", "user:uma", {"held": 2}),
    ("controller", "user:dora", {"held": 2}),
    ("lowest", None, {"held": 2}),
    ("named", "user:amy", {"held": 3}),  # named on the privileged item: it counts for her
)


@pytest.mark.parametrize(("reader", "actor", "expect"), READERS)
def test_five_readers_count_only_what_they_may_read_and_name_nothing_hidden(
    harness: Harness,
    cast: Cast,
    tmp_path: Path,
    reader: str,
    actor: str | None,
    expect: dict[str, int],
) -> None:
    world = stop_world(harness, cast, tmp_path)
    hidden, filed = world["hidden"], world["filed"]
    with harness.backend(readonly=True) as uow:
        conn = uow.conn()
        viewer = cf.viewer_for_actor(conn, actor) if actor else cf.LOWEST
        full = {row.agent: row for row in agent_stop.list_stopped(conn, viewer)}
        first = agent_stop.list_stopped(conn, viewer, limit=1)

    # TRIAGE's count is what the reader may see; CONTROL is the world that never had the privileged
    # proposal, so the non-named readers must count exactly as CONTROL does
    assert full[TRIAGE].held == expect["held"], reader
    assert full[CONTROL].held == 2, reader
    # the same answer at limit 1 (the first stopped agent is TRIAGE): filtered before any LIMIT
    assert [row.agent for row in first] == [TRIAGE]
    assert first[0].held == full[TRIAGE].held, reader

    # the serialised list names no hidden record, no title, no proposal id
    dumped = "".join(row.model_dump_json() for row in full.values())
    for hidden_text in (
        hidden.ids["privileged"],
        TOKENS["privileged"],
        filed["triage_privileged"],
    ):
        assert hidden_text not in dumped, (reader, hidden_text)


def test_the_admin_over_http_sees_the_same_held_count_and_no_hidden_name(
    harness: Harness, cast: Cast, tmp_path: Path
) -> None:
    world = stop_world(harness, cast, tmp_path)
    response = cast.clients["ada"].get("/admin/agents/stopped")
    assert response.status_code == 200, response.text
    rows = {row["agent"]: row for row in response.json()}
    assert rows[TRIAGE]["held"] == 2 and rows[CONTROL]["held"] == 2
    assert rows[TRIAGE]["reason"] == "review"
    hidden = world["hidden"]
    for leaked in (
        hidden.ids["privileged"],
        TOKENS["privileged"],
        world["filed"]["triage_privileged"],
    ):
        assert leaked not in response.text


# --- (4) agents and the admin routes, (5) the route count

STOP_ACTIONS = {
    "admin.agents.stop",
    "admin.agents.resume",
    "admin.agents.list",
    "admin.command.StopAgent",
    "admin.command.ResumeAgent",
}


@pytest.mark.parametrize("who", [BARE, TRIAGE])
def test_an_agent_token_is_403_on_stop_resume_and_the_stopped_list(
    harness: Harness, cast: Cast, who: str
) -> None:
    client = cast.clients[who]
    assert client.post("/admin/agents/stop", json={"agent": TRIAGE}).status_code == 403
    assert client.post("/admin/agents/resume", json={"agent": TRIAGE}).status_code == 403
    assert client.get("/admin/agents/stopped").status_code == 403


def test_the_agent_may_not_entries_for_the_stop_commands_are_present() -> None:
    assert STOP_ACTIONS <= AGENT_MAY_NOT


def test_the_walk_finds_the_stopped_list_route(harness: Harness) -> None:
    def listed(container: Any) -> list[Any]:  # an included router is one route with its own routes
        found: list[Any] = []
        for route in container:
            inner = getattr(route, "original_router", None)
            if inner is not None:
                found.extend(listed(inner.routes))
            else:
                found.append(route)
        return found

    found = [
        route
        for route in listed(harness.app.routes)
        if getattr(route, "path", None) == "/admin/agents/stopped"
        and "GET" in (getattr(route, "methods", None) or set())
    ]
    assert len(found) == 1
