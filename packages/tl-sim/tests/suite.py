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
from tl_adapters.objectstore.fs import FsObjectStore
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_adapters.sqlite.uow import create_schema
from tl_api.app import create_app
from tl_api.client import ApiClient
from tl_api.settings import ApiSettings
from tl_api.tokens import TokenStore, add_token
from tl_core.files.service import FileService
from tl_sim.client import HttpSimClient, Keys, install_stamp
from tl_sim.clock import SimClock

ACME = (
    Path(__file__).resolve().parents[3]
    / "schema"
    / "fixtures"
    / "standards"
    / "co.acme.standards@1.0.0.yaml"
)
ACME_DOCUMENTS = ACME.with_name("co.acme.documents@1.0.0.yaml")
RUN_ID = "rt1"
SCOPE = f"project:sim-{RUN_ID}"
START = datetime(2026, 11, 2, 7, 0, tzinfo=UTC)
IDENTITIES = [
    "user:sim-orchestrator",
    "user:sim-document_controller",
    "user:sim-planner",
    "user:sim-crew",
    "user:sim-tag_clerk",
    "user:sim-document_registrar",
    "user:sim-schedule_updater",
    "user:sim-rfi_author",
    "user:sim-client_rep",
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
    db: Path

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


def build_suite(tmp_path: Path, *, standards: bool = False, objects: bool = False) -> Suite:
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = tmp_path / "tl.db"
    create_schema(db)
    backend = SqliteUowFactory(db)
    tokens_path = tmp_path / "tokens.json"
    tokens = {who: add_token(tokens_path, who) for who in IDENTITIES}
    settings = ApiSettings(db_path=db, tokens_path=tokens_path, poll_interval_s=0.05)
    if standards:  # the company and the document standards, as `tl standards load` leaves them
        from tl_mod_engineering.document import load_standards_file
        from tl_mod_engineering.loader import load_standards

        with backend(False) as uow:
            load_standards(uow, load_standards_file(ACME), actor="user:seed", source="test")
            load_standards(
                uow, load_standards_file(ACME_DOCUMENTS), actor="user:seed", source="test"
            )
    store = FsObjectStore(tmp_path / "objects", secret=b"k") if objects else None
    files = FileService(store, secret=b"s") if store is not None else None
    app = create_app(
        backend,
        settings=settings,
        tokens=TokenStore(tokens_path),
        object_store=store,
        files_service=files,
    )
    return Suite(tokens, backend, TestClient(app), Keys(RUN_ID, {}), [], db)


def close_suite(built: Suite) -> None:
    for http in built.http:
        http.close()
    built.app_client.close()
    built.backend.close()
