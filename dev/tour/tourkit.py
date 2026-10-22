"""Shared tooling for the screenshot tours (`dev/tour/phase0.py`, `dev/tour/phase1.py`).

A tour builds a throw-away ledger in a temporary directory, drives the real application headless
and writes SVG screenshots:

* the TUI is driven with Textual's pilot and saved with `App.export_screenshot` (a fixed terminal
  size, so reruns are stable);
* a `tl` command, an API call or an MCP tool call has no screen, so its transcript is rendered as a
  terminal (`Transcript`, Rich `Console(record=True)` and `export_svg`).

Determinism: the wall clock and the ULID generator are replaced by a frozen clock that only moves
when the script says so (`CLOCK.advance`), and ULIDs come from a counter. Nothing leaves the
machine: no network (the API runs in process, webhooks go to a loopback receiver), no secrets (the
documented dev account `demo` / `demo`), no personal data (made-up names and `example.com`).

Every step either passes or raises: a tour that cannot finish writes nothing it did not finish.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Awaitable, Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.style import Style
from rich.text import Text
from textual.app import App
from textual.pilot import Pilot
from textual.widgets import DataTable
from ulid import ULID

# --- the frozen clock ------------------------------------------------------------------------

START = datetime(2026, 10, 12, 8, 0, 0, tzinfo=UTC)


class Clock:
    """The one source of time and identifiers during a tour."""

    def __init__(self) -> None:
        self.now = START
        self.counter = 0

    def reset(self) -> None:
        self.now = START
        self.counter = 0

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


CLOCK = Clock()
_ORIGINAL_DATETIME = datetime


class _FrozenDatetime(_ORIGINAL_DATETIME):
    @classmethod
    def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
        return CLOCK.now if tz is None else CLOCK.now.astimezone(tz)


class _FrozenDate(date):
    @classmethod
    def today(cls) -> date:  # type: ignore[override]
        return CLOCK.now.date()


class _CountingUlid:
    """What `tl_core.util.new_ulid` calls instead of `ULID()`: frozen time plus a counter."""

    def __str__(self) -> str:
        CLOCK.counter += 1
        millis = int(CLOCK.now.timestamp() * 1000)
        return str(ULID.from_bytes(millis.to_bytes(6, "big") + CLOCK.counter.to_bytes(10, "big")))


def freeze() -> None:
    """Replace the clock and the ULID source of `tl_core` (idempotent)."""
    import tl_core.util as util
    import tl_core.webhooks.base as webhook_base

    util.datetime = _FrozenDatetime  # type: ignore[misc,assignment]
    webhook_base.datetime = _FrozenDatetime  # type: ignore[misc,assignment]
    util.ULID = _CountingUlid  # type: ignore[misc,assignment]
    import tl_lake.query as lake_query
    import tl_lake.sync as lake_sync

    lake_sync.datetime = _FrozenDatetime  # type: ignore[misc,assignment]
    lake_query.datetime = _FrozenDatetime  # type: ignore[misc,assignment]
    import tl_tui.widgets.domain_screen as domain_screen

    domain_screen.date = _FrozenDate  # type: ignore[misc,assignment]  # its "today" for evidence
    CLOCK.reset()


def fixed_archive_key() -> None:
    """Make `tl archive keygen` write the same key every time (a key for the tour only).

    A real key is random; a tour that prints key ids, manifest digests and signatures would differ
    on every run. The key is derived from a public phrase, so it protects nothing.
    """
    import hashlib

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from tl_core.archive import signing

    def generate() -> signing.Ed25519Signer:
        seed = hashlib.sha256(b"throughline screenshot tour: a key that protects nothing").digest()
        return signing.Ed25519Signer(Ed25519PrivateKey.from_private_bytes(seed))

    signing.generate_signer = generate


# --- SVG files -------------------------------------------------------------------------------

_FONT_FACE = re.compile(r"@font-face\s*\{.*?\}", re.S)


def clean_svg(svg: str) -> str:
    """Drop the web-font downloads Rich and Textual add, so an SVG makes no network request."""
    svg = _FONT_FACE.sub("", svg)
    fetched = re.search(r"""(url\(|href=|src=)["']?https?://""", svg)
    assert fetched is None, "an SVG would fetch a URL"
    return svg


# --- terminal transcripts --------------------------------------------------------------------


@dataclass
class Transcript:
    """Commands and what they printed, rendered as one terminal window."""

    title: str
    width: int = 110
    items: list[tuple[str, str, str]] = field(default_factory=list[tuple[str, str, str]])

    def command(self, line: str, who: str | None = None) -> None:
        """A line the person types; ``who`` puts their name in the prompt (`amy$`)."""
        self.items.append(("cmd", line, who or ""))

    def output(self, text: str, *, error: bool = False) -> None:
        """What a command printed (stdout and stderr as one stream, like a terminal)."""
        for line in text.rstrip("\n").split("\n"):
            self.items.append(("err" if error else "out", line, ""))

    def comment(self, line: str) -> None:
        self.items.append(("note", line, ""))

    def blank(self) -> None:
        self.items.append(("out", "", ""))

    def svg(self) -> str:
        console = Console(
            file=io.StringIO(),
            record=True,
            width=self.width,
            force_terminal=True,
            color_system="truecolor",
            legacy_windows=False,
            highlight=False,
            markup=False,
            emoji=False,
        )
        prompt = Style(color="green", bold=True)
        for kind, line, who in self.items:
            text = Text(no_wrap=False, overflow="fold")
            if kind == "cmd":
                text.append(f"{who}$ " if who else "$ ", style=prompt)
                text.append(line, style=Style(bold=True))
            elif kind == "note":
                text.append("# " + line, style=Style(color="bright_black", italic=True))
            elif kind == "err":
                text.append(line, style=Style(color="red"))
            else:
                style = None
                if line.startswith("PASS") or line.startswith("verified") or "OK" in line[:12]:
                    style = Style(color="green")
                text.append(line, style=style)
            console.print(text)
        return clean_svg(console.export_svg(title=self.title))


# --- the workspace ---------------------------------------------------------------------------

ENV_UNSET = (
    "TL_SCHEMA_DIR",
    "TL_OBJECT_STORE",
    "TL_REMOTE",
    "TL_TOKEN",
    "TL_AGENT_TOKEN",
    "TL_PROJECT",
    "TL_WEBHOOK_ALLOWLIST",
    "TL_API_URL",
    "TL_PG_URL",
    "TL_DEMO_PASSWORD",
)


class TourFailed(Exception):
    """A step of the tour did not do what the tour says it does."""


def expect(condition: object, message: str) -> None:
    if not condition:
        raise TourFailed(message)


class Workspace:
    """A temporary directory with a ledger, and the environment the commands read."""

    def __init__(self, out: Path, *, size: tuple[int, int] = (140, 40)) -> None:
        self.out = out
        self.size = size
        self.root = Path(tempfile.mkdtemp(prefix="tl-tour-"))
        self.db = self.root / "tl.db"
        self.written: list[Path] = []
        self.masks: dict[str, str] = {str(self.root): "."}
        out.mkdir(parents=True, exist_ok=True)
        for name in ENV_UNSET:
            os.environ.pop(name, None)
        os.environ.update(
            {
                "TL_ENV": "dev",
                "TL_DB": str(self.db),
                "TL_SESSION_FILE": str(self.root / "session.json"),
                "TL_OBJECT_ROOT": str(self.root / "objects"),
                "TL_LAKE_DIR": str(self.root / "lake"),
                "TL_SIM_DIR": str(self.root / "sim"),
                "TL_TOKENS": str(self.root / "tokens.json"),
                "HOME": str(self.root / "home"),
                "XDG_CONFIG_HOME": str(self.root / "home" / ".config"),
                "NO_COLOR": "1",
                "COLUMNS": "110",
            }
        )
        (self.root / "home").mkdir()
        os.chdir(self.root)  # commands take short relative paths, like a person's would
        logging.disable(logging.WARNING)  # request and audit log lines carry real times

    def clean(self, text: str) -> str:
        """``text`` with the temporary paths and other run-specific values replaced."""
        for found, shown in self.masks.items():
            text = text.replace(found, shown)
        return re.sub(r"\b\d+\.\d+s\b", "<t>s", text)  # elapsed times differ on every run

    def close(self) -> None:
        os.chdir("/")
        shutil.rmtree(self.root, ignore_errors=True)

    # --- the `tl` command, in process -------------------------------------------------------

    def tl(
        self, *args: str, ok: bool = True, stdin: str | None = None, who: str | None = None
    ) -> str:
        """Run `tl <args>` in this process; return what it printed (stdout and stderr).

        A non-zero exit fails the tour unless ``ok`` is false, and a zero exit fails it then.
        The clock moves three minutes after each command so events have distinct times.
        """
        from tl_cli.main import app
        from typer.testing import CliRunner

        if who:  # each person has their own signed-in session, as on their own machine
            os.environ["TL_SESSION_FILE"] = str(self.root / f"session-{who}.json")
        try:
            result = CliRunner().invoke(app, list(args), input=stdin, catch_exceptions=False)
        finally:
            os.environ["TL_SESSION_FILE"] = str(self.root / "session.json")
        shown = self.clean(result.output)
        if ok and result.exit_code != 0:
            raise TourFailed(f"tl {' '.join(args)} exited {result.exit_code}:\n{shown}")
        if not ok and result.exit_code == 0:
            raise TourFailed(f"tl {' '.join(args)} should have failed:\n{shown}")
        CLOCK.advance(minutes=3)
        return shown

    def shot_cli(
        self,
        name: str,
        title: str,
        steps: list[tuple[str, str]],
        *,
        width: int = 110,
        note: str | None = None,
    ) -> None:
        """Render ``(command line, output)`` pairs as one terminal window and save it."""
        transcript = Transcript(title, width)
        if note:
            transcript.comment(note)
        for line, output in steps:
            transcript.command(line)
            if output.strip():
                transcript.output(output)
        self.save(name, transcript.svg())

    def run_cli(
        self, steps: list[tuple[str, tuple[str, ...]]], *, ok: bool = True
    ) -> list[tuple[str, str]]:
        """Run each ``(display, args)`` and return ``(display, output)`` pairs."""
        return [(display, self.tl(*args, ok=ok)) for display, args in steps]

    def save(self, name: str, svg: str) -> Path:
        path = self.out / f"{name}.svg"
        path.write_text(svg, encoding="utf-8")
        self.written.append(path)
        print(f"  wrote {path.name} ({len(svg) // 1024} KB)", flush=True)
        return path


# --- a transcript that is filled as commands run ----------------------------------------------


def redact(output: str, *prefixes: str) -> str:
    """Hide the value on lines that start with a secret's name (a token or a signing secret)."""
    lines: list[str] = []
    for line in output.splitlines():
        for prefix in prefixes:
            if line.startswith(prefix):
                head, _, _ = line.partition(" ")
                line = f"{head} ...(not shown here)" if prefix.endswith(" ") else f"{prefix}..."
        lines.append(line)
    return "\n".join(lines) + "\n"


class Shell:
    """Runs `tl` commands and writes each one, and what it printed, into a transcript."""

    def __init__(self, ws: Workspace, title: str, width: int = 120) -> None:
        self.ws = ws
        self.transcript = Transcript(title, width)

    def run(
        self,
        *argv: str,
        who: str | None = None,
        ok: bool = True,
        stdin: str | None = None,
        hide: tuple[str, ...] = (),
        show: str | None = None,
        tail: int | None = None,
        head: int | None = None,
    ) -> str:
        """Run `tl <argv>` (as ``who``); show it. ``ok=False`` means it must be refused.

        ``hide`` names output lines to blank out (secrets), ``show`` replaces the typed line (for
        arguments that are paths of the temporary directory), ``tail`` keeps only the last lines
        and ``head`` only the first ones.
        """
        import shlex

        output = self.ws.tl(*argv, ok=ok, stdin=stdin, who=who)
        typed = show or self.ws.clean("tl " + shlex.join(argv))
        self.transcript.command(typed, who)
        shown = redact(output, *hide) if hide else output
        if tail is not None:
            shown = "\n".join(shown.rstrip("\n").split("\n")[-tail:]) + "\n"
        if head is not None:
            shown = "\n".join(shown.rstrip("\n").split("\n")[:head]) + "\n"
        if shown.strip():
            self.transcript.output(shown, error=not ok)
        return output

    def note(self, text: str) -> None:
        self.transcript.comment(text)

    def line(self, command: str, output: str = "", who: str | None = None) -> None:
        """Something that is not a `tl` command (an API or MCP call) and what it returned."""
        self.transcript.command(command, who)
        if output.strip():
            self.transcript.output(output)

    def blank(self) -> None:
        self.transcript.blank()

    def save(self, name: str) -> None:
        self.ws.save(name, self.transcript.svg())


# --- an MCP server in this process, acting through an agent token ---------------------------


def mcp_for_token(ws: Workspace, token: str) -> tuple[Any, Any]:
    """An MCP server in this process, built the way `python -m tl_mcp` builds it.

    The agent is who its token says, and the token is checked again before every call. Returns
    ``(server, backend)``; close the backend when done.
    """
    from tl_adapters.backend import open_backend
    from tl_mcp.identity import resolve_agent, token_authorizer
    from tl_mcp.server import build_server

    backend = open_backend(str(ws.db))
    principal = resolve_agent(backend, token)
    server = build_server(
        backend, actor=principal.actor, authorize_hook=token_authorizer(backend, token)
    )
    return server, backend


def agent_server(
    ws: Workspace, agent: str, *, label: str = "triage assistant"
) -> tuple[Any, Any, str]:
    """Make the agent account and its token (as the signed-in admin); return the MCP server.

    Returns ``(server, backend, token)``. The token is a secret: show it nowhere.
    """
    ws.tl("admin", "user", "add", agent, "--kind", "agent")
    issued = ws.tl("admin", "token", "issue", agent, "--label", label)
    token = issued.splitlines()[0].strip()
    expect(token.startswith("tla_"), "no agent token was issued")
    server, backend = mcp_for_token(ws, token)
    return server, backend, token


async def call_tool(server: Any, name: str, **arguments: Any) -> dict[str, Any]:
    """Call an MCP tool and return its structured result."""
    result = await server.call_tool(name, arguments)
    expect(result.structured_content is not None, f"{name} returned no structured content")
    return result.structured_content


# --- the TUI ---------------------------------------------------------------------------------


def fit_tables(app: App[Any]) -> None:
    """Measure the columns of every table on the screen, and draw the cells again.

    A Textual table measures its cells when the app next goes idle, and keeps what it drew before
    that: a frame drawn in between stays in its cache with every column as wide as its header
    (`Path`, `acme` for `acme-nde/results`) and the table never redraws it. Which shots that
    spoiled differed from run to run. Measuring only ever widens a column, so doing this again
    changes nothing."""
    for table in app.screen.query(DataTable):
        table._update_dimensions(list(table.rows))  # pyright: ignore[reportPrivateUsage]
        table._clear_caches()  # pyright: ignore[reportPrivateUsage]
        table.refresh(layout=True)


async def settle(pilot: Pilot[Any], rounds: int = 4) -> None:
    """Let the app redraw ``rounds`` times and wait for its workers: a log reads its rows, its
    actions bar and its files off the UI thread, and a shot taken before they finish differs
    from run to run."""
    for _ in range(rounds):
        await pilot.pause()
    try:
        await asyncio.wait_for(pilot.app.workers.wait_for_complete(), timeout=15)
    except TimeoutError:  # a worker that never ends must not hang the tour
        pass
    fit_tables(pilot.app)
    await pilot.pause()


async def until(
    pilot: Pilot[Any], predicate: Callable[[], object], what: str, timeout: float = 8.0
) -> None:
    """Pump the app until ``predicate()`` holds; fail the tour on a timeout."""
    loop = asyncio.get_running_loop()
    started = loop.time()
    while True:
        fit_tables(pilot.app)
        if predicate():
            break
        if loop.time() - started > timeout:
            raise TourFailed(
                f"timed out waiting for {what}; the screen shows:\n{screen_text(pilot.app)}"
            )
        await pilot.pause(0.03)
    await settle(pilot, 2)


def screen_text(app: App[Any]) -> str:
    """The screen as plain text (to check a screenshot shows what it should)."""
    strips = app.screen._compositor.render_strips()  # pyright: ignore[reportPrivateUsage]
    return "\n".join(strip.text.rstrip() for strip in strips)


LEAKS: list[str] = []  # one "<shot> <tokens>" per plain screenshot that carries technical text


def leaks_in(text: str, labels: Any = None, keys: Sequence[str] = ()) -> list[str]:
    """The technical tokens in a captured screen's text: ids, hashes, versions, internal keys.

    ``keys`` are the record-type and property keys of the schema (``labels_load.schema_keys``);
    the plain walk (``test_plain_walk.py``) looks for the same two kinds of token.
    """
    from tl_tui.display import find_technical, key_hits

    return [*find_technical(text, labels), *key_hits(text, keys)]


def check_plain(name: str, text: str, labels: Any = None, keys: Sequence[str] = ()) -> list[str]:
    """Record a screenshot whose text carries technical text; return its tokens (none is clean)."""
    found = leaks_in(text, labels, keys)
    if found:
        LEAKS.append(f"{name} {' '.join(repr(token) for token in found)}")
    return found


def report_leaks() -> int:
    """Print one ``LEAK <shot> <tokens>`` line per leak; return the tour's exit code."""
    for line in LEAKS:
        print(f"LEAK {line}", flush=True)
    return 1 if LEAKS else 0


_KEYS: dict[
    tuple[int, str], tuple[Any, list[str]]
] = {}  # the client is kept so its id is not reused


def _labels_and_keys(app: App[Any]) -> tuple[Any, Sequence[str]]:
    """The viewer's labels and the schema keys for one app (keys are read once per client)."""
    from tl_tui.labels_load import load_labels, schema_keys

    client, scope = getattr(app, "client", None), getattr(app, "scope", None)
    if client is None or scope is None:
        return None, ()
    labels = load_labels(client, scope)
    if (id(client), scope) not in _KEYS:
        _KEYS[(id(client), scope)] = (client, schema_keys(client, scope, labels))
    return labels, _KEYS[(id(client), scope)][1]


def shot_tui(
    ws: Workspace, app: App[Any], name: str, title: str, *needles: str, technical: bool = False
) -> None:
    """Save the current screen as an SVG after checking each needle is on it.

    The screen's text also goes through the leak finder (``check_plain``); ``technical=True``
    marks a shot that shows technical details on purpose (Ctrl+D on), which is not checked.
    """
    text = screen_text(app)
    for needle in needles:
        expect(needle in text, f"{name}: {needle!r} is not on the screen:\n{text}")
    if not technical:
        labels, keys = _labels_and_keys(app)
        check_plain(name, text, labels, keys)
    ws.save(name, clean_svg(app.export_screenshot(title=title)))


def run_tui(
    ws: Workspace,
    app: App[Any],
    scenario: Callable[[Pilot[Any]], Awaitable[None]],
    *,
    size: tuple[int, int] | None = None,
) -> None:
    """Run ``app`` headless at the tour's terminal size and await ``scenario``."""

    async def main() -> None:
        async with app.run_test(size=size or ws.size) as pilot:
            await settle(pilot)
            await scenario(pilot)

    asyncio.run(main())


@contextmanager
def quiet_stderr() -> Iterator[None]:
    """Hide the harmless warnings some libraries print while a tour runs."""
    saved = sys.stderr
    sys.stderr = io.StringIO()
    try:
        yield
    finally:
        sys.stderr = saved
