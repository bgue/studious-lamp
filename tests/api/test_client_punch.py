"""The punch reads and the command door on both clients (P2-PUNCH-T04).

The ledger is built by the quality module's commands (``punch_world.py``, loaded by path, never a
projection write) on one database. The embedded client and ``ApiClient`` over a ``TestClient`` sit
on that database, one per person: they must give equal answers for the three reads, and the
command door must change what the next read shows. A restricted correspondence item is the source
of one punch item: the lowest-clearance reader must not see it, a document controller must.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
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
from tl_mod_quality.commands import ClearPunchItem, RaisePunchItem, VerifyPunchItem
from tl_mod_quality.handlers.punch import MSG_SELF_VERIFY
from tl_tui.embedded import EmbeddedClient

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
PEOPLE = ("uma", "rob", "dora")  # uma: the lowest clearance; rob: verify word; dora: restricted
MISSING = "P123-PUN-9999"
OVERDUE = "2026-01-01"  # before the day the tests run


def load_world() -> ModuleType:
    """The quality module's ``punch_world`` helper, loaded by path (as the API punch test does)."""
    name = "punch_world"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "packages" / "tl-modules" / "quality" / "tests" / "punch_world.py"
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

    def keys_of(self, who: str) -> list[str]:
        return [row.key for row in self.api[who].list_punch_items(PROJECT).rows]


@pytest.fixture
def rig(
    tmp_path: Path, new_db: Callable[[], Any], monkeypatch: pytest.MonkeyPatch
) -> Iterator[Rig]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)  # the repository's fixture schema
    db = new_db()
    create_schema(db)
    factory = open_backend(db)
    world = load_world().World(db)
    world.people()
    tokens_path = tmp_path / "tokens.json"  # the API's static-token file; no static token is used
    # Each person signs in, so the API reads as that person's roles (a static token has none).
    tokens = {
        who: sessions.sign_in(factory, username=who, password=load_world().PASSWORD)[1]
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
    ids["open"] = world.raise_item(
        "uma",
        "Stair guard missing",
        area="L2",
        system="HVAC",
        due_on=OVERDUE,
        assignee="Ferrari",
        category="A",
    )
    ids["cleared"] = world.raise_item("uma", "Door closer loose")
    world.call("uma", "ClearPunchItem", punch_item=ids["cleared"], note="Tightened")
    ids["verified"] = world.raise_item("uma", "Cable tray gap")
    world.call("uma", "ClearPunchItem", punch_item=ids["verified"], note="Closed")
    world.call("rob", "VerifyPunchItem", punch_item=ids["verified"])
    ids["self"] = world.raise_item("rob", "Cleared by its raiser")
    world.call("rob", "ClearPunchItem", punch_item=ids["self"], note="Done")
    ids["secret"] = world.hidden_record()
    ids["from_secret"] = str(
        world.call(
            "dora", "RaisePunchItem", subject="From the secret", from_record_id=ids["secret"]
        ).stream_id
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


@pytest.mark.parametrize("who", PEOPLE)
def test_the_three_reads_give_equal_answers_on_both_clients(rig: Rig, who: str) -> None:
    api, emb = rig.api[who], rig.embedded[who]
    assert plain(api.list_punch_items(PROJECT)) == plain(emb.list_punch_items(PROJECT))
    assert plain(api.list_punch_items(PROJECT, state="Open", overdue=True)) == plain(
        emb.list_punch_items(PROJECT, state="Open", overdue=True)
    )
    assert plain(api.list_punch_items(PROJECT, from_key=rig.keys["secret"])) == plain(
        emb.list_punch_items(PROJECT, from_key=rig.keys["secret"])
    )
    assert plain(api.get_punch_item(PROJECT, rig.keys["open"])) == plain(
        emb.get_punch_item(PROJECT, rig.keys["open"])
    )
    assert api.get_punch_counts(PROJECT) == emb.get_punch_counts(PROJECT)


def test_the_lowest_clearance_reader_does_not_see_the_restricted_source(rig: Rig) -> None:
    secret = rig.keys["from_secret"]
    for client in (rig.api["uma"], rig.embedded["uma"]):
        page = client.list_punch_items(PROJECT)
        assert secret not in [row.key for row in page.rows]
        assert page.total == len(page.rows) == 4
        assert sum(client.get_punch_counts(PROJECT).values()) == 4
        with pytest.raises(RecordNotFoundError):
            client.get_punch_item(PROJECT, secret)
    for client in (rig.api["dora"], rig.embedded["dora"]):
        assert secret in [row.key for row in client.list_punch_items(PROJECT).rows]
        assert client.get_punch_item(PROJECT, secret).row.source_key == rig.keys["secret"]


def test_a_missing_or_hidden_key_is_one_not_found_text_on_both(rig: Rig) -> None:
    texts: set[str] = set()
    for client in (rig.api["uma"], rig.embedded["uma"]):
        for key in (MISSING, rig.keys["from_secret"]):
            with pytest.raises(RecordNotFoundError) as raised:
                client.get_punch_item(PROJECT, key)
            texts.add(str(raised.value))
    assert len(texts) == 1


def test_the_command_door_changes_state_and_the_next_read_shows_it(rig: Rig) -> None:
    before = len(rig.keys_of("uma"))
    raised = rig.api["uma"].quality_command(
        "RaisePunchItem",
        RaisePunchItem(actor="user:uma", source="tui", scope=SCOPE, subject="Via the door"),
    )
    assert raised.stream_id
    assert len(rig.keys_of("uma")) == before + 1
    assert len(rig.embedded["uma"].list_punch_items(PROJECT).rows) == before + 1

    rig.embedded["uma"].quality_command(
        "ClearPunchItem",
        ClearPunchItem(
            actor="user:uma", source="tui", scope=SCOPE, punch_item=rig.ids["open"], note="Done"
        ),
    )
    assert rig.api["uma"].get_punch_item(PROJECT, rig.keys["open"]).row.state == "Cleared"
    assert rig.embedded["uma"].get_punch_item(PROJECT, rig.keys["open"]).row.state == "Cleared"


def test_the_clearer_may_not_verify_through_either_client(rig: Rig) -> None:
    verify = VerifyPunchItem(
        actor="user:rob", source="tui", scope=SCOPE, punch_item=rig.ids["self"]
    )
    with pytest.raises(ForbiddenError) as embedded:
        rig.embedded["rob"].quality_command("VerifyPunchItem", verify)
    with pytest.raises(ForbiddenError) as remote:
        rig.api["rob"].quality_command("VerifyPunchItem", verify)
    assert MSG_SELF_VERIFY in str(embedded.value)
    assert MSG_SELF_VERIFY in str(remote.value)
    assert rig.embedded["rob"].get_punch_item(PROJECT, rig.keys["self"]).row.state == "Cleared"
