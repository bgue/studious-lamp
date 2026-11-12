"""The highlight tour: only the everyday screens, for a quick look at how Throughline reads.

    uv run python dev/tour/highlights.py [--out docs/reports/tour/highlights]
    just tour highlights

Same method as `phase1.py` (see `tourkit.py`): a fresh SQLite ledger in a temporary directory,
the standards code lists loaded (so a discipline reads `Structural`, not `STR`), the real TUI
driven headless, the frozen clock, and the leak check on every plain screenshot. It writes
eighteen SVGs and one pack HTML file, and no transcripts:

    01 RFI log, 170 columns (the panel beside the list)    10 the RFI's Insights (key 9)
    02 RFI log, 100 columns (the panel below the list)     11 the intent panel of an event
    03 an RFI's Details                                    12 a foreman's landing (IWP log, mine)
    04 the same RFI's Files tab                            13 week: look-ahead (step 1)
    05 correspondence log                                  14 week: constraints (step 2)
    06 a letter's Details                                  15 week: commitments (step 4)
    07 the document log                                    16 week: progress (step 5)
    08 the document preview line                           17 week: the closed week and its PPC
    09 an RFI's Activity (key 4)                           18 the work pack (a CLI shot; the HTML
                                                              file is kept beside the SVGs)

01 to 08 are the same ledger and screens as before; 09 to 11 add an intent to an RFI's history;
12 to 18 are the awp project P200 of the demo generator, with a published schedule, Issued IWPs
and one week taken through its cycle (`dev/tour/wave1.py` builds the project the same way).

The text is `docs/reports/HIGHLIGHTS-TOUR.md`; its headings match the file names. The people and
helpers are those of `phase1.py`.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import phase1 as p1
import tourkit as tk
import wave1 as w1
from textual.pilot import Pilot
from textual.widgets import DataTable, Input
from tourkit import Workspace

from dev.seed.demo_project.core import PASSWORD as GENERATOR_PASSWORD

REPO = p1.REPO
P = p1.P
DOCUMENT = "ISO-6100"
DOCUMENT_B = "ISO-1234"
SUBJECTS = {
    "round": "Conflict in piling and utilities at AZ203",
    "tray": "Cable tray support spacing in the pipe rack",
    "pump": "Pump P-201 baseplate grouting sequence",
    "rail": "Handrail height at platform PL-3",
}


def world(ws: Workspace) -> dict[str, str]:
    """The ledger, its people and the standards; four RFIs in different states, a few letters,
    three documents. Returns the numbers the shots need."""
    p1.setup(ws)
    ws.tl("standards", "load", p1.STANDARDS, who="demo")
    ws.tl("standards", "load", p1.DOC_STANDARDS, who="demo")
    ws.tl(
        "admin",
        "user",
        "add",
        "dora",
        "--display-name",
        "Dora C",
        "--password-stdin",
        stdin=p1.password("dora"),
        who="demo",
    )
    p1.sign_in(ws, "dora")
    ws.tl(
        "admin",
        "user",
        "roles",
        "dora",
        "--add",
        "document_controller",
        "--reason",
        "takes over document control",
        who="demo",
    )
    p1.renew_sessions(ws)
    numbers: dict[str, str] = {}
    numbers.update(rfis(ws))
    numbers.update(letters(ws))
    numbers.update(documents(ws))
    return numbers


def raise_rfi(ws: Workspace, subject: str, question: str, discipline: str, days: int) -> str:
    needed = (tk.CLOCK.now.date() + timedelta(days=days)).isoformat()
    out = ws.tl(
        "rfi",
        "raise",
        *P,
        "--subject",
        subject,
        "--question",
        question,
        "--discipline",
        discipline,
        "--required-by",
        needed,
        "--to",
        p1.MERIDIAN,
        who="amy",
    )
    return p1.made(out, "raised")


def rfis(ws: Workspace) -> dict[str, str]:
    p1.make_pdf(ws.root / "beam-b12-sketch.pdf", 1)
    (ws.root / "survey-notes.txt").write_text(
        "Survey of the corridor at AZ203\npile P-17 at grid C-4, east offset to be confirmed\n"
    )
    rfi = raise_rfi(ws, SUBJECTS["round"], p1.QUESTION_24, "STR", 10)
    for name in ("beam-b12-sketch.pdf", "survey-notes.txt"):
        ws.tl(
            "file", "put", name, *P, "--record", rfi, "--slot", "attachment",
            "--actor", "user:amy", who="amy",
        )  # fmt: skip
    ws.tl("rfi", "submit", rfi, *P, who="amy")
    ws.tl("rfi", "issue", rfi, *P, who="dora")
    ws.tl(
        "rfi", "answer", rfi, *P, "--answer", "Use the original routing.",
        "--cost-impact", "no", "--schedule-impact", "no", who="amy",
    )  # fmt: skip
    ws.tl(
        "rfi", "review", rfi, *P, "--reject", "--note",
        "The beam moved in revision C; please check again.", who="dora",
    )  # fmt: skip
    ws.tl("rfi", "reissue", rfi, *P, "--reason", "Revision C attached", who="amy")
    ws.tl("rfi", "issue", rfi, *P, who="dora")
    tray = raise_rfi(
        ws, SUBJECTS["tray"], "Confirm 1.5 m support spacing for the cable trays on rack R-2.",
        "ELE", 6,
    )  # fmt: skip
    ws.tl("rfi", "submit", tray, *P, who="amy")
    pump = raise_rfi(
        ws, SUBJECTS["pump"], "Which grouting sequence applies to the baseplate of pump P-201?",
        "MEC", 14,
    )  # fmt: skip
    ws.tl("rfi", "submit", pump, *P, who="amy")
    ws.tl("rfi", "issue", pump, *P, who="dora")
    rail = raise_rfi(
        ws, SUBJECTS["rail"], "Is the handrail on platform PL-3 1.0 m or 1.1 m high?", "CIV", 3
    )
    ws.tl("rfi", "submit", rail, *P, who="amy")
    return {"rfi": rfi, "tray": tray, "pump": pump, "rail": rail}


def letters(ws: Workspace) -> dict[str, str]:
    (ws.root / "letter.txt").write_text(
        "Please find our revised programme. We would be grateful for your comments.\n"
    )
    ws.tl(
        "corr", "party", "add", "ACME", *P, "--name", "Acme Construction", "--role", "contractor",
        "--email-domain", "acme.example", "--contact", "Ann:ann@acme.example", who="dora",
    )  # fmt: skip
    received = ws.tl(
        "corr", "receive", *P, "--subject", "Revised programme", "--from", "Acme Construction",
        "--file", "letter.txt", "--body-file", "letter.txt", who="amy",
    )  # fmt: skip
    letter = p1.made(received, "received")
    ws.tl("corr", "triage", letter, *P, "--accept", who="amy")
    drafted = ws.tl(
        "corr", "draft", *P, "--subject", "Re: Revised programme", "--to",
        "Acme Construction:ann@acme.example", "--reply-to", letter, "--domain", "general",
        "--subtype", "letter", "--body",
        "We have received the programme and will reply by the due date.", who="amy",
    )  # fmt: skip
    reply = p1.made(drafted, "drafted")
    ws.tl("corr", "issue", reply, *P, who="dora")
    access = ws.tl(
        "corr", "receive", *P, "--subject", "Request for site access on Saturday",
        "--from", "Acme Construction", "--file", "letter.txt", "--body-file", "letter.txt",
        who="amy",
    )  # fmt: skip
    return {"letter": letter, "reply": reply, "access": p1.made(access, "received")}


def documents(ws: Workspace) -> dict[str, str]:
    p1.make_pdf(ws.root / "iso-6100.pdf", 3)
    for number, title, kind, discipline in (
        (DOCUMENT_B, "Isometric, line 47-P-101", "ISO", "PIP"),
        (DOCUMENT, "Isometric, line 47-P-103", "ISO", "PIP"),
        ("PID-4100", "P&ID, hydrotreater feed", "PID", "PRO"),
    ):
        ws.tl(
            "doc", "register", number, *P, "--title", title, "--type", kind,
            "--discipline", discipline, who="amy",
        )  # fmt: skip
    for number in (DOCUMENT_B, DOCUMENT):
        ws.tl("doc", "rev", "create", number, *P, "--purpose", "For review", who="amy")
        ws.tl(
            "doc", "rendition", "add", number, "A", "iso-6100.pdf", *P, "--kind", "pdf", who="amy"
        )
        ws.tl("doc", "rev", "issue", number, "A", *P, "--status", "IFR", who="demo")
    ws.tl("doc", "rev", "create", DOCUMENT_B, *P, "--purpose", "For construction", who="amy")
    return {}


# --- the shots -------------------------------------------------------------------------------


async def open_log(pilot: Pilot[Any], app: Any, key: str, number: str, what: str) -> DataTable[Any]:
    """Open a log with its key, put the cursor on ``number`` and wait for the panel to draw."""
    await pilot.press(key)
    await tk.until(pilot, lambda: number in tk.screen_text(app), what)
    table = app.screen.query_one("#log-table", DataTable)
    table.move_cursor(row=p1.row_with(table, number))
    await tk.settle(pilot, 4)
    return table


def log_shot(
    ws: Workspace,
    name: str,
    title: str,
    key: str,
    number: str,
    size: tuple[int, int],
    *needles: str,
    actor: str = "user:amy",
) -> None:
    app = p1.build_app(ws, actor=actor)

    async def scenario(pilot: Pilot[Any]) -> None:
        await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
        await open_log(pilot, app, key, number, "the log")
        await tk.until(pilot, lambda: "Open record" in tk.screen_text(app), "the actions bar")
        tk.shot_tui(ws, app, name, title, number, *needles)

    tk.run_tui(ws, app, scenario, size=size)


def record_shots(
    ws: Workspace,
    key: str,
    number: str,
    shots: list[tuple[str, str, str | None, tuple[str, ...]]],
    size: tuple[int, int],
) -> None:
    """Open the log ``key``, Enter on ``number``, then take each ``(name, title, tab key,
    needles)`` shot of the record screen (a tab key is pressed first)."""
    from tl_tui.widgets.record_screen import RecordScreen

    app = p1.build_app(ws, actor="user:amy")

    async def scenario(pilot: Pilot[Any]) -> None:
        await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
        await open_log(pilot, app, key, number, "the log")
        await pilot.press("enter")
        await tk.until(pilot, lambda: isinstance(app.screen, RecordScreen), "the record screen")
        for name, title, tab, needles in shots:
            if tab:
                await pilot.press(tab)
            await tk.until(pilot, lambda n=needles: all(x in tk.screen_text(app) for x in n), name)
            tk.shot_tui(ws, app, name, title, *needles)

    tk.run_tui(ws, app, scenario, size=size)


def shots(ws: Workspace, n: dict[str, str]) -> None:
    rfi = n["rfi"]
    log_shot(
        ws,
        "01-rfi-log-wide",
        "Ctrl+G: the RFI log at 170 columns: number, subject, state first; the record beside it",
        "ctrl+g",
        rfi,
        (170, 40),
        SUBJECTS["round"],
        "Question",
        "Structural",
        "[a] Answer",
    )
    log_shot(
        ws,
        "02-rfi-log-stacked",
        "The same log at 100 columns: the record panel moves below the list",
        "ctrl+g",
        rfi,
        (100, 40),
        SUBJECTS["round"],
        "Question",
    )
    record_shots(
        ws,
        "ctrl+g",
        rfi,
        [
            (
                "03-rfi-details",
                "Enter on the RFI: Details: the question, the answer, key facts, the timeline",
                None,
                ("Question", "Key facts", "Timeline", "Answer rejected", "Files ("),
            ),
            (
                "04-rfi-files",
                "6: the Files tab: each attachment with its kind, size and (for a PDF) pages",
                "6",
                ("beam-b12-sketch.pdf", "survey-notes.txt"),
            ),
        ],
        (150, 64),
    )
    log_shot(
        ws,
        "05-correspondence-log",
        "F5: the correspondence register: number, subject, state first; the letter beside it",
        "f5",
        n["reply"],
        (170, 44),
        "Revised programme",
        "Correspondence register",
        "Message",
    )
    record_shots(
        ws,
        "f5",
        n["reply"],
        [
            (
                "06-letter-details",
                "Enter on a letter: Details: the message, key facts, people, dates, clocks",
                None,
                ("Message", "Key facts", "People", "Dates", "Timeline"),
            )
        ],
        (150, 56),
    )
    saved = os.environ.get("TL_IMAGES")
    os.environ["TL_IMAGES"] = "off"  # a terminal without images: the panel gives the page count
    try:
        log_shot(
            ws,
            "07-document-log",
            "F7: the document log: number, title, state first; revisions and links in the panel",
            "f7",
            DOCUMENT_B,
            (170, 44),
            "Revisions",
            "Links",
            "Key facts",
        )
        log_shot(
            ws,
            "08-document-preview-line",
            "The preview line of a PDF where images are not shown: kind, size and 3 pages",
            "f7",
            DOCUMENT,
            (170, 44),
            "PDF document",
            "3 pages",
            "[v] Open file",
        )
    finally:
        if saved is None:
            os.environ.pop("TL_IMAGES", None)
        else:
            os.environ["TL_IMAGES"] = saved


INTENT_WHY = "Hold the answer until the drawing revision is confirmed"


def intent_event(ws: Workspace, rfi: str) -> None:
    """Link the RFI to the isometric with an intent: why, what it moves toward, and a goal."""
    ws.tl(
        "link", "add", rfi, DOCUMENT, *P, "--why", INTENT_WHY,
        "--toward", f"{DOCUMENT}:~the drawing is confirmed", "--goal-ref", "drawing-confirmed",
        who="amy",
    )  # fmt: skip


def activity_shots(ws: Workspace, n: dict[str, str]) -> None:
    """09 the RFI's Activity, 10 its Insights, 11 the Activity with an intent under the cursor."""
    rfi = n["rfi"]
    intent_event(ws, rfi)
    tk.CLOCK.advance(days=30)  # the answer clock of the round is past due: the Checks read says so
    record_shots(
        ws,
        "ctrl+g",
        rfi,
        [
            (
                "09-record-activity",
                "4: the Activity tab: the events of the RFI by person and day, newest first",
                "4",
                ("When", "Who", "Link"),
            ),
            (
                "10-record-insights",
                "9: the Insights tab: the checks that apply, each with its result and what to do",
                "9",
                ("Checks", "late"),
            ),
        ],
        (150, 80),
    )
    app = p1.build_app(ws, actor="user:amy")

    async def scenario(pilot: Pilot[Any]) -> None:
        from tl_tui.widgets.record_screen import RecordScreen

        await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
        await open_log(pilot, app, "ctrl+g", rfi, "the log")
        await pilot.press("enter")
        await tk.until(pilot, lambda: isinstance(app.screen, RecordScreen), "the record screen")
        await pilot.press("4")
        await tk.until(pilot, lambda: "Why: " in tk.screen_text(app), "the intent panel")
        tk.shot_tui(
            ws, app, "11-intent-panel",
            "4 with the cursor on an event that has an intent: why, next and toward, as stated",
            "Why: " + INTENT_WHY, "Toward: ISO-6100 -> the drawing is confirmed",
        )  # fmt: skip

    tk.run_tui(ws, app, scenario, size=(150, 80))


