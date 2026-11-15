"""The scaffold commands through the API command door (P2-I4B-T09a, pre-hook form).

The nine scaffold commands sit in ``COMMANDS`` through one splat line over ``SCAFFOLD_COMMANDS``.
The ledger (a requisition raised and approved, then the register) is built by the scaffold
module's own world helper (``scaffold_world.py``, loaded by path as ``test_api_punch.py`` loads
``punch_world.py``), never by a projection write. Access is checked by the door as for any command.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from harness import Harness
from tl_adapters.db import open_uow
from tl_core.auth import accounts, sessions
from tl_mod_scaffold.views import scaffold_list

ROOT = Path(__file__).resolve().parents[3]
PASSWORD = "correct horse battery"
SCOPE = "project:P123"
NAMES = {
    "RegisterScaffold": "scaffold.register",
    "DesignScaffold": "scaffold.design",
    "ErectScaffold": "scaffold.erect",
    "InspectScaffold": "scaffold.inspect",
    "TagScaffoldGreen": "scaffold.tag.green",
    "ReleaseScaffold": "scaffold.release",
    "ModifyScaffold": "scaffold.modify",
    "DismantleScaffold": "scaffold.dismantle",
    "RemoveScaffold": "scaffold.remove",
}
MESSAGE = "agents propose record changes through MCP (P0-I6 D4); a human accepts them"


def load_world() -> ModuleType:
    """The scaffold module's ``scaffold_world`` helper (the S1 ledger), loaded by path."""
    name = "scaffold_world"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "packages" / "tl-modules" / "scaffold" / "tests" / "scaffold_world.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Seeded:
    def __init__(self, h: Harness, world: Any) -> None:
        self.h = h
        self.world = world
        self.tokens: dict[str, str] = {}
        self.request = ""  # an approved scaffold request, the register's source
        self.request_key = ""


class Rig:
    def __init__(self, seeded: Seeded) -> None:
        self.s = seeded
        self.h = seeded.h

    def client(self, who: str) -> Any:
        client = self.h.client_for(None)
        client.headers.update({"Authorization": f"Bearer {self.s.tokens[who]}"})
        return client

    def post(self, who: str, name: str, body: dict[str, Any]) -> Any:
        return self.client(who).post(f"/commands/{name}", json={"scope": SCOPE, **body})


def seed(h: Harness) -> Seeded:
    target = h.target or h.db
    world = load_world().World(target)
    world.people()
    with h.backend(False) as uow:
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
            label="scaffold",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            by="svc:test",
        )
    s = Seeded(h, world)
    s.tokens = {
        name: sessions.sign_in(h.backend, username=name, password=PASSWORD)[1]
        for name in ("uma", "rob", "sue", "vera")
    }
    s.tokens["bot"] = agent_token
    s.request = world.request()
    s.request_key = str(world.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=s.request))
    return s


@pytest.fixture(scope="module")
def rig(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Rig]:
    h = Harness.build(tmp_path_factory.mktemp("api-scaffold"))
    try:
        yield Rig(seed(h))
    finally:
        h.close()


def test_the_nine_names_are_in_the_table_once_each_with_their_word(rig: Rig) -> None:
    from tl_api.commands import COMMANDS

    rows = [spec for spec in COMMANDS if spec.module == "scaffold"]
    assert sorted(spec.name for spec in rows) == sorted(NAMES)
    assert len({spec.name for spec in COMMANDS}) == len(COMMANDS)  # no duplicate name
    assert {spec.name: spec.access for spec in rows} == NAMES
    paths = rig.h.app.openapi()["paths"]
    assert {f"/commands/{name}" for name in NAMES} <= set(paths)


def test_a_person_with_the_word_registers_through_the_door_and_the_register_reads_it(
    rig: Rig,
) -> None:
    response = rig.post("uma", "RegisterScaffold", {"request_id": rig.s.request, "title": "A"})
    assert response.status_code == 200, response.text
    with open_uow(rig.s.h.target or rig.s.h.db, readonly=True) as uow:
        page = scaffold_list(uow.conn(), SCOPE)
    rows = [r for r in page.rows if r.request_key == rig.s.request_key]
    assert len(rows) == 1
    assert rows[0].subject == "A" and rows[0].state == "Requested"


def test_a_person_without_the_register_word_is_refused_and_writes_no_event(rig: Rig) -> None:
    before = rig.s.world.count()
    response = rig.post("vera", "RegisterScaffold", {"request_id": rig.s.request, "title": "B"})
    assert response.status_code == 403, response.text
    assert rig.s.world.count() == before


def test_tagging_green_is_refused_to_a_plain_user_and_opened_to_the_controller(
    rig: Rig,
) -> None:
    made = rig.s.world.register()
    rig.s.world.advance(made, "Erecting")
    before = rig.s.world.count()
    refused = rig.post("uma", "TagScaffoldGreen", {"scaffold": made})
    assert refused.status_code == 403, refused.text
    assert rig.s.world.count() == before
    granted = rig.post("sue", "TagScaffoldGreen", {"scaffold": made})
    assert granted.status_code == 200, granted.text


def test_an_agent_token_is_refused_register_with_the_proposal_reason(rig: Rig) -> None:
    before = rig.s.world.count()
    response = rig.post("bot", "RegisterScaffold", {"request_id": rig.s.request, "title": "D"})
    assert response.status_code == 403, response.text
    assert response.json()["error"] == "agent_must_propose"
    assert response.json()["message"] == MESSAGE
    assert rig.s.world.count() == before


def test_the_door_refuses_a_reserved_field(rig: Rig) -> None:
    """``actor`` is not a body field (extra fields are refused); a ``source`` the server reserves
    (``svc:``) is refused as a reserved identifier, before the handler runs."""
    before = rig.s.world.count()
    forged = rig.post(
        "uma", "RegisterScaffold", {"request_id": rig.s.request, "title": "Forged", "actor": "x"}
    )
    assert forged.status_code == 422, forged.text
    reserved = rig.post(
        "uma",
        "RegisterScaffold",
        {"request_id": rig.s.request, "title": "Forged", "source": "svc:scaffold"},
    )
    assert reserved.status_code == 422, reserved.text
    assert reserved.json()["error"] == "reserved_identifier"
    assert rig.s.world.count() == before
