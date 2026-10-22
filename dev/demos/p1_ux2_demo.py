"""Driver for dev/demos/P1-UX2.sh: the log standard, the RFI record and document preview.

Modes (first argument), each ending in a PASS line for its clause:

* ``prepare DIR``: write the sample files into DIR: a 3-page PDF for the document, a one-page PDF
  and a text file for the RFI, the long question, the two subjects, and the recorder script that
  stands in for the system viewer (``TL_VIEWER_CMD``).
* ``crumb``: clause 1. In the RFI log the breadcrumb reads ``P123 > RFI log > <number>: <title>``
  for the highlighted row and changes when the cursor moves.
* ``bar``: clause 2. The actions bar of an RFI awaiting an answer shows Answer, and not once it is
  answered; an RFI waiting to be issued shows Issue to a controller and not to a plain user (an
  agent cannot open the TUI); ``a``, typed text and Ctrl+S from the bar answer the RFI and the
  status line stays clean.
* ``record``: clause 3. The RFI record opened from the log shows the question whole first, the
  timeline of the answer round in order, and the Files tab lists both files.
* ``preview``: clause 4. ``v`` on the document row hands a copy of the PDF to the viewer: it sits
  in a private folder (mode 0700) and its sha256 equals the stored file's; with images off the
  panel reads ``PDF document ... 3 pages``.

Reads TL_DB (a SQLite path or postgresql:// URL), TL_DEMO_RFI_1 to TL_DEMO_RFI_3 (the RFI
numbers) and, for ``preview``, TL_DEMO_VIEWER_OUT. Every expectation is an assert: a failing
demo exits non-zero. Nothing printed holds a password or token.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import stat
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
SIZE = (200, 70)
CRUMB_HEAD = f"{PROJECT} › RFI log › "

SUBJECT_1 = "Conflict in piling and utilities at AZ203"
SUBJECT_2 = "Gasket class for the new flange at line 47"
SUBJECT_3 = "Cable tray support spacing in the pipe rack"
QUESTION = (
    "The piling layout in revision B puts pile P-17 inside the route of the fuel gas line "
    "47-P-101, and the utilities drawing shows the same corridor for the cooling water return. "
    "Please confirm which of the two keeps the corridor, whether the pile can move 400 mm to the "
    "east without a new load calculation, and whether the cooling water line may be re-routed "
    "above the beam B12 if the pile stays where it is. We need the answer before the pile cap "
    "formwork is ordered."
)
VIEWER = """\
import hashlib
import json
import os
import stat
import sys

path = sys.argv[-1]
folder = os.path.dirname(path)
info = {
    "path": path,
    "folder_mode": stat.S_IMODE(os.stat(folder).st_mode),
    "file_mode": stat.S_IMODE(os.stat(path).st_mode),
    "sha256": hashlib.sha256(open(path, "rb").read()).hexdigest(),
}
out = os.environ["TL_DEMO_VIEWER_OUT"]
with open(out + ".tmp", "w") as handle:
    json.dump(info, handle)