class _TourNow(datetime):
    """The tour's clock as ``datetime``: the awp handlers stamp the close and the progress
    with ``datetime.now``, and `tourkit.freeze` does not reach them."""

    @classmethod
    def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
        return tk.CLOCK.now if tz is None else tk.CLOCK.now.astimezone(tz)


class _TourToday(date):
    """The tour's day as ``date``: the pack's ``generated_on`` defaults to today."""

    @classmethod
    def today(cls) -> date:  # type: ignore[override]
        return tk.CLOCK.now.date()


def freeze_awp_clock() -> None:
    """Freeze the clock of the awp weekly plan, progress and pack (no wall-clock text anywhere)."""
    import tl_mod_awp.handlers.progress as awp_progress
    import tl_mod_awp.handlers.week as awp_week
    import tl_mod_awp.pack as awp_pack

    awp_week.datetime = _TourNow  # type: ignore[misc,assignment]
    awp_progress.datetime = _TourNow  # type: ignore[misc,assignment]
    awp_pack.date = _TourToday  # type: ignore[misc,assignment]


# --- the awp project P200 of the demo generator: the weekly cycle ----------------------------

AWP_PROJECT = w1.PROJECT
P200 = ("--project", AWP_PROJECT)
WEEK = "2026-W46"  # the ISO week of the Monday after the project calendar's today
ADMIN = "mokafor"  # project administrator
PLANNER = "lhartmann"  # project engineer, awp user
CONTROLLER = "ipetrov"  # awp controller (granted in the tour)
FOREMAN = "pnair"  # foreman, civil: the IWPs this foreman is on are Issued
PIPING = "cbrooks"  # foreman, piping: the new package
WEEKLY_ACTOR = f"user:{PLANNER}"


