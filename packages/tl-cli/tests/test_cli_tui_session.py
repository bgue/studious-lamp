"""`tl tui` uses the session `tl login` made, and asks for none when there is none (P1-I0-S4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from auth_support import bootstrap, new_ledger, sign_in
from auth_support import run as tl
from tl_tui import main as tui_main


@pytest.fixture
def seen(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(tui_main, "run", lambda **kwargs: calls.append(kwargs))
    return calls


def test_a_signed_in_person_is_passed_on_so_the_tui_does_not_ask_again(
    tmp_path: Path, seen: list[dict[str, Any]]
) -> None:
    env = new_ledger(tmp_path)
    assert bootstrap(env).exit_code == 0
    sign_in(env)
    assert tl(env, "tui").exit_code == 0
    signed = seen[0]["signed_in"]
    assert signed.actor == "user:root" and signed.roles == ("admin",) and signed.is_admin
    assert signed.token is None


def test_without_a_session_the_tui_signs_in_for_itself(
    tmp_path: Path, seen: list[dict[str, Any]]
) -> None:
    env = new_ledger(tmp_path)
    assert bootstrap(env).exit_code == 0
    assert tl(env, "tui").exit_code == 0
    assert seen[0]["signed_in"] is None


def test_remote_mode_never_uses_the_ledger_session(
    tmp_path: Path, seen: list[dict[str, Any]]
) -> None:
    env = new_ledger(tmp_path)
    assert bootstrap(env).exit_code == 0
    sign_in(env)
    assert tl(env, "tui", "--remote", "http://127.0.0.1:1").exit_code == 0
    assert seen[0]["signed_in"] is None and seen[0]["remote"] == "http://127.0.0.1:1"
