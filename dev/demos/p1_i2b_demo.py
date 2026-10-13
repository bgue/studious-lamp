"""Driver for dev/demos/P1-I2b.sh: the document controller role in the ledger, HTTP and the TUI.

Modes (first argument), each ending in a PASS line for its clause:

* ``granted``: clause 2. The admin's ``Account.RolesSet`` event for ``dora`` names the admin and
  the reason, holds the new role and no secret.
* ``actors``: clause 3. ``Revision.Issued``, ``Transmittal.Issued`` and the import's registrations
  name ``user:dora`` as the actor; no event was written by an admin on her behalf.
* ``matrix``: clause 5. A user, the document controller, an admin and an agent over every
  controlling command (HTTP), then the admin routes and link recovery for the controller.
* ``tui``: clause 6. The accounts screen offers the role (key ``c``) to the admin, and the
  transmittal composer issues for the controller (``Ctrl+T``) and says what is missing to a user.

Reads TL_DB (a SQLite path or postgresql:// URL), TL_DEMO_URL (the API) and the demo passwords.
Every expectation is an assert: a failing demo exits non-zero. Nothing printed holds a password or
a token.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
DEMO = ("demo", "demo")  # the documented dev account (ADR-0009 section 9)
CONTROLLING = (
    "SetDocumentConfidentiality",
    "SupersedeDocument",
    "VoidDocument",
    "IssueRevision",
    "SupersedeRevision",
    "RegisterSignedRendition",
    "ReplaceSignedRendition",
    "IssueTransmittal",
    "RecordReviewOutcomeOnBehalf",
    "OverrideReviewOutcome",
)


def say(text: str) -> None:
    print(f"   {text}")


def passed(clause: int, text: str) -> None:
    print(f"PASS {clause}: {text}")


def token_of(name: str, password: str) -> str:
    from tl_api.client.auth import sign_in

    return sign_in(os.environ["TL_DEMO_URL"], name, password).token


def tokens() -> dict[str, str]:
    return {
        "user": token_of("amy", os.environ["TL_DEMO_AMY_PASSWORD"]),
        "controller": token_of("dora", os.environ["TL_DEMO_DORA_PASSWORD"]),
        "admin": token_of(*DEMO),
        "agent": os.environ["TL_DEMO_AGENT_TOKEN"],
    }


def http(method: str, path: str, token: str, body: dict[str, Any] | None = None) -> tuple[int, str]:
    import httpx2

    response = httpx2.request(
        method,
        f"{os.environ['TL_DEMO_URL']}{path}",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    data = response.json() if response.content else {}
    return response.status_code, str(data.get("error", "ok")) if isinstance(data, dict) else "ok"


def events(types: list[str]) -> list[Any]:
    from tl_api.client import ApiClient

    api = ApiClient(os.environ["TL_DEMO_URL"], token_of(*DEMO))
    try:
        return list(api.events_after(0, types=types, limit=1000).events)
    finally:
        api.close()


def granted() -> None:
    found = [e for e in events(["Account.RolesSet"]) if "document_controller" in str(e.payload)]
    assert len(found) == 1, found
    event = found[0]
    assert event.actor == "user:demo", event.actor
    assert event.payload["roles"] == ["document_controller", "user"], event.payload
    assert event.payload["reason"] == "takes over document control", event.payload
    text = str(event.model_dump())
    assert "scrypt" not in text and os.environ["TL_DEMO_DORA_PASSWORD"] not in text
    say(f"Account.RolesSet by {event.actor}: {event.payload['roles']} ({event.payload['reason']})")
    passed(2, "dora holds document_controller and user; the grant names the admin and the reason")


def actors() -> None:
    issued = events(["Revision.Issued", "Transmittal.Issued"])
    by = {(e.event_type, e.actor) for e in issued}
    assert ("Revision.Issued", "user:dora") in by, by
    assert ("Transmittal.Issued", "user:dora") in by, by
    assert not [a for _, a in by if a == "user:demo"], by
    registered = [e for e in events(["Record.Created"]) if e.actor == "user:dora"]
    assert registered, "the import registered documents as dora"
    say(
        f"{len(issued)} issue events, all by user:dora; {len(registered)} records registered by her"
    )
    passed(3, "dora issued a revision, a transmittal and an import; the ledger names her")


def matrix() -> None:
    tok = tokens()
    refused_text = ""
    for name in CONTROLLING:
        body = {"scope": SCOPE}  # empty command: the access check comes before the body
        user = http("POST", f"/commands/{name}", tok["user"], body)
        assert user == (403, "forbidden"), (name, user)
        for who in ("controller", "admin"):
            got = http("POST", f"/commands/{name}", tok[who], body)
            assert got[0] != 403, (name, who, got)
        agent = http("POST", f"/commands/{name}", tok["agent"], body)
        assert agent == (403, "agent_must_propose"), (name, agent)
        refused_text = name
    say(f"{len(CONTROLLING)} controlling commands: user 403, controller and admin pass, agent 403")
    mine = http("POST", "/commands/CreateRecord", tok["controller"],
                {"scope": SCOPE, "record_type": "core.Record", "title": "Note"})  # fmt: skip
    assert mine[0] == 200, mine  # the controller is also a user
    for method, path, body in (
        ("GET", "/admin/accounts", None),
        ("POST", "/admin/accounts", {"username": "eve", "display_name": "Eve", "roles": ["user"]}),
        ("POST", "/admin/tokens", {"account_id": "x", "label": "x"}),
        ("PUT", "/admin/accounts/x/roles", {"roles": ["admin", "user"]}),
        (
            "POST",
            "/commands/AdminFlagLink",
            {"scope": SCOPE, "link_id": "x", "status": "broken", "reason": "x"},
        ),
        ("POST", "/commands/AdminRetractLink", {"scope": SCOPE, "link_id": "x", "reason": "x"}),
    ):
        got = http(method, path, tok["controller"], body)
        assert got == (403, "forbidden"), (method, path, got)
        say(f"controller: {method} {path} -> 403")
    assert http("GET", "/admin/accounts", tok["admin"])[0] == 200
    assert refused_text
    passed(
        5,
        "user, controller, admin and agent over the controlling commands; no admin route for her",
    )


async def tui_admin(db: str) -> None:
    from textual.widgets import DataTable, Input
    from tl_tui.app import TlApp
    from tl_tui.embedded import EmbeddedClient
    from tl_tui.widgets.admin_screen import AdminScreen

    client = EmbeddedClient.for_target(db, actor="user:demo")
    try:
        app = TlApp(client, scope=SCOPE, actor="user:demo", is_admin=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("f10")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, AdminScreen)
            assert "c controller role" in AdminScreen.KEY_HINTS_MORE
            names = [a.username for a in screen.accounts]
            screen.query_one("#admin-accounts", DataTable).move_cursor(row=names.index("amy"))
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()
            app.screen.query_one("#prompt-input", Input).value = "covers for dora"
            await pilot.press("enter")
            await pilot.pause()
            amy = next(a for a in screen.accounts if a.username == "amy")
            assert amy.roles == ["document_controller", "user"], amy.roles
            await pilot.press("c")  # and back
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            amy = next(a for a in screen.accounts if a.username == "amy")
            assert amy.roles == ["user"], amy.roles
    finally:
        client.close()


async def tui_composer(db: str, actor: str, controller: bool) -> str:
    from textual.widgets import DataTable, Input, Static
    from tl_tui.app import TlApp
    from tl_tui.embedded import EmbeddedClient
    from tl_tui.widgets.document_register import DocumentRegisterScreen
    from tl_tui.widgets.transmittal_composer import TransmittalComposerScreen

    client = EmbeddedClient.for_target(db, actor=actor)
    try:
        app = TlApp(client, scope=SCOPE, actor=actor, is_controller=controller)
        async with app.run_test(size=(140, 44)) as pilot:
            await pilot.press("f7")
            await pilot.pause()
            register = app.screen
            assert isinstance(register, DocumentRegisterScreen)
            shown = [v.number for v in register.shown]
            register.query_one("#docs-table", DataTable).move_cursor(row=shown.index("ISO-1234"))
            await pilot.pause()
            await pilot.press("t")
            await pilot.pause()
            composer = app.screen
            assert isinstance(composer, TransmittalComposerScreen)
            hints = str(composer.query_one("#tc-hints", Static).render())
            assert ("Ctrl+T" in hints) is controller, hints
            composer.query_one("#tc-subject", Input).value = f"By {actor}"
            composer.query_one("#tc-to", Input).value = "Site Office"
            await pilot.press("ctrl+t")
            await pilot.pause()
            if controller:
                assert app.screen is not composer, composer.query_one("#tc-status", Static).render()
                return composer.issue_error or ("issued" if composer.issued else "drafted")
            return str(composer.query_one("#tc-status", Static).render())
    finally:
        client.close()


def tui() -> None:
    db = os.environ["TL_DB"]
    asyncio.run(tui_admin(db))
    say("accounts screen (F10, as demo): c gave amy document_controller and took it back")
    outcome = asyncio.run(tui_composer(db, "user:dora", controller=True))
    assert outcome == "issued", outcome
    say("transmittal composer (F7, t, as dora): Ctrl+T drafted and issued a transmittal")
    outcome = asyncio.run(tui_composer(db, "user:amy", controller=False))
    assert "needs the document_controller or admin role" in outcome, outcome
    say(f"transmittal composer as amy: Ctrl+T says: {outcome}")
    passed(
        6,
        "the accounts screen offers the role; the composer issues for a controller, not a user",
    )


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    modes = {"granted": granted, "actors": actors, "matrix": matrix, "tui": tui}
    if mode not in modes:
        raise SystemExit(f"unknown mode {mode!r}")
    modes[mode]()


if __name__ == "__main__":
    main()
