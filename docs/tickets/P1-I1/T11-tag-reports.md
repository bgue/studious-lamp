# P1-I1-T11 — Tag reports: summary, missing property sets, pattern violations

Status: ready
Tier: haiku
Labels: core, cli
Depends on: P1-I1-T08 (the class binding, `bound_psets`), T06 and S3, on `p1/i1`; no other ticket
Branch: `p1/i1-t11-tag-reports`

## Goal
Three base reports on a project's tags, as module functions and as the CLI group `tl tag report` (registered in `tl_cli/main.py`
as a sub-group of `tl tag`). `tl_mod_engineering/reports.py` and `tl_cli/tag_report.py` have their values, signatures and
docstrings final and the bodies raise `NotImplementedError`. You implement them. Two provided test files (`6` + `6` test
functions, 6 + 6 cases) must pass.

## Brief references (pasted)
> **Brief 12 Base reporting.** Reports run on current state (and the lake where heavy); the same query serves the TUI, the API and exports.
>
> **Brief 9 M2 / 27.5.** Tag class determines mandatory psets. A constraining change (a class that gains a required pset) flags existing records non-conformant; nothing is rewritten.
>
> **P1-I1 plan T11.** Reports: tag register by class/status, missing mandatory psets, pattern violations.

### Specification
- `register_summary`: one SQL (`_SUMMARY_SQL`, given) that groups tags in service by class and workflow state and counts the stored conformance (`ok` and `waived` together, `warning`, `nonconformant`). Tags that are `Superseded` or `Deleted` are excluded by the SQL.
- `missing_psets`: evaluated now, against the scope's current effective schema, with `tl_core.services.psets.conformance(uow, tag_id)`. Only issues whose rule is in `MISSING_RULES` count. A tag with none is left out. `level` narrows to issues of that level.
- `pattern_violations`: reads `registry.list_tags`; `number_status == "violation"` always counts; with `include_warnings` a tag with any `violations` entry counts.
- The CLI commands call exactly these functions and print. `--json` prints `json.dumps(..., indent=2)` of `dataclasses.asdict` of each line.
- The reports read only: open units of work with `readonly=True`.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-modules/engineering/src/tl_mod_engineering/reports.py` (the stub you complete):
```python
"""Base reports of the engineering module (brief 12, 9 M2; P1-I1-T11).

Three views of a project's tags: how many there are by class and workflow state and how they
conform (``register_summary``), which of them still lack what their class requires
(``missing_psets``, evaluated live against the current effective schema, so a class that gained a
required pset shows at once), and which numbers break the numbering pattern
(``pattern_violations``). They read; nothing here writes. A tag that left service (state
``Superseded`` or ``Deleted``) is not reported.

STUB (P1-I1-T11): the three report functions raise NotImplementedError; the values, `_SUMMARY_SQL`
and the signatures are final. Each body has a STEPS comment. Implement them, then delete this
paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, text
from tl_core.services.psets import conformance
from tl_core.uow import UnitOfWork

from tl_mod_engineering import registry
from tl_mod_engineering.names import TAG_TABLE

#: Conformance rules that mean "a value the record's class or state requires is missing".
MISSING_RULES = ("class_required", "required_in_state")


@dataclass(frozen=True)
class SummaryLine:
    class_code: str | None  # None: tags with no class
    status: str | None  # None: tags that never left the initial state
    tags: int
    ok: int  # tags whose stored conformance is ok or waived
    warning: int
    nonconformant: int


@dataclass(frozen=True)
class MissingIssue:
    path: str  # psets.valve_data or psets.valve_data.size_in
    rule: str  # class_required | required_in_state
    level: str  # warning | nonconformant
    message: str


@dataclass(frozen=True)
class MissingLine:
    number: str
    class_code: str | None
    status: str | None
    issues: list[MissingIssue]


@dataclass(frozen=True)
class ViolationLine:
    number: str
    number_status: str  # ok | violation
    problems: list[dict[str, Any]]  # {segment, rule, level, message}


_SUMMARY_SQL = text(
    "SELECT t.class_code AS class_code, r.status AS status, COUNT(*) AS tags, "
    "SUM(CASE WHEN r.conformance IN ('ok', 'waived') THEN 1 ELSE 0 END) AS ok, "
    "SUM(CASE WHEN r.conformance = 'warning' THEN 1 ELSE 0 END) AS warning, "
    "SUM(CASE WHEN r.conformance = 'nonconformant' THEN 1 ELSE 0 END) AS nonconformant "
    f"FROM {TAG_TABLE} t JOIN cur_core_record r ON r.id = t.id "
    "WHERE r.voided = :no AND t.scope = :scope "
    "AND (r.status IS NULL OR r.status NOT IN ('Superseded', 'Deleted')) "
    "GROUP BY t.class_code, r.status ORDER BY t.class_code, r.status"
)


def register_summary(conn: Connection, scope: str) -> list[SummaryLine]:
    """Tags in service by class and workflow state, with their stored conformance counts.

    Lines are ordered by class then state, a missing class or state first. Counts come from the
    conformance stored with the tag at its last write.
    """
    # STEPS
    # 1. rows = conn.execute(_SUMMARY_SQL, {"no": False, "scope": scope}).
    # 2. One SummaryLine per row: class_code, status, tags, ok, warning, nonconformant (the
    #    counts as int). The SQL already groups and orders.
    raise NotImplementedError


def missing_psets(uow: UnitOfWork, scope: str, *, level: str | None = None) -> list[MissingLine]:
    """Tags in service that lack a value their class or state requires, by number.

    Each tag is evaluated now against the scope's current effective schema (``conformance``). Only
    the issues of ``MISSING_RULES`` are listed; a tag with none is left out. With ``level``
    ("warning" or "nonconformant") only issues of that level count.
    """
    # STEPS
    # 1. For each tag of registry.list_tags(uow.conn(), scope, limit=100000) (ordered by number):
    #    report = conformance(uow, tag.id).
    # 2. issues = [MissingIssue(i.path, i.rule, i.level, i.message) for i in report.issues if
    #    i.rule in MISSING_RULES and (level is None or i.level == level)].
    # 3. If issues is not empty append MissingLine(tag.number, tag.class_code, tag.status, issues).
    # 4. return the lines.
    raise NotImplementedError


def pattern_violations(
    conn: Connection, scope: str, *, include_warnings: bool = False
) -> list[ViolationLine]:
    """Tags in service whose number breaks the numbering pattern, by number.

    These are tags stored with ``number_status`` ``violation`` (a legacy import). With
    ``include_warnings`` tags whose number is fine but carries a warning (a mnemonic that does not
    usually identify the class) are listed too.
    """
    # STEPS
    # 1. For each tag of registry.list_tags(conn, scope, limit=100000): include it when
    #    tag.number_status == "violation", or when include_warnings is true and tag.violations is
    #    not empty. A line is ViolationLine(tag.number, tag.number_status, tag.violations).
    # 2. return the lines (already in number order).
    raise NotImplementedError
```

`packages/tl-cli/src/tl_cli/tag_report.py` (the stub you complete):
```python
"""The `tl tag report` group: summary, missing property sets, pattern violations (P1-I1-T11).