def login(ws: Workspace, who: str, password: str) -> None:
    ws.tl("login", who, "--password-stdin", stdin=password + "\n", who=who)


def version_of(output: str) -> int:
    """The version a command printed (`commit 2026-W46  version 4`)."""
    match = re.search(r"version (\d+)", output)
    tk.expect(match is not None, f"no version in:\n{output}")
    return int(match.group(1)) if match else 0


def issue(ws: Workspace, iwp: str, foreman: str) -> None:
    """Hash the IWP, two sign-offs of the hash, then issue it to the foreman."""
    out = ws.tl("awp", "iwp", "hash", iwp, *P200, who=PLANNER)
    found = re.search(r"record hash (\S+)", out)
    tk.expect(found is not None, f"no record hash for {iwp}")
    digest = found.group(1) if found else ""
    ws.tl("awp", "iwp", "sign-off", iwp, *P200, "--hash", digest, who=ADMIN)
    ws.tl("awp", "iwp", "sign-off", iwp, *P200, "--hash", digest, who=CONTROLLER)
    ws.tl("awp", "iwp", "issue", iwp, *P200, "--hash", digest, "--foreman", foreman, who=CONTROLLER)


def schedule(ws: Workspace, iwp: str) -> None:
    """A published schedule snapshot (a synthetic XER, as the demos use), with one IWP linked."""
    from tl_xer.synth import make_xer, week_pair

    first, _ = week_pair()
    (ws.root / "update-1.xer").write_bytes(make_xer(first))
    ws.tl("xer", "define", "MAIN", *P200, "--name", "Pipe rack schedule", "--type", "current",
          who=ADMIN)  # fmt: skip
    ws.tl("xer", "upload", "update-1.xer", *P200, "--schedule", "MAIN", who=PLANNER)
    ws.tl("xer", "worker", "--once", who=ADMIN)
    ws.tl("xer", "publish", "1", *P200, "--schedule", "MAIN", who=CONTROLLER)
    ws.tl("xer", "link", iwp, "A1230", *P200, "--schedule", "MAIN", who=PLANNER)