os.replace(out + ".tmp", out)
"""


def say(text: str) -> None:
    print(f"   {text}")


def passed(clause: int, text: str) -> None:
    print(f"PASS {clause}: {text}")


def screen_text(app: Any) -> str:
    """The screen as plain text, the way the viewer sees it."""
    strips = app.screen._compositor.render_strips()
    return "\n".join(strip.text.rstrip() for strip in strips)


def text_of(app: Any, ident: str) -> str:
    from textual.widgets import Static

    return str(app.screen.query_one(ident, Static).render())


async def settle(pilot: Any, rounds: int = 4) -> None:
    for _ in range(rounds):
        await pilot.pause()
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()


async def until(pilot: Any, predicate: Callable[[], object], what: str, tries: int = 400) -> None:
    for _ in range(tries):
        if predicate():
            await settle(pilot, 2)
            return
        await pilot.pause(0.05)
    raise AssertionError(f"timed out waiting for {what}:\n{screen_text(pilot.app)}")


def make_app(actor: str, *, controller: bool = False) -> Any:
    from tl_tui.main import build_app

    return build_app(
        os.environ["TL_DB"],
        PROJECT,
        live=False,
        actor=actor,
        is_admin=False,
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


def numbers() -> tuple[str, str, str]:
    return os.environ["TL_DEMO_RFI_1"], os.environ["TL_DEMO_RFI_2"], os.environ["TL_DEMO_RFI_3"]


def title_of(number: str) -> str:
    first, second, _third = numbers()
    return {first: SUBJECT_1, second: SUBJECT_2}.get(number, SUBJECT_3)


def table_of(app: Any) -> Any:
    from textual.widgets import DataTable

    return app.screen.query_one("#log-table", DataTable)


def row_number(table: Any) -> str:
    """The RFI number in the highlighted row."""
    cells = [str(cell) for cell in table.get_row_at(table.cursor_row)]
    for number in numbers():
        if any(number in cell for cell in cells):
            return number
    raise AssertionError(f"no RFI number in the highlighted row: {cells}")


async def open_rfi_log(pilot: Any) -> Any:
    """Ctrl+G, 1: the RFI log; return its table once the rows and the bar have been read."""
    app = pilot.app
    await pilot.press("ctrl+g")
    await settle(pilot)
    await pilot.press("1")
    await until(pilot, lambda: app.screen.query("#log-table"), "the RFI log")
    table = table_of(app)
    await until(pilot, lambda: table.row_count >= 3, "three RFIs in the log")
    return table


async def go_to(pilot: Any, table: Any, number: str) -> None:
    """Move the cursor to the row of ``number`` (the way a person arrows to it)."""
    rows = [
        index
        for index in range(table.row_count)
        if any(number in str(cell) for cell in table.get_row_at(index))
    ]
    assert rows, f"{number} is not in the log"
    while table.cursor_row != rows[0]:
        await pilot.press("down" if table.cursor_row < rows[0] else "up")
        await settle(pilot)
    await settle(pilot)


# --- clause 1 ---------------------------------------------------------------------------------


async def crumb_scenario(pilot: Any) -> list[str]:
    app = pilot.app
    table = await open_rfi_log(pilot)
    seen: list[str] = []
    for _ in range(2):
        number = row_number(table)
        expected = f"{CRUMB_HEAD}{number}: {title_of(number)}"
        shown = text_of(app, "#log-crumb")
        assert shown == expected, f"the crumb reads {shown!r}, not {expected!r}"
        seen.append(shown)
        await pilot.press("down")
        await settle(pilot)
    assert seen[0] != seen[1], "the crumb did not change when the cursor moved"
    return seen


def crumb() -> None:
    seen = run(make_app("user:amy"), crumb_scenario)
    for line in seen:
        say(line)
    passed(
        1,
        "the breadcrumb reads project, log, number and title for the highlighted row and "
        "changes when the cursor moves",
    )


# --- clause 2 ---------------------------------------------------------------------------------


async def bar_of(pilot: Any, number: str) -> tuple[Any, str]:
    table = await open_rfi_log(pilot)
    await go_to(pilot, table, number)
    await until(
        pilot, lambda: "Open record" in text_of(pilot.app, "#log-actions"), "the actions bar"
    )
    return table, text_of(pilot.app, "#log-actions")


async def answerer_scenario(pilot: Any) -> dict[str, str]:
    """Amy sees Answer on the RFI awaiting an answer, answers from the bar, and sees it go."""
    app = pilot.app
    _first, second, third = numbers()
    table, bar = await bar_of(pilot, second)
    assert "[a] Answer" in bar, f"the answerer's bar has no Answer: {bar!r}"
    state_before = rfi_state(second)
    await pilot.press("a")
    await settle(pilot)
    text = "Use class 300 spiral-wound gaskets."
    await pilot.press(*text)
    await pilot.press("ctrl+s")
    await until(pilot, lambda: rfi_state(second) != state_before, "the RFI to move")
    await settle(pilot, 6)
    status = text_of(app, "#log-status")
    assert "!" not in status, f"the status line shows a refusal: {status!r}"
    await go_to(pilot, table, third)  # away and back: the bar is read again for the row
    await go_to(pilot, table, second)
    await until(
        pilot, lambda: "Open record" in text_of(app, "#log-actions"), "the bar of the answered RFI"
    )
    after_bar = text_of(app, "#log-actions")
    assert "[a] Answer" not in after_bar, f"Answer is still offered once answered: {after_bar!r}"
    return {
        "bar": bar,
        "before": state_before,
        "after": rfi_state(second),
        "status": status,
        "after_bar": after_bar,
    }


async def internal_review_scenario(pilot: Any) -> str:
    """The bar of the RFI that waits for a controller to issue it."""
    _first, _second, third = numbers()
    _table, bar = await bar_of(pilot, third)
    return bar


def rfi_state(number: str) -> str:
    from tl_tui.embedded import EmbeddedClient

    client = EmbeddedClient.for_target(os.environ["TL_DB"], actor="user:demo")
    try:
        return str(client.get_rfi(PROJECT, number).state)
    finally:
        client.close()


def bar() -> None:
    # What a person is offered depends on who they are: the RFI waiting to be issued shows Issue
    # to a controller and not to a plain user (an agent cannot open the TUI at all).
    reader_bar = run(make_app("user:amy"), internal_review_scenario)
    controller_bar = run(make_app("user:dora", controller=True), internal_review_scenario)
    assert "Issue" not in reader_bar, f"a plain user is offered Issue: {reader_bar!r}"
    assert "[u] Issue" in controller_bar, f"a controller is not offered Issue: {controller_bar!r}"
    found = run(make_app("user:amy"), answerer_scenario)
    assert found["after"] == "Answered", f"the RFI is {found['after']!r}, not Answered"
    say(f"answerer's bar, RFI awaiting an answer: {found['bar']}")
    say(f"same RFI once answered:                  {found['after_bar']}")
    say(f"RFI waiting to be issued, amy:  {reader_bar}")
    say(f"RFI waiting to be issued, dora: {controller_bar}")
    say(
        f"Answer from the bar: {found['before']} -> {found['after']}; "
        f"status line {found['status']!r}"
    )
    passed(
        2,
        "the bar offers Answer where an answer is due and Issue only to a controller, nothing "
        "that would be refused, and Answer from the bar answers the RFI with a clean status line",
    )


# --- clause 3 ---------------------------------------------------------------------------------

TIMELINE = ("Raised", "Submitted", "Issued", "Answered", "Answer rejected", "Reissued", "Issued")


async def record_scenario(pilot: Any) -> dict[str, Any]:
    from tl_tui.widgets.record_screen import RecordScreen

    app = pilot.app
    first, _second, _third = numbers()
    table = await open_rfi_log(pilot)
    await go_to(pilot, table, first)
    await pilot.press("enter")
    await until(pilot, lambda: isinstance(app.screen, RecordScreen), "the record screen")
    await until(pilot, lambda: "Question" in screen_text(app), "the narrative")
    await settle(pilot, 6)
    details = screen_text(app)
    flat = " ".join(details.split())
    assert " ".join(QUESTION.split()) in flat, "the question is not shown whole"
    head = details.index("Question")
    assert "Number" not in details[:head] and "Created" not in details[:head], (
        "metadata comes before the question"
    )
    lines = details.splitlines()
    found: list[int] = []
    for word in TIMELINE:  # each row after the one before it
        pattern = re.compile(rf"\d{{4}}-\d{{2}}-\d{{2}}\s+\S+: {re.escape(word)}(\s|$)")
        start = found[-1] + 1 if found else 0
        hits = [i for i, line in enumerate(lines) if i >= start and pattern.search(line)]
        assert hits, f"no timeline row {word!r} after line {start} on\n{details}"
        found.append(hits[0])
    question_line = next(i for i, line in enumerate(lines) if line.startswith("Question"))
    assert question_line < found[0], "the timeline comes before the question"
    await pilot.press("6")
    await until(pilot, lambda: "survey-notes.txt" in screen_text(app), "the Files tab")
    files = screen_text(app)
    for name in ("beam-b12-sketch.pdf", "survey-notes.txt"):
        assert name in files, f"{name} is not in the Files tab:\n{files}"
    return {"rows": len(TIMELINE), "files": 2}


def record() -> None:
    found = run(make_app("user:amy"), record_scenario)
    say(
        f"Details start with the question (whole); {found['rows']} timeline rows in order; "
        f"{found['files']} files on the Files tab"
    )
    passed(3, "the RFI record shows the narrative, the timeline in order and both files")


# --- clause 4 ---------------------------------------------------------------------------------


def stored_sha(client: Any) -> str:
    """The sha256 the file service holds for the current revision of ISO-1234."""
    view = client.get_document(PROJECT, "ISO-1234")
    current = [r for r in view.revisions if r.is_current] or view.revisions[-1:]
    files = client.list_record_files(current[0].id)
    assert len(files) == 1, f"{len(files)} files on the revision"
    return str(files[0].sha256)


async def preview_scenario(pilot: Any) -> dict[str, Any]:
    app = pilot.app
    out = Path(os.environ["TL_DEMO_VIEWER_OUT"])
    await pilot.press("f7")
    await until(pilot, lambda: app.screen.query("#log-table"), "the document log")
    table = table_of(app)
    await until(pilot, lambda: table.row_count >= 1, "the document row")
    await until(pilot, lambda: "Open file" in text_of(app, "#log-actions"), "the Open file action")
    await until(pilot, lambda: "3 pages" in screen_text(app), "the page-count fallback")
    panel = screen_text(app)
    fallback = next(line.strip(" │>") for line in panel.splitlines() if "3 pages" in line)
    assert re.search(r"PDF document\s+.*3 pages", fallback), f"the fallback reads {fallback!r}"
    stored = stored_sha(app.client)
    await pilot.press("v")
    await until(pilot, out.exists, "the viewer to receive the path", tries=300)
    return {"fallback": fallback, "stored": stored, "viewer": json.loads(out.read_text())}


def preview() -> None:
    found = run(make_app("user:amy"), preview_scenario)
    viewer = found["viewer"]
    folder = Path(viewer["path"]).parent
    assert viewer["folder_mode"] == 0o700, f"the folder is mode {viewer['folder_mode']:o}"
    assert stat.S_IMODE(viewer["file_mode"]) & 0o077 == 0, "the file is open to other users"
    assert folder.name.startswith("throughline-open-"), folder.name
    assert viewer["sha256"] == found["stored"], "the opened copy differs from the stored file"
    assert not folder.exists(), "the private folder was not removed when the screen closed"
    say(
        f"the viewer got a file in a private folder (mode {viewer['folder_mode']:o}); "
        f"its sha256 equals the stored file's; the folder is gone after the screen closed"
    )
    say(f"panel: {found['fallback']}")
    passed(
        4,
        "v opens the PDF from a private temp copy whose sha256 equals the stored file's, "
        "and the panel reads the page-count fallback",
    )


# --- seed -------------------------------------------------------------------------------------


def make_pdf(path: Path, pages: int) -> None:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument.new()
    for _ in range(pages):
        document.new_page(300, 400)
    document.save(str(path))


def prepare(directory: str) -> None:
    root = Path(directory)
    make_pdf(root / "iso-1234.pdf", 3)
    make_pdf(root / "beam-b12-sketch.pdf", 1)
    (root / "survey-notes.txt").write_text(
        "Survey of the corridor at AZ203\npile P-17 at grid C-4, east offset to be confirmed\n"
    )
    (root / "question").write_text(QUESTION)
    (root / "subject-1").write_text(SUBJECT_1)
    (root / "subject-2").write_text(SUBJECT_2)
    (root / "subject-3").write_text(SUBJECT_3)
    (root / "viewer.py").write_text(VIEWER)
    say("wrote the sample files and the viewer recorder")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "prepare":
        prepare(sys.argv[2])
    elif mode == "crumb":
        crumb()
    elif mode == "bar":
        bar()
    elif mode == "record":
        record()
    elif mode == "preview":
        preview()
    else:
        raise SystemExit(f"unknown mode {mode!r}")


if __name__ == "__main__":
    main()
