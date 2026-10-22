"""The files of one record, with the page-1 picture of the selected PDF (P1-UX2-S4).

``FilePanel.show(record_id)`` lists the record's current files (``list_record_files``, off the UI
thread) as ``file_line`` rows. ``v`` or Enter opens the selected file: it is fetched into a
``PrivateTemp`` (size and SHA-256 verified by ``fetch_file``) and handed to the system viewer.
Where the terminal has colour (``image_protocol(env) != "none"``) the first page of a PDF is drawn
as half-block cells; elsewhere, or when the drawing fails, the line shows the type, size and page
count. The picture is made by ``render_first_page`` (a bounded child process, cached by content
hash) in a worker thread; selecting another file cancels the previous one. ``rich_pixels`` is
imported only when a picture is drawn. A hidden file and a missing one read the same:
``NOT_AVAILABLE``.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from rich.console import RenderableType
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static
from textual.worker import get_current_worker
from tl_core.files.queries import FileInfo
from tl_core.services.errors import UnknownFileError

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.file_text import file_kind, file_line
from tl_tui.preview import cache, render
from tl_tui.preview.temp import PrivateTemp
from tl_tui.preview.terminal import image_protocol
from tl_tui.preview.viewer import Launcher, open_in_viewer

if TYPE_CHECKING:
    from textual.worker import Worker

NOT_AVAILABLE = "File not available."
NO_FILES = "No files."
THUMB_COLUMNS = 30  # the picture is about this wide (cells)
THUMB_MAX_ROWS = 20  # and at most this tall (two pixels per row)
PDF_KIND = "PDF document"


class FilePanel(Widget, can_focus=True):
    """The files of one record. Keys (when focused): Up/Down choose a file, ``v``/Enter open it."""

    class Note(Message):
        """Something to tell the person (an open failed, or a file went missing)."""

        def __init__(self, text: str, *, error: bool = False) -> None:
            super().__init__()
            self.text = text
            self.error = error

    class Listed(Message):
        """The record's files were read: ``count`` of them."""

        def __init__(self, count: int) -> None:
            super().__init__()
            self.count = count

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("v", "open_file", "Open", show=False),
        Binding("enter", "open_file", "Open", show=False),
        Binding("up", "choose(-1)", show=False),
        Binding("down", "choose(1)", show=False),
    ]

    DEFAULT_CSS = """
    FilePanel { height: auto; }
    FilePanel #fp-lines, FilePanel #fp-thumb, FilePanel #fp-note { height: auto; }
    FilePanel #fp-note { color: $text-muted; }
    """

    def __init__(
        self,
        client: ClientInterface,
        *,
        env: Mapping[str, str] | None = None,
        launcher: Launcher | None = None,
        cache_root: Path | None = None,
        id: str | None = None,  # noqa: A002
    ) -> None:
        super().__init__(id=id)
        self.client = client
        self.env: Mapping[str, str] = os.environ if env is None else env
        self.launcher = launcher
        self.cache_root = cache_root
        self.files: list[FileInfo] = []
        self.index = 0
        self.pages: dict[str, int] = {}  # sha256 -> page count, known or learnt
        self.hints: Mapping[str, int | None] = {}
        self.thumbnail: RenderableType | None = None
        self.thumbnail_cells = (0, 0)  # its width and height in terminal cells
        self.note = ""
        self._temp = PrivateTemp()
        self._fetched: dict[str, Path] = {}
        self._gen = 0
        self._listing: Worker[None] | None = None
        self._preview: Worker[None] | None = None

    def _call(self, fn: Callable[..., None], *args: object, **kwargs: object) -> None:
        """Run ``fn`` on the UI thread (from a worker thread); nothing if the app is gone."""
        try:
            self.app.call_from_thread(fn, *args, **kwargs)
        except RuntimeError:
            pass

    # --- layout ---------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static("", markup=False, id="fp-lines")
        yield Static("", markup=False, id="fp-thumb")
        yield Static("", markup=False, id="fp-note")

    def on_unmount(self) -> None:
        self._gen += 1
        self._temp.cleanup()
        self._fetched.clear()

    # --- what to show ---------------------------------------------------------------------

    def show(self, record_id: str | None, pages: Mapping[str, int | None] | None = None) -> None:
        """List the files of ``record_id``; ``pages`` maps a SHA-256 to a known page count."""
        self._gen += 1
        gen = self._gen
        self.hints = pages or {}
        self.files = []
        self.index = 0
        self.thumbnail = None
        self.note = ""
        self._cancel()
        if record_id is None:
            self._draw()
            return
        self._draw(loading=True)
        self._listing = self.run_worker(
            self._list(gen, record_id), thread=True, group="file-list", exclusive=True
        )

    def _cancel(self) -> None:
        for worker in (self._listing, self._preview):
            if worker is not None:
                worker.cancel()
        self._preview = None

    def _list(self, gen: int, record_id: str) -> Callable[[], None]:
        def work() -> None:
            try:
                found = self.client.list_record_files(record_id)
                failure = ""
            except CLIENT_ERRORS as exc:
                found, failure = [], describe_error(exc)
            if get_current_worker().is_cancelled:
                return
            self._call(self._listed, gen, found, failure)

        return work

    def _listed(self, gen: int, found: list[FileInfo], failure: str) -> None:
        if gen != self._gen or not self.is_attached:
            return
        self.files = found
        self.index = 0
        self.note = failure
        self._draw()
        self.post_message(self.Listed(len(found)))
        self._preview_selected()

    # --- the selected file ----------------------------------------------------------------

    @property
    def selected(self) -> FileInfo | None:
        return self.files[self.index] if 0 <= self.index < len(self.files) else None

    def action_choose(self, by: int) -> None:
        if len(self.files) > 1:
            self.select((self.index + by) % len(self.files))

    def select(self, index: int) -> None:
        """Choose a file; this cancels the previous picture and starts the next."""
        if not 0 <= index < len(self.files):
            return
        self.index = index
        self.thumbnail = None
        self._draw()
        self._preview_selected()

    def _page_count(self, info: FileInfo) -> int | None:
        return self.pages.get(info.sha256) or self.hints.get(info.sha256)

    def _wants_picture(self) -> bool:
        return image_protocol(self.env) != "none"

    def _preview_selected(self) -> None:
        """Start the picture (and page count) of the selected PDF, cancelling the last one."""
        if self._preview is not None:
            self._preview.cancel()
            self._preview = None
        info = self.selected
        if info is None or file_kind(info.content_type, info.filename) != PDF_KIND:
            return
        if not self._wants_picture() and self._page_count(info) is not None:
            return  # the text line is complete
        self._gen += 1  # an answer for an earlier selection is dropped
        gen = self._gen
        self._preview = self.run_worker(
            self._make_preview(gen, info), thread=True, group="file-preview", exclusive=True
        )

    def _make_preview(self, gen: int, info: FileInfo) -> Callable[[], None]:
        def work() -> None:
            worker = get_current_worker()

            def cancelled() -> bool:
                return worker.is_cancelled or gen != self._gen

            pages: int | None = None
            picture: tuple[RenderableType, int, int] | None = None
            root = self.cache_root if self.cache_root is not None else cache.cache_dir()
            hit = cache.lookup(root, info.sha256)
            result = None
            if hit is not None:
                result = render.PreviewResult("ok", cache.read_pages(hit), hit)
            elif info.size <= render.MAX_BYTES:
                try:
                    local = self._fetch(info)
                    result = render.render_first_page(
                        local, info.sha256, root=root, cancelled=cancelled
                    )
                except (*CLIENT_ERRORS, OSError):
                    result = None
            if cancelled():
                return
            if result is not None and result.state == "ok":
                pages = result.pages
                if self._wants_picture() and result.png is not None:
                    picture = self._picture(result.png, self._columns())
            self._call(self._previewed, gen, info, pages, picture)

        return work

    def _columns(self) -> int:
        width = self.size.width
        return THUMB_COLUMNS if width <= 0 else max(8, min(THUMB_COLUMNS, width - 2))

    @staticmethod
    def _picture(png: Path, columns: int) -> tuple[RenderableType, int, int] | None:
        """The PNG as half-block cells, about ``columns`` wide: ``(picture, columns, rows)``;
        ``None`` if it cannot be drawn."""
        try:
            from PIL import Image  # noqa: PLC0415
            from rich_pixels import Pixels  # noqa: PLC0415

            with Image.open(png) as image:
                width, height = image.size
                if width < 1 or height < 1:
                    return None
                rows_px = min(THUMB_MAX_ROWS * 2, max(2, round(columns * height / width)))
                rows_px -= rows_px % 2
                cols = max(1, min(columns, round(rows_px * width / height)))
                shown = Pixels.from_image(image.convert("RGB"), resize=(cols, rows_px))
                return shown, cols, rows_px // 2
        except Exception:  # noqa: BLE001  # a picture is a courtesy; the text line stays
            return None

    def _previewed(
        self,
        gen: int,
        info: FileInfo,
        pages: int | None,
        picture: tuple[RenderableType, int, int] | None,
    ) -> None:
        if gen != self._gen or not self.is_attached or self.selected != info:
            return
        if pages is not None:
            self.pages[info.sha256] = pages
        self.thumbnail = picture[0] if picture is not None else None
        self.thumbnail_cells = (picture[1], picture[2]) if picture is not None else (0, 0)
        self._draw()

    # --- drawing --------------------------------------------------------------------------

    def lines(self) -> list[str]:
        """The file rows as shown: ``> `` marks the selected file."""
        out = []
        for position, info in enumerate(self.files):
            mark = ">" if position == self.index else " "
            row = file_line(info.filename, info.content_type, info.size, self._page_count(info))
            out.append(f"{mark} {row}")
        return out

    def _draw(self, *, loading: bool = False) -> None:
        if not self.is_attached:
            return
        lines = self.lines()
        if loading:
            body = "Loading files..."
        elif lines:
            body = "\n".join(lines)
        else:
            body = NO_FILES
        self.query_one("#fp-lines", Static).update(Text(body))
        thumb = self.query_one("#fp-thumb", Static)
        thumb.update(self.thumbnail if self.thumbnail is not None else "")
        thumb.display = self.thumbnail is not None
        hint = "v or Enter: open in viewer" if lines else ""
        self.query_one("#fp-note", Static).update(Text(self.note or hint))

    # --- open -----------------------------------------------------------------------------

    def _fetch(self, info: FileInfo) -> Path:
        """The file in the private folder, fetched once; raises the client's errors or OSError."""
        have = self._fetched.get(info.file_id)
        if have is not None:
            try:
                return self._temp.verify(have)
            except OSError:
                self._fetched.pop(info.file_id, None)
        path = self.client.fetch_file(info.file_id, self._temp.directory)
        self._temp.verify(path)
        self._fetched[info.file_id] = path
        return path

    def action_open_file(self) -> None:
        info = self.selected
        if info is None:
            self._tell(NOT_AVAILABLE, error=True)
            return
        self.run_worker(self._open(info), thread=True, group="file-open", exclusive=True)

    def _open(self, info: FileInfo) -> Callable[[], None]:
        def work() -> None:
            try:
                path = self._fetch(info)
                open_in_viewer(path, self.launcher)
                text, error = f"Opened {info.filename}.", False
            except UnknownFileError:
                text, error = NOT_AVAILABLE, True
            except CLIENT_ERRORS as exc:
                text, error = describe_error(exc), True
            except OSError:
                text, error = "The file could not be opened.", True
            self._call(self._tell, text, error=error)

        return work

    def _tell(self, text: str, *, error: bool = False) -> None:
        self.note = text
        self._draw()
        self.post_message(self.Note(text, error=error))