def new_package(ws: Workspace) -> str:
    """A new IWP with four scope items, through the constraint check to Ready; not yet issued."""
    created = ws.tl(
        "awp", "iwp", "create", *P200, "--discipline", "PIP",
        "--title", "Pipe rack spools, level 2",
        "--planned-start", "2026-11-16", "--planned-finish", "2027-02-05",
        "--foreman", f"user:{PIPING}", "--hours", "60", who=PLANNER,
    )  # fmt: skip
    iwp = created.split()[-1]  # `created IWP P200-IWP-PIP-0001`
    keys = [
        ws.tl(
            "awp",
            "iwp",
            "item-create",
            *P200,
            "--commodity",
            "piping",
            "--description",
            f"Spool {n}, line 48-P-{n}",
            "--qty",
            "10",
            "--uom",
            "m",
            "--hours",
            "4",
            who=PLANNER,
        ).split()[-1]
        for n in range(1, 5)
    ]
    ws.tl("awp", "iwp", "add-scope", iwp, *keys, *P200, who=PLANNER)
    ws.tl("awp", "iwp", "move", iwp, "start-development", *P200, who=PLANNER)
    ws.tl("awp", "iwp", "move", iwp, "constraint-check", *P200, who=PLANNER)
    for _ in range(2):  # the readiness worker evaluates the package (one run per step)
        ws.tl("awp", "worker", "--once", who=ADMIN)
    return iwp


