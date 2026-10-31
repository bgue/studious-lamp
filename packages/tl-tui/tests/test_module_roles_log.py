"""The module roles log (RM-S3, T1): three rows, the panel, the revoke refusal in the status line,
the 80 and 170 column readings and snapshots, and the plain-words walk (no id, no technical text).

Opened with ``m`` on the accounts screen (F10) by an admin, over the fake client.
"""

from __future__ import annotations

import re
from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text, settle
from textual.pilot import Pilot
from tl_tui.app import TlApp
from tl_tui.display import find_technical
from tl_tui.labels_load import load_labels
from tl_tui.widgets.admin_screen import AdminScreen
from tl_tui.widgets.module_roles_log import ModuleRolesLog


def seeded() -> FakeClient:
    client = FakeClient()
    boss = client.seed_account("boss", roles=["admin", "user"], display_name="Boss B")
    amy = client.seed_account("amy", display_name="Amy A")
    bob = client.seed_account("bob", display_name="Bob B")
    client.me_account_id = boss.account_id
    client.seed_module_role(amy.account_id, SCOPE, "documents", "superuser")
    client.seed_module_role(amy.account_id, SCOPE, "schedule", "viewer")
    client.seed_module_role(bob.account_id, SCOPE, "*", "user")
    client.admin_calls.clear()
    return client


def admin_app(client: FakeClient) -> TlApp:
    return TlApp(client, scope=SCOPE, actor="user:boss", is_admin=True)


async def open_log(pilot: Pilot[Any], app: TlApp) -> ModuleRolesLog:
    await pilot.press("f10")
    await settle(pilot)
    assert isinstance(app.screen, AdminScreen)
    await pilot.press("m")
    await settle(pilot)
    assert isinstance(app.screen, ModuleRolesLog), type(app.screen).__name__
    return app.screen


def status_line(app: TlApp) -> str:
    return "\n".join(
        line.strip() for line in screen_text(app).splitlines() if line.strip().startswith("!")
    )


def calls(client: FakeClient, name: str) -> list[dict[str, Any]]:
    return [args for method, args in client.admin_calls if method == name]


# --- the log: three rows and the panel -----------------------------------------------------------


def test_the_log_lists_the_three_grants_with_plain_words_at_80_columns() -> None:
    client = seeded()
    app = admin_app(client)
    seen: dict[str, Any] = {}

    async def scenario(pilot: Pilot[Any]) -> None:
        log = await open_log(pilot, app)
        seen["rows"] = len(log.rows)
        seen["text"] = screen_text(app)

    run_pilot(app, scenario, size=(80, 24))
    assert seen["rows"] == 3
    text = seen["text"]
    for needle in ("Module roles", "Amy A", "Bob B", "Documents", "Superuser", "Effective roles"):
        assert needle in text, needle
    for column in ("Account", "Module", "Role", "Granted by", "Since"):
        assert column in text, column
    assert "01FAKE" not in text and "documents.Document" not in text  # no id, no type key


def test_the_log_lists_the_three_grants_at_170_columns_with_the_panel() -> None:
    client = seeded()
    app = admin_app(client)
    seen: dict[str, str] = {}

    async def scenario(pilot: Pilot[Any]) -> None:
        log = await open_log(pilot, app)
        assert len(log.rows) == 3
        seen["first"] = screen_text(app)
        await pilot.press("down")
        await settle(pilot)
        seen["second"] = screen_text(app)

    run_pilot(app, scenario, size=(170, 40))
    assert "Amy A" in seen["first"] and "Granted" in seen["first"]
    # the panel follows the highlighted row: one property line per module under Effective roles
    assert "Effective roles" in seen["first"]
    assert "Documents" in seen["first"] and "superuser" in seen["first"].lower()
    assert seen["second"] != seen["first"]


def test_the_panel_states_where_the_roles_come_from() -> None:
    client = seeded()
    app = admin_app(client)
    texts: list[str] = []

    async def scenario(pilot: Pilot[Any]) -> None:
        await open_log(pilot, app)
        texts.append(screen_text(app))
        await pilot.press("down", "down")
        await settle(pilot)
        texts.append(screen_text(app))

    run_pilot(app, scenario, size=(120, 40))
    assert "Granted" in texts[0]
    assert "Bob B" in texts[1]


def test_an_empty_log_says_so_in_plain_words() -> None:
    client = FakeClient()
    boss = client.seed_account("boss", roles=["admin", "user"])
    client.me_account_id = boss.account_id
    app = admin_app(client)
    seen: dict[str, Any] = {}

    async def scenario(pilot: Pilot[Any]) -> None:
        log = await open_log(pilot, app)
        seen["rows"] = len(log.rows)
        seen["text"] = screen_text(app)

    run_pilot(app, scenario)
    assert seen["rows"] == 0 and "Module roles (0)" in seen["text"]


# --- the revoke refusal in the status line --------------------------------------------------------


