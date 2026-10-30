"""User-facing performance of the Throughline terminal app (P1-UX3, owner highlight "Performance").

    just perf-ux [--sizes 1000,10000] [--backends sqlite,postgres,remote]

What a person waits for, measured with the real TUI driven headless by Textual's pilot (not unit
timings), against a project seeded through the real commands:

* open each everyday log (RFI log ``Ctrl+G``, correspondence ``F5``, documents ``F7``) until its
  rows are shown;
* move the cursor one row until the panel shows the new record;
* ``Enter`` until the record screen's Details are shown, then switch to Properties (``2``);
* type a filter in the log's box and see the list narrow (the time of the last keystroke);
* launch the app until the record grid shows its first rows, reload it, and run one property-set
  filter in the grid (text, number and code-list property).

Each action is repeated ``--reps`` times (default 25) after ``--warmup`` untimed repetitions; the
very first repetition in the process is kept as the cold first-open. Two times are taken per
repetition: *state* (the widgets hold the answer) and *painted* (the pilot has also let the app
paint it, one idle round on top: the headline). ``floor`` is the pilot's own cost for a key that
does nothing, so a reader can see how much of a small number is the harness.

Backends: ``sqlite`` (embedded SQLite file), ``postgres`` (embedded, a throw-away database on
``TL_PG_URL``, loopback, TLS off), ``remote`` (the API as a separate process on loopback over the
same SQLite file; the TUI talks HTTP). Seeding: ``core.Record`` streams with property sets through
the bulk writer of the benches (``tests/bench/bench_gen.py``) and RFIs, letters and documents
through the real command handlers, batched 500 to a transaction. While seeding only, the workflow,
numbering and link definitions are read once (``use_workflows`` and friends), because the handlers
otherwise parse the same YAML files on every call; the measurement runs without that.

The measurement of one (backend, size) runs in its own process (``measure``), so "cold" is cold.
Results: ``docs/reports/perf/P1-UX-perf.md`` and ``.json`` (``--merge`` keeps cells of an earlier
run that this run does not repeat). Nothing is left behind: databases and folders are removed.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import cProfile
import io
import json
import logging
import math
import os
import platform
import pstats
import re
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "docs" / "reports" / "perf"
PROJECT = "P123"
SCOPE = f"project:{PROJECT}"
ACTOR = "user:amy"
SIZE = (170, 45)  # terminal columns x rows; from 160 columns a log shows its panel beside the list
SLOW_MS = 250.0
FULL_LIMIT = 10_000  # above this a size seeds core records only (the grid actions)
BACKENDS = ("sqlite", "postgres", "remote")
SCHEMA_VERSION = 1

TOPICS = (
    "Piling and utilities conflict",
    "Gasket class at the new flange",
    "Cable tray support spacing",
    "Anchor bolt projection",
    "Insulation thickness on the cold line",
    "Valve access platform height",
    "Pipe rack beam clash",
    "Grounding of the skid frame",
)
AREAS = ("AZ203", "AZ118", "Unit 47", "Unit 20", "Tank farm", "Pump house")
DISCIPLINES = ("piping", "structural", "electrical", "civil")
DOC_TYPES = ("ISO", "PID", "GA", "DS", "LD", "SPC", "PRC", "CAL", "MTO", "ITR", "WPS", "DRW")
GRID_FILTERS = (
    ("grid_filter_text", "psets.valve_data.body_material=SS316L"),
    ("grid_filter_number", "psets.valve_data.size_in>=12"),
    ("grid_filter_code", "psets.valve_data.fail_action=FC"),
)

#: One line per action that was slow, written after reading the cProfile of a run (the profile in
#: the results file is the evidence; a rerun that is no longer slow does not show the line).
CAUSES: dict[str, str] = {}


# --- the machine -----------------------------------------------------------------------------


def _read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def _git(*args: str) -> str:
    done = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False)
    return done.stdout.strip()


def machine_info(work: Path) -> dict[str, Any]:
    """CPU, memory, disk and software of the container this ran on."""
    import sqlite3

    cpu = next(
        (
            line.split(":", 1)[1].strip()
            for line in _read("/proc/cpuinfo").splitlines()
            if line.startswith("model name")
        ),
        platform.processor() or "unknown",
    )
    mem_kb = next(
        (
            int(line.split()[1])
            for line in _read("/proc/meminfo").splitlines()
            if "MemTotal" in line
        ),
        0,
    )
    usage = shutil.disk_usage(work)
    device = ""
    for line in _read("/proc/mounts").splitlines():
        parts = line.split()
        if len(parts) > 1 and parts[1] == "/":
            device = parts[0]
    block = Path(device).name.rstrip("0123456789") if device.startswith("/dev/") else ""
    rotational = _read(f"/sys/block/{block}/queue/rotational").strip() if block else ""
    return {
        "cpu_model": cpu,
        "cpu_count": os.cpu_count(),
        "ram_gb": round(mem_kb / 1024 / 1024, 1),
        "disk": {
            "device": device or "unknown",
            "total_gb": round(usage.total / 1e9),
            "free_gb": round(usage.free / 1e9),
            "kind": f"virtual block device, kernel rotational flag {rotational or 'unknown'}",
        },
        "kernel": platform.release(),
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "load_average": [round(x, 2) for x in os.getloadavg()],
        "terminal": f"{SIZE[0]}x{SIZE[1]}",
    }


# --- seeding ---------------------------------------------------------------------------------


def pg_server() -> str:
    return os.environ.get("TL_PG_URL", "postgresql://postgres:postgres@localhost:5432/tl_test")


def pg_url(database: str) -> str:
    from tl_adapters.postgres import admin

    return admin.database_url(pg_server(), database) + "?sslmode=disable"


@contextlib.contextmanager
def seeding_caches() -> Iterator[None]:
    """Definitions read once while seeding (a supported hook); the measurement does not use it."""
    from tl_core.links.expected import default_expected_links
    from tl_core.numbering.config import get_numbering, use_numbering
    from tl_core.workflow.loader import default_workflows
    from tl_core.workflow.provider import use_expected_links, use_workflows

    with (
        use_workflows(default_workflows()),
        use_expected_links(default_expected_links()),
        use_numbering(get_numbering()),
    ):
        yield


def _batches(total: int, size: int = 500) -> Iterator[range]:
    for start in range(0, total, size):
        yield range(start, min(start + size, total))


def seed(target: Any, records: int, *, full: bool, say: Callable[[str], None]) -> dict[str, Any]:
    """Fill an empty ledger: ``records`` core records with property sets and, when ``full``,
    ``records`` RFIs, letters and documents. Returns the facts (counts and seconds)."""
    sys.path.insert(0, str(REPO / "tests" / "bench"))
    from bench_gen import SeedSpec, seed_database  # pyright: ignore[reportMissingImports]
    from tl_adapters import db as adapter_db
    from tl_adapters.db import open_uow

    facts: dict[str, Any] = {"records": records, "full": full}
    started = time.perf_counter()
    last = [started]

    def progress(done: int) -> None:
        now = time.perf_counter()
        if now - last[0] >= 30:
            last[0] = now
            say(f"    core records {done}/{records}")

    seed_database(target, SeedSpec(records=records, batch=500), on_progress=progress)
    facts["core_seconds"] = round(time.perf_counter() - started, 1)
    if not full:
        facts["seconds"] = facts["core_seconds"]
        return facts
    from tl_mod_correspondence.handlers.items import (
        ReceiveCorrespondence,
        handle_receive_correspondence,
    )
    from tl_mod_correspondence.handlers.technical import (
        RaiseTechnical,
        SubmitTechnical,
        handle_raise_technical,
        handle_submit_technical,
    )
    from tl_mod_documents.handlers.documents import RegisterDocument, handle_register_document
    from tl_mod_documents.handlers.revisions import CreateRevision, handle_create_revision
    from tl_mod_engineering.document import load_standards_file
    from tl_mod_engineering.loader import load_standards

    base: dict[str, Any] = {"actor": "user:perf", "source": "perf", "scope": SCOPE}
    today = date.today()
    with seeding_caches():
        with open_uow(target) as uow:
            for name in ("co.acme.standards@1.0.0.yaml", "co.acme.documents@1.0.0.yaml"):
                load_standards(
                    uow,
                    load_standards_file(REPO / "schema" / "fixtures" / "standards" / name),
                    actor="user:perf",
                    source="perf",
                )
        began = time.perf_counter()
        for batch in _batches(records):
            with open_uow(target) as uow:
                for i in batch:
                    made = handle_raise_technical(
                        uow,
                        RaiseTechnical(
                            **base,
                            subtype="rfi",
                            subject=f"{TOPICS[i % len(TOPICS)]} V{i:05d}",
                            question=f"Please confirm the arrangement at {AREAS[i % len(AREAS)]}.",
                            discipline=DISCIPLINES[i % len(DISCIPLINES)],
                            required_by=(today + timedelta(days=3 + i % 60)).isoformat(),
                            to=[{"name": "Meridian", "email": "pm@meridian.example"}],
                        ),
                    )
                    if i % 2 == 0:  # half of them are submitted for review
                        handle_submit_technical(
                            uow, SubmitTechnical(**base, stream_id=made.stream_id)
                        )
            if batch.stop % 2000 == 0 or batch.stop == records:
                say(f"    RFIs {batch.stop}/{records}")
        facts["rfi_seconds"] = round(time.perf_counter() - began, 1)
        began = time.perf_counter()
        for batch in _batches(records):
            with open_uow(target) as uow:
                for i in batch:
                    handle_receive_correspondence(
                        uow,
                        ReceiveCorrespondence(
                            **base,
                            subject=f"Letter about {TOPICS[i % len(TOPICS)]} V{i:05d}",
                            from_name="Meridian Energy",
                            body="Please see the attached revision and confirm receipt.",
                        ),
                    )
            if batch.stop % 2000 == 0 or batch.stop == records:
                say(f"    letters {batch.stop}/{records}")
        facts["letter_seconds"] = round(time.perf_counter() - began, 1)
        began = time.perf_counter()
        for batch in _batches(records):
            with open_uow(target) as uow:
                for i in batch:
                    kind = DOC_TYPES[i % len(DOC_TYPES)]
                    made = handle_register_document(
                        uow,
                        RegisterDocument(
                            **base,
                            number=f"{kind}-{i // len(DOC_TYPES) + 1:04d}",
                            title=f"{TOPICS[i % len(TOPICS)]} V{i:05d}",
                            doc_type=kind,
                            discipline="PIP",
                            originator="Acme Piping",
                        ),
                    )
                    if i % 2 == 0:  # half of them have a draft revision
                        handle_create_revision(
                            uow,
                            CreateRevision(**base, document_id=made.stream_id, purpose="Review"),
                        )
            if batch.stop % 2000 == 0 or batch.stop == records:
                say(f"    documents {batch.stop}/{records}")
        facts["document_seconds"] = round(time.perf_counter() - began, 1)
    engine = adapter_db.make_engine(target)
    try:
        with engine.connect() as conn:
            facts["events"] = conn.exec_driver_sql("SELECT COUNT(*) FROM events").scalar_one()
            if engine.dialect.name == "postgresql":
                conn.commit()
                conn.execution_options(isolation_level="AUTOCOMMIT").exec_driver_sql("ANALYZE")
    finally:
        engine.dispose()
    facts["seconds"] = round(time.perf_counter() - started, 1)
    return facts


# --- the measurement (one process per backend and size) --------------------------------------


@dataclass
class Series:
    """The repetitions of one action: the cold first one, then the timed ones (milliseconds)."""

    cold: tuple[float, float] | None = None  # (state, painted)
    runs: list[tuple[float, float]] = field(default_factory=list[tuple[float, float]])
    note: str = ""


class Recorder:
    """Collects the timings. A flow calls ``timed``; the runner says which repetition it is."""

    def __init__(self, warmup: int, profile: bool = False) -> None:
        self.warmup = warmup
        self.profile = profile
        self.index = 0
        self.series: dict[str, Series] = {}
        self.profilers: dict[str, cProfile.Profile] = {}

    def add(self, name: str, state: float, painted: float) -> None:
        found = self.series.setdefault(name, Series())
        if self.index == 0:
            found.cold = (state, painted)
        elif self.index > self.warmup:
            found.runs.append((state, painted))

    def profiler(self, name: str) -> cProfile.Profile | None:
        if not self.profile or self.index <= self.warmup:
            return None
        return self.profilers.setdefault(name, cProfile.Profile())


MIN_REPS = 20
SLOW_REP_S = 8.0  # a repetition slower than this on average stops at MIN_REPS timed ones


def repetitions(rec: Recorder, count: int) -> Iterator[int]:
    """The repetition numbers; sets ``rec.index``. A slow action (seconds per repetition) stops
    after ``MIN_REPS`` timed repetitions instead of ``count`` so that a run stays bounded."""
    began = time.perf_counter()
    for i in range(count):
        if i >= rec.warmup + 1 + MIN_REPS and (time.perf_counter() - began) / i > SLOW_REP_S:
            return
        rec.index = i
        yield i


async def settle(pilot: Any) -> None:
    """Let the app finish what it started (workers read rows and the actions bar off-thread)."""
    await pilot.pause()
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()


REFRESHES = [0]  # how many times a screen has been drawn (counted by ``count_refreshes``)


def count_refreshes() -> None:
    """Count every compositor refresh, so "painted" can mean: drawn after the answer arrived."""
    from textual.screen import Screen

    original = Screen._compositor_refresh  # pyright: ignore[reportPrivateUsage]

    def counted(self: Any) -> None:
        original(self)
        REFRESHES[0] += 1

    Screen._compositor_refresh = counted  # type: ignore[method-assign]  # pyright: ignore[reportPrivateUsage]


def paint_pending(app: Any) -> bool:
    screen = app.screen
    return bool(
        screen._layout_required  # pyright: ignore[reportPrivateUsage]
        or screen._scroll_required  # pyright: ignore[reportPrivateUsage]
        or screen._repaint_required  # pyright: ignore[reportPrivateUsage]
        or screen._recompose_required  # pyright: ignore[reportPrivateUsage]
        or screen._dirty_widgets  # pyright: ignore[reportPrivateUsage]
    )


async def send_key(app: Any, key: str) -> None:
    """Hand one key to the app as the terminal would and return at once. (``pilot.press`` also
    waits for the screen to go idle, which is the answer's time plus the harness's.)"""
    from textual import events

    event = events.Key(key, key if len(key) == 1 else None)
    event.set_sender(app)
    app._driver.send_message(event)  # pyright: ignore[reportPrivateUsage]


async def wait_painted(app: Any, since: int, started: float, limit: float, what: str) -> None:
    """Until the screen has been drawn after ``since`` and nothing is waiting to be drawn."""
    while REFRESHES[0] == since or paint_pending(app):
        if time.perf_counter() - started > limit:
            raise TimeoutError(f"{what}: not painted after {limit} s")
        await asyncio.sleep(0.001)


async def timed(
    rec: Recorder,
    name: str,
    pilot: Any,
    act: Callable[[], Awaitable[Any]],
    done: Callable[[], bool],
    *,
    limit: float = 300.0,
    paint: bool = True,
) -> None:
    """Run ``act``, wait until ``done()`` (the *state*), then until the screen is drawn (*painted*;
    ``paint=False``: the action changes nothing on the screen, so only nothing may be pending).

    Both times run from just before ``act``."""
    profiler = rec.profiler(name)
    since = REFRESHES[0]
    started = time.perf_counter()
    if profiler is not None:
        profiler.enable()
    await act()
    while not done():
        if time.perf_counter() - started > limit:
            raise TimeoutError(f"{name}: not done after {limit} s\n{screen_text(pilot.app)}")
        await asyncio.sleep(0.001)
    state = time.perf_counter()
    await wait_painted(pilot.app, since if paint else -1, started, limit, name)
    painted = time.perf_counter()
    if profiler is not None:
        profiler.disable()
    rec.add(name, (state - started) * 1000.0, (painted - started) * 1000.0)


def screen_text(app: Any) -> str:
    strips = app.screen._compositor.render_strips()  # pyright: ignore[reportPrivateUsage]
    return "\n".join(strip.text.rstrip() for strip in strips)


def widget_text(app: Any, ident: str) -> str:
    from textual.widgets import Static

    return str(app.screen.query_one(ident, Static).render())


@contextlib.contextmanager
def inline_threads(enabled: bool) -> Iterator[None]:
    """Profile pass: run ``asyncio.to_thread`` calls inline so cProfile sees the worker's calls."""
    if not enabled:
        yield
        return
    original = asyncio.to_thread

    async def inline(func: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)

    asyncio.to_thread = inline  # type: ignore[assignment]
    try:
        yield
    finally:
        asyncio.to_thread = original


