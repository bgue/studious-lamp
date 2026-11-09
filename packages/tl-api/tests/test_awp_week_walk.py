"""P2-I5-T16: the five readers walk every awp progress and weekly-plan read (T11a1, T11a2).

The nine GET routes added by T11a1 and T11a2 are called as each of five readers: ``bob`` (a plain
user), ``ctl`` (a document controller), ``boss`` (an admin, a controller with no privilege), ``amy``
(named on the privileged record) and ``bot`` (an agent, whose word may close a route with 403). The
ledger holds a closed weekly plan (restricted), an open plan with one restricted commitment, one
privileged IWP named to ``amy`` only, one restricted scope item on a Draft IWP, and the visible
records. Per route and reader: every answer is 200, 404 or (for ``bot``) 403; the answers hold none
of what the reader may not read; a hidden plan, IWP or item answers as one that never existed; a
list counts visible rows only; the three clients (embedded, remote and the HTTP routes) agree.

The fixtures ``harness`` and ``seeded`` (the five readers' tokens) are those of
``test_confidentiality_walk``; the awp seed is ``test_api_awp.seed_awp``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from harness import Harness
from sqlalchemy import bindparam, text
from test_api_awp import ROOT, load_world, seed_awp
from tl_adapters.db import open_uow
from tl_api.client import ApiClient
from tl_core import confidentiality as cf
from tl_core import modules as core_modules
from tl_core.modules import ConfidentialSource
from tl_core.services.errors import RecordNotFoundError
from tl_mod_awp.names import IWP, SCOPE_ITEM, WEEKLY_PLAN
from tl_mod_schedule.testing import BASE as SCHEDULE_BASE
from tl_mod_schedule.testing import ScheduleWorld
from tl_tui.embedded import EmbeddedClient
from tl_xer.synth import make_xer, week_pair

ROOT_API_TESTS = Path(__file__).resolve().parent
PROJECT = "P123"
P = f"/projects/{PROJECT}/awp"
SCHEDULE = "MAIN"
WEEK_CLOSED = "2026-W45"  # restricted: hidden from every reader below a controller
WEEK_OPEN = "2026-W46"
NO_WEEK = "2099-W01"  # names nothing
MISSING_IWP = "P123-IWP-8888"  # names nothing
#: The nine routes T11a1 and T11a2 added (the walk's list, checked against the app's openapi).
WALKED = {
    "/projects/{project}/awp/iwps/counts",
    "/projects/{project}/awp/iwps/{number}/progress",
    "/projects/{project}/awp/iwps/{number}/hash",
    "/projects/{project}/awp/progress/rollup",
    "/projects/{project}/awp/kpis",
    "/projects/{project}/awp/weeks",
    "/projects/{project}/awp/weeks/{week}",
    "/projects/{project}/awp/miss-reasons",
    "/projects/{project}/awp/look-ahead",
}
#: What each reader may read of the classed records (the class of each kind below).
READS = {
    "bob": {"open"},
    "ctl": {"open", "restricted"},
    "boss": {"open", "restricted"},
    "amy": {"open", "privileged"},
    "bot": {"open"},
}
READERS = sorted(READS)
#: The kinds of hidden record, with the class each one carries and the markers it is known by.
CLASS_OF = {
    "restricted_plan": "restricted",
    "restricted_iwp": "restricted",
    "restricted_item": "restricted",
    "privileged_iwp": "privileged",
}
ALLOWED = {"bot": (200, 403, 404)}
CLASS_TABLE = "t16_week_class"
CLEAR_TABLE = "t16_week_clear"


@dataclass(frozen=True)
class Ledger:
    closed_plan: str  # id of the restricted weekly plan
    closed_iwp: str  # id of the visible IWP committed to the closed plan
    visible_iwp: str  # id of the visible IWP committed to the open plan
    hidden_iwp: str  # id of the restricted IWP committed to the open plan
    privileged_iwp: str  # id of the IWP named to amy only
    draft_iwp: str  # id of a Draft IWP holding the restricted scope item
    scope_item: str  # id of the restricted scope item
    numbers: dict[str, str]  # kind -> number ("visible", "hidden", "privileged", "closed", ...)
    all_numbers: frozenset[str]  # every IWP number of the project

    def hidden_kinds(self, reader: str) -> dict[str, tuple[str, str]]:
        """Kind -> (week or number, record id) the reader may not read."""
        known = {
            "restricted_plan": (WEEK_CLOSED, self.closed_plan),
            "restricted_iwp": (self.numbers["hidden"], self.hidden_iwp),
            "restricted_item": ("", self.scope_item),
            "privileged_iwp": (self.numbers["privileged"], self.privileged_iwp),
        }
        return {k: v for k, v in known.items() if CLASS_OF[k] not in READS[reader]}

    def hidden_markers(self, reader: str) -> list[str]:
        out: list[str] = []
        for label, record_id in self.hidden_kinds(reader).values():
            out += [record_id] + ([label] if label else [])
        return out


#: ``test_confidentiality_walk`` is loaded by path under its own name: the MCP file of the same name
#: is in the same pytest session under ``just gate``, and two modules cannot share that name.
Seed = Any  # the walk's ``Seed`` dataclass: ids, numbers, extra ids and the five readers' tokens


def walk_module() -> ModuleType:
    name = "api_confidentiality_walk"
    if name not in sys.modules:
        path = ROOT_API_TESTS / "test_confidentiality_walk.py"
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


@pytest.fixture
def harness(parity_harness: Harness) -> Harness:
    """The walk's harness: the parity fixture, on SQLite and under ``--adapters postgres``."""
    return parity_harness


