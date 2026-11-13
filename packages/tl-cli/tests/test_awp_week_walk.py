"""P2-I5-T16: the five readers of the awp CLI reads (`week show|ls|ppc`, `iwp progress`, `export
progress`, `roc show`), as the dev owner and as the lowest viewer.

The dev owner is the file's owner on a dev ledger (``TL_ENV=dev``, ``session_viewer``): a controller
of restricted records, named on nothing. The lowest viewer has no session and no dev environment, so
it reads as ``LOWEST``. Each read is run as each of the two; a hidden plan, IWP or item answers as a
missing one (the same exit code and text, but for the name the caller sent), and no answer holds a
``Traceback`` or the id of a record the reader may not read. The hidden world is the one of the
API and MCP walks: a closed week (restricted), an IWP committed to the open week (restricted), an
IWP named to ``amy`` only (privileged) and a restricted scope item.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import bindparam, text
from test_cli_awp import ROOT, Cli, load_world, seed_copy
from tl_adapters.db import as_target, open_uow
from tl_cli.main import app
from tl_core import confidentiality as cf
from tl_core import modules as core_modules
from tl_core.modules import ConfidentialSource
from tl_mod_awp.names import IWP, SCOPE_ITEM, WEEKLY_PLAN
from typer.testing import CliRunner, Result

PROJECT = "P123"
WEEK_CLOSED = "2026-W45"  # restricted
WEEK_OPEN = "2026-W46"
NO_WEEK = "2099-W01"
MISSING_IWP = "P123-IWP-8888"
CLASS_TABLE = "t16_cli_class"
CLEAR_TABLE = "t16_cli_clear"
DEV = {"TL_ENV": "dev"}


def progress_module() -> ModuleType:
    """``progress_world`` of the awp module tests, loaded by path (after ``awp_world``)."""
    load_world()
    if "progress_world" not in sys.modules:
        path = ROOT / "packages" / "tl-modules" / "awp" / "tests" / "progress_world.py"
        spec = importlib.util.spec_from_file_location("progress_world", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["progress_world"] = module
        spec.loader.exec_module(module)
    return sys.modules["progress_world"]


class World:
    """The seed ledger with the hidden records: ids and numbers the reads must not leak."""

    def __init__(self, cli: Cli) -> None:
        progress = progress_module()
        w = load_world().World(as_target(str(cli.db)))
        pw = progress.ProgressWorld(w)
        ww = progress.WeekWorld(pw)
        ww.standards()
        self.w = w
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
        _draft, [item] = pw.package(["8.0"])
        self.visible = self.number(visible)
        self.hidden = self.number(hidden)
        self.privileged = self.number(privileged)
        self.privileged_id = str(privileged)
        self.all_ids = [str(closed), str(hidden), str(privileged), str(item)]
        classes = {
            str(closed): "restricted",
            str(hidden): "restricted",
            str(item): "restricted",
            str(privileged): "privileged",
        }
        with open_uow(as_target(str(cli.db))) as uow:
            conn = uow.conn()
            conn.execute(
                text(f"CREATE TABLE {CLASS_TABLE} (id TEXT PRIMARY KEY, cls TEXT NOT NULL)")
            )
            conn.execute(
                text(f"CREATE TABLE {CLEAR_TABLE} (record_id TEXT NOT NULL, account TEXT NOT NULL)")
            )
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
        self.source = ConfidentialSource(
            record_types=frozenset({WEEKLY_PLAN, IWP, SCOPE_ITEM}),
            table=CLASS_TABLE,
            id_column="id",
            class_column="cls",
            clearance_table=CLEAR_TABLE,
        )

    def number(self, iwp: str) -> str:
        return str(self.w.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=iwp))


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Cli, World]]:
    cli = Cli(seed_copy(tmp_path), tmp_path)
    built = World(cli)
    real = core_modules.confidential_sources
    monkeypatch.setattr(cf, "confidential_sources", lambda: [*real(), built.source])
    yield cli, built


def run_as(cli: Cli, reader: str, *argv: str) -> Result:
    """The verb as ``reader``: ``dev`` is the dev owner (a session-less dev ledger), ``low`` the
    lowest viewer (no session, not dev, so no dev owner)."""
    if reader == "dev":
        return CliRunner().invoke(
            app,
            ["--db", str(cli.db), "awp", *argv, "--project", PROJECT],
            env={**DEV, "TL_SESSION_FILE": str(cli.db.parent / "dev.json")},
        )
    # TL_ENV is unset (None): a test process may be run with TL_ENV=test, which honours dev tokens
    return CliRunner().invoke(
        app,
        ["--db", str(cli.db), "awp", *argv, "--project", PROJECT],
        env={"TL_ENV": None, "TL_SESSION_FILE": str(cli.db.parent / "none.json")},
    )


READS: dict[str, tuple[str, ...]] = {
    "week_show_closed": ("week", "show", WEEK_CLOSED),
    "week_show_open": ("week", "show", WEEK_OPEN),
    "week_show_missing": ("week", "show", NO_WEEK),
    "week_ls": ("week", "ls"),
    "week_ppc": ("week", "ppc"),
    "iwp_progress_visible": ("iwp", "progress", "VISIBLE"),
    "iwp_progress_hidden": ("iwp", "progress", "HIDDEN"),
    "iwp_progress_privileged": ("iwp", "progress", "PRIVILEGED"),
    "iwp_progress_missing": ("iwp", "progress", MISSING_IWP),
    "export_progress": ("export", "progress", "--period", WEEK_OPEN),
    "roc_show": ("roc", "show"),
}


def argv_of(world: World, name: str) -> tuple[str, ...]:
    """The argv of a read, with the IWP numbers of the ledger in place of the placeholders."""
    names = {"VISIBLE": world.visible, "HIDDEN": world.hidden, "PRIVILEGED": world.privileged}
    return tuple(names.get(part, part) for part in READS[name])


@pytest.mark.parametrize("reader", ["dev", "low"])
@pytest.mark.parametrize("name", sorted(READS))
def test_no_read_tells_a_reader_what_they_may_not_read(
    world: tuple[Cli, World], reader: str, name: str
) -> None:
    cli, built = world
    result = run_as(cli, reader, *argv_of(built, name))
    assert "Traceback" not in result.output, (reader, name)
    assert result.exit_code in (0, 1, 2), (reader, name, result.exit_code)
    # the dev owner reads restricted records (the closed week, the restricted IWP and item) but is
    # named on nothing: the privileged record is left out for it, and for the lowest viewer all four
    hidden_ids = {"dev": [built.privileged_id], "low": built.all_ids}[reader]
    hidden_numbers = {"dev": [built.privileged], "low": [built.hidden, built.privileged]}[reader]
    for marker in [*hidden_ids, *hidden_numbers]:
        if any(marker in part for part in argv_of(built, name)):
            continue  # the caller named it: a missing answer repeats it, the next test checks that
        assert marker not in result.output, (reader, name, marker)


def test_a_hidden_week_and_a_made_up_week_answer_the_same(world: tuple[Cli, World]) -> None:
    """The lowest viewer cannot read the restricted week (the dev owner can, so it is not tested
    for the dev owner): it gets what a week that never existed gets."""
    cli, _ = world
    reader = "low"
    hidden = run_as(cli, reader, "week", "show", WEEK_CLOSED)
    missing = run_as(cli, reader, "week", "show", NO_WEEK)
    assert hidden.exit_code == missing.exit_code == 1
    assert hidden.stderr.replace(WEEK_CLOSED, "X") == missing.stderr.replace(NO_WEEK, "X")
    assert hidden.stdout == missing.stdout


@pytest.mark.parametrize("reader", ["dev", "low"])
def test_a_hidden_iwp_and_a_made_up_number_answer_the_same(
    world: tuple[Cli, World], reader: str
) -> None:
    cli, built = world
    missing = run_as(cli, reader, "iwp", "progress", MISSING_IWP)
    assert "Traceback" not in missing.output
    for hidden_number in (
        (built.privileged,) if reader == "dev" else (built.hidden, built.privileged)
    ):
        hidden = run_as(cli, reader, "iwp", "progress", hidden_number)
        assert hidden.exit_code == missing.exit_code, (reader, hidden_number)
        assert hidden.stdout.replace(hidden_number, "X") == missing.stdout.replace(MISSING_IWP, "X")
        assert hidden.stderr.replace(hidden_number, "X") == missing.stderr.replace(MISSING_IWP, "X")


def test_the_lowest_viewer_reads_the_visible_week_and_the_dev_owner_reads_the_closed_one(
    world: tuple[Cli, World],
) -> None:
    cli, built = world
    low = run_as(cli, "low", "week", "ls")
    dev = run_as(cli, "dev", "week", "ls")
    assert low.exit_code == dev.exit_code == 0, low.output
    assert WEEK_OPEN in low.stdout and WEEK_CLOSED not in low.stdout
    assert WEEK_CLOSED in dev.stdout
    assert built.visible in run_as(cli, "low", "iwp", "progress", built.visible).stdout
