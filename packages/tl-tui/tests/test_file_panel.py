"""FilePanel: the file rows, the text fallback, the picture, open in the viewer (P1-UX2-S4).

The tests use the text fallback (``TL_IMAGES=off``) except the one that draws a picture, which
needs no terminal image: the picture is half-block cells in a Rich renderable.
"""

from __future__ import annotations

import hashlib
import sys
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from doc_support import pdf_bytes, settle
from fakes import FakeClient
from helpers import run_pilot
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from textual.widgets import Static
from tl_core.files.queries import FileInfo
from tl_tui.file_text import human_size
from tl_tui.preview import render
from tl_tui.widgets.file_panel import NO_FILES, NOT_AVAILABLE, FilePanel

RECORD = "REV-ISO-1234-B"
OFF = {"TL_IMAGES": "off"}


class Opened:
    """A launcher spy: records the path and what the file held when it was launched."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int, int]] = []

    def __call__(self, argv: Sequence[str]) -> None:
        path = Path(argv[-1])
        mode = path.stat().st_mode & 0o777
        folder = path.parent.stat().st_mode & 0o777
        self.calls.append((path.name, hashlib.sha256(path.read_bytes()).hexdigest(), mode, folder))


class PanelApp(App[None]):
    def __init__(self, panel: FilePanel) -> None:
        super().__init__()
        self.panel = panel
        self.notes: list[FilePanel.Note] = []

    def compose(self) -> ComposeResult:
        yield self.panel

    def on_file_panel_note(self, message: FilePanel.Note) -> None:
        self.notes.append(message)


def drive(panel: FilePanel, steps: Any) -> PanelApp:
    app = PanelApp(panel)

    async def go(pilot: Pilot[None]) -> None:
        await settle(pilot)
        await steps(pilot, app)

    run_pilot(app, go)
    return app


def shown(panel: FilePanel) -> str:
    return str(panel.query_one("#fp-lines", Static).render())


def make_panel(
    client: FakeClient, tmp_path: Path, env: dict[str, str] | None = None, launcher: Any = None
) -> FilePanel:
    return FilePanel(
        client, env=OFF if env is None else env, launcher=launcher, cache_root=tmp_path / "cache"
    )


def test_the_text_fallback_shows_type_size_and_page_count(tmp_path: Path) -> None:
    client = FakeClient()
    data = pdf_bytes(pages=3)
    info = client.add_record_file(RECORD, "sheet-B.pdf", data)
    panel = make_panel(client, tmp_path)

    async def steps(pilot: Pilot[None], app: PanelApp) -> None:
        panel.show(RECORD, {info.sha256: 3})
        await settle(pilot)
        assert shown(panel) == f"> sheet-B.pdf  PDF document  {human_size(len(data))}  3 pages"
        assert panel.thumbnail is None

    drive(panel, steps)
    assert "fetch_file" not in client.calls  # the hint made a download needless


def test_without_a_hint_the_page_count_comes_from_the_render(tmp_path: Path) -> None:
    client = FakeClient()
    client.add_record_file(RECORD, "plan.pdf", pdf_bytes(pages=4))
    panel = make_panel(client, tmp_path)

    async def steps(pilot: Pilot[None], app: PanelApp) -> None:
        panel.show(RECORD)
        await settle(pilot)
        assert "PDF document" in shown(panel) and "4 pages" in shown(panel)
        assert panel.thumbnail is None  # no colour: text only

    drive(panel, steps)


def test_no_picture_library_is_imported_when_the_terminal_shows_none(tmp_path: Path) -> None:
    for name in [m for m in sys.modules if m == "rich_pixels" or m.startswith("rich_pixels.")]:
        del sys.modules[name]
    client = FakeClient()
    client.add_record_file(RECORD, "plan.pdf", pdf_bytes())
    panel = make_panel(client, tmp_path, env={"TERM": "dumb"})

    async def steps(pilot: Pilot[None], app: PanelApp) -> None:
        panel.show(RECORD)
        await settle(pilot)
        assert "1 page" in shown(panel)

    drive(panel, steps)
    assert "rich_pixels" not in sys.modules


def test_a_terminal_with_colour_gets_the_page_as_half_block_cells(tmp_path: Path) -> None:
    client = FakeClient()
    client.add_record_file(RECORD, "plan.pdf", pdf_bytes(pages=2, width=300, height=400))
    panel = make_panel(client, tmp_path, env={"TL_IMAGES": "kitty"})

    async def steps(pilot: Pilot[None], app: PanelApp) -> None:
        panel.show(RECORD)
        await settle(pilot)
        thumb = panel.query_one("#fp-thumb", Static)
        assert panel.thumbnail is not None and thumb.display
        assert "2 pages" in shown(panel)
        cols, rows = panel.thumbnail_cells
        assert (cols, rows) == (30, 20)  # a 3:4 page: 30 columns, 40 pixels, 20 rows
        assert thumb.size.height == rows
        panel.show(None)
        await settle(pilot)
        assert panel.thumbnail is None and not thumb.display

    drive(panel, steps)


def test_a_failed_render_leaves_the_text_line(tmp_path: Path) -> None:
    client = FakeClient()
    client.add_record_file(RECORD, "broken.pdf", pdf_bytes()[:40])  # a truncated PDF
    panel = make_panel(client, tmp_path, env={"TL_IMAGES": "kitty"})

    async def steps(pilot: Pilot[None], app: PanelApp) -> None:
        panel.show(RECORD)
        await settle(pilot)
        assert panel.thumbnail is None
        assert "broken.pdf  PDF document" in shown(panel) and "page" not in shown(panel)

    drive(panel, steps)


def test_v_fetches_into_a_private_folder_then_opens_the_verified_file(tmp_path: Path) -> None:
    client = FakeClient()
    data = pdf_bytes(pages=2)
    info = client.add_record_file(RECORD, "sheet B.pdf", data)
    spy = Opened()
    panel = make_panel(client, tmp_path, launcher=spy)

    async def steps(pilot: Pilot[None], app: PanelApp) -> None:
        panel.show(RECORD, {info.sha256: 2})
        await settle(pilot)
        assert "fetch_file" not in client.calls
        panel.focus()
        await pilot.press("v")
        await settle(pilot)
        assert spy.calls == [("sheet B.pdf", info.sha256, 0o600, 0o700)]
        assert client.calls.count("fetch_file") == 1
        assert app.notes[-1].text == "Opened sheet B.pdf." and not app.notes[-1].error
        await pilot.press("enter")  # Enter on the file line opens it too; no second download
        await settle(pilot)
        assert len(spy.calls) == 2 and client.calls.count("fetch_file") == 1
        folder = panel._temp.directory  # noqa: SLF001
        assert folder.exists()
        panel.remove()
        await settle(pilot)
        assert not folder.exists()  # the screen closed: everything fetched is gone

    drive(panel, steps)


def test_an_unreadable_launcher_is_told_not_raised(tmp_path: Path) -> None:
    client = FakeClient()
    info = client.add_record_file(RECORD, "a.pdf", pdf_bytes())

    def broken(argv: Sequence[str]) -> None:
        raise FileNotFoundError("no xdg-open")

    panel = make_panel(client, tmp_path, launcher=broken)

    async def steps(pilot: Pilot[None], app: PanelApp) -> None:
        panel.show(RECORD, {info.sha256: 1})
        await settle(pilot)
        panel.action_open_file()
        await settle(pilot)
        assert app.notes[-1].error and app.notes[-1].text == "The file could not be opened."

    drive(panel, steps)


def test_a_hidden_file_reads_the_same_as_a_missing_one(tmp_path: Path) -> None:
    client = FakeClient()
    info = client.add_record_file(RECORD, "secret.pdf", pdf_bytes())
    spy = Opened()
    panel = make_panel(client, tmp_path, launcher=spy)
    words: list[str] = []

    async def steps(pilot: Pilot[None], app: PanelApp) -> None:
        panel.show(RECORD, {info.sha256: 1})
        await settle(pilot)
        client.hide_record(RECORD)  # the viewer lost the right to read it
        panel.action_open_file()
        await settle(pilot)
        words.append(app.notes[-1].text)
        client._hidden_records.clear()  # noqa: SLF001
        client._known_files.clear()  # noqa: SLF001  (a file id this client never listed)
        panel.action_open_file()
        await settle(pilot)
        words.append(app.notes[-1].text)
        assert words == [NOT_AVAILABLE, NOT_AVAILABLE] and app.notes[-1].error
        assert spy.calls == []  # nothing was launched

    drive(panel, steps)


def test_a_hidden_record_lists_the_same_as_one_with_no_files(tmp_path: Path) -> None:
    client = FakeClient()
    client.add_record_file("hidden-rec", "x.pdf", pdf_bytes())
    client.hide_record("hidden-rec")
    panel = make_panel(client, tmp_path)
    lines: list[str] = []

    async def steps(pilot: Pilot[None], app: PanelApp) -> None:
        panel.show("hidden-rec")
        await settle(pilot)
        lines.append(shown(panel))
        panel.show("no-such-record")
        await settle(pilot)
        lines.append(shown(panel))
        assert lines == [NO_FILES, NO_FILES]
        assert "x.pdf" not in lines[0]

    drive(panel, steps)


def test_a_new_selection_cancels_the_previous_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = FakeClient()
    first = client.add_record_file(RECORD, "first.pdf", pdf_bytes(pages=5))
    second = client.add_record_file(RECORD, "second.pdf", pdf_bytes(pages=2))
    started, was_cancelled = threading.Event(), threading.Event()
    real = render.render_first_page

    def slow(path: Path, sha256: str, **kwargs: Any) -> render.PreviewResult:
        if sha256 != first.sha256:
            return real(path, sha256, **kwargs)
        started.set()
        for _ in range(200):
            if kwargs["cancelled"]():
                was_cancelled.set()
                return render.PreviewResult("error")
            threading.Event().wait(0.02)
        return render.PreviewResult("ok", 5, None)

    monkeypatch.setattr(render, "render_first_page", slow)
    panel = make_panel(client, tmp_path, env={"TL_IMAGES": "kitty"})

    async def steps(pilot: Pilot[None], app: PanelApp) -> None:
        panel.show(RECORD)
        for _ in range(100):
            await pilot.pause(0.05)
            if started.is_set():
                break
        assert started.is_set()
        panel.focus()
        await pilot.press("down")  # the second file: the first render must stop
        await settle(pilot)
        assert was_cancelled.is_set()
        assert panel.index == 1 and "2 pages" in shown(panel) and "5 pages" not in shown(panel)
        assert panel.thumbnail is not None

    drive(panel, steps)
    assert second.sha256 in {p.stem for p in (tmp_path / "cache").iterdir()}


def test_a_file_that_is_not_a_pdf_gets_a_line_and_no_render(tmp_path: Path) -> None:
    client = FakeClient()
    client.add_record_file(RECORD, "memo.docx", b"PK zip", content_type="application/octet-stream")
    panel = make_panel(client, tmp_path, env={"TL_IMAGES": "kitty"})

    async def steps(pilot: Pilot[None], app: PanelApp) -> None:
        panel.show(RECORD)
        await settle(pilot)
        assert shown(panel).startswith("> memo.docx  Word document  6 B")
        assert panel.thumbnail is None and "fetch_file" not in client.calls

    drive(panel, steps)


def test_the_file_info_type_is_what_the_client_returns() -> None:
    assert FileInfo.model_fields["sha256"] is not None