@pytest.fixture
def seeded(harness: Harness, tmp_path: Path) -> Seed:
    """The five readers' accounts and tokens, and the hidden correspondence world of the walk."""
    return walk_module().seed(harness, tmp_path)


def progress_module() -> ModuleType:
    """``progress_world`` of the awp module tests, loaded by path (after ``awp_world``)."""
    name = "progress_world"
    load_world()
    if name not in sys.modules:
        path = ROOT / "packages" / "tl-modules" / "awp" / "tests" / "progress_world.py"
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


@pytest.fixture
def ledger(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> Iterator[Ledger]:
    """The S4 seed, a closed week and an open week, and a schedule that links an IWP to A1230."""
    target = harness.target or harness.db
    world = seed_awp(harness, rollup=True)
    progress = progress_module()
    pw = progress.ProgressWorld(world)
    ww = progress.WeekWorld(pw)
    ww.standards()
    closed = ww.open("2026-11-02")
    closed_iwp = ww.issued()
    ww.commit(closed, closed_iwp, hours="40.0")
    ww.outcome(closed, closed_iwp, "done")
    ww.close(closed)
    opened = ww.open("2026-11-09")
    visible = ww.issued()
    hidden = ww.issued()
    privileged = ww.issued()
    ww.commit(opened, visible, hours="20.0")
    ww.commit(opened, hidden, hours="10.0")
    ww.commit(opened, privileged, hours="12.0")
    draft, [item] = pw.package(["8.0"])

    def key(record: str) -> str:
        return str(world.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=record))

    saved = dict(SCHEDULE_BASE)
    SCHEDULE_BASE["actor"] = "user:sue"
    try:
        sched = ScheduleWorld(target, harness.root / "sched_objects")
        sched.define()
        first, _ = week_pair()
        sched.publish(sched.upload(make_xer(first)))
        sched.link(visible, "A1230")
        sched.link(hidden, "A1230")
    finally:
        SCHEDULE_BASE.clear()
        SCHEDULE_BASE.update(saved)

    with open_uow(target) as uow:
        conn = uow.conn()
        conn.execute(text(f"CREATE TABLE {CLASS_TABLE} (id TEXT PRIMARY KEY, cls TEXT NOT NULL)"))
        conn.execute(
            text(f"CREATE TABLE {CLEAR_TABLE} (record_id TEXT NOT NULL, account TEXT NOT NULL)")
        )
        classes = {
            str(closed): "restricted",
            str(hidden): "restricted",
            str(item): "restricted",
            str(privileged): "privileged",
        }
        found = conn.execute(
            text("SELECT id FROM cur_core_record WHERE type IN :t").bindparams(
                bindparam("t", expanding=True)
            ),
            {"t": [WEEKLY_PLAN, IWP, SCOPE_ITEM]},
        ).all()
        for (record_id,) in found:
            conn.execute(
                text(f"INSERT INTO {CLASS_TABLE} (id, cls) VALUES (:i, :c)"),
                {"i": str(record_id), "c": classes.get(str(record_id), "internal")},
            )
        conn.execute(
            text(f"INSERT INTO {CLEAR_TABLE} (record_id, account) VALUES (:r, :a)"),
            {"r": str(privileged), "a": "user:amy"},
        )
    source = ConfidentialSource(
        record_types=frozenset({WEEKLY_PLAN, IWP, SCOPE_ITEM}),
        table=CLASS_TABLE,
        id_column="id",
        class_column="cls",
        clearance_table=CLEAR_TABLE,
    )
    real = core_modules.confidential_sources
    monkeypatch.setattr(cf, "confidential_sources", lambda: [*real(), source])
    all_numbers = frozenset(
        str(r["key"]) for r in world.rows("SELECT key FROM cur_core_record WHERE type = :t", t=IWP)
    )
    yield Ledger(
        closed_plan=str(closed),
        closed_iwp=str(closed_iwp),
        visible_iwp=str(visible),
        hidden_iwp=str(hidden),
        privileged_iwp=str(privileged),
        draft_iwp=str(draft),
        scope_item=str(item),
        numbers={
            "closed": key(closed_iwp),
            "visible": key(visible),
            "hidden": key(hidden),
            "privileged": key(privileged),
            "draft": key(draft),
        },
        all_numbers=all_numbers,
    )


