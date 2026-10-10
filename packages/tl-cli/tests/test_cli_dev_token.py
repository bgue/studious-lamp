"""`tl dev token add` (P0-I4-T45; ADR-0005): create a dev bearer token for an actor."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from tl_api.tokens import TokenStore
from tl_cli.main import app
from typer.testing import CliRunner, Result

runner = CliRunner()


def add(*args: str, env: dict[str, str] | None = None) -> Result:
    result = runner.invoke(app, ["dev", "token", "add", *args], env=env)
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    return result


def test_add_prints_only_the_token_and_stores_it_privately(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    result = add("user:alice", "--tokens", str(path))
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert len(lines) == 1 and len(lines[0]) >= 20 and " " not in lines[0]
    token = lines[0]
    assert json.loads(path.read_text()) == {token: "user:alice"}
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert TokenStore(path).actor_for(token) == "user:alice"
    assert f"added token for user:alice to {path}" in result.stderr
    assert token not in result.stderr


def test_each_call_adds_a_new_token_and_keeps_the_old_ones(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    first = add("user:alice", "--tokens", str(path)).stdout.strip()
    second = add("agent:triage", "--tokens", str(path)).stdout.strip()
    third = add("user:alice", "--tokens", str(path)).stdout.strip()
    assert len({first, second, third}) == 3
    assert json.loads(path.read_text()) == {
        first: "user:alice",
        second: "agent:triage",
        third: "user:alice",
    }


def test_an_actor_that_is_not_user_or_agent_is_refused_and_nothing_is_written(
    tmp_path: Path,
) -> None:
    path = tmp_path / "tokens.json"
    for bad in ("alice", "svc:scanner", "user:", "user:a b"):
        result = add(bad, "--tokens", str(path))
        assert result.exit_code == 1, bad
        assert result.stderr.startswith("error:"), result.stderr
        assert result.stdout == ""
    assert not path.exists()


def test_the_tokens_file_comes_from_the_environment_or_the_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from_env = tmp_path / "env-tokens.json"
    result = add("user:bob", env={"TL_TOKENS": str(from_env)})
    assert result.exit_code == 0, result.output
    assert TokenStore(from_env).actor_for(result.stdout.strip()) == "user:bob"

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TL_TOKENS", raising=False)
    default = add("user:carol")
    assert default.exit_code == 0, default.output
    token = default.stdout.strip()
    assert TokenStore(tmp_path / "dev" / "data" / "tokens.json").actor_for(token) == "user:carol"


def test_a_token_file_that_is_not_an_object_is_an_error_not_a_crash(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    path.write_text("[1, 2]")
    result = add("user:alice", "--tokens", str(path))
    assert result.exit_code == 1 and result.stderr.startswith("error:")
    assert path.read_text() == "[1, 2]"


def test_the_group_is_listed_in_help() -> None:
    result = runner.invoke(app, ["dev", "--help"])
    assert result.exit_code == 0 and "token" in result.stdout