@dataclass(frozen=True)
class Conn:
    """How the child reaches the ledger."""

    mode: str  # embedded | remote
    target: str  # a SQLite path, a postgresql:// URL or the API's base URL
    token: str = ""


async def _no_wait() -> None:
    return None


def make_app(conn: Conn) -> Any:
    """The app over the ledger. The pilot waits for every animation after a key (a tab's 0.3 s
    underline, say); a person does not wait for it, so that wait is switched off."""
    from tl_tui.main import build_app, build_remote_app

    if conn.mode == "remote":
        app = build_remote_app(conn.target, conn.token, PROJECT, actor=ACTOR, live=False)
    else:
        app = build_app(conn.target, PROJECT, live=False, actor=ACTOR)
    app._animator.wait_until_complete = _no_wait  # type: ignore[method-assign]  # pyright: ignore[reportPrivateUsage]
    return app


def close_app(app: Any) -> None:
    with contextlib.suppress(Exception):
        app.client.close()


@dataclass(frozen=True)
class LogSpec:
    """One everyday log: the key that opens it, its screen class and the names of its actions."""

    key: str
    keys: tuple[str, ...]
    prefix: str
    screen: str  # the class name of the log's screen


LOGS = (
    LogSpec("RFI log (Ctrl+G)", ("ctrl+g",), "rfi", "DomainScreen"),
    LogSpec("Correspondence (F5)", ("f5",), "corr", "CorrespondenceScreen"),
    LogSpec("Documents (F7)", ("f7",), "docs", "DocumentRegisterScreen"),
)