def awp_world(ws: Workspace) -> tuple[str, str]:
    """The P200 project next to the RFI world, the schedule, the Issued packages and the week's
    commitments. Returns (the foreman's landing IWP, the new IWP of the week)."""
    w1.seed_demo_project(ws)
    tk.CLOCK.now = w1.TODAY  # the project calendar's today, as wave1 has it
    for who in (ADMIN, PLANNER, CONTROLLER, FOREMAN, PIPING):
        login(ws, who, GENERATOR_PASSWORD)
    ws.tl(
        "standards",
        "load",
        str(REPO / "schema/fixtures/standards/co.acme.standards@1.0.0.yaml"),
        who=ADMIN,
    )  # fmt: skip  (the units of measure of the scope items)
    ws.tl(
        "standards",
        "load",
        str(REPO / "schema/fixtures/standards/co.acme.awp@1.1.0.yaml"),
        who=ADMIN,
    )  # fmt: skip  (the miss reasons of the adopted edition)
    ws.tl("admin", "roles", "grant", CONTROLLER, *P200, "--module", "awp", "--role", "superuser",
          "--reason", "the awp controller of the weekly cycle", who=ADMIN)  # fmt: skip
    schedule(ws, "P200-IWP-INS-0005")
    for iwp in ("P200-IWP-INS-0005", "P200-IWP-INS-0006", "P200-IWP-ISL-0001"):
        issue(ws, iwp, f"user:{FOREMAN}")
    new = new_package(ws)
    issue(ws, new, f"user:{PIPING}")
    return "P200-IWP-INS-0005", new


