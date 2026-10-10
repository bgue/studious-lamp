"""A real suite for the HTTP client tests: the API app over a temporary SQLite ledger.

``Suite.client(identity, clock)`` is an ``HttpSimClient`` that talks to the app in process through
a Starlette ``TestClient`` (an httpx2 client), with the same request stamping the real
``connect()`` installs. Nothing about the suite is mocked.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_adapters.sqlite.uow import create_schema
from tl_api.app import create_app
from tl_api.client import ApiClient
from tl_api.settings import ApiSettings
from tl_api.tokens import TokenStore, add_token
from tl_sim.client import HttpSimClient, Keys, install_stamp
from tl_sim.clock import SimClock

RUN_ID = "rt1"
SCOPE = f"project:sim-{RUN_ID}"
START = datetime(2026, 11, 2, 7, 0, tzinfo=UTC)
IDENTITIES = [
    "user:sim-orchestrator",
    "user:sim-document_controller",
    "user:sim-planner",
    "user:sim-crew",
    "user:sim-approver",
    "agent:sim-assistant",
    "user:alice",
]


@dataclass
class Suite:
    tokens: dict[str, str]
    backend: SqliteUowFactory
    app_client: TestClient
    keys: Keys
    http: list[TestClient]

    def api(self, identity: str, clock: SimClock | None = None) -> ApiClient:
        http = TestClient(self.app_client.app, raise_server_exceptions=False)
        self.http.append(http)
        if clock is not None:
            install_stamp(http, clock)
        return ApiClient("http://testserver", self.tokens[identity], http=http)

    def client(self, identity: str, clock: SimClock | None = None, **kw: object) -> HttpSimClient:
        clock = clock or SimClock(START)
        return HttpSimClient(
            self.api(identity, clock),  # type: ignore[arg-type]
            run_id=RUN_ID,
            scope=SCOPE,
            clock=clock,
            keys=self.keys,
            identity=identity,
            **kw,  # type: ignore[arg-type]
        )


def build_suite(tmp_path: Path) -> Suite:
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = tmp_path / "tl.db"
    create_schema(db)
    backend = SqliteUowFactory(db)
    tokens_path = tmp_path / "tokens.json"
    tokens = {who: add_token(tokens_path, who) for who in IDENTITIES}
    settings = ApiSettings(db_path=db, tokens_path=tokens_path, poll_interval_s=0.05)
    app = create_app(backend, settings=settings, tokens=TokenStore(tokens_path))
    return Suite(tokens, backend, TestClient(app), Keys(RUN_ID, {}), [])


def close_suite(built: Suite) -> None:
    for http in built.http:
        http.close()
    built.app_client.close()
    built.backend.close()
