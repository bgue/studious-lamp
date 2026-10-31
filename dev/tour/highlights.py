"""The highlight tour: only the everyday screens, for a quick look at how Throughline reads.

    uv run python dev/tour/highlights.py [--out docs/reports/tour/highlights]
    just tour highlights

Same method as `phase1.py` (see `tourkit.py`): a fresh SQLite ledger in a temporary directory,
the standards code lists loaded (so a discipline reads `Structural`, not `STR`), the real TUI
driven headless, the frozen clock, and the leak check on every plain screenshot. It writes eight
SVGs and no transcripts:

    01 RFI log, 170 columns (the panel beside the list)    05 correspondence log
    02 RFI log, 100 columns (the panel below the list)     06 a letter's Details
    03 an RFI's Details                                    07 the document log
    04 the same RFI's Files tab                            08 the document preview line

The text is `docs/reports/HIGHLIGHTS-TOUR.md`; its headings match the file names. The people and
helpers are those of `phase1.py`.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

import phase1 as p1
import tourkit as tk
from textual.pilot import Pilot
from textual.widgets import DataTable
from tourkit import Workspace

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=REPO / "docs/reports/tour/highlights")
    args = parser.parse_args(argv)
    out = args.out if args.out.is_absolute() else Path.cwd() / args.out
    for old in out.glob("*.svg"):
        old.unlink()
    tk.freeze()
    tk.fixed_archive_key()
    ws = Workspace(out)
    try:
        print("building the world: people, standards, RFIs, letters, documents", flush=True)
        numbers = world(ws)
        print("the shots", flush=True)
        shots(ws, numbers)
    finally:
        ws.close()
    print(f"wrote {len(ws.written)} screenshots to {out}")
    return tk.report_leaks()


if __name__ == "__main__":
    sys.exit(main())