Each subcommand reads through `tl_mod_engineering.reports` and prints. Nothing is written.

STUB (P1-I1-T11): the three command bodies raise NotImplementedError; the signatures, options and
docstrings are final. Each body has a STEPS comment. Implement them, then delete this paragraph, the
STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_engineering import reports

app = typer.Typer(help="Reports on a project's tags.", no_args_is_help=True)

_Project = Annotated[str, typer.Option("--project", help="Project ID; scope project:<ID>.")]
_Json = Annotated[bool, typer.Option("--json", help="Print JSON.")]


@app.command("summary")
def summary(ctx: typer.Context, project: _Project, as_json: _Json = False) -> None:
    """Tags in service by class and state: total, ok, warning, nonconformant."""
    # STEPS
    # 1. db: DbTarget = ctx.obj. Inside `with open_uow(db, readonly=True) as uow:` lines =
    #    reports.register_summary(uow.conn(), f"project:{project}").
    # 2. With --json print json.dumps([asdict(line) for line in lines], indent=2) and return.
    # 3. Otherwise one line per SummaryLine, fields joined with two spaces: class_code or "-",
    #    status or "-", f"tags={n}", f"ok={n}", f"warning={n}", f"nonconformant={n}".
    raise NotImplementedError


@app.command("missing")
def missing(
    ctx: typer.Context,
    project: _Project,
    level: Annotated[
        str | None,
        typer.Option("--level", help="Only issues of this level: warning or nonconformant."),
    ] = None,
    as_json: _Json = False,
) -> None:
    """Tags that lack a value their class or state requires, with what is missing."""
    # STEPS
    # 1. db: DbTarget = ctx.obj. Inside `with open_uow(db, readonly=True) as uow:` lines =
    #    reports.missing_psets(uow, f"project:{project}", level=level).
    # 2. With --json print json.dumps([asdict(line) for line in lines], indent=2) and return.
    # 3. Otherwise per MissingLine print f"{number}  {class_code or '-'}  {status or '-'}" and
    #    then, per issue, f"  {level} {path} {rule}: {message}".
    raise NotImplementedError


