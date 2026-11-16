"""The permit, isolation and gas-test reads and the permit command door on both clients
(P2-PTW-T10).

The ledger is built by the permits module's commands (``permit_world.py``, loaded by path, never a
projection write) on one database. The embedded client and ``ApiClient`` over a ``TestClient`` sit
on that database, one per person: they must give equal answers for the six reads, and the command
door must change what the next read shows. A permit for a restricted correspondence item is hidden
from the lowest-clearance reader (``uma``); a document controller (``dora``) reads it. The clock is
the world's (``world.at``): the handlers and the two read paths are pointed at it, so a Lapsed
permit is read by moving that clock past the stored ``valid_until``, never by sleeping.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tl_adapters.db import create_schema
from tl_api.app import create_app
from tl_api.backend import open_backend
from tl_api.client import ApiClient
from tl_api.settings import ApiSettings
from tl_api.tokens import TokenStore
from tl_core.auth import sessions
from tl_core.auth.errors import ForbiddenError
from tl_core.services.errors import RecordNotFoundError
from tl_mod_permits import routes as permit_routes
from tl_mod_permits.commands import ApprovePermit
from tl_mod_permits.handlers import common as common_handlers
from tl_mod_permits.handlers import permit as permit_handlers
from tl_mod_permits.handlers.permit import MSG_SELF_APPROVE
from tl_tui import embedded as embedded_module
from tl_tui.embedded import EmbeddedClient

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
PEOPLE = ("uma", "rob", "pam", "sue", "dora")  # uma: the lowest clearance; dora: restricted
MISSING_PERMIT = "P123-PTW-9999"
MISSING_ISOLATION = "P123-ISL-9999"


def _load(name: str) -> ModuleType:
    """A permits-module test helper, loaded by path (the module is not on the import path)."""
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "packages" / "tl-modules" / "permits" / "tests" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def plain(value: Any) -> Any:
    """Dataclasses, lists and dicts as plain data, so two clients' answers can be compared."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    if isinstance(value, list):
        return [plain(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
    return value


@dataclass
class Rig:
    world: Any
    api: dict[str, ApiClient]
    embedded: dict[str, EmbeddedClient]
    ids: dict[str, str]
    keys: dict[str, str]


@pytest.fixture
def rig(
    tmp_path: Path, new_db: Callable[[], Any], monkeypatch: pytest.MonkeyPatch
) -> Iterator[Rig]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)  # the repository's fixture schema
    db = new_db()
    create_schema(db)
    factory = open_backend(db)
    world = _load("permit_world").World(db)
    world.people()
    # A controller cleared for the restricted record (sue and pam cannot see it).
    world.person("dan", ("user", "document_controller"), grant="superuser")
    # One clock for the handlers (the commands) and for the two read paths.
    monkeypatch.setattr(permit_handlers, "now", lambda: world.at)
    monkeypatch.setattr(common_handlers, "now", lambda: world.at)
    monkeypatch.setattr(embedded_module, "utcnow", lambda: world.at)
    monkeypatch.setattr(permit_routes, "utcnow", lambda: world.at)

    tokens_path = tmp_path / "tokens.json"  # the API's static-token file; no static token is used
    # Each person signs in, so the API reads as that person's roles (a static token has none).
    tokens = {
        who: sessions.sign_in(factory, username=who, password=_load("permit_world").PASSWORD)[1]
        for who in PEOPLE
    }
    app = create_app(
        factory,
        settings=ApiSettings(db_path=db, tokens_path=tokens_path),
        tokens=TokenStore(tokens_path),
    )
    http = TestClient(app, raise_server_exceptions=False)
    api = {who: ApiClient("http://testserver", tokens[who], http=http) for who in PEOPLE}
    embedded = {who: EmbeddedClient(factory, actor=f"user:{who}") for who in PEOPLE}

    ids: dict[str, str] = {}
    ids["requested"] = world.request("rob", "general")
    ids["approved"] = world.approved("general")
    ids["active"] = world.active("general")
    ids["other"] = world.request("rob", "hot_work")
    ids["secret"] = world.request("dora", "general", for_record_id=world.hidden_record())
    world.call("dan", "ApprovePermit", permit=ids["secret"])
    world.issue(ids["secret"], who="dan")
    ids["isolation"] = world.isolation(ids["active"], verified=True)
    world.call(
        "uma",
        "RecordGasTest",
        permit=ids["active"],
        instrument_text="MX6",
        o2_pct="20.9",
        co_ppm="3",
        taken_at=world.at - timedelta(minutes=10),
    )
    keys = {
        name: str(world.scalar("SELECT key FROM cur_core_record WHERE id = :id", id=record))
        for name, record in ids.items()
    }
    try:
        yield Rig(world, api, embedded, ids, keys)
    finally:
        http.close()
        factory.close()


def _iso_key(rig: Rig) -> str:
    return str(
        rig.world.scalar("SELECT key FROM cur_core_record WHERE id = :id", id=rig.ids["isolation"])
    )


@pytest.mark.parametrize("who", ("uma", "rob", "dora"))
def test_the_six_reads_give_equal_answers_on_both_clients(rig: Rig, who: str) -> None:
    api, emb = rig.api[who], rig.embedded[who]
    active = rig.keys["active"]
    assert plain(api.list_permits(PROJECT)) == plain(emb.list_permits(PROJECT))
    assert plain(api.list_permits(PROJECT, state="Active")) == plain(
        emb.list_permits(PROJECT, state="Active")
    )
    assert plain(api.get_permit(PROJECT, active)) == plain(emb.get_permit(PROJECT, active))
    assert plain(api.get_permit_board(PROJECT)) == plain(emb.get_permit_board(PROJECT))
    assert plain(api.list_isolations(PROJECT)) == plain(emb.list_isolations(PROJECT))
    assert plain(api.get_isolation(PROJECT, _iso_key(rig))) == plain(
        emb.get_isolation(PROJECT, _iso_key(rig))
    )
    assert plain(api.list_gas_tests(PROJECT, active)) == plain(emb.list_gas_tests(PROJECT, active))


def test_a_controller_who_is_not_the_requester_approves_through_either_client(rig: Rig) -> None:
    requested = rig.keys["requested"]
    approve = ApprovePermit(
        actor="user:pam", source="tui", scope=SCOPE, permit=rig.ids["requested"]
    )
    rig.api["pam"].permit_command("ApprovePermit", approve)
    assert rig.api["uma"].get_permit(PROJECT, requested).row.state == "Approved"
    assert rig.embedded["uma"].get_permit(PROJECT, requested).row.state == "Approved"

    second = rig.world.request("rob", "general")
    second_key = str(rig.world.scalar("SELECT key FROM cur_core_record WHERE id = :id", id=second))
    rig.embedded["pam"].permit_command(
        "ApprovePermit",
        ApprovePermit(actor="user:pam", source="tui", scope=SCOPE, permit=second),
    )
    assert rig.api["pam"].get_permit(PROJECT, second_key).row.state == "Approved"
    assert rig.embedded["pam"].get_permit(PROJECT, second_key).row.state == "Approved"


def test_the_requester_may_not_approve_through_either_client(rig: Rig) -> None:
    own = rig.world.request("sue", "general")
    key = str(rig.world.scalar("SELECT key FROM cur_core_record WHERE id = :id", id=own))
    approve = ApprovePermit(actor="user:sue", source="tui", scope=SCOPE, permit=own)
    with pytest.raises(ForbiddenError) as embedded:
        rig.embedded["sue"].permit_command("ApprovePermit", approve)
    with pytest.raises(ForbiddenError) as remote:
        rig.api["sue"].permit_command("ApprovePermit", approve)
    assert MSG_SELF_APPROVE in str(embedded.value)
    assert MSG_SELF_APPROVE in str(remote.value)
    assert rig.embedded["sue"].get_permit(PROJECT, key).row.state == "Requested"


def test_a_missing_key_is_one_not_found_text_on_both(rig: Rig) -> None:
    permit_texts: set[str] = set()
    iso_texts: set[str] = set()
    for client in (rig.api["uma"], rig.embedded["uma"]):
        with pytest.raises(RecordNotFoundError) as permit:
            client.get_permit(PROJECT, MISSING_PERMIT)
        with pytest.raises(RecordNotFoundError) as gas:
            client.list_gas_tests(PROJECT, MISSING_PERMIT)
        with pytest.raises(RecordNotFoundError) as iso:
            client.get_isolation(PROJECT, MISSING_ISOLATION)
        permit_texts.update({str(permit.value), str(gas.value)})
        iso_texts.add(str(iso.value))
    assert permit_texts == {"no permit"}
    assert iso_texts == {"no isolation"}


def test_a_permit_for_a_restricted_record_is_absent_for_the_lowest_clearance(rig: Rig) -> None:
    secret = rig.keys["secret"]
    for client in (rig.api["uma"], rig.embedded["uma"]):
        page = client.list_permits(PROJECT)
        assert secret not in [row.key for row in page.rows]
        assert page.total == len(page.rows)
        assert sum(client.get_permit_board(PROJECT).counts.values()) == 1  # the active one only
        with pytest.raises(RecordNotFoundError, match="no permit"):
            client.get_permit(PROJECT, secret)
        with pytest.raises(RecordNotFoundError, match="no permit"):
            client.list_gas_tests(PROJECT, secret)
    for client in (rig.api["dora"], rig.embedded["dora"]):
        assert secret in [row.key for row in client.list_permits(PROJECT).rows]
        assert client.get_permit(PROJECT, secret).row.state == "Active"


def test_a_lapsed_permit_reads_lapsed_on_both_clients(rig: Rig) -> None:
    active = rig.keys["active"]
    before = rig.api["uma"].get_permit(PROJECT, active)
    assert before.row.state == "Active"
    assert before.row.valid_until is not None
    rig.world.at = before.row.valid_until + timedelta(minutes=1)  # the clock moves, nothing sleeps
    assert rig.api["uma"].get_permit(PROJECT, active).row.state == "Lapsed"
    assert rig.embedded["uma"].get_permit(PROJECT, active).row.state == "Lapsed"
    assert rig.api["uma"].get_permit_board(PROJECT).counts["Lapsed"] == 1
    assert rig.embedded["uma"].get_permit_board(PROJECT).counts["Lapsed"] == 1