def requests_for(led: Ledger) -> list[tuple[str, str, dict[str, Any]]]:
    """(template, url, params) of every walked GET, over every candidate value."""
    numbers = [*led.numbers.values(), MISSING_IWP]
    out: list[tuple[str, str, dict[str, Any]]] = [
        ("/projects/{project}/awp/iwps/counts", f"{P}/iwps/counts", {}),
        ("/projects/{project}/awp/progress/rollup", f"{P}/progress/rollup", {}),
        ("/projects/{project}/awp/kpis", f"{P}/kpis", {}),
        ("/projects/{project}/awp/weeks", f"{P}/weeks", {}),
        ("/projects/{project}/awp/miss-reasons", f"{P}/miss-reasons", {}),
        ("/projects/{project}/awp/look-ahead", f"{P}/look-ahead", {"schedule": SCHEDULE}),
    ]
    for week in (WEEK_CLOSED, WEEK_OPEN, NO_WEEK):
        out.append(("/projects/{project}/awp/weeks/{week}", f"{P}/weeks/{week}", {}))
    for number in numbers:
        out.append(
            ("/projects/{project}/awp/iwps/{number}/progress", f"{P}/iwps/{number}/progress", {})
        )
        out.append(("/projects/{project}/awp/iwps/{number}/hash", f"{P}/iwps/{number}/hash", {}))
    return out


def walked_routes(harness: Harness) -> set[str]:
    """The awp GET routes of the app that the walk must cover (read from the openapi)."""
    fragments = ("/progress", "/kpis", "/weeks", "/hash", "/look-ahead", "/miss-reasons", "/counts")
    paths = harness.app.openapi()["paths"]
    return {
        p
        for p, ops in paths.items()
        if "get" in ops
        and p.startswith("/projects/{project}/awp/")
        and any(f in p for f in fragments)
    }


