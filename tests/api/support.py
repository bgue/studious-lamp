"""Support for the API round-trip test: a real app and an embedded client on one SQLite ledger."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_adapters.sqlite.uow import create_schema
from tl_api.app import create_app
from tl_api.client import ApiClient
from tl_api.settings import ApiSettings
from tl_api.tokens import TokenStore, add_token
from tl_tui.embedded import EmbeddedClient

ACTOR = "user:alice"


@dataclass
class Pair:
    remote: ApiClient
    embedded: EmbeddedClient
    factory: SqliteUowFactory
    http: TestClient

    def close(self) -> None:
        self.http.close()
        self.factory.close()


def build_pair(root: Path) -> Pair:
    db = root / "tl.db"
    create_schema(db)
    factory = SqliteUowFactory(db)
    tokens_path = root / "tokens.json"
    token = add_token(tokens_path, ACTOR)
    app = create_app(
        factory,
        settings=ApiSettings(db_path=db, tokens_path=tokens_path),
        tokens=TokenStore(tokens_path),
    )
    http = TestClient(app, raise_server_exceptions=False)
    remote = ApiClient("http://testserver", token, http=http)
    return Pair(remote, EmbeddedClient(factory), factory, http)
