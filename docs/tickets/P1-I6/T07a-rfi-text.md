# P1-I6-T07a — TUI: the text of the RFI log

Status: ready
Tier: haiku
Labels: tui, text
Depends on: — (the client interface, the fake client with its seed, the report models and the helpers are in the tree at the branch point)
Branch: `p1/i6-t07a-rfi-text`

## Goal
`rfi_text.py` holds the column names of the RFI log (`RFI_COLUMNS`) and five functions that raise `NotImplementedError`: `timing_text`, `impact_text`, `rfi_cells`, `rfi_summary` and `rfi_lines`. You implement them by their STEPS comments. They turn the report's lines (`RfiLogLine`, `RfiLog`) and the view of one RFI (`TechnicalView`) into the cells of a table row, the summary line under the table and the panel for the highlighted RFI. The screen (`widgets/domain_screen.py`) is built and calls them. One provided test file must pass.

## Brief references (pasted)
> **§9 M10, Technical / RFI.** An RFI is raised, issued, answered (with the answerer's statement on cost and schedule impact), accepted or rejected, and may lead to a Commercial item. **§16 reports.** "RFI log with response times and impact flags." What the log means (decided in the P1-I6 plan): *response days* are the calendar days from the latest issue to the answer; *on time* means answered on or before the day needed; *overdue* means awaiting a response and past the day needed; the *impact flags* are the raiser's own before the answer and the answerer's statement after it.
>
> **Command, report and model docstrings are the contract.** Do not change a constant, a name, a docstring or a signature in a file you complete; only the function bodies that carry a STEPS comment are yours. The functions are pure: they read the values they are given and decide nothing; the figures (days, totals, late) are the report's and are shown as they come.
>
> The fake client used by the provided test (`seed_domains` in `packages/tl-tui/tests/fakes_correspondence.py`) holds three RFIs; `list_rfis("P123")` returns them in this order as `RfiLogLine`s:
> 
> | Number | State | Discipline | Needed | Answered | Days | on_time | overdue | Answerer: cost / schedule | Raiser: cost / schedule |
> |---|---|---|---|---|---|---|---|---|---|
> | P123-RFI-0001 | Answered | structural | 2026-10-19 | 2026-10-12 | 7 | true | false | yes / no | unknown / unknown |
> | P123-RFI-0002 | Awaiting response | structural | 2026-10-19 | - | - | None | true (1 day) | none / none | unknown / yes |
> | P123-RFI-0003 | Draft | none | none | - | - | None | false | none / none | unknown / unknown |
> 
> `get_rfi` returns the `TechnicalView` of each: 0001 has an answer ("Re-route above the beam."), is escalated to P123-EW-0001 (Draft) and has no clock; 0002 has one clock (`P123-RFI-0002-C01`, effective state `expired`, due 2026-10-19, left -1); 0003 has nothing yet.

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
`packages/tl-tui/src/tl_tui/rfi_text.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
"""What the RFI log shows, as pure functions (P1-I6; brief 9 M10, brief 16).

The rows of the RFI log, its summary line and the panel under it are text built from
``tl_mod_correspondence.reports_technical`` and ``views_domain`` values and nothing else, so the
tests check them without a terminal. The figures (response days, overdue, on time) are the
report's: this module shows them as they come and decides nothing.

STUB (P1-I6-T07a): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

from tl_mod_correspondence.reports_technical import RfiLog, RfiLogLine
from tl_mod_correspondence.views_domain import TechnicalView

from tl_tui.correspondence_text import clock_line

RFI_COLUMNS = (
    "Number",
    "State",
    "Kind",
    "Disc",
    "Raised",
    "Needed",
    "Answered",
    "Days",
    "Timing",
    "Impact",
    "Subject",
)


def timing_text(line: RfiLogLine) -> str:
    """``overdue 3d`` (still waiting, past the date needed), ``late`` or ``on time`` (answered),
    ``-`` otherwise."""
    # STEPS
    # 1. If `line.overdue` is true return `f"overdue {line.days_overdue}d"`.
    # 2. Otherwise, if `line.on_time is None`, return `"-"`.
    # 3. Otherwise return `"on time"` when `line.on_time` is true and `"late"` when it is
    #    false.
    raise NotImplementedError


def impact_text(line: RfiLogLine) -> str:
    """``C:yes S:no`` from the answerer's statement; before an answer the raiser's own flags, in
    brackets: ``C:(unknown) S:(yes)``."""

    # STEPS
    # 1. Define a small inner function `one(answered: str | None, expected: str) -> str`
    #    that returns `answered` when it is not `None` and `f"({expected})"` otherwise.
    # 2. `cost = one(line.cost_impact, line.potential_cost_impact)` and `schedule =
    #    one(line.schedule_impact, line.potential_schedule_impact)`.
    # 3. Return `f"C:{cost} S:{schedule}"`.
    raise NotImplementedError


def rfi_cells(line: RfiLogLine) -> tuple[str, ...]:
    """The eleven cells of a log row, in the order of ``RFI_COLUMNS``."""
    # STEPS
    # 1. Return a tuple of exactly eleven strings, in the order of `RFI_COLUMNS`:
    #    `line.number`, `line.state`, `line.subtype`, `line.discipline or "-"`,
    #    `line.raised_on`, `line.required_by or "-"`, `line.answered_on or "-"`, `"-" if
    #    line.response_days is None else str(line.response_days)` (0 days is `"0"`, not a
    #    dash), `timing_text(line)`, `impact_text(line)`, `line.subject`.
    raise NotImplementedError


def rfi_summary(
    log: RfiLog, *, only_open: bool = False, only_overdue: bool = False, only_impact: bool = False
) -> str:
    """``3 items | answered 1 | open 2 | overdue 1 | impact yes 1 | average answer 6.0 days``, and
    ``| filter: open, overdue`` when a filter is on."""
    # STEPS
    # 1. `parts` is a list of strings, in this order: `f"{log.total} item{'s' if log.total
    #    != 1 else ''}"`, `f"answered {log.answered}"`, `f"open {log.open}"`, `f"overdue
    #    {log.overdue}"`, `f"impact yes {log.impact_yes}"`.
    # 2. When `log.average_response_days is not None` (0.0 counts) append `f"average
    #    answer {log.average_response_days:.1f} days"`.
    # 3. `filters` is the list of the names `"open"`, `"overdue"`, `"impact"` whose flag
    #    (`only_open`, `only_overdue`, `only_impact`) is true, in that order. When it is
    #    not empty append `"filter: " + ", ".join(filters)`.
    # 4. Return `" | ".join(parts)`.
    raise NotImplementedError


def rfi_lines(view: TechnicalView) -> list[str]:
    """The panel under the log: the highlighted RFI, its answer, its review and what it led to."""
    # STEPS
    # 1. Start `lines` with these six strings: `f"{view.number}  {view.state}
    #    {view.subtype or '-'}  class {view.confidentiality}"`; `f"subject:
    #    {view.subject}"`; `f"question: {view.question}"`; `f"proposed:
    #    {view.proposed_solution or '-'}"`; `f"discipline {view.discipline or '-'}  needed
    #    by {view.required_by or '-'}  issued {view.issued_on or '-'}"` (two spaces
    #    between the parts); `f"raiser expects: cost {view.potential_cost_impact},
    #    schedule {view.potential_schedule_impact}"`.
    # 2. When `view.answered_on is not None` append `f"answer ({view.answered_on}):
    #    {view.answer or '-'}"` and then `f"answerer says: cost {view.answer_cost_impact
    #    or '-'}, schedule {view.answer_schedule_impact or '-'}"`.
    # 3. When `view.answer_item_number` is set append `f"answered by item
    #    {view.answer_item_number}"`.
    # 4. When `view.review_decision` is set append `f"reviewed {view.reviewed_on or '-'}:
    #    {view.review_decision}"` followed, only when `view.review_note` is set, by `f"
    #    ({view.review_note})"` (one line).
    # 5. When `view.escalations` is not empty append `"escalated to: " + ",
    #    ".join(f"{e.number} ({e.state})" for e in view.escalations)`.
    # 6. When `view.clocks` is not empty append `"clocks:"` and then, for each clock, `f"
    #    {clock_line(c)}"` (two spaces).
    # 7. Return `lines`.
    raise NotImplementedError
```

`packages/tl-tui/src/tl_tui/correspondence_text.py` (read-only; one clock as a line; abridged to the names used):
```python
def clock_line(clock: ClockView) -> str:
    """One clock under an item: ``C01 running due 2026-11-02 left 14 (14 calendar days) Reply``."""
    ...
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/reports_technical.py` (read-only; the two models):
```python
class RfiLogLine(BaseModel):
    """One Technical item as the log shows it. Dates are ISO days; ``None`` means not yet."""

    id: str
    number: str
    subject: str
    subtype: str
    discipline: str | None
    state: str
    raised_on: str  # the day the record was made
    issued_on: str | None
    required_by: str | None
    answered_on: str | None
    response_days: int | None  # calendar days from the latest issue to the answer
    on_time: bool | None  # answered on or before required_by; None until answered or no date
    overdue: bool  # still awaiting a response and required_by is before today
    days_overdue: int | None
    potential_cost_impact: str
    potential_schedule_impact: str
    cost_impact: str | None  # the answerer's statement
    schedule_impact: str | None
    review_decision: str | None
    confidentiality: str

class RfiLog(BaseModel):
    """The lines and the counts over them (the counts follow the filters, not the whole scope)."""

    scope: str
    as_of: str
    lines: list[RfiLogLine]
    total: int
    answered: int
    open: int  # not answered, and neither Closed nor Void
    overdue: int
    impact_yes: int  # the answerer said yes to cost or to schedule
    average_response_days: float | None  # over the answered lines, one decimal place
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/views_domain.py` (read-only; abridged to the names used):
```python
class EscalationView(BaseModel):
    """A Commercial item raised from an RFI, as the reader of the RFI sees it: only if readable."""

    id: str
    number: str
    subtype: str
    state: str

class TechnicalView(views.ItemView):
    question: str
    proposed_solution: str | None
    discipline: str | None
    required_by: str | None
    potential_cost_impact: str
    potential_schedule_impact: str
    answer: str | None
    answered_on: str | None
    answer_cost_impact: str | None
    answer_schedule_impact: str | None
    answer_item_id: str | None
    answer_item_number: str | None
    answering_revision_id: str | None
    review_decision: str | None
    reviewed_on: str | None
    review_note: str | None
    escalations: list[EscalationView] = []
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
- `packages/tl-tui/src/tl_tui/rfi_text.py`
- `packages/tl-tui/src/tl_tui/correspondence_text.py`
- `packages/tl-tui/tests/fakes_correspondence.py`
- `docs/tickets/P1-I6/provided/t07a-test_rfi_text.py.txt`
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/rfi_text.py` (complete)
- `packages/tl-tui/tests/test_rfi_text.py` (create: a byte-for-byte copy of the provided file)
- `docs/reports/P1-I6/P1-I6-T07a.md` (create: your report)

## Steps
1. `cp docs/tickets/P1-I6/provided/t07a-test_rfi_text.py.txt packages/tl-tui/tests/test_rfi_text.py` and do not edit it.
2. Replace the body of each function that has a STEPS comment (`timing_text`, `impact_text`, `rfi_cells`, `rfi_summary`, `rfi_lines`) by the steps of its comment; delete the STEPS comments, the `STUB` paragraph of the module docstring and the `ruff: noqa` line.
3. Run the commands below and keep their output.

## Acceptance
```
uv run ruff format packages/tl-tui/src/tl_tui/rfi_text.py
uv run pytest packages/tl-tui/tests/test_rfi_text.py -q
just check
uv run pytest packages/tl-tui -q
```
Expected: 9 passed; `just check` clean (ruff, format, pyright, no codegen drift); the package suite passes. These tests do not use a database, so there is no parity run.

## Tests to add
- `packages/tl-tui/tests/test_rfi_text.py` (provided, 9 tests): the eleven cells of a row (a dash for what is not there, `0` days is not a dash); the timing (overdue wins over the answer's timing, late, on time, none); the impact (the answerer's statement, or the raiser's flag in brackets, per side); the summary (plural, the average with one place and `0.0` shown, the filters that are on, in order); the panel (question, proposal, answer and statement, the item that carried the answer, the review with and without a note, escalations, clocks; a draft with dashes).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved as `docs/reports/P1-I6/P1-I6-T07a.md` and committed with the ticket. Deviations first. Paste the decisive lines of every acceptance command. Say which lines of the STEPS you found unclear, if any.

## Escalation triggers
- Stop and report *Blocked* if the pasted interface and the repo disagree, a command in *Acceptance* fails for a reason outside *Allowed paths*, or the provided test cannot pass without editing it.
- Stop if you find yourself changing a model, a field, a docstring or a name that this ticket does not own.
- Stop if a STEPS line and the provided test disagree.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
