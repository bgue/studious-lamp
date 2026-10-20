# P1-I6-T09a — The RFI log report

Status: ready
Tier: haiku
Labels: module, reports
Depends on: — (the reads, the models and the test world are in the tree at the branch point)
Branch: `p1/i6-t09a-rfi-log`

## Goal
`reports_technical.py` has the two models of the RFI log (`RfiLogLine`, `RfiLog`) and the helper `_days_between`; `rfi_log` raises `NotImplementedError`. You implement it by its STEPS comment. The log lists the Technical items (RFIs, technical queries, deviation requests) the viewer may read, newest number first, each with its dates, the response time, whether it came in time, whether it is overdue, and the impact flags the raiser expected and the answerer gave, with counts over the lines. It is also the register of the Technical domain: the API, the CLI and the TUI list these lines. One provided test file (16 tests) must pass on SQLite and on Postgres.

## Brief references (pasted)
> **§9 M10, Initial domains, Technical / RFI.** Subtypes: RFI, Technical Query (TQ), Deviation/Concession request. Workflow: Draft → Internal review → Issued → Awaiting response → Answered → (Accepted / Rejected → re-issue) → Closed. Data: question, proposed solution, discipline, required-by, cost/schedule impact flags, answer, answering document revision. "The RFI record is a Technical-domain correspondence item. It feeds AWP constraints (IWP blocked until answered). If the answer flags cost or schedule impact, a rule proposes a linked Commercial item."
>
> **§16 reports, Correspondence.** "Master register (confidentiality-filtered); per-domain registers; responses due/overdue; running clocks and time bars; **RFI log with response times and impact flags**; commercial notice/claim register with values (estimated vs assessed); ..."
>
> **What the log means (decided in the P1-I6 plan).** *Response time* is the calendar days from the latest issue (`item.issued_on`) to the answer (`data.answered_on`). *On time* means answered on or before `required_by` (None until answered or when there is no date). *Overdue* means the item is in the state `Awaiting response` and `required_by` is before today. *Impact flags* are the raiser's own (`potential_*`, before the answer) and the answerer's statement (`cost_impact`, `schedule_impact`, after it). The counts are over the lines the filters kept.
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
`packages/tl-modules/correspondence/src/tl_mod_correspondence/reports_technical.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
"""The RFI log: every Technical item with its response time and its impact flags (brief 9, M10).

"RFI log with response times and impact flags": for each RFI, technical query or deviation request
the log shows when it was raised, issued, needed and answered, how many days the answer took,
whether it came in time, whether it is overdue, and what the raiser expected and the answerer said
about cost and schedule. It is also the register of the Technical domain: the API, the CLI and the
TUI list these lines.

Reads go through ``registry_domain``, which applies the viewer's confidentiality (ADR-0016): an
item the viewer may not read is not a line and is not counted. Nothing here writes. Time comes in
as ``today`` (an ISO date), so a report is a pure function of the ledger and a day.

STUB (P1-I6-T09a): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel
from sqlalchemy import Connection

from tl_mod_correspondence import registry_domain
from tl_mod_correspondence.handlers.common import today as module_today
from tl_mod_correspondence.names import ST_AWAITING_RESPONSE


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


def _days_between(first: str, last: str) -> int:
    return (date.fromisoformat(last) - date.fromisoformat(first)).days


def rfi_log(
    conn: Connection,
    scope: str,
    *,
    subtype: str | None = None,
    state: str | None = None,
    discipline: str | None = None,
    only_open: bool = False,
    only_overdue: bool = False,
    only_impact: bool = False,
    today: str | None = None,
    limit: int = 500,
) -> RfiLog:
    """The log of the Technical items of ``scope`` that the viewer may read, newest number first.

    ``subtype``, ``state`` and ``discipline`` keep the items that have them. ``only_open`` keeps
    the items that are not answered and not Closed or Void. ``only_overdue`` keeps those still
    awaiting a response whose ``required_by`` is before ``today`` (the module's today by default).
    ``only_impact`` keeps those whose answer said yes to cost or to schedule.
    """
    # STEPS
    # 1. `day = today or module_today()` (ISO dates compare as text, so every date test
    #    below is a string comparison).
    # 2. `rows = registry_domain.list_technical(conn, scope, subtype=subtype, state=state,
    #    discipline=discipline, limit=limit)`. The viewer's class filter is applied inside
    #    it: read the items only this way, never with a query of your own, and a row the
    #    viewer may not read is simply not there.
    # 3. For each `row`: `item, data = row.item, row.data`; `answered = data.answered_on
    #    is not None`; `waiting = item.state == ST_AWAITING_RESPONSE`; `late = waiting and
    #    data.required_by is not None and data.required_by < day`.
    # 4. Build the `RfiLogLine`: `id`, `number`, `subject` from `item`;
    #    `subtype=item.subtype or ""`; `discipline` from `data`; `state=item.state`;
    #    `raised_on=item.created_at[:10]`; `issued_on=item.issued_on`; `required_by` and
    #    `answered_on` from `data`; `response_days=_days_between(item.issued_on,
    #    data.answered_on)` when both are not None, else None; `on_time=data.answered_on
    #    <= data.required_by` when both are not None, else None; `overdue=late`;
    #    `days_overdue=_days_between(data.required_by, day)` when `late`, else None;
    #    `potential_cost_impact`, `potential_schedule_impact` from `data`;
    #    `cost_impact=data.answer_cost_impact`,
    #    `schedule_impact=data.answer_schedule_impact`;
    #    `review_decision=data.review_decision`; `confidentiality=item.confidentiality`.
    # 5. Filters, applied to the built line in this order, each with `continue`:
    #    `only_open` skips a line that is `answered` or whose `item.state` is `Closed`;
    #    `only_overdue` skips a line whose `overdue` is false; `only_impact` skips a line
    #    when `"yes"` is neither its `cost_impact` nor its `schedule_impact`. Keep the
    #    others in `lines`, in the order `list_technical` gave them.
    # 6. `times` is the `response_days` of the kept lines that have one. Return
    #    `RfiLog(scope=scope, as_of=day, lines=lines, total=len(lines), answered=<kept
    #    lines with an answered_on>, open=<kept lines with no answered_on whose state is
    #    neither Closed nor Void>, overdue=<kept lines with overdue>, impact_yes=<kept
    #    lines with "yes" as cost_impact or schedule_impact>,
    #    average_response_days=round(sum(times) / len(times), 1) if times else None)`.
    raise NotImplementedError
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/registry_domain.py` (read-only; the dataclasses and the one function you call; abridged):
```python
@dataclass(frozen=True)
class TechnicalData:
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
    answering_revision_id: str | None
    review_decision: str | None
    reviewed_on: str | None
    review_note: str | None

@dataclass(frozen=True)
class TechnicalRow:
    """An RFI, a technical query or a deviation request: the item and its domain data."""

    item: ItemRow
    data: TechnicalData

def list_technical(
    conn: Connection,
    scope: str,
    *,
    subtype: str | None = None,
    state: str | None = None,
    discipline: str | None = None,
    open_only: bool = False,
    include_void: bool = False,
    limit: int = 500,
    offset: int = 0,
) -> list[TechnicalRow]:
    """The Technical items of a scope the viewer may read, newest number first.

    ``open_only`` keeps the items that are not Closed or Void. A void item is left out unless
    ``include_void``.
    """
    ...
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/registry.py` (read-only; the fields of `ItemRow` you use; abridged to the ones named):
```python
@dataclass(frozen=True)
class ItemRow:
    id: str
    number: str
    subject: str
    state: str  # the workflow state; "Draft" for a record that never moved
    subtype: str | None
    issued_on: str | None  # ISO date of the latest issue
    confidentiality: str
    created_at: str  # an ISO timestamp, "2026-10-20T09:00:00.000000Z"
    # ... more fields that this report does not use

```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/common.py` (read-only):
```python
def today() -> str:
    """Today's date, ISO, from ``now``."""
    ...

```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/testing.py` (read-only; what the provided test calls):
```python
class CorrWorld:
    def forge_technical(
        self,
        number: str = "P123-RFI-0001",
        *,
        subject: str = "Beam B12 clashes with line 47",
        state: str = "Draft",   # Draft, Internal review, Issued, Awaiting response, Answered,
        subtype: str = "rfi",   # Accepted, Rejected or Closed
        confidentiality: str = "internal",
        scope: str = PROJECT,
        issued_on: str = "2026-10-20",
        item: dict[str, Any] | None = None,
        answer: dict[str, Any] | None = None,   # overrides the fields of Technical.Answered
        **data: Any,                            # overrides the fields of Technical.Defined
    ) -> str: ...
    def void_draft(self, item_id: str, reason: str = "made in error") -> CommandResult: ...

```

## Context (read these, nothing else)
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/reports_technical.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/registry_domain.py`
- `docs/tickets/P1-I6/provided/t09a-test_reports_technical.py.txt`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/testing.py`
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/reports_technical.py` (complete)
- `packages/tl-modules/correspondence/tests/test_reports_technical.py` (create: a byte-for-byte copy of the provided file)
- `docs/reports/P1-I6/P1-I6-T09a.md` (create: your report)

## Steps
1. `cp docs/tickets/P1-I6/provided/t09a-test_reports_technical.py.txt packages/tl-modules/correspondence/tests/test_reports_technical.py` and do not edit it.
2. Replace the `rfi_log` body by the steps of its STEPS comment, delete the STEPS comments, the `STUB` paragraph of the module docstring and the `ruff: noqa` line.
3. Run the commands below and keep their output.

## Acceptance
```
uv run ruff format packages/tl-modules/correspondence/src/tl_mod_correspondence/reports_technical.py
uv run pytest packages/tl-modules/correspondence/tests/test_reports_technical.py -q
uv run pytest packages/tl-modules/correspondence/tests/test_reports_technical.py -q --adapters sqlite,postgres
just check
uv run pytest packages/tl-modules/correspondence -q
```
Expected: 16 passed on SQLite; 32 passed with both adapters (every case uses the `world` fixture, so each runs twice); `just check` clean (ruff, format, pyright, no codegen drift); the package suite passes. `TL_PG_URL` is exported by the session hook; if Postgres is not running, `sudo pg_ctlcluster 16 main start`.

## Tests to add
- `packages/tl-modules/correspondence/tests/test_reports_technical.py` (provided, 16 tests): the empty log; a line's dates, response time and flags; calendar days from the issue to the answer; `on_time` at, before and after the day needed and with no date; `overdue` and `days_overdue` (only while awaiting a response, and not on the day itself); the order and the limit; the counts and the average (one place, a same-day answer counts as 0); the judgement of the answer; every filter; a voided item; another project; a restricted, a privileged and an unclassed item are neither lines nor counted for a plain viewer, an agent or a controller as the class says.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved as `docs/reports/P1-I6/P1-I6-T09a.md` and committed with the ticket. Deviations first. Paste the decisive lines of every acceptance command. Say which lines of the STEPS you found unclear, if any.

## Escalation triggers
- Stop and report *Blocked* if the pasted interface and the repo disagree, a command in *Acceptance* fails for a reason outside *Allowed paths*, or the provided test cannot pass without editing it.
- Stop if you find yourself changing a model, a field, a docstring or a name that this ticket does not own.
- Stop if a STEPS line and the provided test disagree.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
