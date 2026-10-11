"""Table cells and detail text of the accounts screen (P1-I0-T09)."""

from __future__ import annotations

from tl_core.auth.types import AccountView, AgentTokenView
from tl_tui.admin_text import (
    ACCOUNT_COLUMNS,
    TOKEN_COLUMNS,
    account_cells,
    detail_lines,
    lock_text,
    moment,
    status_text,
    token_cells,
    token_state,
)

NOW = "2026-10-11T12:00:00.000000Z"


def account(**changes: object) -> AccountView:
    values: dict[str, object] = {
        "account_id": "A1",
        "username": "amy",
        "display_name": "Amy A",
        "kind": "person",
        "roles": ["user"],
        "status": "active",
        "locked_until": None,
        "created_at": "2026-10-09T09:01:02.123456Z",
        "seq": 3,
    }
    return AccountView.model_validate(values | changes)


def token(**changes: object) -> AgentTokenView:
    values: dict[str, object] = {
        "token_id": "T1",
        "account_id": "A1",
        "label": "mcp",
        "expires_at": "2026-12-01T00:00:00.000000Z",
        "revoked": False,
        "issued_by": "user:boss",
    }
    return AgentTokenView.model_validate(values | changes)


def test_a_moment_is_shown_to_the_minute_in_utc() -> None:
    assert moment("2026-10-11T12:15:59.999999Z") == "2026-10-11 12:15"
    assert moment("2026-10-11T12:15:00Z") == "2026-10-11 12:15"


def test_status_and_lock_carry_a_symbol_not_only_a_colour() -> None:
    assert status_text(account()) == "✓ active"
    assert status_text(account(status="disabled")) == "✗ disabled"
    assert lock_text(account()) == ""
    assert lock_text(account(locked_until="2026-10-11T12:15:00.000000Z")) == (
        "■ until 2026-10-11 12:15"
    )


def test_an_account_row_has_one_cell_per_column() -> None:
    assert len(ACCOUNT_COLUMNS) == 5
    assert account_cells(account()) == ("amy", "person", "user", "✓ active", "")
    boss = account(username="boss", roles=["admin", "user"], locked_until="2026-10-11T12:15:00Z")
    assert account_cells(boss) == (
        "boss",
        "person",
        "admin, user",
        "✓ active",
        "■ until 2026-10-11 12:15",
    )


def test_a_token_is_revoked_expired_or_active() -> None:
    assert token_state(token(), NOW) == "✓ active"
    assert token_state(token(expires_at=None), NOW) == "✓ active"
    assert token_state(token(expires_at="2026-10-11T12:00:00.000000Z"), NOW) == "! expired"
    assert token_state(token(expires_at="2026-10-01T00:00:00.000000Z"), NOW) == "! expired"
    assert token_state(token(revoked=True), NOW) == "✗ revoked"
    assert token_state(token(revoked=True, expires_at="2026-10-01T00:00:00Z"), NOW) == "✗ revoked"


def test_a_token_row_names_the_agent_and_never_holds_a_secret() -> None:
    assert len(TOKEN_COLUMNS) == 5
    names = {"A1": "triage"}
    assert token_cells(token(), names, NOW) == (
        "triage",
        "mcp",
        "2026-12-01 00:00",
        "✓ active",
        "T1",
    )
    assert token_cells(token(expires_at=None), names, NOW)[2] == "never"
    assert token_cells(token(account_id="gone"), names, NOW)[0] == "?"


def test_the_detail_panel_lists_the_facts_one_per_line() -> None:
    lines = detail_lines(account(), [], NOW)
    assert lines == [
        "Name      amy",
        "Shown as  Amy A",
        "Kind      person",
        "Roles     user",
        "Status    ✓ active",
        "Lock      none",
        "Created   2026-10-09 09:01",
    ]


def test_the_detail_panel_shows_a_lock_and_counts_an_agents_tokens() -> None:
    locked = detail_lines(account(locked_until="2026-10-11T12:15:00Z"), [], NOW)
    assert "Lock      ■ locked until 2026-10-11 12:15 UTC" in locked
    bot = account(kind="agent", username="triage")
    tokens = [
        token(token_id="T1"),
        token(token_id="T2", revoked=True),
        token(token_id="T3", expires_at="2026-10-01T00:00:00Z"),
        token(token_id="T4", account_id="other"),
    ]
    lines = detail_lines(bot, tokens, NOW)
    assert lines[-1] == "Tokens    1 live, 1 revoked"
    assert not any(line.startswith("Tokens") for line in detail_lines(account(), tokens, NOW))
