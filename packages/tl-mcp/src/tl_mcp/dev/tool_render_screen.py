"""``render_screen``: a TUI screen as SVG and plain text, headless, on a copy of the dev ledger
(brief 25.3, FANOUT D12).

The ledger is copied first, so the keys cannot write to it; the copy is removed afterwards.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import sqlite3
import tempfile
import unicodedata
from pathlib import Path
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from textual.keys import KEY_NAME_REPLACEMENTS, KEY_TO_UNICODE_NAME, Keys
from tl_tui.main import build_app

from tl_mcp.dev.errors import DevGuardError, DevToolFailure
from tl_mcp.dev.runtime import DevContext, guarded

WRITES_SNAPSHOT = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, open_world_hint=False
)

SETTLE_TIMEOUT_S = 30
SVG_MAX_CHARS = 400_000
TEXT_MAX_CHARS = 20_000
TEMP_PREFIX = "tl-render-"

_NAMED_KEYS = frozenset(
    {*(key.value for key in Keys), *KEY_NAME_REPLACEMENTS, *KEY_NAME_REPLACEMENTS.values()}
    | set(KEY_TO_UNICODE_NAME)
)
_MODIFIERS = re.compile(r"^(?:(?:ctrl|shift|alt|meta)\+)*")


class ScreenOutput(BaseModel):
    """The answer of ``render_screen``."""

    svg: str  # the SVG document; "" when svg_truncated (the full document is in ``file``)
    svg_truncated: bool = False
    text: str  # the screen as plain rows, one line per terminal row
    file: str  # repository-relative path of the saved SVG
    width: int
    height: int
    keys: list[str]


def _is_key_name(key: str) -> bool:
    """True when Textual can name the key: modifiers over a character or a named key.

    Textual takes any string as a key, so this check is what turns a misspelt name into an error.
    Names follow Textual's own scheme: a Unicode character name in lower case with underscores.
    """
    base = _MODIFIERS.sub("", key, count=1)
    if not base:
        return False
    if len(base) == 1 or base in _NAMED_KEYS:
        return True
    try:
        unicodedata.lookup(base.replace("_", " ").upper())
    except KeyError:
        return False
    return True


def _copy_ledger(source: Path, workdir: Path) -> Path:
    """A consistent copy of the SQLite ledger, opened read-only, in ``workdir``."""
    copy = workdir / "tl.db"
    try:
        src = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)
        try:
            dst = sqlite3.connect(copy)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
    except sqlite3.Error as exc:  # its text can carry a path: say only the kind
        raise DevToolFailure(f"the ledger could not be copied ({type(exc).__name__})") from exc
    return copy


async def _screen(
    db: Path, project: str, keys: list[str], width: int, height: int
) -> tuple[str, str]:
    """Run the app on ``db`` headless, press ``keys``; returns the SVG and the plain text."""
    app = build_app(db, project, live=False)
    try:
        async with app.run_test(size=(width, height)) as pilot:
            await pilot.pause()
            for key in keys:
                await pilot.press(key)
                await pilot.pause()
            await pilot.pause()
            svg = app.export_screenshot(title="t")
            # Textual keeps the rows in a private compositor; no public API gives them as text.
            strips = app.screen._compositor.render_strips()  # pyright: ignore[reportPrivateUsage]
            text = "\n".join(strip.text.rstrip() for strip in strips)
            return svg, text
    finally:
        close = getattr(app.client, "close", None)
        if callable(close):
            close()


def _save_svg(directory: Path, stem: str, svg: str) -> Path:
    """Write ``svg`` to ``directory/<stem>.svg`` atomically: a reader never sees half a file."""
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{stem}.svg"
    fd, partial = tempfile.mkstemp(dir=directory, prefix=f".{stem}.", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(svg)
        os.replace(partial, target)
    except BaseException:
        Path(partial).unlink(missing_ok=True)
        raise
    return target


def register(server: MCPServer, ctx: DevContext) -> None:
    @server.tool(annotations=WRITES_SNAPSHOT)
    async def render_screen(
        project: Annotated[
            str,
            Field(
                max_length=64,
                pattern=r"^[A-Za-z0-9_.-]+$",
                description="Project id; the screen opens project:<project>.",
            ),
        ] = "P123",
        keys: Annotated[
            list[
                Annotated[
                    str,
                    Field(
                        max_length=30,
                        pattern=r"^[A-Za-z0-9_+]+$",
                        description="One Textual key name, e.g. enter, down, f2, ctrl+p.",
                    ),
                ]
            ],
            Field(max_length=20, default_factory=list, description="Keys, pressed in order."),
        ] = Field(default_factory=list),  # noqa: B008 (pydantic default_factory, not a call)
        width: Annotated[
            int, Field(ge=40, le=200, description="Terminal columns (default 120).")
        ] = 120,
        height: Annotated[int, Field(ge=10, le=60, description="Terminal rows (default 40).")] = 40,
        name: Annotated[
            str | None,
            Field(
                max_length=60,
                pattern=r"^[A-Za-z0-9_-]+$",
                description="File name stem of the saved SVG (default screen); same name replaces.",
            ),
        ] = None,
    ) -> ScreenOutput:
        """Render a TUI screen headless and return it as an SVG document, as plain text rows, and
        the name of the saved SVG file (dev/data/snapshots/<name>.svg).

        The dev ledger is copied first and the keys run on the copy, so nothing a key does reaches
        the dev ledger; the copy is removed afterwards. The screen opens project:<project>.
        Useful keys: f1 (help and the key map), f2 and f3 (navigation and context panels), enter
        (open the selected record), slash (filter the list), n (new record form). Key names are
        Textual's: letters and digits as they are, names such as down, escape, ctrl+p, f2.
        Limits: at most 20 keys, 40 to 200 columns, 10 to 60 rows, 30 s to settle. The answer
        holds the SVG (empty above 400000 characters; the file has it all) and up to 20000
        characters of text.

        Example: keys=["enter"], name="record".
        """
        stem = name or "screen"
        detail = {
            "project": project,
            "keys": keys,
            "width": width,
            "height": height,
            "name": stem,
        }
        with guarded(ctx, "render_screen", detail):
            target = ctx.target
            if target.kind != "sqlite" or target.path is None:
                raise DevGuardError("render_screen needs a SQLite dev database")
            if not target.path.is_file():
                raise DevToolFailure("the database file does not exist")
            unknown = [key for key in keys if not _is_key_name(key)]
            if unknown:
                raise DevToolFailure(
                    f"unknown key name {unknown[0]!r}: use Textual key names such as enter, "
                    "down, f2, ctrl+p, slash"
                )
            workdir = Path(tempfile.mkdtemp(prefix=TEMP_PREFIX))
            try:
                copy = _copy_ledger(target.path, workdir)
                try:
                    svg, text = await asyncio.wait_for(
                        _screen(copy, project, keys, width, height), timeout=SETTLE_TIMEOUT_S
                    )
                except TimeoutError as exc:
                    raise DevToolFailure(
                        f"the screen did not settle within {SETTLE_TIMEOUT_S} s"
                    ) from exc
            finally:
                shutil.rmtree(workdir, ignore_errors=True)
            saved = _save_svg(ctx.snapshots_dir, stem, svg)
            too_long = len(svg) > SVG_MAX_CHARS
            return ScreenOutput(
                svg="" if too_long else svg,
                svg_truncated=too_long,
                text=text[:TEXT_MAX_CHARS],
                file=saved.relative_to(ctx.repo_root).as_posix(),
                width=width,
                height=height,
                keys=keys,
            )