def is_screen(app: Any, name: str) -> bool:
    return type(app.screen).__name__ == name


def log_ready(app: Any, name: str) -> bool:
    """The log is the screen and its table holds the rows it read."""
    if not is_screen(app, name):
        return False
    screen = app.screen
    tables = screen.query("#log-table")  # not there while the screen is still being built
    return bool(tables) and bool(screen.shown) and tables.first().row_count == len(screen.shown)


async def run_log(
    conn: Conn, spec: LogSpec, rec: Recorder, count: int, *, with_app: Callable[[], Any]
) -> None:
    """Every action of one log, in one app: open, cursor, Enter and Properties, filter."""
    app = with_app()
    name = spec.screen
    open_name, cursor_name = f"{spec.prefix}_open", f"{spec.prefix}_cursor"
    enter_name, props_name = f"{spec.prefix}_enter", f"{spec.prefix}_props"
    filter_name = f"{spec.prefix}_filter"
    try:
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot)
            for _ in repetitions(rec, count):  # open
                await timed(
                    rec,
                    open_name,
                    pilot,
                    lambda: send_key(app, spec.keys[0]),
                    lambda: log_ready(app, name),
                )
                await pilot.press("escape")
                await settle(pilot)
            await pilot.press(*spec.keys)  # open it once more (untimed) for the other actions
            while not log_ready(app, name):
                await asyncio.sleep(0.005)
            await settle(pilot)
            screen = app.screen
            table = screen.query_one("#log-table")
            for i in repetitions(rec, count):  # move the cursor one row, down then up
                step = "down" if i % 2 == 0 else "up"
                before = table.cursor_row

                def moved(before: int = before) -> bool:
                    row = screen.current()
                    if table.cursor_row == before or row is None:
                        return False
                    return screen.row_record(row)[0] in widget_text(app, "#log-panel-text")

                await timed(rec, cursor_name, pilot, lambda step=step: send_key(app, step), moved)
                await settle(pilot)
            for _ in repetitions(rec, count):  # Enter -> Details, then Properties
                await timed(
                    rec,
                    enter_name,
                    pilot,
                    lambda: send_key(app, "enter"),
                    lambda: (
                        is_screen(app, "RecordScreen")
                        and app.screen.view is not None
                        and bool(app.screen.view.details)
                    ),
                )
                await settle(pilot)
                tabs = app.screen.query_one("#rv-tabs")
                await timed(
                    rec,
                    props_name,
                    pilot,
                    lambda: send_key(app, "2"),
                    lambda tabs=tabs: tabs.active == "tab-psets",
                )
                await settle(pilot)
                await pilot.press("escape")
                while not is_screen(app, name):
                    await asyncio.sleep(0.005)
                await settle(pilot)
            await type_filters(rec, filter_name, pilot, app, count)
    finally:
        close_app(app)


