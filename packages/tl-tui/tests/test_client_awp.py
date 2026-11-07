"""The awp reads on the embedded client, the API client and the fake (T03b): the same CWP."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fakes import FakeClient
from fakes_awp import seed_awp
from fastapi.testclient import TestClient
from tl_adapters.backend import open_backend
from tl_adapters.db import as_target, create_schema
from tl_api.app import create_app
from tl_api.client import ApiClient
from tl_api.settings import ApiSettings
from tl_api.tokens import TokenStore
from tl_core.auth import sessions
from tl_core.services.errors import RecordNotFoundError
from tl_tui.embedded import EmbeddedClient

ROOT = Path(__file__).resolve().parents[3]
PASSWORD = "correct horse battery"
READER = "vera"  # the awp viewer grant in the seed
PROJECT = "P123"
MISSING = "NO-SUCH"


def load_world() -> ModuleType:
    """The ``awp_world`` helper of the module tests (the S4 seed ledger), loaded by path."""
    name = "awp_world"
    if name in sys.modules:
        return sys.modules[name]
    path = ROOT / "packages" / "tl-modules" / "awp" / "tests" / "awp_world.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def plain(value: Any) -> Any:
    """A model or a list of models as plain data, so two answers can be compared."""
    if isinstance(value, list):
        return [plain(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")  # pyright: ignore[reportUnknownMemberType]
    return value


def reads(client: Any) -> dict[str, Any]:
    """The eight reads, called the same way on every client."""
    return {
        "list_cwps": lambda: client.list_cwps(PROJECT),
        "get_cwp": lambda: client.get_cwp(PROJECT, client.list_cwps(PROJECT)[0].number),
        "list_cwas": lambda: client.list_cwas(PROJECT),
        "wbs_tree": lambda: client.wbs_tree(PROJECT),
        "get_wbs_node": lambda: client.get_wbs_node(PROJECT, client.wbs_tree(PROJECT)[0].code),
        "get_path": lambda: client.get_path(PROJECT),
        "list_path_versions": lambda: client.list_path_versions(PROJECT),
        "list_packages": lambda: client.list_packages(PROJECT),
    }


def count(value: Any) -> int:
    """Rows of a list answer, the steps of a path answer, 1 for one record."""
    if isinstance(value, list):
        return len(value)  # pyright: ignore[reportUnknownArgumentType]
    return len(value.steps) if hasattr(value, "steps") else 1


class Clients:
    def __init__(self, embedded: EmbeddedClient, api: ApiClient, fake: FakeClient) -> None:
        self.embedded = embedded
        self.api = api
        self.fake = fake


@pytest.fixture(scope="module")
def clients(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Clients]:
    work = tmp_path_factory.mktemp("client-awp")
    db = work / "ledger.db"
    target = as_target(str(db))
    create_schema(target)
    world = load_world().World(target)
    world.people()
    world.editions()
    world.seed()
    embedded = EmbeddedClient.for_sqlite(db, actor=f"user:{READER}")
    tokens = work / "tokens.json"
    backend = open_backend(db)
    app = create_app(
        backend,
        settings=ApiSettings(db_path=db, tokens_path=tokens),
        tokens=TokenStore(tokens),
    )
    _, token = sessions.sign_in(backend, username=READER, password=PASSWORD)
    http = TestClient(app, raise_server_exceptions=False)
    api = ApiClient("http://testserver", token, http=http)
    fake = FakeClient()
    seed_awp(fake)
    try:
        yield Clients(embedded, api, fake)
    finally:
        api.close()
        http.close()
        backend.close()


@pytest.mark.parametrize("method", sorted(reads(FakeClient())))
def test_the_api_client_answers_what_the_embedded_client_answers(
    clients: Clients, method: str
) -> None:
    embedded = plain(reads(clients.embedded)[method]())
    api = plain(reads(clients.api)[method]())
    assert api == embedded


@pytest.mark.parametrize("method", sorted(reads(FakeClient())))
def test_every_client_answers_every_read(clients: Clients, method: str) -> None:
    for client in (clients.embedded, clients.api, clients.fake):
        answer = reads(client)[method]()
        assert count(answer) >= 0
    assert count(reads(clients.embedded)[method]()) >= 1 or method == "list_packages"
    assert count(reads(clients.fake)[method]()) >= 1


def test_the_embedded_and_the_api_client_return_the_same_cwp(clients: Clients) -> None:
    first = clients.embedded.list_cwps(PROJECT)[0].number
    assert first == "P123-CWP-CIV-0001"
    embedded = plain(clients.embedded.get_cwp(PROJECT, first))
    assert plain(clients.api.get_cwp(PROJECT, first)) == embedded
    assert embedded["number"] == first
    assert embedded["timeline"]  # the detail view of the route, as the fake serves it


def test_the_fake_answers_the_shape_of_the_embedded_detail(clients: Clients) -> None:
    fake = plain(clients.fake.get_cwp(PROJECT, clients.fake.list_cwps(PROJECT)[0].number))
    real = plain(clients.embedded.get_cwp(PROJECT, clients.embedded.list_cwps(PROJECT)[0].number))
    assert set(fake) == set(real)


@pytest.mark.parametrize("which", ["embedded", "api", "fake"])
def test_a_missing_cwp_and_a_missing_node_raise_record_not_found(
    clients: Clients, which: str
) -> None:
    client = getattr(clients, which)
    with pytest.raises(RecordNotFoundError):
        client.get_cwp(PROJECT, MISSING)
    with pytest.raises(RecordNotFoundError):
        client.get_wbs_node(PROJECT, MISSING)


@pytest.mark.parametrize("which", ["embedded", "api", "fake"])
def test_the_filters_reach_every_client(clients: Clients, which: str) -> None:
    client = getattr(clients, which)
    everything = client.list_cwps(PROJECT)
    states = {row.state for row in everything}
    one = sorted(states)[0]
    assert {r.state for r in client.list_cwps(PROJECT, state=one)} == {one}
    assert [r.code for r in client.wbs_tree(PROJECT, depth=1)] == [client.wbs_tree(PROJECT)[0].code]
    assert client.list_packages(PROJECT, kind="PWP") == [
        p for p in client.list_packages(PROJECT) if p.kind == "PWP"
    ]
