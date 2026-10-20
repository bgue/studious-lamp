# P1-I6-T09b — The Commercial register report

Status: ready
Tier: haiku
Labels: module, reports
Depends on: — (the reads, the clocks view, the models and the test world are in the tree at the branch point)
Branch: `p1/i6-t09b-commercial-register`

## Goal
`reports_commercial.py` has the models of the Commercial register (`CommercialLine`, `CurrencyTotal`, `CommercialRegister`) and the helpers `_amount` and `_money`; `commercial_register` raises `NotImplementedError`. You implement it by its STEPS comment. The register lists the Commercial items (early warnings, change notices, claims, ...) the viewer may read, newest number first, each with its clause, its time bar (due day, days left, whether it was late), its estimated and assessed value and their difference, and totals per currency. One provided test file (22 tests) must pass on SQLite and on Postgres.

## Brief references (pasted)
> **§9 M10, Initial domains, Commercial.** "Time bars are hard clocks with escalating warnings. The register exports to the cost system as pending/approved changes (M11). Forecast impacts are visible to the future cost module." Data: contract clause, estimated value ($, hours, qty by cost code), schedule impact, entitlement basis, assessed value; links to RFIs, instructions, cost codes, activities.
>
> **§16 reports, Correspondence.** "... running clocks and time bars; RFI log with response times and impact flags; **commercial notice/claim register with values (estimated vs assessed)**; ..."
>
> **What the register means (decided in the P1-I6 plan).** Money is a decimal text with two places and is added as `Decimal`: **amounts of different currencies are never added**, so the totals are per currency, in currency-code order. The *time bar* of an item is its clock of kind `time_bar` (`views.clock_view` gives the figures as of a day). A bar is *late* when it has expired, or was met after its due day. *Variance* is the assessed value minus the estimated value, when both are stated. Commercial items are `restricted` (ADR-0016): a plain viewer or an agent gets an empty register; that comes from `registry_domain`, not from this report.
>
> **Reading rule of the module (`packages/tl-modules/correspondence/AGENTS.md`, ADR-0016).** Read an item only through `registry`, `registry_domain`, `views`, `load_item` or `open_item`: they apply the viewer's class filter. A raw `SELECT` on a `cur_correspondence_*` table is a leak. A hidden item, a foreign item and an unknown id are the same "absent". The viewer defaults to the lowest clearance; do not set a viewer in the report, the caller does.
>
> **Command, report and model docstrings are the contract.** Do not change a model, a field, a docstring or a name in a file you complete; only the function bodies that carry a STEPS comment are yours.