async def type_filters(rec: Recorder, name: str, pilot: Any, app: Any, count: int) -> None:
    """``/`` and a reference taken from a row that is listed; the last key narrows the list."""
    screen = app.screen
    table = screen.query_one("#log-table")
    pool = [
        m.group(0).lower()
        for row in screen.rows[:300]
        if (m := re.search(r"V\d{5}", " ".join(screen.row_cells(row))))
    ]
    if not pool:
        raise RuntimeError("no row carries a reference to type")
    for i in repetitions(rec, count):
        text = pool[(i * 7) % len(pool)]
        total = len(screen.rows)
        await pilot.press("slash")
        # The keys before the last are typed with the rows held back: each costs the same as the
        # last one (every key filters and redraws the whole list), so n keys cost n times the
        # figure, and a slow list would take minutes per repetition to type.
        held = screen.rows
        screen.rows = []
        await pilot.press(*text[:-1])
        await settle(pilot)
        screen.rows = held

        def narrowed(text: str = text, total: int = total) -> bool:
            return (
                screen.filter_text == text
                and 0 < len(screen.shown) < total
                and table.row_count == len(screen.shown)
            )

        await timed(rec, name, pilot, lambda text=text: send_key(app, text[-1]), narrowed)
        await settle(pilot)
        await pilot.press("escape")  # clears the box, back to the full list
        await settle(pilot)
        if len(screen.shown) != len(screen.rows):
            raise RuntimeError("the filter was not cleared")


def grid_ready(app: Any) -> bool:
    grid = app.query_one("#grid")
    return bool(grid.rows)


