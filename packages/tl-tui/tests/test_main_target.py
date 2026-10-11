"""The embedded TUI opens its ledger from a SQLite path or a Postgres URL (P1-I0-S32).

Runs on the adapters named by ``--adapters``. The app is built the way ``tl tui`` builds it
(``make_app``), headless, and shows a record written through the same ledger by another client.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from tl_adapters.backend import BackendUnavailableError
from tl_adapters.db import DbTarget, create_schema
from tl_core.services.commands import CreateRecord
from tl_tui.embedded import EmbeddedClient
from tl_tui.main import make_app

SCOPE = "project:P123"


@pytest.fixture(autouse=True)
def _environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("TL_REMOTE", "TL_TYPE", "TL_PROJECT", "TL_DB"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def target(new_db: Callable[[], DbTarget]) -> DbTarget:
    found = new_db()
    create_schema(found)
    writer = EmbeddedClient.for_target(found)
    writer.create_record(
        CreateRecord(
            actor="user:t",
            source="test",
            scope=SCOPE,
            record_type="core.Record",
            key="P123-REC-0001",
            title="Bevel gauge",
        )
    )
    writer.close()
    return found


def test_make_app_shows_the_records_of_the_ledger_it_was_given(target: DbTarget) -> None:
    app = make_app(db=target)

    async def scenario(pilot: Pilot[object]) -> None:
        await pilot.pause()
        await pilot.pause()
        assert "P123-REC-0001" in screen_text(app)

    try:
        run_pilot(app, scenario)
    finally:
        close = getattr(app.client, "close", None)
        if callable(close):
            close()


def test_the_environment_names_the_ledger_when_no_option_does(
    target: DbTarget, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TL_DB", str(target))
    app = make_app()
    try:
        assert [r["key"] for r in app.client.list_records(SCOPE)] == ["P123-REC-0001"]
    finally:
        close = getattr(app.client, "close", None)
        if callable(close):
            close()


def test_an_unreachable_server_is_a_named_error() -> None:
    with pytest.raises(BackendUnavailableError, match="cannot reach the database"):
        make_app(db="postgresql://u:hunter2@127.0.0.1:1/tl?sslmode=disable")
