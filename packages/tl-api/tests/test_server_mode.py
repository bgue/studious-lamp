"""Server mode (P2-REL-S2): the bind policy, the prod start-up checks, dev tokens ignored."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_adapters.sqlite.uow import create_schema
from tl_api import main as server
from tl_api.app import create_app
from tl_api.settings import ApiSettings, check_bind
from tl_api.tokens import TokenStore, add_token
from tl_core.auth import accounts, seed

LOOPBACK = ("127.0.0.1", "::1", "localhost")
OPEN = ("0.0.0.0", "192.168.1.5", "example.com", "::")
PROD_ENVS = ("prod", "production", "staging", "whatever")
DEV_ENVS = ("dev", "test", "ci", "demo", None, "")


def env_of(name: str | None) -> dict[str, str]:
    return {} if name is None else {"TL_ENV": name}


@pytest.mark.parametrize("host", LOOPBACK)
@pytest.mark.parametrize("name", [*PROD_ENVS, *DEV_ENVS])
@pytest.mark.parametrize("insecure", [False, True])
def test_loopback_is_always_allowed(host: str, name: str | None, insecure: bool) -> None:
    check_bind(host, insecure_dev=insecure, env=env_of(name))


@pytest.mark.parametrize("host", OPEN)
@pytest.mark.parametrize("name", PROD_ENVS)
@pytest.mark.parametrize("insecure", [False, True])
def test_a_non_loopback_bind_is_allowed_for_a_deployment_name(
    host: str, name: str, insecure: bool
) -> None:
    check_bind(host, insecure_dev=insecure, env=env_of(name))


@pytest.mark.parametrize("host", OPEN)
@pytest.mark.parametrize("name", DEV_ENVS)
def test_a_non_loopback_bind_needs_insecure_dev_outside_a_deployment(
    host: str, name: str | None
) -> None:
    check_bind(host, insecure_dev=True, env=env_of(name))
    with pytest.raises(ValueError) as refused:
        check_bind(host, insecure_dev=False, env=env_of(name))
    text = str(refused.value)
    assert "TLS proxy" in text and "TL_ENV" in text and "Phase 0" not in text
    assert repr(host) in text


def test_check_bind_reads_the_process_environment_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TL_ENV", raising=False)
    with pytest.raises(ValueError):
        check_bind("0.0.0.0", insecure_dev=False)
    monkeypatch.setenv("TL_ENV", "prod")
    check_bind("0.0.0.0", insecure_dev=False)


# --- start-up checks -------------------------------------------------------------------------


@pytest.fixture
def ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "tl.db"
    create_schema(path)
    for name in ("TL_OBJECT_SECRET", "TL_TOKENS", "TL_TRUSTED_PROXY_HEADER", "TL_DB"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TL_ENV", "prod")
    return path


class FakeServer:
    started = True

    def run(self) -> None:
        return None


@pytest.fixture
def listens(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def fake(app: Any, settings: ApiSettings, on_started: Any) -> FakeServer:
        calls.append(settings.host)
        return FakeServer()

    monkeypatch.setattr(server, "started_server", fake)
    return calls


def run_main(ledger: Path, *extra: str) -> int:
    return server.main(["--db", str(ledger), "--host", "0.0.0.0", "--port", "9", *extra])


def test_a_prod_start_without_the_object_secret_exits_2_and_never_listens(
    ledger: Path, listens: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_main(ledger) == 2
    assert "TL_OBJECT_SECRET" in capsys.readouterr().err
    assert listens == []


def test_a_prod_start_with_the_secret_listens_and_says_whether_a_proxy_is_set(
    ledger: Path,
    listens: list[str],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("TL_OBJECT_SECRET", "s3cret-value-for-test")
    caplog.set_level(logging.INFO, logger="tl_api")
    assert run_main(ledger) == 0
    assert listens == ["0.0.0.0"]
    assert "serving on 0.0.0.0:9 behind TLS proxy: no" in caplog.text
    assert "s3cret-value-for-test" not in caplog.text
    caplog.clear()
    monkeypatch.setenv("TL_TRUSTED_PROXY_HEADER", "X-Forwarded-For")
    assert run_main(ledger) == 0
    assert "serving on 0.0.0.0:9 behind TLS proxy: yes" in caplog.text


def test_an_enabled_demo_account_stops_a_prod_start(
    ledger: Path,
    listens: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("TL_OBJECT_SECRET", "s3cret-value-for-test")
    assert seed.seed_demo(SqliteUowFactory(ledger), env="dev") is not None
    assert run_main(ledger) == 2
    err = capsys.readouterr().err
    assert "demo account" in err and "demo/demo" not in err.replace("(demo/demo)", "")
    assert listens == []


def test_a_token_file_is_ignored_with_one_log_line_in_a_prod_start(
    ledger: Path,
    listens: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("TL_OBJECT_SECRET", "s3cret-value-for-test")
    loose = tmp_path / "tokens.json"
    loose.write_text("{}")
    loose.chmod(0o644)  # the dev start would refuse this mode; a prod start does not read it
    caplog.set_level(logging.INFO, logger="tl_api")
    assert run_main(ledger, "--tokens", str(loose)) == 0
    assert caplog.text.count("dev token file is ignored") == 1


def test_a_loose_token_file_is_still_refused_outside_server_mode(
    ledger: Path, listens: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TL_ENV", "dev")
    loose = tmp_path / "tokens.json"
    loose.write_text("{}")
    loose.chmod(0o644)
    assert server.main(["--db", str(ledger), "--tokens", str(loose)]) == 2
    assert listens == []


def test_a_prod_env_on_loopback_does_not_need_the_object_secret(
    ledger: Path, listens: list[str]
) -> None:
    assert server.main(["--db", str(ledger), "--port", "9"]) == 0
    assert listens == ["127.0.0.1"]


def test_a_non_loopback_bind_outside_a_deployment_is_refused_by_main(
    ledger: Path,
    listens: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("TL_ENV")
    assert run_main(ledger) == 2
    assert "TLS proxy" in capsys.readouterr().err
    assert listens == []


# --- tokens ----------------------------------------------------------------------------------


def test_a_dev_file_token_is_not_honoured_by_a_prod_server_but_an_agent_token_is(
    ledger: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tokens = tmp_path / "dev-tokens.json"
    dev_token = add_token(tokens, "user:alice")
    backend = SqliteUowFactory(ledger)
    with backend() as uow:
        bot = accounts.create_account(
            uow, username="triage", display_name="Triage", kind="agent", roles=["user"],
            password=None, by="svc:test",
        )  # fmt: skip
        _, good = accounts.issue_agent_token(
            uow, account_id=bot.account_id, label="ok",
            expires_at=datetime.now(UTC) + timedelta(days=1), by="svc:test",
        )  # fmt: skip
        _, stale = accounts.issue_agent_token(
            uow, account_id=bot.account_id, label="old",
            expires_at=datetime.now(UTC) + timedelta(seconds=1), by="svc:test",
        )  # fmt: skip
    del stale
    monkeypatch.setenv("TL_ENV", "prod")
    app = create_app(
        backend,
        settings=ApiSettings(db_path=ledger, tokens_path=tokens),
        tokens=TokenStore(tokens),
    )
    with TestClient(app, raise_server_exceptions=False) as client:

        def whoami(token: str) -> int:
            return client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code

        assert whoami(dev_token) == 401
        assert whoami("not-a-token") == 401
        assert whoami(good) == 200
    monkeypatch.setenv("TL_ENV", "dev")
    dev_app = create_app(
        backend,
        settings=ApiSettings(db_path=ledger, tokens_path=tokens),
        tokens=TokenStore(tokens),
    )
    with TestClient(dev_app, raise_server_exceptions=False) as client:
        assert (
            client.get("/auth/me", headers={"Authorization": f"Bearer {dev_token}"}).status_code
            == 200
        )  # the same file and token do work where TL_ENV allows them
    backend.dispose()