async def run_grid(conn: Conn, rec: Recorder, count: int) -> None:
    """Launch to the first rows of the record grid (a fresh app each time), then the reload and
    the property-set filters in one running app."""
    for _ in repetitions(rec, count):
        app = make_app(conn)
        try:
            manager = app.run_test(size=SIZE)
            profiler = rec.profiler("grid_open")
            since = REFRESHES[0]
            started = time.perf_counter()
            if profiler is not None:
                profiler.enable()
            await manager.__aenter__()
            try:
                while not grid_ready(app):
                    await asyncio.sleep(0.001)
                state = time.perf_counter()
                await wait_painted(app, since, started, 300.0, "grid_open")
                painted = time.perf_counter()
                if profiler is not None:
                    profiler.disable()
                rec.add("grid_open", (state - started) * 1000.0, (painted - started) * 1000.0)
            finally:
                await manager.__aexit__(None, None, None)
        finally:
            close_app(app)
    app = make_app(conn)
    try:
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot)
            grid = app.query_one("#grid")
            for _ in repetitions(rec, count):
                generation = grid._generation  # pyright: ignore[reportPrivateUsage]
                await timed(
                    rec,
                    "grid_reload",
                    pilot,
                    lambda: send_key(app, "r"),
                    lambda generation=generation: (
                        grid._generation != generation  # pyright: ignore[reportPrivateUsage]
                        and bool(grid.rows)
                    ),
                )
                await settle(pilot)
            for name, text in GRID_FILTERS:
                for _ in repetitions(rec, count):
                    await pilot.press("slash")
                    await settle(pilot)
                    box = app.query_one("#filter-input")
                    box.value = text
                    await settle(pilot)
                    await timed(
                        rec,
                        name,
                        pilot,
                        lambda: send_key(app, "enter"),
                        lambda text=text: grid.filter_text == text and grid.match_count is not None,
                    )
                    await settle(pilot)
                    await pilot.press("slash")
                    box.value = ""
                    await pilot.press("enter")
                    await settle(pilot)
                    if grid.filter_text:
                        raise RuntimeError("the grid filter was not cleared")
    finally:
        close_app(app)


async def run_floor(conn: Conn, rec: Recorder, count: int) -> None:
    """The pilot's own cost: a key nothing is bound to, on the grid."""
    app = make_app(conn)
    try:
        async with app.run_test(size=SIZE) as pilot:
            await settle(pilot)
            for _ in repetitions(rec, count):
                await timed(
                    rec, "floor", pilot, lambda: send_key(app, "f20"), lambda: True, paint=False
                )
                await settle(pilot)
    finally:
        close_app(app)


def top_lines(profiler: cProfile.Profile, limit: int = 12) -> list[str]:
    """Where the time went: the repository's calls, libraries' and Textual's by cumulative time,
    then the five calls with the most time of their own (any file)."""
    stats = pstats.Stats(profiler, stream=io.StringIO())
    mine: list[tuple[float, float, int, str]] = []
    own: list[tuple[float, float, int, str]] = []
    for (filename, line, func), (_cc, nc, tt, ct, _callers) in stats.stats.items():  # type: ignore[attr-defined]
        where = filename.split("/packages/")[-1].split("site-packages/")[-1]
        entry = (ct, tt, nc, f"{where}:{line}({func})")
        if "/packages/" in filename or "sqlalchemy" in filename or "httpx" in filename:
            mine.append(entry)
        own.append(entry)
    mine.sort(reverse=True)
    own.sort(key=lambda e: e[1], reverse=True)
    lines = [
        f"{ct * 1000:.0f} ms cumulative, {tt * 1000:.0f} ms own, {n} calls  {w}"
        for ct, tt, n, w in mine[:limit]
    ]
    lines += [
        f"own time {tt * 1000:.0f} ms, {ct * 1000:.0f} ms cumulative, {n} calls  {w}"
        for ct, tt, n, w in own[:5]
    ]
    return lines


def median(values: list[float]) -> float:
    return statistics.median(values) if values else math.nan


def painted_median(series: Series) -> float:
    return median([p for _s, p in series.runs])


async def measure(conn: Conn, full: bool, reps: int, warmup: int) -> dict[str, Any]:
    """Run every section once; profile the sections with a slow action. Returns the cell."""
    count = 1 + warmup + reps
    rec = Recorder(warmup)
    sections: list[tuple[str, Callable[[Recorder, int], Awaitable[None]], set[str]]] = []
    sections.append(("floor", lambda r, n: run_floor(conn, r, n), {"floor"}))
    sections.append(
        (
            "grid",
            lambda r, n: run_grid(conn, r, n),
            {"grid_open", "grid_reload", *(name for name, _ in GRID_FILTERS)},
        )
    )
    if full:
        for spec in LOGS:
            sections.append(
                (
                    spec.prefix,
                    lambda r, n, spec=spec: run_log(
                        conn, spec, r, n, with_app=lambda: make_app(conn)
                    ),
                    {
                        f"{spec.prefix}_{step}"
                        for step in ("open", "cursor", "enter", "props", "filter")
                    },
                )
            )
    only = os.environ.get("TL_PERF_ONLY")  # development: run only these sections, e.g. "rfi,grid"
    if only:
        sections = [sec for sec in sections if sec[0] in only.split(",")]
    for name, run, _names in sections:
        began = time.perf_counter()
        await run(rec, count)
        print(f"  section {name}: {time.perf_counter() - began:.1f} s", file=sys.stderr, flush=True)
    profile: dict[str, list[str]] = {}
    for _name, run, names in sections:
        slow = [n for n in names if n in rec.series and painted_median(rec.series[n]) > SLOW_MS]
        if not slow:
            continue
        again = Recorder(1, profile=True)
        with inline_threads(True):
            await run(again, 3)  # the first, one warm-up and one profiled repetition
        for n in slow:
            if n in again.profilers:
                profile[n] = top_lines(again.profilers[n])
    actions = {
        name: {
            "cold": list(series.cold) if series.cold else None,
            "state_ms": [round(s, 3) for s, _p in series.runs],
            "painted_ms": [round(p, 3) for _s, p in series.runs],
        }
        for name, series in rec.series.items()
    }
    return {"actions": actions, "profile": profile, "reps": reps, "warmup": warmup}


def child_main(args: argparse.Namespace) -> int:
    logging.disable(logging.WARNING)
    os.environ["TL_ENV"] = "dev"
    count_refreshes()
    conn = Conn(args.mode, args.target, os.environ.get("TL_PERF_TOKEN", ""))
    result = asyncio.run(measure(conn, not args.grid_only, args.reps, args.warmup))
    Path(args.out).write_text(json.dumps(result), encoding="utf-8")
    return 0