### Learnings that apply
> **L-P1-I5-2.** The viewer (ADR-0016) defaults to the lowest clearance, so a helper that reads a record in a test reads nothing unless the test set a viewer (`use_viewer(...)`, `as_controller()`). Do not widen the default to get a test green.
>
> **L-P1-I3-5.** A test that only passes with the whole module in place is the module's test: run the provided file as it is; do not add helpers to it or to the shared test support (`tl_mod_correspondence/testing.py`).
>
> **L-P1-I1-6.** A parity run's count is not the SQLite count twice: a case that does not use the `db`/`new_db`/`engine`/`world` fixtures runs once. The counts in *Acceptance* are exact.
>
> **L-P0-I1-6.** ruff's `E501` applies to docstrings and comments at 100 columns, and pyright strict flags `@contextmanager` functions annotated `Iterator[X]`. Wrap prose.
>
> **L-P0-I6C-8.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain (it hung until the timeout), and never `pkill -f <pattern>` (it kills your own shell): kill only a PID you started.
>
> **L-P1-I3B-6.** Copy the provided test byte for byte (`cp`), run `ruff` and `pyright` on the tree, and do not edit the copy: if it cannot pass, stop and report *Blocked*.
>
> **L-P1-I4-9.** A first `just check` in a fresh worktree takes over two minutes and the Postgres run of a module suite can take longer: give the shell tool `timeout` 600000, or run it in the background and wait for it. Run `ruff format <your file>` first, because the format check rewrites a hand-wrapped line.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-modules/correspondence/src/tl_mod_correspondence/reports_commercial.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
"""The Commercial register: every notice and claim with its values and its time bar (brief 9, M10).

"Commercial notice/claim register with values (estimated vs assessed)": for each Commercial item
the register shows the clause it is given under, the day the contractor became aware, the time bar
(due date, days left, whether it was met in time), the estimated and the assessed value with the
difference, the schedule impact and the assessment. Totals are per currency: amounts of different
currencies are never added together. Money is exact (``Decimal``), written with two places.

Reads go through ``registry_domain``, which applies the viewer's confidentiality (ADR-0016):
Commercial items are ``restricted``, so a plain user's register is empty. Nothing here writes. The
export to the cost system (``export.py``) builds on these lines.

STUB (P1-I6-T09b): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import Connection

from tl_mod_correspondence import registry, registry_domain, views
from tl_mod_correspondence.handlers.common import today as module_today

_CENT = Decimal("0.01")


class CommercialLine(BaseModel):
    """One Commercial item as the register shows it. Amounts are decimal texts with two places."""

    id: str
    number: str
    subject: str
    subtype: str
    state: str
    direction: str
    confidentiality: str
    clause: str | None  # ``<contract>/<clause number>``
    aware_on: str | None
    issued_on: str | None
    time_bar_due: str | None
    time_bar_days_left: int | None  # in the clock's own day type; negative once overdue
    time_bar_state: str | None  # running, paused, met, cancelled or expired (as of today)
    time_bar_late: bool  # expired, or met after its due date
    currency: str | None
    estimated_value: str | None
    assessed_value: str | None
    variance: str | None  # assessed minus estimated, when both are stated
    schedule_impact_days: int | None
    assessment_status: str | None
    derived_from: str | None  # the number of the RFI it was escalated from, when readable


class CurrencyTotal(BaseModel):
    currency: str
    count: int
    estimated: str
    assessed: str


class CommercialRegister(BaseModel):
    scope: str
    as_of: str
    lines: list[CommercialLine]
    totals: list[CurrencyTotal]  # by currency, in code order
    time_bars_running: int
    time_bars_late: int


def _amount(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def _money(value: Decimal) -> str:
    return str(value.quantize(_CENT))


def commercial_register(
    conn: Connection,
    scope: str,
    *,
    subtype: str | None = None,
    state: str | None = None,
    only_open: bool = False,
    time_bars_only: bool = False,
    today: str | None = None,
    limit: int = 500,
) -> CommercialRegister:
    """The register of the Commercial items of ``scope`` the viewer may read, newest first.

    ``subtype`` and ``state`` keep the items that have them. ``only_open`` leaves out Closed and
    Void items. ``time_bars_only`` keeps the items whose time bar is still running or paused, or
    was late. ``today`` (an ISO date; the module's today by default) is the day the time bars
    are judged on.
    """
    # STEPS
    # 1. `day = today or module_today()`.
    # 2. `rows = registry_domain.list_commercial(conn, scope, subtype=subtype,
    #    state=state, open_only=only_open, limit=limit)`. The viewer's class filter is
    #    applied inside it (Commercial items are restricted, so a plain user gets no
    #    rows): read the items only this way, never with a query of your own.
    # 3. For each `row`: `item, data = row.item, row.data`. The time bar is the first
    #    clock of the item whose `kind` is `time_bar` among `registry.clocks_of(conn,
    #    item.id)`; make it `bar = views.clock_view(conn, clock, date.fromisoformat(day))`
    #    (it carries `due_on`, `days_left`, `state`, `effective_state` and `closed_on`),
    #    or `bar = None` when there is none.
    # 4. `clause = registry.get_clause(conn, data.contract_clause_id)` when the item names
    #    a clause, else None. `source = registry.get_item(conn, data.derived_from_id)`
    #    when it has a source item (this is None when the viewer may not read it), else
    #    None. `estimated, assessed = _amount(data.estimated_value),
    #    _amount(data.assessed_value)`.
    # 5. `late = bar is not None and (bar.effective_state == "expired" or (bar.state ==
    #    "met" and bar.closed_on is not None and bar.closed_on > bar.due_on))`.
    # 6. Build the `CommercialLine`: `id`, `number`, `subject`, `state`, `direction`,
    #    `confidentiality` from `item`; `subtype=item.subtype or ""`;
    #    `clause=f"{clause.contract}/{clause.clause_number}"` or None; `aware_on` from
    #    `data`; `issued_on=item.issued_on`; `time_bar_due=bar.due_on`,
    #    `time_bar_days_left=bar.days_left`, `time_bar_state=bar.effective_state` (all
    #    None without a bar); `time_bar_late=late`; `currency`, `estimated_value`,
    #    `assessed_value`, `schedule_impact_days`, `assessment_status` from `data`;
    #    `variance=_money(assessed - estimated)` when both are not None, else None;
    #    `derived_from=source.number` or None.
    # 7. With `time_bars_only`, `continue` (skip the line) unless its `time_bar_state` is
    #    `running` or `paused`, or `time_bar_late` is true. Append the others to `lines`.
    # 8. Totals: `counts: dict[str, int]` and `sums: dict[str, list[Decimal]]` (estimated,
    #    assessed). For each kept line that has a `currency`, add 1 to its count, and add
    #    `_amount(line.estimated_value) or Decimal(0)` to the first sum and
    #    `_amount(line.assessed_value) or Decimal(0)` to the second (a currency is never
    #    added to another).
    # 9. Return `CommercialRegister(scope=scope, as_of=day, lines=lines,
    #    totals=[CurrencyTotal(currency=code, count=counts[code], estimated=_money(est),
    #    assessed=_money(ass)) for code, (est, ass) in sorted(sums.items())],
    #    time_bars_running=<lines whose time_bar_state is running or paused>,
    #    time_bars_late=<lines with time_bar_late>)`.
    raise NotImplementedError
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/registry_domain.py` (read-only; the dataclasses and the one function you call; abridged):
```python
@dataclass(frozen=True)
class CommercialData:
    contract_clause_id: str | None
    aware_on: str | None
    derived_from_id: str | None
    currency: str | None
    estimated_value: str | None
    estimated_hours: str | None
    cost_code_impacts: list[dict[str, Any]]
    schedule_impact_days: int | None
    schedule_impact_note: str | None
    entitlement_basis: str | None
    assessed_value: str | None
    assessed_on: str | None
    assessment_status: str | None
    assessment_note: str | None

@dataclass(frozen=True)
class CommercialRow:
    """A Commercial item: the item and its domain data."""

    item: ItemRow
    data: CommercialData

def list_commercial(
    conn: Connection,
    scope: str,
    *,
    subtype: str | None = None,
    state: str | None = None,
    assessment_status: str | None = None,
    clause_id: str | None = None,
    open_only: bool = False,
    include_void: bool = False,
    limit: int = 500,
    offset: int = 0,
) -> list[CommercialRow]:
    """The Commercial items of a scope the viewer may read, newest number first.

    ``open_only`` keeps the items that are not Closed or Void. A void item is left out unless
    ``include_void``.
    """
    ...
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/registry.py` and `packages/tl-modules/correspondence/src/tl_mod_correspondence/views.py` (read-only; what you call and read; abridged to the names used):
```python
# registry.py
def get_clause(conn: Connection, clause_id: str) -> ClauseRow | None: ...   # .contract, .clause_number
def get_item(conn: Connection, item_id: str) -> ItemRow | None: ...         # None when hidden; .number
def clocks_of(conn: Connection, item_id: str) -> list[ClockRow]: ...        # ClockRow.kind: str

# ItemRow fields used here: id, number, subject, state, direction, subtype (str | None),
# issued_on (str | None), confidentiality

# views.py
class ClockView(BaseModel):
    kind: str
    due_on: str
    state: str            # as stored: running, paused, met, cancelled or expired
    effective_state: str  # as of the day given: a running clock past its day is "expired"
    days_left: int | None
    closed_on: str | None

def clock_view(conn: Connection, row: registry.ClockRow, today: date | None = None) -> ClockView: ...

```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/common.py` (read-only):
```python
def today() -> str:
    """Today's date, ISO, from ``now``."""
    ...

```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/testing.py` (read-only; what the provided test calls):
```python
CONTROLLER: cf.Viewer   # a document controller (level 1): reads restricted items

def as_controller() -> ContextManager[None]: ...   # act and read as a controller inside the block
def frozen_today(day: str | date) -> ContextManager[None]: ...

class CorrWorld:
    def forge_commercial(
        self,
        number: str = "P123-EW-0001",
        *,
        subject: str = "Early warning: routing change",
        state: str = "Draft",   # Draft, Commercial review, PM approval, Issued, Awaiting assessment,
        subtype: str = "early_warning",  # Agreed, Disputed, Partially agreed, Closed or Escalated
        confidentiality: str = "restricted",
        scope: str = PROJECT,
        issued_on: str = "2026-10-20",
        item: dict[str, Any] | None = None,
        assessment: dict[str, Any] | None = None,   # overrides the fields of Commercial.Assessed
        **data: Any,                                # overrides the fields of Commercial.Defined
    ) -> str: ...
    def forge_technical(self, number: str = "P123-RFI-0001", *, state: str = "Draft", **more: Any) -> str: ...
    def clause(self, contract: str = "CT-1", number: str = "20.1", **more: Any) -> CommandResult: ...
    def start_clock(self, item_id: str, **more: Any) -> CommandResult: ...
    def pause(self, clock_id: str, **more: Any) -> CommandResult: ...
    def meet(self, clock_id: str, **more: Any) -> CommandResult: ...
    def void_draft(self, item_id: str, reason: str = "made in error") -> CommandResult: ...

```

## Context (read these, nothing else)
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/reports_commercial.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/registry_domain.py`
- `docs/tickets/P1-I6/provided/t09b-test_reports_commercial.py.txt`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/testing.py`
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/reports_commercial.py` (complete)
- `packages/tl-modules/correspondence/tests/test_reports_commercial.py` (create: a byte-for-byte copy of the provided file)
- `docs/reports/P1-I6/P1-I6-T09b.md` (create: your report)

## Steps
1. `cp docs/tickets/P1-I6/provided/t09b-test_reports_commercial.py.txt packages/tl-modules/correspondence/tests/test_reports_commercial.py` and do not edit it.
2. Replace the `commercial_register` body by the steps of its STEPS comment, delete the STEPS comments, the `STUB` paragraph of the module docstring and the `ruff: noqa` line.
3. Run the commands below and keep their output.

## Acceptance
```
uv run ruff format packages/tl-modules/correspondence/src/tl_mod_correspondence/reports_commercial.py
uv run pytest packages/tl-modules/correspondence/tests/test_reports_commercial.py -q
uv run pytest packages/tl-modules/correspondence/tests/test_reports_commercial.py -q --adapters sqlite,postgres
just check
uv run pytest packages/tl-modules/correspondence -q
```
Expected: 22 passed on SQLite; 44 passed with both adapters (every case uses the `world` fixture, so each runs twice); `just check` clean; the package suite passes. `TL_PG_URL` is exported by the session hook; if Postgres is not running, `sudo pg_ctlcluster 16 main start`.

## Tests to add
- `packages/tl-modules/correspondence/tests/test_reports_commercial.py` (provided, 22 tests): the empty register; a line's clause, dates, values and variance to the cent; a missing figure; totals per currency and exact (0.10 + 0.20 = 0.30); the assessed total; the time bar's due day and days left, expired and late, met in time, met after its day, met on its day, paused; only the clock of kind `time_bar`; the RFI an item came from, and none when the viewer may not read it; every filter; void and closed items; the order and the limit; a plain viewer and an agent see no restricted item; another project.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved as `docs/reports/P1-I6/P1-I6-T09b.md` and committed with the ticket. Deviations first. Paste the decisive lines of every acceptance command. Say which lines of the STEPS you found unclear, if any.

## Escalation triggers
- Stop and report *Blocked* if the pasted interface and the repo disagree, a command in *Acceptance* fails for a reason outside *Allowed paths*, or the provided test cannot pass without editing it.
- Stop if you find yourself changing a model, a field, a docstring or a name that this ticket does not own.
- Stop if a STEPS line and the provided test disagree.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
