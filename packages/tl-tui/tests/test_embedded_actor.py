"""The embedded client is for a person: an agent actor is refused (WS-B review ruling)."""

from __future__ import annotations

from pathlib import Path

import pytest
from tl_adapters.sqlite.uow import create_schema
from tl_tui.embedded import EmbeddedClient
from tl_tui.main import build_app, make_app

MESSAGE = "agent_must_propose: an agent cannot use the embedded client to change records"


def test_the_code_is_the_one_the_api_and_the_cli_use() -> None:
    from tl_api.auth import AGENT_MUST_PROPOSE

    assert MESSAGE.startswith(AGENT_MUST_PROPOSE + ": ")


def test_an_agent_actor_is_refused_when_the_client_is_made(tmp_path: Path) -> None:
    db = tmp_path / "tl.db"
    create_schema(db)
    with pytest.raises(ValueError) as caught:
        EmbeddedClient.for_sqlite(db, actor="agent:triage")
    assert str(caught.value) == MESSAGE
    with pytest.raises(ValueError, match="agent_must_propose"):
        EmbeddedClient(lambda _readonly: None, actor="agent:x")  # type: ignore[arg-type,return-value]


def test_the_app_builders_pass_the_refusal_on(tmp_path: Path) -> None:
    db = tmp_path / "tl.db"
    create_schema(db)
    with pytest.raises(ValueError, match="agent_must_propose"):
        build_app(db, actor="agent:triage")
    with pytest.raises(ValueError, match="agent_must_propose"):
        make_app(db=db, actor="agent:triage")


def test_a_person_and_the_default_are_accepted(tmp_path: Path) -> None:
    db = tmp_path / "tl.db"
    create_schema(db)
    assert EmbeddedClient.for_sqlite(db).actor == "user:dev"
    assert EmbeddedClient.for_sqlite(db, actor="user:kim").actor == "user:kim"