# --- the parent: seeding, servers, children --------------------------------------------------


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextlib.contextmanager
def api_server(db: Path, work: Path) -> Iterator[tuple[str, str]]:
    """The API as its own process on loopback over ``db``; yields ``(base URL, token)``."""
    from tl_api.tokens import add_token

    tokens = work / "tokens.json"
    token = add_token(tokens, ACTOR)
    port = free_port()
    env = {**os.environ, "TL_ENV": "dev", "TL_OBJECT_ROOT": str(work / "objects")}
    log = (work / "api.log").open("w")
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "tl_api", "--db", str(db), "--tokens", str(tokens),
            "--host", "127.0.0.1", "--port", str(port),
        ],  # fmt: skip
        cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT,
    )  # fmt: skip
    try:
        deadline = time.monotonic() + 60
        while True:
            if proc.poll() is not None:
                raise RuntimeError(f"the API exited early:\n{(work / 'api.log').read_text()}")
            with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", port), 0.5):
                break
            if time.monotonic() > deadline:
                raise RuntimeError("the API did not start")
            time.sleep(0.2)
        yield f"http://127.0.0.1:{port}", token
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()


def run_child(
    mode: str, target: str, work: Path, *, grid_only: bool, reps: int, warmup: int, token: str = ""
) -> dict[str, Any]:
    out = work / f"cell-{mode}-{abs(hash(target)) % 10**6}.json"
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        *("measure", "--mode", mode, "--target", target, "--out", str(out)),
        *("--reps", str(reps), "--warmup", str(warmup)),
    ]
    if grid_only:
        command.append("--grid-only")
    env = {**os.environ, "TL_PERF_TOKEN": token, "TL_ENV": "dev"}
    for name in ("TL_SCHEMA_DIR", "TL_REMOTE", "TL_TOKEN", "TL_DB", "TL_PROJECT"):
        env.pop(name, None)
    done = subprocess.run(command, cwd=REPO, env=env, check=False)
    if done.returncode != 0:
        raise RuntimeError(f"the measurement of {mode} {target} failed ({done.returncode})")
    return json.loads(out.read_text(encoding="utf-8"))