@app.command("violations")
def violations(
    ctx: typer.Context,
    project: _Project,
    include_warnings: Annotated[
        bool, typer.Option("--warnings", help="Also list numbers that carry only a warning.")
    ] = False,
    as_json: _Json = False,
) -> None:
    """Tags whose number breaks the numbering pattern, with each problem."""
    # STEPS
    # 1. db: DbTarget = ctx.obj. Inside `with open_uow(db, readonly=True) as uow:` lines =
    #    reports.pattern_violations(uow.conn(), f"project:{project}",
    #    include_warnings=include_warnings).
    # 2. With --json print json.dumps([asdict(line) for line in lines], indent=2) and return.
    # 3. Otherwise per ViolationLine print f"{number}  {number_status}" and then, per problem,
    #    f"  {level} {segment or 'number'}: {message}".
    raise NotImplementedError
```

`packages/tl-modules/engineering/src/tl_mod_engineering/registry.py`:
```python
@dataclass(frozen=True)
class TagRow:
    id: str
    scope: str
    number: str
    class_code: str | None
    title: str
    status: str | None
    area: str | None
    mnemonic: str | None
    sequence: int | None
    segments: dict[str, str]
    pattern_code: str | None
    number_status: str  # ok | violation
    violations: list[dict[str, Any]]
    origin: str
    conformance: str
    version: int
    psets: dict[str, Any]

def list_tags(
    conn: Connection,
    scope: str,
    *,
    class_code: str | None = None,
    status: str | None = None,
    mnemonic: str | None = None,
    area: str | None = None,
    number_status: str | None = None,
    include_ended: bool = False,
    limit: int = 1000,
    offset: int = 0,
) -> list[TagRow]:
```

## Context (read these, nothing else)
- `packages/tl-modules/engineering/src/tl_mod_engineering/reports.py` and `packages/tl-cli/src/tl_cli/tag_report.py` (the files you edit)
- `packages/tl-modules/engineering/src/tl_mod_engineering/registry.py`
- `docs/tickets/P1-I1/provided/t11-test_reports.py.txt` and `docs/tickets/P1-I1/provided/t11-test_cli_tag_report.py.txt` (the tests)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- pyright is `standard` for `packages/tl-modules`; ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing.
- Provided files live under `docs/tickets/P1-I1/provided/` as `.py.txt`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I1/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line when you implement a stub.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number of cases (L-P0-I8A-8).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never write a hand-made `cur_*` table or change `schema/**` or anything under `generated/` unless this ticket says so.
- CLI tests (L-P0-I4-B8): the test asserts `exit_code` and that `result.exception` is `None`; do not catch exceptions.
- The module test runs on both databases (`new_db`): `TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test uv run pytest packages/tl-modules/engineering/tests/test_reports.py packages/tl-cli/tests/test_cli_tag_report.py -q --adapters sqlite,postgres`.

## Allowed paths
- `packages/tl-modules/engineering/src/tl_mod_engineering/reports.py` (edit)
- `packages/tl-cli/src/tl_cli/tag_report.py` (edit)
- `packages/tl-modules/engineering/tests/test_reports.py` (create; byte-identical copy)
- `packages/tl-cli/tests/test_cli_tag_report.py` (create; byte-identical copy)
- `docs/reports/P1-I1/P1-I1-T11.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy the two provided tests to the two paths above.
3. Implement the three functions and the three commands by their STEPS comments; remove the STUB paragraphs, the STEPS comments and both `ruff: noqa` lines.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-modules/engineering/tests/test_reports.py packages/tl-cli/tests/test_cli_tag_report.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test uv run pytest packages/tl-modules/engineering/tests/test_reports.py packages/tl-cli/tests/test_cli_tag_report.py -q --adapters sqlite,postgres
uv run pytest packages/tl-modules packages/tl-cli -q
```
Expected: `just check` clean; 12 passed on SQLite; all passed with both adapters; both packages pass (the `tl tag` commands of another ticket are stubs in your tree, so `tl_cli` tests of `tl tag` are not in it).

## Tests to add
None beyond the provided files.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the output of the parity run (decisive lines).

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and a provided test disagree.
- Stop if a test needs a change in `registry.py`, a handler or another `tl_cli` file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