def bearer(seed: Seed, reader: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {seed.tokens[reader]}"}


def body_of(harness: Harness, seed: Seed, reader: str, url: str, params: dict[str, Any]) -> Any:
    response = harness.client_for(None).get(url, params=params, headers=bearer(seed, reader))
    assert response.status_code == 200, (reader, url, response.text[:200])
    return response.json()


def test_the_walk_finds_the_nine_routes(harness: Harness) -> None:
    assert walked_routes(harness) == WALKED
    assert len(WALKED) == 9


@pytest.mark.parametrize("reader", READERS)
def test_every_week_route_shows_a_reader_only_what_they_may_read(
    harness: Harness, seeded: Seed, ledger: Ledger, reader: str
) -> None:
    client = harness.client_for(None)
    answers = {
        url: client.get(url, params=params, headers=bearer(seeded, reader))
        for _, url, params in requests_for(ledger)
    }
    allowed = ALLOWED.get(reader, (200, 404))
    for url, response in answers.items():
        assert response.status_code in allowed, (reader, url, response.status_code)
    blob = " ".join(r.text for r in answers.values() if r.status_code == 200)
    for marker in ledger.hidden_markers(reader):
        assert marker not in blob, (reader, marker)
    if reader != "bot":
        assert ledger.numbers["visible"] in blob  # the reader does read some
    if answers[f"{P}/weeks"].status_code == 200:
        weeks = [row["week"] for row in answers[f"{P}/weeks"].json()]
        expected = [WEEK_OPEN] if "restricted" not in READS[reader] else [WEEK_CLOSED, WEEK_OPEN]
        assert sorted(weeks) == sorted(expected), (reader, weeks)
    counts = answers[f"{P}/iwps/counts"]
    if counts.status_code == 200:
        shown = {row["number"] for row in counts.json()}
        hidden_numbers = {
            label
            for kind, (label, _) in ledger.hidden_kinds(reader).items()
            if kind in ("restricted_iwp", "privileged_iwp")
        }
        assert shown == set(ledger.all_numbers) - hidden_numbers, reader


@pytest.mark.parametrize(
    ("reader", "kind"),
    [
        (reader, kind)
        for reader in READERS
        for kind in ("restricted_plan", "restricted_iwp", "privileged_iwp")
        if CLASS_OF[kind] not in READS[reader]
    ],
)
def test_a_hidden_plan_or_iwp_answers_byte_for_byte_as_one_that_never_existed(
    harness: Harness, seeded: Seed, ledger: Ledger, reader: str, kind: str
) -> None:
    client = harness.client_for(None)
    headers = bearer(seeded, reader)
    if kind == "restricted_plan":
        hidden_url, missing_url = f"{P}/weeks/{WEEK_CLOSED}", f"{P}/weeks/{NO_WEEK}"
        pairs = [(hidden_url, WEEK_CLOSED, missing_url, NO_WEEK)]
    else:
        number = ledger.numbers["hidden" if kind == "restricted_iwp" else "privileged"]
        pairs = []
        for suffix in ("progress", "hash"):
            pairs.append(
                (
                    f"{P}/iwps/{number}/{suffix}",
                    number,
                    f"{P}/iwps/{MISSING_IWP}/{suffix}",
                    MISSING_IWP,
                )
            )
    for hidden_url, hidden_token, missing_url, missing_token in pairs:
        hidden = client.get(hidden_url, headers=headers)
        missing = client.get(missing_url, headers=headers)
        assert hidden.status_code == missing.status_code, (reader, hidden_url)
        assert hidden.text.replace(hidden_token, "X") == missing.text.replace(missing_token, "X")
        assert sorted(hidden.headers) == sorted(missing.headers), hidden_url
        assert ledger.hidden_iwp not in hidden.text and ledger.closed_plan not in hidden.text


@pytest.mark.parametrize("reader", ["bob", "ctl", "amy"])
def test_the_hidden_commitment_is_dropped_from_the_open_week_with_its_note(
    harness: Harness, seeded: Seed, ledger: Ledger, reader: str
) -> None:
    detail = body_of(harness, seeded, reader, f"{P}/weeks/{WEEK_OPEN}", {})
    numbers = {c["iwp_key"] for c in detail["commitments"]}
    visible_for_reader = ledger.numbers["visible"] in numbers
    assert visible_for_reader
    hidden_here = ledger.numbers["hidden"] in numbers
    assert hidden_here == (CLASS_OF["restricted_iwp"] in READS[reader])
    if not hidden_here:
        assert "some commitments not shown" in json.dumps(detail)


@pytest.mark.parametrize("reader", ["bob", "ctl", "boss", "amy"])
def test_the_embedded_and_remote_clients_agree_and_obey_the_walk(
    harness: Harness, seeded: Seed, ledger: Ledger, reader: str
) -> None:
    target = harness.target or harness.db
    embedded = EmbeddedClient.for_target(target, actor=f"user:{reader}")
    remote = ApiClient("http://testserver", seeded.tokens[reader], http=harness.client_for(None))
    reads: dict[str, Callable[[Any], Any]] = {
        "get_weekly_plan": lambda c: c.get_weekly_plan(PROJECT, WEEK_OPEN),
        "list_weekly_plans": lambda c: c.list_weekly_plans(PROJECT),
        "get_iwp_progress": lambda c: c.get_iwp_progress(PROJECT, ledger.numbers["visible"]),
        "list_iwp_counts": lambda c: c.list_iwp_counts(PROJECT),
        "list_kpis": lambda c: c.list_kpis(PROJECT),
        "get_awp_look_ahead": lambda c: c.get_awp_look_ahead(PROJECT, SCHEDULE),
    }
    markers = ledger.hidden_markers(reader)
    for name, read in reads.items():
        here = plain(read(embedded))
        there = plain(read(remote))
        assert here == there, name
        blob = json.dumps(here, default=str)
        for marker in markers:
            assert marker not in blob, (reader, name, marker)


def plain(value: Any) -> Any:
    """An answer of a client as plain JSON data, so two answers can be compared."""
    if isinstance(value, list | tuple):
        return [plain(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")  # pyright: ignore[reportUnknownMemberType]
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType]
    if hasattr(value, "__dataclass_fields__"):
        return {k: plain(getattr(value, k)) for k in value.__dataclass_fields__}
    return value


def error_of(call: Callable[..., Any], *args: Any) -> tuple[str, str]:
    try:
        call(*args)
    except RecordNotFoundError as exc:
        return type(exc).__name__, str(exc)
    raise AssertionError("expected RecordNotFoundError")


@pytest.mark.parametrize("reader", ["bob", "amy", "ctl"])
def test_the_clients_answer_a_hidden_record_as_a_missing_one(
    harness: Harness, seeded: Seed, ledger: Ledger, reader: str
) -> None:
    embedded = EmbeddedClient.for_target(harness.target or harness.db, actor=f"user:{reader}")
    remote = ApiClient("http://testserver", seeded.tokens[reader], http=harness.client_for(None))
    for client in (embedded, remote):
        for kind, (label, _) in ledger.hidden_kinds(reader).items():
            if kind == "restricted_plan":
                hidden = error_of(client.get_weekly_plan, PROJECT, WEEK_CLOSED)
                missing = error_of(client.get_weekly_plan, PROJECT, NO_WEEK)
                assert hidden[0] == missing[0]
                assert hidden[1].replace(WEEK_CLOSED, "X") == missing[1].replace(NO_WEEK, "X")
            elif kind in ("restricted_iwp", "privileged_iwp"):
                hidden = error_of(client.get_iwp_progress, PROJECT, label)
                missing = error_of(client.get_iwp_progress, PROJECT, MISSING_IWP)
                assert hidden[0] == missing[0]
                assert hidden[1].replace(label, "X") == missing[1].replace(MISSING_IWP, "X")