def summarise(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    rank = max(1, math.ceil(0.95 * len(ordered)))
    return {
        "n": len(ordered),
        "median": round(statistics.median(ordered), 1),
        "p95": round(ordered[rank - 1], 1),
        "min": round(ordered[0], 1),
        "max": round(ordered[-1], 1),
    }


def build_cell(
    backend: str, size: int, facts: dict[str, Any], raw: dict[str, Any]
) -> dict[str, Any]:
    actions: dict[str, Any] = {}
    for name, data in raw["actions"].items():
        cold = data["cold"]
        actions[name] = {
            "painted": summarise(data["painted_ms"]),
            "state": summarise(data["state_ms"]),
            "cold_painted": round(cold[1], 1) if cold else None,
            "cold_state": round(cold[0], 1) if cold else None,
        }
    return {
        "backend": backend,
        "size": size,
        "seed": facts,
        "actions": actions,
        "profile": raw["profile"],
        "reps": raw["reps"],
        "warmup": raw["warmup"],
    }


def run_all(args: argparse.Namespace) -> int:
    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    backends = [b.strip() for b in args.backends.split(",") if b.strip()]
    for b in backends:
        if b not in BACKENDS:
            raise SystemExit(f"unknown backend {b!r}; use {', '.join(BACKENDS)}")
    print_ = lambda text: print(text, flush=True)  # noqa: E731
    work = Path(tempfile.mkdtemp(prefix="tl-ux-perf-"))
    print_(f"work folder {work}")
    os.environ["TL_ENV"] = "dev"
    for name in ("TL_SCHEMA_DIR", "TL_REMOTE", "TL_TOKEN", "TL_DB", "TL_PROJECT"):
        os.environ.pop(name, None)
    os.environ["TL_OBJECT_ROOT"] = str(work / "objects")
    cells: list[dict[str, Any]] = []
    machine = machine_info(work)
    pg_names: list[str] = []
    try:
        for size in sizes:
            full = size <= FULL_LIMIT
            if "postgres" in backends:
                from tl_adapters.postgres import admin

                name = f"tl_perf_ux_{size}_{os.getpid()}"
                admin.create_database(pg_server(), name)
                pg_names.append(name)
                print_(f"[{size}] seeding Postgres")
                facts = seed(pg_url(name), size, full=full, say=print_)
                print_(f"[{size}] Postgres seeded in {facts['seconds']} s; measuring")
                raw = run_child(
                    "embedded",
                    pg_url(name),
                    work,
                    grid_only=not full,
                    reps=args.reps,
                    warmup=args.warmup,
                )
                cells.append(build_cell("postgres", size, facts, raw))
                admin.drop_database(pg_server(), name)
                pg_names.remove(name)
            if "sqlite" in backends or "remote" in backends:
                db = work / f"ux-{size}.db"
                print_(f"[{size}] seeding SQLite")
                facts = seed(db, size, full=full, say=print_)
                print_(f"[{size}] SQLite seeded in {facts['seconds']} s")
                if "sqlite" in backends:
                    print_(f"[{size}] measuring sqlite")
                    raw = run_child(
                        "embedded",
                        str(db),
                        work,
                        grid_only=not full,
                        reps=args.reps,
                        warmup=args.warmup,
                    )
                    cells.append(build_cell("sqlite", size, facts, raw))
                if "remote" in backends:
                    print_(f"[{size}] measuring remote")
                    with api_server(db, work) as (url, token):
                        raw = run_child(
                            "remote", url, work, grid_only=not full, reps=args.reps,
                            warmup=args.warmup, token=token,
                        )  # fmt: skip
                    cells.append(build_cell("remote", size, facts, raw))
                for suffix in ("", "-wal", "-shm"):
                    Path(str(db) + suffix).unlink(missing_ok=True)
    finally:
        if pg_names:
            from tl_adapters.postgres import admin

            for name in pg_names:
                with contextlib.suppress(Exception):
                    admin.drop_database(pg_server(), name)
        shutil.rmtree(work, ignore_errors=True)
    write_results(args, machine, cells)
    return 0


# --- the report ------------------------------------------------------------------------------

ACTION_TABLES: tuple[tuple[str, str, str], ...] = (
    ("rfi_open", "Open the RFI log (Ctrl+G) until rows are shown", "full"),
    ("rfi_cursor", "RFI log: move the cursor one row until the panel shows the record", "full"),
    ("rfi_enter", "RFI log: Enter until the record's Details are shown", "full"),
    ("rfi_props", "RFI record: switch to Properties", "full"),
    ("rfi_filter", "RFI log: type a filter, the last key narrows the list", "full"),
    ("corr_open", "Open the correspondence register (F5) until rows are shown", "full"),
    (
        "corr_cursor",
        "Correspondence: move the cursor one row until the panel shows the record",
        "full",
    ),
    ("corr_enter", "Correspondence: Enter until the letter's Details are shown", "full"),
    ("corr_props", "Letter record: switch to Properties", "full"),
    ("corr_filter", "Correspondence: type a filter, the last key narrows the list", "full"),
    ("docs_open", "Open the document register (F7) until rows are shown", "full"),
    (
        "docs_cursor",
        "Documents: move the cursor one row until the panel shows the document",
        "full",
    ),
    ("docs_enter", "Documents: Enter until the document's Details are shown", "full"),
    ("docs_props", "Document record: switch to Properties", "full"),
    ("docs_filter", "Documents: type a filter, the last key narrows the list", "full"),
    ("grid_open", "Launch the app until the record grid shows its first rows", "grid"),
    ("grid_reload", "Record grid: reload (r) until the rows are back", "grid"),
    (
        "grid_filter_text",
        "Record grid: property-set filter, text (psets.valve_data.body_material=SS316L)",
        "grid",
    ),
    (
        "grid_filter_number",
        "Record grid: property-set filter, number (psets.valve_data.size_in>=12)",
        "grid",
    ),
    (
        "grid_filter_code",
        "Record grid: property-set filter, code (psets.valve_data.fail_action=FC)",
        "grid",
    ),
)
HEADLINE = (
    "rfi_open",
    "rfi_cursor",
    "rfi_enter",
    "rfi_props",
    "rfi_filter",
    "corr_open",
    "docs_open",
    "grid_open",
    "grid_filter_text",
)
#: Screen plumbing that every profile starts with; the cause is below it.
WRAPPERS = (
    r"\((_load|_fill|_draw_table|_show_row|reload|on_mount|on_input_changed|panel_text|"
    r"action_tab|show_tab|on_data_table_row_highlighted|on_key|_fetch_actions|_apply_actions|"
    r"on_filter_submitted|apply_filter|load|on_record_highlighted|show_record)\)"
)
BACKEND_ORDER = {name: i for i, name in enumerate(BACKENDS)}


def _fmt(value: float | None) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "-"
    return f"{value:,.0f}" if value >= 100 else f"{value:.1f}"


def render_markdown(doc: dict[str, Any]) -> str:
    cells: list[dict[str, Any]] = sorted(
        doc["cells"], key=lambda c: (c["size"], BACKEND_ORDER[c["backend"]])
    )
    machine = doc["machine"]
    sizes = sorted({c["size"] for c in cells})
    big = max(sizes)
    titles = {name: title for name, title, _kind in ACTION_TABLES}
    disk = machine["disk"]
    lines: list[str] = [
        "# User-facing performance (P1-UX)",
        "",
        "What a person waits for in the terminal app, measured with the real TUI driven headless "
        "by Textual's pilot against a seeded project. Re-run with `just perf-ux`; every number "
        "is also in `P1-UX-perf.json`. The earlier backend benchmark is "
        "`docs/reports/P0-I8-perf.md` (queries and the bare grid widget, 100k records); this "
        "report measures whole screens.",
        "",
        "## Machine and run",
        f"- Date {doc['date']}, code `{doc['commit']}`"
        + (" (the working tree had uncommitted changes)." if doc["dirty"] else "."),
        f"- CPU `{machine['cpu_model']}`, {machine['cpu_count']} CPUs; RAM {machine['ram_gb']} GB; "
        f"disk `{disk['device']}` {disk['total_gb']} GB, {disk['free_gb']} GB free "
        f"({disk['kind']}).",
        f"- Linux {machine['kernel']}, Python {machine['python']}, SQLite {machine['sqlite']}, "
        f"Postgres {doc.get('postgres', 'n/a')}. Load average at the start "
        f"{machine['load_average']} (a shared container: expect noise of some milliseconds).",
        f"- Terminal {machine['terminal']} (columns x rows): the panel sits beside the list.",
        "",
        "## How to read the numbers",
        "- Milliseconds. **Median** and **p95** (nearest rank) over the timed repetitions of one "
        "action (**n**, at least 20) after untimed warm-up repetitions; **first** is the very "
        "first repetition in a fresh process (cold caches and connections). A figure of 1,000 "
        "ms or more is shown without decimals.",
        "- A time runs from the key press to the moment the screen holds the answer *and* has "
        "been drawn (the app's screen refresh after it). The *state* median (answer held, not "
        "yet drawn) is the last column of each table. The harness's own cost, a key nothing is "
        "bound to, is under 1 ms (`floor` in the JSON).",
        "- Backends: **sqlite** embedded SQLite file; **postgres** embedded, local Postgres "
        "(loopback, TLS off); **remote** the API in its own process on loopback over the same "
        "SQLite file, the TUI over HTTP. The live-update feed is off: only the screens are "
        "measured. No pytest, no mocks: the real app, the real services, the real database.",
        "- Data per size: that many core records with property sets (the bulk writer of the "
        "benches), and that many RFIs, letters and documents through the command handlers (half "
        "of the RFIs submitted, half of the documents with a draft revision). The RFI log and "
        "the correspondence register list at most 500 lines and the document register 5,000: "
        "at 10,000 records the list is cut, but the server still has the whole project.",
        "- The filter rows time the **last** key of the filter; the earlier keys are typed with "
        "the rows held back. Every key filters and redraws the whole list, so a filter of n "
        "keys costs about n times the figure.",
        "- The pilot normally waits for every animation after a key (a tab's underline takes "
        "0.3 s); that wait is off here, since a person does not wait for it.",
        "",
        f"## Headline: median ms at {big:,} records",
        "",
    ]
    head_cells = [c for c in cells if c["size"] == big]
    lines += [
        "| Action | " + " | ".join(c["backend"] for c in head_cells) + " |",
        "|---|" + "---:|" * len(head_cells),
    ]
    for name in HEADLINE:
        row = [
            _fmt(c["actions"][name]["painted"]["median"]) if name in c["actions"] else "-"
            for c in head_cells
        ]
        lines.append(f"| {titles[name]} | " + " | ".join(row) + " |")
    lines.append("")
    lines += [f"## Slow spots (median over {SLOW_MS:.0f} ms at {big:,} records)", ""]
    slow = 0
    for name, title, _kind in ACTION_TABLES:
        hits = [
            (c, c["actions"][name])
            for c in head_cells
            if name in c["actions"] and c["actions"][name]["painted"]["median"] > SLOW_MS
        ]
        if not hits:
            continue
        slow += 1
        medians = ", ".join(f"{c['backend']} {_fmt(d['painted']['median'])} ms" for c, d in hits)
        lines.append(f"- **{title}**: {medians}. {CAUSES.get(name, '')}".rstrip())
        profiled = next((c["profile"][name] for c, _d in hits if name in c["profile"]), [])
        inner = [t for t in profiled if not re.search(WRAPPERS, t)]
        for text in inner[:3]:
            lines.append(f"  - cProfile: {text}")
    if not slow:
        lines.append("None.")
    lines += ["", "## Results by action", ""]
    for name, title, _kind in ACTION_TABLES:
        rows = [(c, c["actions"][name]) for c in cells if name in c["actions"]]
        if not rows:
            continue
        lines += [
            f"### {title}",
            "",
            "| Records | Backend | n | median | p95 | first | state median |",
            "|---:|---|---:|---:|---:|---:|---:|",
        ]
        for c, data in rows:
            lines.append(
                f"| {c['size']:,} | {c['backend']} | {data['painted']['n']} | "
                f"{_fmt(data['painted']['median'])} | {_fmt(data['painted']['p95'])} | "
                f"{_fmt(data['cold_painted'])} | {_fmt(data['state']['median'])} |"
            )
        lines.append("")
    lines += ["## Seeding", "", "| Records | Backend | Seconds | Events |", "|---:|---|---:|---:|"]
    for c in cells:
        seed_info = c["seed"]
        lines.append(
            f"| {c['size']:,} | {c['backend']} | {seed_info.get('seconds', '-')} | "
            f"{seed_info.get('events', '-')} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_results(
    args: argparse.Namespace, machine: dict[str, Any], cells: list[dict[str, Any]]
) -> None:
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "P1-UX-perf.json"
    kept: list[dict[str, Any]] = []
    old: dict[str, Any] = {}
    if args.merge and json_path.exists():
        old = json.loads(json_path.read_text(encoding="utf-8"))
        fresh = {(c["backend"], c["size"]) for c in cells}
        kept = [c for c in old["cells"] if (c["backend"], c["size"]) not in fresh]
    postgres = "n/a"
    if any(c["backend"] == "postgres" for c in cells):
        postgres = _pg_version()
    elif old:
        postgres = old.get("postgres", "n/a")
    doc: dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "commit": _git("rev-parse", "--short", "HEAD"),
        "dirty": bool(_git("status", "--porcelain", "--", "dev/perf", "packages")),
        "machine": machine,
        "postgres": postgres,
        "slow_ms": SLOW_MS,
        "cells": kept + cells,
    }
    json_path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    (out / "P1-UX-perf.md").write_text(render_markdown(doc), encoding="utf-8")
    print(f"wrote {out / 'P1-UX-perf.md'} and {json_path}", flush=True)