def week_commit(ws: Workspace, iwps: list[tuple[str, str, str]]) -> None:
    """Open the week of the Monday, then commit each ``(IWP, foreman, hours)`` to it."""
    version = version_of(ws.tl("awp", "week", "open", "--date", "2026-11-09", *P200, who=PLANNER))
    for iwp, foreman, hours in iwps:
        out = ws.tl(
            "awp", "week", "commit", WEEK, iwp, "--foreman", foreman, "--hours", hours,
            "--expected-version", str(version), *P200, who=PLANNER,
        )  # fmt: skip
        version = version_of(out)


async def open_weekly_cycle(pilot: Pilot[Any], app: Any) -> None:
    """The palette entry "Weekly cycle", then wait for its steps line."""
    from tl_tui.widgets.palette import CommandPalette

    await pilot.press("ctrl+p")
    await tk.until(pilot, lambda: isinstance(app.screen, CommandPalette), "the palette")
    app.screen.query_one("#palette-input", Input).value = "Weekly cycle"
    await pilot.pause()
    await pilot.press("enter")
    await tk.until(pilot, lambda: "1 Look-ahead" in tk.screen_text(app), "the weekly cycle")


def week_shot(
    ws: Workspace,
    name: str,
    title: str,
    keys: tuple[str, ...],
    *needles: str,
    row: str | None = None,
) -> None:
    """The weekly cycle, opened from the palette and taken to step ``keys`` (1 to 5); the cursor
    goes to the row that shows ``row`` when one is given (its panel is the one shown)."""
    from tl_tui.main import build_app as make

    app = make(ws.db, AWP_PROJECT, live=False, actor=WEEKLY_ACTOR)

    async def scenario(pilot: Pilot[Any]) -> None:
        await tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")
        await open_weekly_cycle(pilot, app)
        for key in keys:
            await pilot.press(key)
            await tk.settle(pilot, 3)
        if row is not None:
            table = app.screen.query_one("#log-table", DataTable)
            table.move_cursor(row=p1.row_with(table, row))
            await tk.settle(pilot, 3)
        await tk.until(pilot, lambda: all(x in tk.screen_text(app) for x in needles), name)
        tk.shot_tui(ws, app, name, title, *needles)

    tk.run_tui(ws, app, scenario, size=(150, 64))


def landing_shot(ws: Workspace, iwp: str) -> None:
    """A foreman signs in: the app opens on the IWP log with mine on (T06c2)."""
    from tl_tui.main import build_app as make

    app = make(ws.db, AWP_PROJECT, live=False, actor=f"user:{FOREMAN}")

    async def scenario(pilot: Pilot[Any]) -> None:
        await tk.until(pilot, lambda: iwp in tk.screen_text(app), "the IWP log")
        tk.shot_tui(
            ws,
            app,
            "12-iwp-landing",
            "A foreman's landing: the IWP log opens with mine on; Ready, Blocking and Since",
            iwp,
            "Ready",
            "Blocking",
            "Since",
        )

    tk.run_tui(ws, app, scenario, size=(170, 44))


