# P1-I6-T07b — TUI: the text of the Commercial register

Status: ready
Tier: haiku
Labels: tui, text
Depends on: — (the client interface, the fake client with its seed, the report models and the helpers are in the tree at the branch point)
Branch: `p1/i6-t07b-commercial-text`

## Goal
`commercial_text.py` holds the column names of the Commercial register (`COMMERCIAL_COLUMNS`) and four functions that raise `NotImplementedError`: `bar_text`, `commercial_cells`, `commercial_summary` and `commercial_lines`. You implement them by their STEPS comments. They turn the report's lines (`CommercialLine`, `CommercialRegister`) and the view of one notice (`CommercialView`) into the cells of a table row, the summary line under the table and the panel for the highlighted notice. The screen (`widgets/domain_screen.py`) is built and calls them. One provided test file must pass.

## Brief references (pasted)
> **§9 M10, Commercial.** "Time bars are hard clocks with escalating warnings. The register exports to the cost system as pending/approved changes." **§16 reports.** "Commercial notice/claim register with values (estimated vs assessed)." What the register means (decided in the P1-I6 plan): money is a decimal text with two places and **amounts of different currencies are never added**, so the totals are one part for each currency; a time bar is *late* when it expired or was met after its due day; the days left are in the clock's own day type and negative once overdue.
>
> **Command, report and model docstrings are the contract.** Do not change a constant, a name, a docstring or a signature in a file you complete; only the function bodies that carry a STEPS comment are yours. The functions are pure: they read the values they are given and decide nothing; the figures (days, totals, late) are the report's and are shown as they come.
>
> The fake client used by the provided test (`seed_domains` in `packages/tl-tui/tests/fakes_correspondence.py`) holds two notices; `list_commercial("P123")` returns them in this order as `CommercialLine`s:
> 
> | Number | State | Kind | Aware | Bar due | Left | Bar state | Late | Estimated | Assessed | Status |
> |---|---|---|---|---|---|---|---|---|---|---|
> | P123-EW-0001 | Awaiting assessment | early_warning | 2026-10-12 | 2026-10-26 | -4 | met | true | USD 12500.00 | none | none |
> | P123-CN-0001 | Agreed | change_notice | 2026-10-12 | 2026-11-09 | 10 | met | false | USD 12500.00 | 9000.00 | agreed |
> 
> `get_commercial` returns the `CommercialView` of each: both under clause CT-1/20.1, 240.0 hours, 3 days of schedule impact, cost code 2.3.1 for 12500.00 and the basis "Clause 20.1"; EW-0001 was escalated from P123-RFI-0001 and issued on 2026-10-30; CN-0001 was assessed on 2026-10-20 (agreed, USD 9000.00, note "as stated") and issued on 2026-10-15.