def _pg_version() -> str:
    try:
        from tl_adapters import db as adapter_db

        engine = adapter_db.make_engine(pg_url("postgres"))
        try:
            with engine.connect() as conn:
                text = str(conn.exec_driver_sql("SHOW server_version").scalar_one())
        finally:
            engine.dispose()
        return text.split()[0]
    except Exception:  # the version is a nicety
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="command")
    parser.add_argument("--sizes", default="1000,10000", help="record counts, comma separated")
    parser.add_argument("--backends", default=",".join(BACKENDS), help="sqlite,postgres,remote")
    parser.add_argument("--reps", type=int, default=25, help="timed repetitions per action")
    parser.add_argument("--warmup", type=int, default=2, help="untimed repetitions after the first")
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    parser.add_argument(
        "--merge", action="store_true", help="keep cells of the earlier results file"
    )
    child = sub.add_parser("measure", help="(internal) measure one backend and size")
    child.add_argument("--mode", choices=("embedded", "remote"), required=True)
    child.add_argument("--target", required=True)
    child.add_argument("--out", required=True)
    child.add_argument("--reps", type=int, default=25)
    child.add_argument("--warmup", type=int, default=2)
    child.add_argument("--grid-only", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "measure":
        return child_main(args)
    if args.reps < MIN_REPS:
        print(f"warning: --reps {args.reps} is below {MIN_REPS}: the p95 is not worth reading")
    return run_all(args)


if __name__ == "__main__":
    raise SystemExit(main())