def test_a_revoke_the_service_refuses_shows_in_the_status_line_at_80_and_170_columns() -> None:
    for size in ((80, 24), (170, 40)):
        client = seeded()
        app = admin_app(client)
        seen: dict[str, str] = {}

        async def scenario(
            pilot: Pilot[Any],
            app: TlApp = app,
            client: FakeClient = client,
            seen: dict[str, str] = seen,
        ) -> None:
            await open_log(pilot, app)
            client._module_grants.clear()  # pyright: ignore[reportPrivateUsage]
            await pilot.press("r")
            await settle(pilot)
            seen["form"] = screen_text(app)
            for key in "gone":
                await pilot.press(key)
            await pilot.press("enter")
            await settle(pilot)
            seen["refused"] = status_line(app)

        run_pilot(app, scenario, size=size)
        assert "Revoke" in seen["form"], size
        assert "is not held by that account" in seen["refused"], (size, seen["refused"])
        assert len(calls(client, "revoke_module_role")) == 1


def test_a_revoke_asks_for_a_reason_then_sends_one_call_and_reads_the_list_again() -> None:
    client = seeded()
    app = admin_app(client)
    seen: dict[str, Any] = {}

    async def scenario(pilot: Pilot[Any]) -> None:
        log = await open_log(pilot, app)
        await pilot.press("r")
        await settle(pilot)
        for key in "moved":
            await pilot.press(key)
        await pilot.press("enter")
        await settle(pilot)
        seen["rows"] = len(log.rows)
        seen["text"] = screen_text(app)

    run_pilot(app, scenario)
    sent = calls(client, "revoke_module_role")
    assert len(sent) == 1 and sent[0]["project"] == SCOPE
    assert seen["rows"] == 2 and "Revoked" in seen["text"]


def test_cancelling_the_revoke_form_changes_nothing() -> None:
    client = seeded()
    app = admin_app(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        log = await open_log(pilot, app)
        await pilot.press("r")
        await settle(pilot)
        await pilot.press("escape")
        await settle(pilot)
        assert len(log.rows) == 3

    run_pilot(app, scenario)
    assert calls(client, "revoke_module_role") == []


def test_key_n_opens_the_grant_form_and_sends_one_grant_for_the_current_project() -> None:
    client = seeded()
    app = admin_app(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await open_log(pilot, app)
        await pilot.press("n")
        await settle(pilot)
        await pilot.press("tab", "tab", "tab")  # account, module, role -> reason
        for key in "demo":
            await pilot.press(key)
        await pilot.press("enter")
        await settle(pilot)

    run_pilot(app, scenario)
    sent = calls(client, "grant_module_role")
    assert len(sent) == 1 and sent[0]["project"] == SCOPE


# --- who may open it ------------------------------------------------------------------------------


def test_key_m_opens_nothing_for_a_non_admin_and_makes_no_module_role_call() -> None:
    client = seeded()
    app = TlApp(client, scope=SCOPE, actor="user:amy", is_admin=False)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.press("f10")
        await settle(pilot)
        assert not isinstance(app.screen, AdminScreen)
        await pilot.press("m")
        await settle(pilot)
        assert not isinstance(app.screen, ModuleRolesLog | AdminScreen)

    run_pilot(app, scenario)
    assert not [c for c in client.admin_calls if "module_role" in c[0] or c[0] == "effective_roles"]


# --- the plain walk entry -------------------------------------------------------------------------


def test_the_plain_walk_enters_the_log_with_no_id_and_no_technical_text() -> None:
    client = seeded()
    labels = load_labels(client, SCOPE)
    app = admin_app(client)
    readings: list[str] = []

    async def scenario(pilot: Pilot[Any]) -> None:
        await open_log(pilot, app)
        readings.append(screen_text(app))
        for _ in range(3):
            await pilot.press("down")
            await settle(pilot)
            readings.append(screen_text(app))

    run_pilot(app, scenario)
    for text in readings:
        assert find_technical(text, labels) == [], text
        assert "01FAKE" not in text


def test_technical_details_add_the_account_id_column_and_plain_mode_takes_it_away() -> None:
    client = seeded()
    app = admin_app(client)
    seen: dict[str, str] = {}

    async def scenario(pilot: Pilot[Any]) -> None:
        await open_log(pilot, app)
        seen["plain"] = screen_text(app)
        await pilot.press("ctrl+d")
        await settle(pilot)
        seen["technical"] = screen_text(app)
        await pilot.press("ctrl+d")
        await settle(pilot)
        seen["again"] = screen_text(app)

    run_pilot(app, scenario, size=(170, 40))
    header = lambda text: next(line for line in text.splitlines() if "Account" in line)  # noqa: E731
    assert re.search(r"Since\s+Id\b", header(seen["technical"]))
    assert not re.search(r"Since\s+Id\b", header(seen["plain"]))
    assert not re.search(r"Since\s+Id\b", header(seen["again"]))


# --- snapshots ------------------------------------------------------------------------------------


def test_the_module_roles_log_snapshot_80x24(snap_compare: Any) -> None:
    async def run_before(pilot: Pilot[Any]) -> None:
        await open_log(pilot, app)

    app = admin_app(seeded())
    assert snap_compare(app, terminal_size=(80, 24), run_before=run_before)


def test_the_module_roles_log_snapshot_170x40(snap_compare: Any) -> None:
    async def run_before(pilot: Pilot[Any]) -> None:
        await open_log(pilot, app)
        await pilot.press("down")
        await settle(pilot)

    app = admin_app(seeded())
    assert snap_compare(app, terminal_size=(170, 40), run_before=run_before)
