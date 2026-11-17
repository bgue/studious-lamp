"""`ext_demo`, a module no platform file names, is served by the API (P2-X4 S5).

The fixture module lives in `tests/ext_demo/` and is added with `use_modules`; the command table
is rebuilt for it (the table is made once per import of `tl_api.commands`). Five readers read an
internal and a restricted note: a hidden note answers as a missing one (status, text, count).
`ExtDemoAddNote` runs for a person who holds the word, is refused without it and for an agent.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import tl_api.commands as commands_module
from fastapi.testclient import TestClient
from harness import SCOPE, Harness
from tl_adapters.db import create_schema
from tl_core import intent
from tl_core.auth import accounts, sessions
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role
from tl_core.auth.password import prepare_password
from tl_core.modules import load_modules, use_modules
from tl_core.services.commands import CommandResult

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests" / "ext_demo"))

from load import ext_demo_spec  # noqa: E402  # pyright: ignore[reportMissingImports]

PASSWORD = "correct horse battery"
ROUTE = "/modules/ext_demo/notes"
OPEN, HIDDEN, MISSING = "N-OPEN", "N-HIDDEN", "N-NONE"
OPEN_TEXT, HIDDEN_TEXT = "words anyone may read", "words only a clearance may read"
KEYS = (OPEN, HIDDEN, MISSING)
#: What each reader may read (the keys that answer 200). The anonymous reader reads nothing.
MAY_READ: dict[str | None, set[str]] = {
    None: set(),
    "bot": {OPEN},
    "bob": {OPEN},
    "ctl": {OPEN, HIDDEN},
    "boss": {OPEN, HIDDEN},
}


@pytest.fixture
def reimport() -> Iterator[Callable[[], Any]]:
    """Re-import ``tl_api.commands`` inside a block and put the real table back afterwards."""
    bodies = set(commands_module.COMMAND_BODIES)
    registered = set(intent._REGISTERED)  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
    saved = dict(vars(commands_module))  # the objects other modules hold (COMMANDS, COMMAND_BODIES)

    def run() -> Any:
        return importlib.reload(commands_module)

    try:
        yield run
    finally:
        importlib.reload(commands_module)
        for name in set(commands_module.COMMAND_BODIES) - bodies:
            commands_module.COMMAND_BODIES.pop(name)
        intent._REGISTERED.intersection_update(registered)  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
        # back to the original objects, not the reloaded ones
        commands_module.__dict__.update(saved)


def person(uow: Any, name: str, roles: list[str]) -> str:
    view = accounts.create_account(
        uow,
        username=name,
        display_name=name.title(),
        kind="person",
        roles=roles,
        password=prepare_password(PASSWORD),
        by="svc:test",
    )
    return view.account_id


class World:
    def __init__(self, h: Harness, tokens: dict[str | None, str]) -> None:
        self.h = h
        self.tokens = tokens

    def client(self, who: str | None) -> TestClient:
        client = self.h.client_for(None)
        if who is not None:
            client.headers.update({"Authorization": f"Bearer {self.tokens[who]}"})
        return client

    def get(self, who: str | None, key: str) -> Any:
        return self.client(who).get(f"{ROUTE}/{key}", params={"scope": SCOPE})

    def add(self, who: str, key: str, **fields: Any) -> Any:
        body = {"scope": SCOPE, "key": key, "title": f"Note {key}", "body": "x", **fields}
        return self.client(who).post("/commands/ExtDemoAddNote", json=body)


def seed_note(h: Harness, key: str, body: str, note_class: str) -> CommandResult:
    from tl_mod_ext_demo.commands import ExtDemoAddNote, handle_add_note  # pyright: ignore

    with h.backend(False) as uow:
        return handle_add_note(
            uow,
            ExtDemoAddNote(
                actor="user:seed",
                source="test",
                scope=SCOPE,
                key=key,
                title=f"Note {key}",
                body=body,
                note_class=note_class,  # pyright: ignore[reportArgumentType]
            ),
        )


@pytest.fixture
def world(
    new_db: Callable[[], str | Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reimport: Callable[[], Any],
) -> Iterator[World]:
    """A ledger and an app with ``ext_demo`` added (SQLite, and Postgres under --adapters)."""
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    with use_modules([*load_modules(), ext_demo_spec()]):
        reimport()
        target = new_db()
        create_schema(target)  # the module's projector makes ``ext_demo_note``
        h = Harness.build(tmp_path, target=target)
        try:
            with h.backend(False) as uow:
                person(uow, "bob", ["user"])
                person(uow, "ctl", ["document_controller"])
                person(uow, "boss", ["admin"])
                vic = person(uow, "vic", ["user"])
                bot = accounts.create_account(
                    uow, username="bot", display_name="Bot", kind="agent", roles=["user"],
                    password=None, by="svc:test",
                )  # fmt: skip
                _, agent_token = accounts.issue_agent_token(
                    uow,
                    account_id=bot.account_id,
                    label="ext_demo",
                    expires_at=datetime.now(UTC) + timedelta(days=1),
                    by="svc:test",
                )
                # vic holds only `viewer` for ext_demo here: no `user` word, so no notes written
                grant_module_role(
                    uow,
                    GrantModuleRole(
                        actor="user:boss", source="test", scope="company", account_id=vic,
                        project=SCOPE, module="ext_demo", role="viewer", reason="test",
                    ),
                )  # fmt: skip
            tokens: dict[str | None, str] = {
                name: sessions.sign_in(h.backend, username=name, password=PASSWORD)[1]
                for name in ("bob", "ctl", "boss", "vic")
            }
            tokens["bot"] = agent_token
            seed_note(h, OPEN, OPEN_TEXT, "internal")
            seed_note(h, HIDDEN, HIDDEN_TEXT, "restricted")
            yield World(h, tokens)
        finally:
            h.close()


def test_the_route_and_the_command_are_served_after_create_app(world: World) -> None:
    paths = world.h.app.openapi()["paths"]
    assert "get" in paths[f"{ROUTE}/{{key}}"]
    assert "post" in paths["/commands/ExtDemoAddNote"]
    assert world.get("bob", OPEN).json() == {
        "key": OPEN,
        "title": f"Note {OPEN}",
        "body": OPEN_TEXT,
    }


@pytest.mark.parametrize("who", [None, "bot", "bob", "ctl", "boss"])
def test_a_hidden_note_answers_as_a_missing_one_for_each_of_five_readers(
    world: World, who: str | None
) -> None:
    answers = {key: world.get(who, key) for key in KEYS}
    readable = {key for key, r in answers.items() if r.status_code == 200}
    assert readable == MAY_READ[who]  # the count of notes this reader reads
    hidden, missing = answers[HIDDEN], answers[MISSING]
    if HIDDEN not in MAY_READ[who]:
        assert (hidden.status_code, hidden.text) == (missing.status_code, missing.text)
        assert HIDDEN_TEXT not in hidden.text and HIDDEN not in hidden.text
        assert hidden.status_code == (401 if who is None else 404)
    else:
        assert hidden.json()["body"] == HIDDEN_TEXT
        assert missing.status_code == 404
    for response in answers.values():
        if response.status_code != 200:
            assert OPEN_TEXT not in response.text


def test_a_person_with_the_word_adds_a_note_and_a_restricted_one_stays_hidden(
    world: World,
) -> None:
    added = world.add("bob", "N-NEW", body="fresh", note_class="restricted")
    assert added.status_code == 200, added.text
    assert world.get("bob", "N-NEW").status_code == 404
    assert world.get("ctl", "N-NEW").json()["body"] == "fresh"
    plain = world.add("bob", "N-PLAIN", body="shared")
    assert plain.status_code == 200 and world.get("bot", "N-PLAIN").json()["body"] == "shared"


def test_the_command_is_refused_without_the_word_and_for_an_agent(world: World) -> None:
    refused = world.add("vic", "N-VIC")
    assert refused.status_code == 403 and "ext_demo" in refused.text, refused.text
    assert world.get("ctl", "N-VIC").status_code == 404  # nothing was written
    agent = world.add("bot", "N-BOT")
    assert agent.status_code == 403 and agent.json()["error"] == "agent_must_propose"
    assert world.get("ctl", "N-BOT").status_code == 404
    assert world.add("bob", "N-BAD", note_class="secret").status_code == 422
