"""Driver for dev/demos/P1-UX.sh: the record screen and plain language, on a real ledger.

Modes (first argument), each ending in a PASS line for its clause:

* ``prepare DIR``: write a synthetic XER schedule update and the enricher registration into DIR
  (seed for the schedule list and the review queue).
* ``registers``: clause 1. As a controller, Enter on the first row of each register opens the
  record screen; its Properties tab lists the set for that type with labels; Esc returns to the
  same row.
* ``plain``: clause 2. As a plain user, every register and every record screen shows no ULID,
  hash, schema version, internal key or clock or calendar id (``find_technical``), and Ctrl+D
  answers with the one-line refusal and changes nothing.
* ``admin``: clause 3. As an admin, Ctrl+D shows technical text on the document register and
  Ctrl+D again hides it.
* ``hidden``: clause 4. A restricted record opened by a plain user from a stale row reads exactly
  like a record that never existed.

Reads TL_DB (a SQLite path or postgresql:// URL) and, for ``hidden``, TL_DEMO_NOTICE. Every
expectation is an assert: a failing demo exits non-zero. Nothing printed holds a password or token.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, NamedTuple

PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
SIZE = (200, 50)
UNKNOWN_ID = "01J7K2M8Q4T6V9W3X5Y8Z1A2B4"  # a well-formed id that no record has


def say(text: str) -> None:
    print(f"   {text}")


def passed(clause: int, text: str) -> None:
    print(f"PASS {clause}: {text}")


class Register(NamedTuple):
    """One list that Enter opens a record from."""

    name: str
    keys: tuple[str, ...]  # pressed from the grid to reach the list
    needs_rows: bool  # a list that must hold a row in this demo's ledger
    set_label: str | None  # the set the Properties tab must list for the first row
    value_label: str | None  # one property label the Properties tab must show


REGISTERS = (
    Register("document register (F7)", ("f7",), True, "Document data", "Originator"),
    Register("tag register (F8)", ("f8",), True, None, None),
    Register(
        "correspondence register (F5)", ("f5",), True, "Correspondence data", "Contract clause"
    ),
    Register("triage inbox (F5, 2)", ("f5", "2"), True, "Correspondence data", "Contract clause"),
    Register("clocks (F5, 3)", ("f5", "3"), False, None, None),
    Register("RFI log (Ctrl+G, 1)", ("ctrl+g", "1"), True, "RFI data", "Trade"),
    Register("commercial register (Ctrl+G, 2)", ("ctrl+g", "2"), True, None, None),
    Register("schedule list (F12)", ("f12",), False, None, None),
    Register("review queue (Ctrl+R)", ("ctrl+r",), True, None, None),
)


def screen_text(app: Any) -> str:
    """The screen as plain text, the way the viewer sees it."""
    strips = app.screen._compositor.render_strips()
    return "\n".join(strip.text.rstrip() for strip in strips)


async def settle(pilot: Any, rounds: int = 4) -> None:
    for _ in range(rounds):
        await pilot.pause()


async def until(pilot: Any, predicate: Callable[[], object], what: str, tries: int = 200) -> None:
    for _ in range(tries):
        if predicate():
            await settle(pilot, 2)
            return
        await pilot.pause(0.03)
    raise AssertionError(f"timed out waiting for {what}:\n{screen_text(pilot.app)}")


def make_app(actor: str, *, admin: bool = False, controller: bool = False) -> Any:
    from tl_tui.main import build_app

    return build_app(
        os.environ["TL_DB"],
        PROJECT,
        live=False,
        actor=actor,
        is_admin=admin,
        is_controller=controller,
    )


def run(app: Any, scenario: Callable[[Any], Awaitable[Any]]) -> Any:
    out: list[Any] = []

    async def main() -> None:
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot)
            out.append(await scenario(pilot))

    try:
        asyncio.run(main())
    finally:
        app.client.close()
    return out[0]


async def to_grid(pilot: Any, app: Any) -> None:
    """Escape until no modal or register is on top of the grid."""
    for _ in range(6):
        if len(app.screen_stack) == 1:
            break
        await pilot.press("escape")
        await settle(pilot)
    assert len(app.screen_stack) == 1, [type(s).__name__ for s in app.screen_stack]


def table_of(app: Any) -> Any:
    """The data table that holds the cursor on the open register (the focused one)."""
    from textual.widgets import DataTable

    focused = app.focused
    if isinstance(focused, DataTable):
        return focused
    tables = list(app.screen.query(DataTable))
    assert tables, f"no table on {type(app.screen).__name__}"
    return tables[0]


async def open_register(pilot: Any, app: Any, reg: Register) -> Any:
    """Go to the register; return its data table (focused, cursor on the first row)."""
    await to_grid(pilot, app)
    for key in reg.keys:
        await pilot.press(key)
        await settle(pilot)
    await settle(pilot)
    return table_of(app)


async def open_first_record(pilot: Any, app: Any, table: Any) -> int:
    """Enter on the second row when there is one (so the return to the row means something)."""
    from tl_tui.widgets.record_screen import RecordScreen

    if table.row_count > 1:
        await pilot.press("down")
        await settle(pilot)
    row = table.cursor_row
    await pilot.press("enter")
    await until(pilot, lambda: isinstance(app.screen, RecordScreen), "the record screen")
    await settle(pilot, 6)
    return row


async def read_tabs(pilot: Any, app: Any) -> dict[str, str]:
    """The text of each tab of the open record screen, keyed by the key that opens it."""
    seen: dict[str, str] = {}
    for key in ("1", "2", "3", "4", "5", "T"):
        await pilot.press(key)
        await settle(pilot, 6)
        seen[key] = screen_text(app)
    return seen


# --- clause 1 ---------------------------------------------------------------------------------


async def registers_scenario(pilot: Any) -> list[str]:
    from textual.widgets import DataTable
    from tl_tui.widgets.record_screen import RecordScreen

    app = pilot.app
    lines: list[str] = []
    for reg in REGISTERS:
        table = await open_register(pilot, app, reg)
        register_screen = type(app.screen).__name__
        if table.row_count == 0:
            assert not reg.needs_rows, f"{reg.name} has no row"
            lines.append(f"{reg.name}: no rows in this ledger (nothing to open)")
            continue
        table_id = table.id
        row = await open_first_record(pilot, app, table)
        assert isinstance(app.screen, RecordScreen), type(app.screen).__name__
        await pilot.press("2")
        await settle(pilot, 6)
        text = screen_text(app)
        assert "Properties" in text, text
        if reg.set_label:
            assert reg.set_label in text, f"{reg.name}: no {reg.set_label!r} on\n{text}"
        if reg.value_label:
            assert reg.value_label in text, f"{reg.name}: no {reg.value_label!r} on\n{text}"
        await pilot.press("escape")
        await until(pilot, lambda: not isinstance(app.screen, RecordScreen), "the list again")
        assert type(app.screen).__name__ == register_screen, type(app.screen).__name__
        back = app.screen.query_one(f"#{table_id}", DataTable) if table_id else table_of(app)
        assert back.cursor_row == row, f"{reg.name}: row {row} became {back.cursor_row}"
        shown = f"set {reg.set_label}, value {reg.value_label}" if reg.set_label else "Properties"
        lines.append(f"{reg.name}: Enter opens the record; {shown}; Esc returns to row {row}")
    return lines


def registers() -> None:
    lines = run(make_app("user:dora", controller=True), registers_scenario)
    for line in lines:
        say(line)
    passed(
        1,
        "from each register Enter opens the record screen, its Properties tab lists the "
        "set for that type with labels, and Esc returns to the same row",
    )


# --- clause 2 ---------------------------------------------------------------------------------


async def plain_scenario(pilot: Any) -> dict[str, Any]:
    from tl_tui.display import REFUSAL, find_technical
    from tl_tui.labels_load import load_labels
    from tl_tui.widgets.record_screen import RecordScreen

    app = pilot.app
    labels = load_labels(app.client, SCOPE)
    leaks: list[str] = []
    checked = 0

    def check(where: str, text: str) -> None:
        nonlocal checked
        checked += 1
        leaks.extend(f"{where}: {token}" for token in find_technical(text, labels))

    opened: list[str] = []
    for reg in REGISTERS:
        table = await open_register(pilot, app, reg)
        check(reg.name, screen_text(app))
        if table.row_count == 0:
            continue
        await open_first_record(pilot, app, table)
        for key, text in (await read_tabs(pilot, app)).items():
            check(f"{reg.name} record, tab {key}", text)
        opened.append(reg.name)
        await pilot.press("escape")
        await until(pilot, lambda: not isinstance(app.screen, RecordScreen), "the list again")
    assert leaks == [], "technical text for a plain user:\n" + "\n".join(leaks)
    assert opened, "no register had a row for the plain user"

    # The toggle key: a plain user gets one line, and the mode and the screen stay as they were.
    from tl_tui.widgets.footer import TlFooter

    await to_grid(pilot, app)
    before = screen_text(app)
    await pilot.press("ctrl+d")
    await settle(pilot)
    after = screen_text(app)
    refusals = [line for line in after.splitlines() if REFUSAL in line]
    assert len(refusals) == 1, after
    assert not app.display_mode.technical
    known = set(before.splitlines())
    new = [line for line in after.splitlines() if line not in known]
    assert all(REFUSAL in line for line in new), f"the screen changed beyond the refusal: {new}"
    # The same key over a register (its screen covers the footer): refused, nothing changes.
    await pilot.press("f7")
    await settle(pilot, 6)
    register = screen_text(app)
    await pilot.press("ctrl+d")
    await settle(pilot, 6)
    assert app.query_one("#footer", TlFooter).status == REFUSAL
    assert not app.display_mode.technical
    assert screen_text(app) == register, "the register changed on a refused Ctrl+D"
    assert find_technical(after, labels) == []
    return {"checked": checked, "opened": opened, "refusal": refusals[0].strip()}


def plain() -> None:
    found = run(make_app("user:amy"), plain_scenario)
    say(f"amy: {found['checked']} screens read, none holds a technical token")
    say(f"records opened from: {', '.join(found['opened'])}")
    say(f"Ctrl+D answers: {found['refusal']!r}")
    passed(
        2,
        "as a plain user no register or record screen shows a ULID, hash, version, internal key "
        "or clock or calendar id, and the toggle key is refused in one line",
    )


# --- clause 3 ---------------------------------------------------------------------------------


async def admin_scenario(pilot: Any) -> dict[str, Any]:
    from tl_tui.display import find_technical
    from tl_tui.labels_load import load_labels
    from tl_tui.widgets.footer import TlFooter

    app = pilot.app
    labels = load_labels(app.client, SCOPE)
    await to_grid(pilot, app)
    await pilot.press("f7")
    await settle(pilot, 6)
    plain_text = screen_text(app)
    assert find_technical(plain_text, labels) == [], find_technical(plain_text, labels)
    await pilot.press("ctrl+d")
    await settle(pilot, 6)
    on_text = screen_text(app)
    shown = find_technical(on_text, labels)
    assert shown, "Ctrl+D showed no technical text on the document register:\n" + on_text
    assert app.query_one("#footer", TlFooter).status == "Technical details on"
    await pilot.press("ctrl+d")
    await settle(pilot, 6)
    off_text = screen_text(app)
    assert find_technical(off_text, labels) == [], find_technical(off_text, labels)
    assert app.query_one("#footer", TlFooter).status == "Technical details off"
    return {"shown": shown}


def admin() -> None:
    found = run(make_app("user:demo", admin=True), admin_scenario)
    say(f"Ctrl+D on: the document register shows {len(found['shown'])} technical token(s)")
    say("Ctrl+D again: none left")
    passed(
        3,
        "as an admin Ctrl+D shows ids and other technical details on the document register "
        "and Ctrl+D again hides them",
    )


# --- clause 4 ---------------------------------------------------------------------------------


async def open_by_id(pilot: Any, record_id: str) -> str:
    """Open the record screen for ``record_id`` over the document register; return its text."""
    from tl_tui.widgets.record_screen import RecordScreen, open_record

    app = pilot.app
    await to_grid(pilot, app)
    await pilot.press("f7")
    await settle(pilot)
    open_record(app.screen, app.client, SCOPE, PROJECT, app.actor, record_id)
    await until(pilot, lambda: isinstance(app.screen, RecordScreen), "the record screen")
    await settle(pilot, 6)
    text = screen_text(app)
    await pilot.press("escape")
    await until(pilot, lambda: not isinstance(app.screen, RecordScreen), "the list again")
    return text


def notice_id(number: str) -> str:
    from tl_tui.embedded import EmbeddedClient

    client = EmbeddedClient.for_target(os.environ["TL_DB"], actor="user:demo")
    try:
        return str(client.get_commercial(PROJECT, number).id)
    finally:
        client.close()


def hidden() -> None:
    from tl_tui.widgets.record_screen import NO_RECORD

    number = os.environ["TL_DEMO_NOTICE"]
    record_id = notice_id(number)

    async def as_boss(pilot: Any) -> str:
        return await open_by_id(pilot, record_id)

    async def as_amy(pilot: Any) -> tuple[str, str]:
        return await open_by_id(pilot, record_id), await open_by_id(pilot, UNKNOWN_ID)

    seen_by_boss = run(make_app("user:demo", admin=True), as_boss)
    assert NO_RECORD not in seen_by_boss and number in seen_by_boss, seen_by_boss
    stale, missing = run(make_app("user:amy"), as_amy)
    assert NO_RECORD in stale, stale
    assert stale == missing, f"restricted and missing differ:\n{stale}\n----\n{missing}"
    for secret in (record_id, number):
        assert secret not in stale, f"{secret} is on the screen"
    say(f"the admin opens {number} and reads it; amy, from a stale row, reads {NO_RECORD!r}")
    say("the screen text of the restricted record and of an unused id is byte-equal")
    passed(
        4,
        "a restricted record opened from a stale row by a plain user reads exactly like a "
        "record that never existed",
    )


# --- seed -------------------------------------------------------------------------------------


# The doc_classifier enricher of the P1-I7 demo: it proposes a document type and a discipline for
# a new document, and both wait in the review queue (Ctrl+R) for a person.
ENRICHER = {
    "when": {"event_types": ["Document.Defined"]},
    "properties": [
        {"name": "doc_type", "kind": "string", "policy": "propose", "threshold": 0.9},
        {"name": "discipline", "kind": "string", "policy": "propose", "threshold": 0.9},
    ],
}


def prepare(directory: str) -> None:
    import json

    from tl_xer.synth import make_xer, week_pair

    (Path(directory) / "enricher.json").write_text(json.dumps(ENRICHER, indent=1) + "\n")

    first, _second = week_pair()
    (Path(directory) / "update-1.xer").write_bytes(make_xer(first))
    say("wrote update-1.xer and enricher.json")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "prepare":
        prepare(sys.argv[2])
    elif mode == "registers":
        registers()
    elif mode == "plain":
        plain()
    elif mode == "admin":
        admin()
    elif mode == "hidden":
        hidden()
    else:
        raise SystemExit(f"unknown mode {mode!r}")


if __name__ == "__main__":
    main()
