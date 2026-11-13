"""Acceptance for P2-I5-T11b: the awp progress, weekly-plan and look-ahead reads and the two command
doors, on the embedded client, the API client and the fake.

Builds a SQLite ledger with the awp test helpers (``awp_world``, ``progress_world``) and the
schedule helper (``tl_mod_schedule.testing.ScheduleWorld``): the S4 seed, one closed weekly plan of
one committed IWP (done), and a published schedule with that IWP linked to activity A1230. The
embedded client reads it as ``vera`` (the awp viewer); the API client calls the T11a1 and T11a2
routes on a copy of it, signed in as ``vera`` too; the fake holds the shape ``seed_week`` gives it.

Prints ``PASS <client> <method> <n>`` for the nine reads on each of the three clients, then
``PASS same`` (embedded and API equal for six reads), ``PASS missing``, ``PASS hidden``,
``PASS door`` and ``PASS write``. Ends with ``T11b ok``; exits 1 on the first failure. No network.

Run: ``uv run python dev/accept/P2-I5/T11b.py``.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import shutil
import sqlite3
import sys
import tempfile
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
AWP_TESTS = ROOT / "packages" / "tl-modules" / "awp" / "tests"
sys.path.insert(0, str(ROOT / "packages" / "tl-tui" / "tests"))  # the fake client and its helpers

from fakes import FakeClient  # noqa: E402
from fakes_week import PROJECT, seed_week  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from tl_adapters.backend import open_backend  # noqa: E402
from tl_adapters.db import as_target, create_schema, open_uow  # noqa: E402
from tl_api.app import create_app  # noqa: E402
from tl_api.client import ApiClient  # noqa: E402
from tl_api.settings import ApiSettings  # noqa: E402
from tl_api.tokens import TokenStore  # noqa: E402
from tl_core import confidentiality as cf  # noqa: E402
from tl_core import modules as core_modules  # noqa: E402
from tl_core.auth import sessions  # noqa: E402
from tl_core.auth.errors import ForbiddenError  # noqa: E402
from tl_core.modules import ConfidentialSource  # noqa: E402
from tl_core.services.commands import CreateRecord  # noqa: E402
from tl_core.services.errors import RecordNotFoundError  # noqa: E402
from tl_mod_awp.commands import OpenWeeklyPlan  # noqa: E402
from tl_mod_awp.look_ahead_view import LookAheadView  # noqa: E402
from tl_mod_awp.names import WEEKLY_PLAN  # noqa: E402
from tl_mod_schedule.testing import BASE as SCHEDULE_BASE  # noqa: E402
from tl_mod_schedule.testing import ScheduleWorld  # noqa: E402
from tl_tui.embedded import EmbeddedClient  # noqa: E402
from tl_xer.synth import make_xer, week_pair  # noqa: E402

PASSWORD = "correct horse battery"  # the S4 seed's password for every person
READER = "vera"  # the awp viewer grant in the S4 seed
ACTOR = f"user:{READER}"
WRITER = "user:uma"  # the foreman who opens weekly plans in the seed
SCOPE = f"project:{PROJECT}"
PLAN_DAY = date(2026, 11, 2)  # the Monday of the closed plan
WEEK = "2026-W45"  # the ISO week of PLAN_DAY
MISSING_WEEK = "2099-W01"
MISSING = "NO-SUCH"
READS = (
    "list_iwp_counts",
    "get_iwp_progress",
    "get_progress_rollup",
    "get_iwp_hash",
    "list_kpis",
    "list_weekly_plans",
    "get_weekly_plan",
    "list_miss_reasons",
    "get_awp_look_ahead",
)


def passed(line: str) -> None:
    print(f"PASS {line}", flush=True)


def need(condition: bool, message: str) -> None:
    if not condition:
        print(f"FAIL {message}", flush=True)
        sys.exit(1)


def load_by_path(name: str, path: Path) -> ModuleType:
    """A test helper module loaded by its path, under the name the other helpers import it by."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def plain(value: Any) -> Any:
    """A model, a dataclass or a list of them as plain JSON data, so two answers can be compared."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, list | tuple):
        return [plain(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")  # pyright: ignore[reportUnknownMemberType]
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType]
    return value


def count(value: Any) -> int:
    """Rows of a list answer, the items of a look-ahead, 1 for one record."""
    if isinstance(value, LookAheadView):
        return len(value.items)
    if isinstance(value, list):
        return len(value)  # pyright: ignore[reportUnknownArgumentType]
    return 1


def reads(client: Any, number: str) -> dict[str, Callable[[], Any]]:
    """The nine reads, called the same way on every client."""
    return {
        "list_iwp_counts": lambda: client.list_iwp_counts(PROJECT),
        "get_iwp_progress": lambda: client.get_iwp_progress(PROJECT, number),
        "get_progress_rollup": lambda: client.get_progress_rollup(PROJECT),
        "get_iwp_hash": lambda: client.get_iwp_hash(PROJECT, number),
        "list_kpis": lambda: client.list_kpis(PROJECT),
        "list_weekly_plans": lambda: client.list_weekly_plans(PROJECT),
        "get_weekly_plan": lambda: client.get_weekly_plan(PROJECT, WEEK),
        "list_miss_reasons": lambda: client.list_miss_reasons(PROJECT),
        "get_awp_look_ahead": lambda: client.get_awp_look_ahead(PROJECT, "MAIN", weeks=4),
    }


def check_reads(label: str, client: Any, number: str) -> dict[str, Any]:
    """Prints one PASS line per read and returns the answers as plain data."""
    answers: dict[str, Any] = {}
    for method in READS:
        answer = reads(client, number)[method]()
        passed(f"{label} {method} {count(answer)}")
        answers[method] = plain(answer)
    return answers


def raises_missing(call: Callable[[], Any]) -> str | None:
    """The error text of a call that raises ``RecordNotFoundError``, else None."""
    try:
        call()
    except RecordNotFoundError as error:
        return str(error)
    return None


def all_missing(client: Any, number: str) -> bool:
    return (
        raises_missing(lambda: client.get_weekly_plan(PROJECT, MISSING_WEEK)) is not None
        and raises_missing(lambda: client.get_iwp_progress(PROJECT, MISSING)) is not None
        and raises_missing(lambda: client.get_iwp_hash(PROJECT, MISSING)) is not None
    )


@contextmanager
def hidden(target: Any, plan_id: str) -> Iterator[None]:
    """The plan is restricted: the lowest viewer cannot open it, so it answers as a missing week.
    A test source, as ``test_api_awp_weeks`` uses, written to the ledger it is given."""
    cls_table = "t11b_plan_class"
    with open_uow(target) as uow:
        conn = uow.conn()
        conn.execute(
            text(f"CREATE TABLE IF NOT EXISTS {cls_table} (id TEXT PRIMARY KEY, cls TEXT)")
        )
        conn.execute(text(f"DELETE FROM {cls_table}"))
        ids = [
            str(r[0])
            for r in conn.execute(
                text("SELECT id FROM cur_core_record WHERE type = :t"), {"t": WEEKLY_PLAN}
            )
        ]
        for row_id in ids:
            cls = "restricted" if row_id == plan_id else "internal"
            conn.execute(
                text(f"INSERT INTO {cls_table} (id, cls) VALUES (:i, :c)"), {"i": row_id, "c": cls}
            )
    source = ConfidentialSource(
        record_types=frozenset({WEEKLY_PLAN}),
        table=cls_table,
        id_column="id",
        class_column="cls",
    )
    real = core_modules.confidential_sources
    cf.confidential_sources = lambda: [*real(), source]  # type: ignore[attr-defined]
    try:
        yield
    finally:
        cf.confidential_sources = real  # type: ignore[attr-defined]


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="t11b-"))
    saved_schedule_base = dict(SCHEDULE_BASE)
    try:
        db = work / "ledger.db"
        target = as_target(str(db))
        create_schema(target)
        awp_world = load_by_path("awp_world", AWP_TESTS / "awp_world.py")
        progress = load_by_path("progress_world", AWP_TESTS / "progress_world.py")
        world = awp_world.World(target)
        world.people()
        world.editions()
        world.seed()
        ww = progress.WeekWorld(progress.ProgressWorld(world))
        ww.standards()
        plan = ww.open(PLAN_DAY.isoformat())
        iwp = ww.issued()
        ww.commit(plan, iwp, hours="40.0")
        ww.outcome(plan, iwp, "done")
        ww.close(plan)
        number = str(world.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=iwp))

        SCHEDULE_BASE["actor"] = "user:sue"
        sw = ScheduleWorld(target, work / "sched_objects")
        sw.define()
        first, _ = week_pair()
        sw.publish(sw.upload(make_xer(first)))
        sw.link(iwp, "A1230")
        SCHEDULE_BASE.clear()
        SCHEDULE_BASE.update(saved_schedule_base)

        # the API client works on a copy of the ledger (SQLite backup, safe with open handles)
        api_db = work / "api.db"
        src = sqlite3.connect(db)
        dst = sqlite3.connect(api_db)
        src.backup(dst)
        dst.close()
        src.close()
        api_target = as_target(str(api_db))

        embedded = EmbeddedClient.for_sqlite(db, actor=ACTOR)
        fake = FakeClient()
        seed_week(fake)
        # the fake answers the progress and hash of the seeded IWP with what the ledger holds
        fake.load_progress(PROJECT, {number: embedded.get_iwp_progress(PROJECT, number)})
        fake.load_hashes(PROJECT, {number: embedded.get_iwp_hash(PROJECT, number)})

        tokens = work / "tokens.json"
        backend = open_backend(api_db)
        app = create_app(
            backend,
            settings=ApiSettings(db_path=api_db, tokens_path=tokens),
            tokens=TokenStore(tokens),
        )
        _, token = sessions.sign_in(backend, username=READER, password=PASSWORD)
        http = TestClient(app, raise_server_exceptions=False)
        api = ApiClient("http://testserver", token, http=http)

        embedded_answers = check_reads("embedded", embedded, number)
        api_answers = check_reads("api", api, number)
        check_reads("fake", fake, number)

        need(
            all(len(embedded_answers[m]) >= 1 for m in ("list_iwp_counts", "list_kpis")),
            "the embedded reads answered no rows",
        )
        same_methods = (
            "get_weekly_plan",
            "get_iwp_progress",
            "get_iwp_hash",
            "list_iwp_counts",
            "get_awp_look_ahead",
            "list_kpis",
        )
        for method in same_methods:
            need(
                embedded_answers[method] == api_answers[method],
                f"embedded and API {method} differ",
            )
        passed("same " + " ".join(same_methods))

        need(
            all_missing(embedded, number)
            and all_missing(api, number)
            and all_missing(fake, number),
            "a client did not raise RecordNotFoundError for the missing week or number",
        )
        passed("missing")

        # hidden: the same error text for a restricted plan as for a missing one
        missing_text = raises_missing(lambda: embedded.get_weekly_plan(PROJECT, MISSING_WEEK))
        with ExitStack() as stack:
            stack.enter_context(hidden(target, plan))
            stack.enter_context(hidden(api_target, plan))
            hidden_embedded = raises_missing(lambda: embedded.get_weekly_plan(PROJECT, WEEK))
            hidden_api = raises_missing(lambda: api.get_weekly_plan(PROJECT, WEEK))
        need(
            hidden_embedded is not None and hidden_api is not None,
            "a hidden plan was readable by the low-clearance reader",
        )
        need(
            hidden_embedded.replace(WEEK, "W") == missing_text.replace(MISSING_WEEK, "W")  # type: ignore[union-attr]
            and hidden_api.replace(WEEK, "W") == missing_text.replace(MISSING_WEEK, "W"),  # type: ignore[union-attr]
            "a hidden plan answers differently from a missing one",
        )
        passed("hidden")

        # the two command doors: a name outside the table, or a command of another class
        other = CreateRecord(
            actor=ACTOR, source="test", scope=SCOPE, record_type="core.Record", title="x", key="K1"
        )
        awp_model = OpenWeeklyPlan(
            actor=ACTOR, source="test", scope=SCOPE, week_start=date(2026, 11, 9)
        )
        doors = (
            lambda c: c.awp_command("CreateRecord", other),
            lambda c: c.constraint_command("OpenWeeklyPlan", awp_model),
        )
        for client in (embedded, api, fake):
            for door in doors:
                try:
                    door(client)
                except ForbiddenError:
                    continue
                need(False, f"{type(client).__name__} let a command through a door")
        passed("door")

        # the write: the foreman opens the plan of the next week on the embedded client
        writer = EmbeddedClient.for_sqlite(db, actor=WRITER)
        next_day = date(2026, 11, 9)
        iso = next_day.isocalendar()
        next_week = f"{iso.year}-W{iso.week:02d}"
        writer.awp_command(
            "OpenWeeklyPlan",
            OpenWeeklyPlan(actor=WRITER, source="test", scope=SCOPE, week_start=next_day),
        )
        opened = writer.get_weekly_plan(PROJECT, next_week)
        need(opened.week == next_week, "the opened plan is not read back")
        passed("write")

        api.close()
        http.close()
        backend.close()
    finally:
        SCHEDULE_BASE.clear()
        SCHEDULE_BASE.update(saved_schedule_base)
        shutil.rmtree(work, ignore_errors=True)
    print("T11b ok", flush=True)


if __name__ == "__main__":
    main()