def weekly_shots(ws: Workspace, landing: str, new: str) -> None:
    """12 the foreman's landing; 13 to 17 the weekly cycle through its steps; 18 the work pack.
    Each screen is a fresh read of the ledger, so the commands of the cycle run between them."""
    landing_shot(ws, landing)
    week_commit(
        ws,
        [
            ("P200-IWP-INS-0005", f"user:{FOREMAN}", "120"),
            ("P200-IWP-INS-0006", f"user:{FOREMAN}", "60"),
            ("P200-IWP-ISL-0001", f"user:{FOREMAN}", "80"),
            (new, f"user:{PIPING}", "120"),
        ],
    )
    week_shot(
        ws, "13-week-look-ahead", "Weekly cycle, step 1: the look-ahead of the next weeks",
        ("1",), "Look-ahead", "need-by",
    )  # fmt: skip
    week_shot(
        ws, "14-week-constraints", "Step 2: a check-raised constraint, cleared as waived",
        ("2",), "waived", row="P200-CON-0045",
    )  # fmt: skip
    ws.tl("awp", "week", "outcome", WEEK, new, "done", *P200, who=PLANNER)
    ws.tl("awp", "week", "outcome", WEEK, "P200-IWP-ISL-0001", "done", *P200, who=PLANNER)
    ws.tl("awp", "week", "outcome", WEEK, "P200-IWP-INS-0005", "done", *P200, who=PLANNER)
    last = ws.tl(
        "awp", "week", "outcome", WEEK, "P200-IWP-INS-0006", "missed", "--reason", "Weather",
        *P200, who=PLANNER,
    )  # fmt: skip
    week_shot(
        ws, "15-week-commitments", "Step 4: the committed IWPs, their hours and foremen, outcomes",
        ("4",), "Commitments", "Weather",
    )  # fmt: skip
    week_shot(
        ws, "16-week-progress", "Step 5: the earned percent per IWP, the PPC and constraint-free",
        ("5",), "PPC", "Constraint",
    )  # fmt: skip
    closed = ws.tl(
        "awp", "week", "close", WEEK, "--expected-version", str(version_of(last)), *P200,
        who=CONTROLLER,
    )  # fmt: skip
    tk.expect(closed.startswith("close "), f"the week did not close:\n{closed}")
    week_shot(
        ws, "17-week-closed", "Step 4 once the week is closed: its PPC in the summary",
        ("4",), "Closed", "PPC",
    )  # fmt: skip
    name = f"pack-{new}.html"
    out = ws.tl("awp", "iwp", "pack", new, *P200, "--out", name, who=PLANNER)
    shutil.copyfile(ws.root / name, ws.out / name)
    ws.shot_cli(
        "18-iwp-pack",
        "The work pack of an IWP: one HTML file, kept beside the screenshots",
        [(f"tl awp iwp pack {new} --out {name}", out)],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=REPO / "docs/reports/tour/highlights")
    args = parser.parse_args(argv)
    out = args.out if args.out.is_absolute() else Path.cwd() / args.out
    for old in out.glob("*.svg"):
        old.unlink()
    tk.freeze()
    freeze_awp_clock()
    tk.fixed_archive_key()
    ws = Workspace(out)
    try:
        print("building the world: people, standards, RFIs, letters, documents", flush=True)
        numbers = world(ws)
        print("the shots", flush=True)
        shots(ws, numbers)
        activity_shots(ws, numbers)
    finally:
        ws.close()
    # The awp project has a ledger of its own: the demo generator numbers documents by its own
    # pattern, which the company documents standards of the RFI world refuse (see the report).
    awp = Workspace(out)
    try:
        print("the weekly cycle of P200: the schedule, the packages, the week", flush=True)
        landing, new = awp_world(awp)
        weekly_shots(awp, landing, new)
    finally:
        awp.close()
    print(f"wrote {len(ws.written) + len(awp.written)} screenshots to {out}")
    return tk.report_leaks()


if __name__ == "__main__":
    sys.exit(main())
