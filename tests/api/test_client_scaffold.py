"""The scaffold reads on both clients (P2-I4B-T09b2): the embedded client and ``ApiClient``.

The ledger is built by the scaffold module's commands (``scaffold_world.py``, loaded by path, never
a projection write) on one database. The embedded client and ``ApiClient`` over a ``TestClient``
sit on that database, one per person: they must give equal answers for the four reads, a missing
key is one not-found text on both, and an export format other than csv or jsonl is a ``ValueError``
on both. No scaffold here is hidden, so no projection write is made.
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
from tl_core.services.errors import RecordNotFoundError
from tl_mod_scaffold.views import EXPORT_COLUMNS
from tl_tui.embedded import EmbeddedClient

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "P123"
PEOPLE = ("uma", "rob", "sue")  # uma registers and inspects; rob holds no grant; sue tags green
MISSING = "P123-SCF-9999"


def load_world() -> ModuleType:
    """The scaffold module's ``scaffold_world`` helper, loaded by path (as the punch test does)."""
    name = "scaffold_world"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "packages" / "tl-modules" / "scaffold" / "tests" / "scaffold_world.py"
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
    api: dict[str, ApiClient]
    embedded: dict[str, EmbeddedClient]
    keys: dict[str, str]


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
    ids["designed"] = world.register(location_text="Unit 1")
    world.advance_as(ids["designed"], "Designed", "uma")
    ids["erecting"] = world.register(location_text="Unit 2")
    world.advance_as(ids["erecting"], "Erecting", "uma")
    ids["inspected"] = world.register(location_text="Unit 3")
    world.advance_as(ids["inspected"], "Erecting", "uma")
    world.call("sue", "TagScaffoldGreen", scaffold=ids["inspected"])
    ids["in_use"] = world.register(location_text="Unit 4")
    world.advance_as(ids["in_use"], "Erecting", "uma")
    world.call("sue", "TagScaffoldGreen", scaffold=ids["in_use"])
    world.call("uma", "ReleaseScaffold", scaffold=ids["in_use"])
    world.call(
        "uma",
        "InspectScaffold",
        scaffold=ids["in_use"],
        result="conditional",
        note="Toe boards",
    )
    # a subject a spreadsheet would read as a formula: the CSV guard must answer the same
    ids["formula"] = str(
        world.call(
            "uma",
            "RegisterScaffold",
            request_id=world.request(),
            title="=SUM(A1)",
            location_text="Unit 5",
        ).stream_id
    )
    keys = {
        name: str(world.scalar("SELECT key FROM cur_core_record WHERE id = :id", id=record))
        for name, record in ids.items()
    }
    try:
        yield Rig(api, embedded, keys)
    finally:
        http.close()
        factory.close()


@pytest.mark.parametrize("who", PEOPLE)
def test_the_four_reads_give_equal_answers_on_both_clients(rig: Rig, who: str) -> None:
    api, emb = rig.api[who], rig.embedded[who]
    assert plain(api.list_scaffolds(PROJECT)) == plain(emb.list_scaffolds(PROJECT))
    assert plain(api.list_scaffolds(PROJECT, limit=2)) == plain(
        emb.list_scaffolds(PROJECT, limit=2)
    )
    assert plain(api.list_scaffolds(PROJECT, state="In Use", tag="green")) == plain(
        emb.list_scaffolds(PROJECT, state="In Use", tag="green")
    )
    assert plain(api.list_scaffolds(PROJECT, overdue=True)) == plain(
        emb.list_scaffolds(PROJECT, overdue=True)
    )
    assert plain(api.get_scaffold(PROJECT, rig.keys["in_use"])) == plain(
        emb.get_scaffold(PROJECT, rig.keys["in_use"])
    )
    assert plain(api.list_scaffolds_due(PROJECT)) == plain(emb.list_scaffolds_due(PROJECT))
    assert api.export_scaffolds(PROJECT) == emb.export_scaffolds(PROJECT)
    assert api.export_scaffolds(PROJECT, fmt="jsonl") == emb.export_scaffolds(PROJECT, fmt="jsonl")


def test_the_reads_carry_the_rows_the_total_and_the_inspections(rig: Rig) -> None:
    page = rig.api["uma"].list_scaffolds(PROJECT)
    assert page.total == len(page.rows) == 5
    assert [row.key for row in page.rows] == sorted(rig.keys.values())
    limited = rig.api["uma"].list_scaffolds(PROJECT, limit=2)
    assert limited.total == 5 and len(limited.rows) == 2
    detail = rig.embedded["uma"].get_scaffold(PROJECT, rig.keys["in_use"])
    # the green tag is a pass inspection; the conditional one follows it (oldest first)
    assert detail.inspection_count == 2
    assert [item.result for item in detail.inspections] == ["pass", "conditional"]
    assert plain(rig.api["uma"].get_scaffold(PROJECT, rig.keys["in_use"])) == plain(detail)
    csv_text = rig.api["uma"].export_scaffolds(PROJECT)
    assert csv_text.splitlines()[0] == ",".join(EXPORT_COLUMNS)
    assert "'=SUM(A1)" in csv_text


def test_a_missing_key_is_one_not_found_text_on_both(rig: Rig) -> None:
    texts: set[str] = set()
    for client in (rig.api["uma"], rig.embedded["uma"]):
        with pytest.raises(RecordNotFoundError) as raised:
            client.get_scaffold(PROJECT, MISSING)
        texts.add(str(raised.value))
    assert len(texts) == 1


def test_an_export_format_other_than_csv_or_jsonl_is_a_value_error_on_both(rig: Rig) -> None:
    for client in (rig.api["uma"], rig.embedded["uma"]):
        with pytest.raises(ValueError):
            client.export_scaffolds(PROJECT, fmt="xml")