### Learnings that apply
> **L-P1-I1-6.** A parity run's count is not the SQLite count twice: a case that does not use the `db`/`new_db`/`engine`/`world` fixtures runs once. The counts in *Acceptance* are exact.
>
> **L-P0-I1-6.** ruff's `E501` applies to docstrings and comments at 100 columns, and pyright strict flags `@contextmanager` functions annotated `Iterator[X]`. Wrap prose.
>
> **L-P0-I6C-8.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain (it hung until the timeout), and never `pkill -f <pattern>` (it kills your own shell): kill only a PID you started.
>
> **L-P1-I3B-6.** Copy the provided test byte for byte (`cp`), run `ruff` and `pyright` on the tree, and do not edit the copy: if it cannot pass, stop and report *Blocked*.
>
> **L-P1-I4-9.** A first `just check` in a fresh worktree takes over two minutes and the Postgres run of a module suite can take longer: give the shell tool `timeout` 600000, or run it in the background and wait for it. Run `ruff format <your file>` first, because the format check rewrites a hand-wrapped line.
>
> **L-P1-I3B-5.** Keep the exact messages that tests compare as they are written in the STEPS: do not paraphrase a message; copy it. A comment that wraps a quoted message is one message.
>
> **L-P1-I6-1.** Pyright strict does not narrow an attribute through a boolean local computed from it (`late = x is not None and ...; if late:` leaves `x` as `T | None`). Where a STEPS line says "when `late`", write the `is not None` check again in the code and say so in the report.
>
> **L-P1-I6-2.** The first `just check` in a fresh worktree can end with a bare exit 247 at the pyright step and no output; run it again once before you read it as a type error.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-tui/src/tl_tui/commercial_text.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
"""What the Commercial register shows, as pure functions (P1-I6; brief 9 M10, brief 16).

The rows of the register, its summary line and the panel under it are text built from
``tl_mod_correspondence.reports_commercial`` and ``views_domain`` values and nothing else. The
figures (days left on the time bar, late, totals by currency) are the report's. Amounts of
different currencies are shown on lines of their own and never added.

STUB (P1-I6-T07b): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

from tl_mod_correspondence.reports_commercial import CommercialLine, CommercialRegister
from tl_mod_correspondence.views_domain import CommercialView

from tl_tui.correspondence_text import clock_line

COMMERCIAL_COLUMNS = (
    "Number",
    "State",
    "Kind",
    "Aware",
    "Bar due",
    "Left",
    "Bar",
    "Cur",
    "Estimated",
    "Assessed",
    "Status",
    "Subject",
)


def bar_text(line: CommercialLine) -> str:
    """``LATE`` for a bar that expired or was met after its due day, else the bar's state
    (``running``, ``met``, ...), ``-`` for an item with no bar."""
    # STEPS
    # 1. If `line.time_bar_late` is true return `"LATE"`.
    # 2. Otherwise return `line.time_bar_state or "-"`.
    raise NotImplementedError


def commercial_cells(line: CommercialLine) -> tuple[str, ...]:
    """The twelve cells of a register row, in the order of ``COMMERCIAL_COLUMNS``."""
    # STEPS
    # 1. Return a tuple of exactly twelve strings, in the order of `COMMERCIAL_COLUMNS`:
    #    `line.number`, `line.state`, `line.subtype`, `line.aware_on or "-"`,
    #    `line.time_bar_due or "-"`, `"-" if line.time_bar_days_left is None else
    #    str(line.time_bar_days_left)` (0 days left is `"0"`, a negative number keeps its
    #    sign), `bar_text(line)`, `line.currency or "-"`, `line.estimated_value or "-"`,
    #    `line.assessed_value or "-"`, `(line.assessment_status or "-").replace("_", "
    #    ")`, `line.subject`.
    raise NotImplementedError


def commercial_summary(
    register: CommercialRegister, *, only_open: bool = False, time_bars_only: bool = False
) -> str:
    """``2 notices | time bars running 1, late 1 | USD: 2 estimated 40000.00 assessed 25000.00``,
    one ``CUR:`` part for each currency, and ``| filter: open, time bars`` when a filter is on."""
    # STEPS
    # 1. `count = len(register.lines)`. `parts` starts with `f"{count} notice{'s' if count
    #    != 1 else ''}"` and `f"time bars running {register.time_bars_running}, late
    #    {register.time_bars_late}"`.
    # 2. For each `total` in `register.totals` (all of them, in the order given) append
    #    `f"{total.currency}: {total.count} estimated {total.estimated} assessed
    #    {total.assessed}"`. Amounts of different currencies are never added: one part for
    #    each currency.
    # 3. `filters` is the list of the names `"open"` and `"time bars"` whose flag
    #    (`only_open`, `time_bars_only`) is true, in that order. When it is not empty
    #    append `"filter: " + ", ".join(filters)`.
    # 4. Return `" | ".join(parts)`.
    raise NotImplementedError


def commercial_lines(view: CommercialView) -> list[str]:
    """The panel under the register: the highlighted notice, its figures, assessment and clocks."""
    # STEPS
    # 1. `money = f"{view.currency or '-'} {view.estimated_value or '-'}"` and `days = "-"
    #    if view.schedule_impact_days is None else str(view.schedule_impact_days)`.
    # 2. Start `lines` with these four strings: `f"{view.number}  {view.state}
    #    {view.subtype or '-'}  class {view.confidentiality}"`; `f"subject:
    #    {view.subject}"`; `f"clause {view.clause or '-'}  aware on {view.aware_on or '-'}
    #    issued {view.issued_on or '-'}"`; `f"estimated {money}  hours
    #    {view.estimated_hours or '-'}  schedule {days} days"` (two spaces between the
    #    parts).
    # 3. When `view.cost_code_impacts` is not empty append `"cost codes: " + ",
    #    ".join(...)` where each impact `i` (a dict) gives
    #    `f"{i['cost_code']}={i.get('amount') or i.get('hours') or '-'}"`.
    # 4. When `view.entitlement_basis` is set append `f"basis: {view.entitlement_basis}"`.
    #    When `view.derived_from_number` is set append `f"escalated from
    #    {view.derived_from_number}"`.
    # 5. When `view.assessment_status` is set append `f"assessment ({view.assessed_on or
    #    '-'}): {view.assessment_status.replace('_', ' ')} {view.currency or ''}
    #    {view.assessed_value or '-'}"` followed, only when `view.assessment_note` is set,
    #    by `f" ({view.assessment_note})"` (one line).
    # 6. When `view.clocks` is not empty append `"clocks:"` and then, for each clock, `f"
    #    {clock_line(c)}"` (two spaces). Return `lines`.
    raise NotImplementedError
```

`packages/tl-tui/src/tl_tui/correspondence_text.py` (read-only; one clock as a line; abridged to the names used):
```python
def clock_line(clock: ClockView) -> str:
    """One clock under an item: ``C01 running due 2026-11-02 left 14 (14 calendar days) Reply``."""
    ...
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/reports_commercial.py` (read-only; the models):
```python
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
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/views_domain.py` (read-only; abridged to the names used):
```python
class CommercialView(views.ItemView):
    contract_clause_id: str | None
    clause: str | None  # ``<contract>/<clause number>``
    aware_on: str | None
    derived_from_id: str | None
    derived_from_number: str | None
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
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/views.py` (read-only; the clocks of a view; abridged to the names used):
```python
class ClockView(BaseModel):
    id: str
    key: str
    item_id: str
    item_number: str
    label: str
    kind: str
    start_on: str
    duration_days: int
    day_type: str
    calendar: str
    warn_days: list[int]
    due_on: str
    state: str  # as stored: running, paused, met, cancelled or expired (the sweep recorded it)
    effective_state: str  # as of today: a running clock past its date is expired
    days_left: int | None  # counted in the clock's own day type; negative once overdue
    warned_level: int | None
    paused_on: str | None
    closed_on: str | None
    closed_reason: str | None
    owner: str | None
    clause_id: str | None
    restarts: int
    problem: str | None = None  # why the figures could not be recomputed, when they could not
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/commercial_text.py`
- `packages/tl-tui/src/tl_tui/correspondence_text.py`
- `packages/tl-tui/tests/fakes_correspondence.py`
- `docs/tickets/P1-I6/provided/t07b-test_commercial_text.py.txt`
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/commercial_text.py` (complete)
- `packages/tl-tui/tests/test_commercial_text.py` (create: a byte-for-byte copy of the provided file)
- `docs/reports/P1-I6/P1-I6-T07b.md` (create: your report)

## Steps
1. `cp docs/tickets/P1-I6/provided/t07b-test_commercial_text.py.txt packages/tl-tui/tests/test_commercial_text.py` and do not edit it.
2. Replace the body of each function that has a STEPS comment (`bar_text`, `commercial_cells`, `commercial_summary`, `commercial_lines`) by the steps of its comment; delete the STEPS comments, the `STUB` paragraph of the module docstring and the `ruff: noqa` line.
3. Run the commands below and keep their output.

## Acceptance
```
uv run ruff format packages/tl-tui/src/tl_tui/commercial_text.py
uv run pytest packages/tl-tui/tests/test_commercial_text.py -q
just check
uv run pytest packages/tl-tui -q
```
Expected: 8 passed; `just check` clean (ruff, format, pyright, no codegen drift); the package suite passes. These tests do not use a database, so there is no parity run.

## Tests to add
- `packages/tl-tui/tests/test_commercial_text.py` (provided, 8 tests): the twelve cells of a row (a dash for every empty cell, a negative number of days kept, an assessment status with a space); the bar (late first, the state, a dash); the summary (singular and plural, the bars, one part for each currency in the order given, the filters that are on); the panel (figures, hours and days, cost codes by amount or by hours, basis, origin, the assessment with and without a note, clocks; an item without figures or clause shows dashes).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved as `docs/reports/P1-I6/P1-I6-T07b.md` and committed with the ticket. Deviations first. Paste the decisive lines of every acceptance command. Say which lines of the STEPS you found unclear, if any.

## Escalation triggers
- Stop and report *Blocked* if the pasted interface and the repo disagree, a command in *Acceptance* fails for a reason outside *Allowed paths*, or the provided test cannot pass without editing it.
- Stop if you find yourself changing a model, a field, a docstring or a name that this ticket does not own.
- Stop if a STEPS line and the provided test disagree.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
