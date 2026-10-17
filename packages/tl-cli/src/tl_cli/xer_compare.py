# ruff: noqa: F401, F841
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false
"""`tl xer compare|look-ahead|trend`: what changed between snapshots and what comes next (T09c).

None of these writes anything. The reads are the module's (`tl_mod_schedule.views`); these
commands parse options and print one line per fact, with two spaces between fields. Floats and
shifts are in days (of the activity's own calendar), as the views give them.


STUB (P1-I4-T09c): the bodies of `compare`, `look_ahead` and `trend` are `NotImplementedError`;
the options, docstrings (the exact output), the helpers `days` and `shift` and `register` are
written. The ticket fills the bodies by their STEPS comments.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_schedule import views
from tl_mod_schedule.compare import LIST_FIELDS

from tl_cli.derive_support import Project, cell, fail, service_errors

_Schedule = Annotated[
    str, typer.Option("--schedule", help="The schedule's code, for example MAIN.")
]


def days(value: float | int | None) -> str:
    """``-`` for none, else the number with no trailing zeros and a ``d`` (``4d``, ``-5.5d``)."""
    return "-" if value is None else f"{value:g}d"


def shift(value: int | None) -> str:
    """A shift in calendar days with its sign: ``+7d``, ``-2d``, ``+0d``; ``-`` for none."""
    return "-" if value is None else f"{value:+d}d"


def compare(
    ctx: typer.Context,
    project: Project,
    schedule: _Schedule,
    new: Annotated[
        int | None, typer.Option("--new", min=1, help="The newer snapshot (default: current).")
    ] = None,
    old: Annotated[
        int | None, typer.Option("--old", min=1, help="The older one (default: the one before).")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=1000, help="Rows per list.")] = 20,
) -> None:
    """Compare two snapshots of a schedule.

    Lines: `compare <new key> (<data date>) with <old key> (<data date>)`,
    `data date shift <+n>d`, `latest finish <old or -> -> <new or ->  <+n>d or -`, then
    `summary added <n>  removed <n>  date shifts <n>  float changes <n>  logic changes <n>
    progress changes <n>  duration changes <n>  critical changes <n>` (the full counts), and up to
    `--limit` rows of each list, in this order:
    `added <id>  <name>`, `removed <id>  <name>`,
    `shift <id>  start <+n>d  finish <+n>d  largest <n>d  <name>`,
    `float <id>  <old>d -> <new>d  eroded or improved  <name>`,
    `logic <added|removed|changed> <pred> -> <succ>  <old type> -> <new type>`,
    `progress <id>  <old>% -> <new>%  <old status> -> <new status>  <name>`,
    `duration <id>  <old>d -> <new>d  <name>`,
    `critical <id>  <entered|left>  float <old>d -> <new>d  <name>`.
    A list longer than `--limit` ends with `... <list> <k> more not shown`.
    """
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the view with `uow.conn()` and the scope `f"project:{project}"`, and leave
    #    the `with` before you print. The view is `views.comparison(conn, scope, schedule,
    #    new, old, limit=limit)`; it already cuts each list to `limit` rows and keeps the
    #    full counts in `c.totals`.
    # 3. Print, in this order: the `compare` line (`c.new.key`, `c.new.data_date`,
    #    `c.old.key`, `c.old.data_date`), the `data date shift` line with
    #    `shift(c.data_date_shift_days)`, the `latest finish` line (`cell()` of both dates,
    #    then `shift(c.finish_shift_days)` after two spaces) and the `summary` line.
    # 4. The `summary` line is `summary ` and then, for each name in `LIST_FIELDS` (imported
    #    above), `<name with _ replaced by a space> <c.totals.get(name, 0)>`, joined by two
    #    spaces.
    # 5. Then for each name in `LIST_FIELDS`, in that order: print the rows of that list in
    #    the format of the docstring (the attribute `c.<name>` is a tuple of rows), and if
    #    `c.totals.get(name, 0)` is more than the rows printed, print `... <name> <k> more
    #    not shown` with k the difference.
    # 6. Row formats: `float` uses `days(old_days) -> days(new_days)` and `eroded` when
    #    `r.eroded` else `improved`; `shift` uses `shift(r.start_shift_days)`,
    #    `shift(r.finish_shift_days)` and `r.largest_days`; `logic` uses `cell(old_type) ->
    #    cell(new_type)`; progress percents with `:g`; names with `cell(name, 60)`.
    raise NotImplementedError


def look_ahead(
    ctx: typer.Context,
    project: Project,
    schedule: _Schedule,
    snapshot: Annotated[
        int | None, typer.Option("--snapshot", min=1, help="A snapshot (default: current).")
    ] = None,
    weeks: Annotated[int, typer.Option("--weeks", help="Weeks to look ahead, 1 to 26.")] = 4,
) -> None:
    """List what is under way or starts in the next weeks from the data date.

    Lines: `look-ahead <snapshot key>  <window start> to <window end>  <weeks> weeks`,
    `in progress <n>  late start <n>  starting <n>  critical <n>  total <n>`, then
    `<id>  <phase>  start <early start>  finish <early finish>  float <n>d  <percent>%
    <critical or ok>  <name>` per activity, in the order the module gives. A `--weeks` outside 1
    to 26 is `error: ...` on stderr, exit 1.
    """
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the view with `uow.conn()` and the scope `f"project:{project}"`, and leave
    #    the `with` before you print. The view is `views.look_ahead_view(conn, scope,
    #    schedule, snapshot, weeks)`; it raises `ValueError` for a `weeks` outside 1 to 26.
    #    Catch it inside the `with` and call `fail(str(problem))` (it prints `error: ...`
    #    and exits 1).
    # 3. Print the `look-ahead` line (`r.snapshot_key`, `r.window_start`, `r.window_end`,
    #    `r.weeks`) and the counts line from `r.counts` (`.get(name, 0)` for `in_progress`,
    #    `late_start`, `starting`, `critical`, `total`).
    # 4. Per row print the line of the docstring: float with `days(a.total_float_days)`,
    #    percent with `:g`, `critical` or `ok`, the name with `cell(a.name, 60)`.
    raise NotImplementedError


def trend(
    ctx: typer.Context,
    activity_id: Annotated[str, typer.Argument(help="The P6 activity id, for example A1230.")],
    project: Project,
    schedule: _Schedule,
) -> None:
    """Show one activity's float in every published snapshot, oldest first.

    `trend <id> in <schedule>`, then `<schedule>#<n>  <state>  data date <date>  float <n>d
    start <early start>  finish <early finish>  <percent>%  <critical or ok>` per snapshot that
    has the activity.
    """
    # STEPS
    # 1. `db: DbTarget = ctx.obj`.
    # 2. Open the read with `with service_errors(), open_uow(db, readonly=True) as uow:`
    #    (reads write nothing, and a module error becomes `error: ...` on stderr with exit
    #    1), call the view with `uow.conn()` and the scope `f"project:{project}"`, and leave
    #    the `with` before you print. The view is `views.float_trend(conn, scope, schedule,
    #    activity_id)`.
    # 3. Print `trend <activity_id> in <schedule>`, then one line per point as in the
    #    docstring: `<schedule>#<number>  <state>  data date <cell>  float <days(...)>
    #    start <cell>  finish <cell>  <percent:g>%  critical|ok`.
    raise NotImplementedError


def register(app: typer.Typer) -> None:
    """Add the comparison commands to the `tl xer` group."""
    for name, function in (
        ("compare", compare),
        ("look-ahead", look_ahead),
        ("trend", trend),
    ):
        app.command(name)(function)
