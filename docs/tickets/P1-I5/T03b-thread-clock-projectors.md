# P1-I5-T03b — ThreadProjector and ClockProjector: thread and response-clock events into their tables

Status: ready
Tier: haiku
Labels: core, module
Depends on: — (the schema, names, `_common.py` and the generated DDL are in the tree at the branch point)
Branch: `p1/i5-t03b-thread-clock-projectors`

## Goal
`ThreadProjector` writes `cur_correspondence_correspondence_thread` from the three `CorrespondenceThread.*` events and `ClockProjector` writes `cur_correspondence_response_clock` from the eight `ResponseClock.*` events. The classes, `name`, `handles` and `ddl` are written; `apply` and `reset` of both raise `NotImplementedError`. You implement them by their STEPS comments. One provided test file must pass on SQLite and on Postgres.

## Brief references (pasted)
> **Clock events (the clock engine, `tl_mod_correspondence.clocks`).** The projector does no date arithmetic. `ResponseClock.Started`, `Resumed` and `Restarted` carry the due date the engine computed; the row copies it. `Paused` records a pause (the days of the pause do not count: the engine moves the due date at `Resumed`), `Met` and `Cancelled` close the clock, `Warned` records the smallest warning threshold raised, `Expired` marks a running clock past its due date. A `Restarted` reopens a clock that was met, cancelled or expired and forgets its warnings.
>
> **Thread events.** A thread is opened by its first item (`Defined`, item count 1), counts further items (`ItemAdded`; `last_item_on` only moves forward) and is opened or closed (`StateChanged`).

### Learnings that apply
> **L-P1-I1-6.** A parity run's count is not the SQLite count twice: a case that does not use the `db`/`new_db`/`engine` fixtures runs once. Every case of this ticket's test uses them, so the counts below are exact.
>
> **L-P1-I5-1.** Postgres cannot infer the type of a bare parameter in `CASE WHEN :p IS NOT NULL ...` (`could not determine data type of parameter $1`), and a Python bool is the portable value for a boolean column. Compute such choices in Python; run the test on both adapters before you report.
>
> **L-P0-I5-A8.** pg8000 re-raises every SQLSTATE class 23 error as `IntegrityError`; `text()` statements with named parameters behave the same on both adapters.

> **L-P0-I1-6.** ruff's `E501` applies to docstrings and comments at 100 columns, and pyright strict flags `@contextmanager` functions annotated `Iterator[X]`. Wrap prose.
>
> **L-P0-I6C-8 / L-P1-I0B-3.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain, and never `pkill -f`: kill only a PID you started.
>
> **L-P1-I3B-6.** Copy the provided test byte for byte (`cp`), run `ruff` and `pyright` on the tree, and do not edit the copy: if it cannot pass, stop and report *Blocked*.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-modules/correspondence/src/tl_mod_correspondence/projectors/thread.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
"""ThreadProjector: the ``CorrespondenceThread.*`` events into the thread table.

``Defined`` inserts the thread with its first item; ``ItemAdded`` counts another item and moves
``last_item_on`` forward (never back); ``StateChanged`` opens or closes it. Deterministic.
Register it after ``RecordProjector``.

STUB (P1-I5-T03b): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_correspondence.names import (
    THREAD_DEFINED,
    THREAD_ITEM_ADDED,
    THREAD_STATE_CHANGED,
    THREAD_TABLE,
    THREAD_VIEW,
)
from tl_mod_correspondence.projectors._common import ddl_for, touch_record


class ThreadProjector:
    name = "correspondence_thread"
    handles = frozenset({THREAD_DEFINED, THREAD_ITEM_ADDED, THREAD_STATE_CHANGED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(THREAD_TABLE, dialect) + ddl_for(THREAD_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        # STEPS
        # 1. `payload = event.payload`; `base = {"id": event.stream_id, "last_seq": event.seq}`.
        #    Named parameters, table name from the constant THREAD_TABLE.
        # 2. THREAD_DEFINED: INSERT into THREAD_TABLE: id, scope (`event.scope`), number,
        #    subject_key (required keys), domain (`payload.get`), state 'open', governing_item_id =
        #    `payload["governing_item_id"]`, item_count 1, last_item_on = `payload.get("item_on")`,
        #    last_seq.
        # 3. THREAD_ITEM_ADDED: SELECT last_item_on FROM THREAD_TABLE WHERE id = :id; no row means
        #    `raise LookupError(f"no {THREAD_TABLE} row for stream {event.stream_id}")`. Choose the
        #    newest date in Python: `item_on = payload.get("item_on")`; the new value is `item_on`
        #    when it is not None and (the current value is None or `item_on` is later: ISO dates
        #    compare as strings), else the current value. Postgres cannot infer the type of a bare
        #    parameter in a CASE expression, so do not do this in SQL. Then UPDATE item_count =
        #    item_count + 1, last_item_on = the chosen value, last_seq.
        # 4. THREAD_STATE_CHANGED: UPDATE state = `payload["state"]` and last_seq; check the row
        #    count with `self._require`.
        # 5. Any other event type: `raise ValueError(f"ThreadProjector cannot apply event type:
        #    {event.event_type}")`. After the branches call `touch_record(conn, event)`.
        raise NotImplementedError

    @staticmethod
    def _require(rowcount: int, event: Event) -> None:
        if rowcount == 0:
            raise LookupError(f"no {THREAD_TABLE} row for stream {event.stream_id}")

    def reset(self, conn: Connection) -> None:
        # STEPS
        # 1. `DELETE FROM` the THREAD_TABLE.
        raise NotImplementedError
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/projectors/clock.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
"""ClockProjector: the ``ResponseClock.*`` events into ``cur_correspondence_response_clock``.

The projector does no arithmetic. ``Started``, ``Resumed`` and ``Restarted`` carry the due date the
clock engine computed (``tl_mod_correspondence.clocks``); the row copies it. ``Paused`` records the
pause, ``Met`` and ``Cancelled`` close the clock, ``Warned`` records the warning threshold crossed
and ``Expired`` marks a running clock past its date. Deterministic. Register it after
``RecordProjector``.

STUB (P1-I5-T03b): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_correspondence.names import (
    CLOCK_CANCELLED,
    CLOCK_EXPIRED,
    CLOCK_MET,
    CLOCK_PAUSED,
    CLOCK_RESTARTED,
    CLOCK_RESUMED,
    CLOCK_STARTED,
    CLOCK_TABLE,
    CLOCK_VIEW,
    CLOCK_WARNED,
)
from tl_mod_correspondence.projectors._common import ddl_for, json_text, touch_record


class ClockProjector:
    name = "correspondence_clock"
    handles = frozenset(
        {
            CLOCK_STARTED,
            CLOCK_PAUSED,
            CLOCK_RESUMED,
            CLOCK_RESTARTED,
            CLOCK_MET,
            CLOCK_CANCELLED,
            CLOCK_WARNED,
            CLOCK_EXPIRED,
        }
    )

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(CLOCK_TABLE, dialect) + ddl_for(CLOCK_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        # STEPS
        # 1. `p = event.payload`, `et = event.event_type`, `base = {"id": event.stream_id,
        #    "last_seq": event.seq}`. Named parameters, table name from the constant CLOCK_TABLE.
        #    The projector does no date arithmetic: due dates come from the events.
        # 2. CLOCK_STARTED: INSERT into CLOCK_TABLE: id, scope (`event.scope`), item_id,
        #    item_number, label, kind, start_on, duration_days, day_type, calendar, due_on (all
        #    required keys), `warn_days_json` = `json_text(p.get("warn_days") or [])`, owner and
        #    clause_id (`p.get`), state 'running', restarts 0, last_seq.
        # 3. CLOCK_PAUSED: UPDATE state 'paused', paused_on = `p["on"]`, pause_reason =
        #    `p["reason"]`, last_seq.
        # 4. CLOCK_RESUMED: UPDATE state 'running', due_on = `p["due_on"]`, paused_on NULL,
        #    pause_reason NULL, last_seq.
        # 5. CLOCK_RESTARTED: UPDATE state 'running', start_on = `p["start_on"]`, due_on =
        #    `p["due_on"]`, paused_on NULL, pause_reason NULL, closed_on NULL, closed_reason NULL,
        #    warned_level NULL, restarts = restarts + 1, last_seq. (A restart reopens a clock that
        #    was met, cancelled or expired.)
        # 6. CLOCK_MET: UPDATE state 'met', closed_on = `p["on"]`, closed_reason = `p.get("reason")
        #    or p.get("response_id")`, paused_on NULL, pause_reason NULL, last_seq.
        # 7. CLOCK_CANCELLED: UPDATE state 'cancelled', closed_on = `p["on"]`, closed_reason =
        #    `p["reason"]`, paused_on NULL, pause_reason NULL, last_seq. (Use one shared statement
        #    with a `:state` parameter for met and cancelled if you like.)
        # 8. CLOCK_WARNED: UPDATE warned_level = `p["level"]` and last_seq.
        # 9. CLOCK_EXPIRED: UPDATE state 'expired' and last_seq (the due date and closed_on stay).
        # 10. Any other event type: `raise ValueError(f"ClockProjector cannot apply event type:
        #    {et}")`. Every UPDATE branch checks its row count with `self._require(rowcount,
        #    event)`. After the branches call `touch_record(conn, event)`.
        raise NotImplementedError

    @staticmethod
    def _require(rowcount: int, event: Event) -> None:
        if rowcount == 0:
            raise LookupError(f"no {CLOCK_TABLE} row for stream {event.stream_id}")

    def reset(self, conn: Connection) -> None:
        # STEPS
        # 1. `DELETE FROM` the CLOCK_TABLE.
        raise NotImplementedError
```

`tl_core.ledger.Event` (read-only; the fields a projector uses):
```python
class Event(BaseModel):
    event_type: str          # "Correspondence.Defined"
    payload: dict[str, Any]
    seq: int                 # ledger sequence; goes into the row's last_seq
    stream_id: str           # the record id (cur_core_record.id)
    scope: str               # "project:P123"
    actor: str               # "user:amy"
    recorded_at: datetime
```

`tl_mod_correspondence/projectors/_common.py` (read-only):
```python
from tl_mod_engineering.projectors._common import ddl_for, json_text, touch_record
# json_text(value) -> canonical JSON text (sorted keys, no spaces)
# touch_record(conn, event) -> moves cur_core_record.version/last_seq/updated_at; raises
#   LookupError when the stream has no envelope row. Every projector calls it last.
```

`packages/tl-schema/src/tl_schema/generated/ddl/sqlite/cur_correspondence_correspondence_thread.sql` (the stub you complete; the whole file):
```sql
CREATE TABLE IF NOT EXISTS cur_correspondence_correspondence_thread (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  number TEXT NOT NULL,
  subject_key TEXT NOT NULL,
  domain TEXT,
  state TEXT NOT NULL DEFAULT 'open',
  governing_item_id TEXT,
  item_count INTEGER NOT NULL DEFAULT 0,
  last_item_on TEXT,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_thread_scope_state ON cur_correspondence_correspondence_thread (scope, state);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_correspondence_thread_scope_subject ON cur_correspondence_correspondence_thread (scope, subject_key);
```

`packages/tl-schema/src/tl_schema/generated/ddl/sqlite/cur_correspondence_response_clock.sql` (the stub you complete; the whole file):
```sql
CREATE TABLE IF NOT EXISTS cur_correspondence_response_clock (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  item_id TEXT NOT NULL,
  item_number TEXT NOT NULL,
  label TEXT NOT NULL,
  kind TEXT NOT NULL,
  start_on TEXT NOT NULL,
  duration_days INTEGER NOT NULL,
  day_type TEXT NOT NULL,
  calendar TEXT NOT NULL,
  warn_days_json TEXT NOT NULL DEFAULT '{}',
  due_on TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'running',
  paused_on TEXT,
  pause_reason TEXT,
  closed_on TEXT,
  closed_reason TEXT,
  warned_level INTEGER,
  owner TEXT,
  clause_id TEXT,
  restarts INTEGER NOT NULL DEFAULT 0,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_response_clock_clause ON cur_correspondence_response_clock (clause_id);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_response_clock_item ON cur_correspondence_response_clock (item_id);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_response_clock_scope_state_due ON cur_correspondence_response_clock (scope, state, due_on);
```

## Context (read these, nothing else)
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/projectors/thread.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/projectors/clock.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/names.py`
- `packages/tl-schema/src/tl_schema/generated/ddl/sqlite/cur_correspondence_response_clock.sql`
- `docs/tickets/P1-I5/provided/t03b-test_projectors_thread_clock.py.txt`
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/projectors/thread.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/projectors/clock.py`
- `packages/tl-modules/correspondence/tests/test_projectors_thread_clock.py (create: the provided test, byte for byte)`
- `docs/reports/P1-I5/P1-I5-T03b.md` (create: your report; commit it)

## Steps
1. Copy the provided test: `cp docs/tickets/P1-I5/provided/t03b-test_projectors_thread_clock.py.txt packages/tl-modules/correspondence/tests/test_projectors_thread_clock.py`. Do not edit the copy.
2. Implement `ThreadProjector` and `ClockProjector` (`apply` and `reset` of each) by their STEPS comments.
3. Delete the `STUB` paragraph of the module docstring, every `# STEPS` comment and the `# ruff: noqa` line at the top of each stub file you completed.
4. Run the acceptance commands, write the report, commit with `P1-I5-T03b: <imperative summary>`.

## Acceptance
```
just check
uv run pytest packages/tl-modules/correspondence/tests/test_projectors_thread_clock.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test TL_REQUIRE_POSTGRES=1 uv run pytest packages/tl-modules/correspondence/tests/test_projectors_thread_clock.py -q --adapters sqlite,postgres
```
Expected: `just check` clean; 12 passed on SQLite; 24 passed with both adapters (every case runs once per adapter).

## Tests to add
- `packages/tl-modules/correspondence/tests/test_projectors_thread_clock.py` is provided; it is the whole test of this ticket. Add no other test file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved to `docs/reports/P1-I5/P1-I5-T03b.md` and committed. State the SQLite count and the both-adapters count you got, and say whether the `STUB` paragraph, the STEPS comments and the `ruff: noqa` line are gone.

## Escalation triggers
- A column the STEPS name does not exist in the DDL pasted above.
- The provided test cannot pass without editing it, a file outside *Allowed paths*, or a pasted interface.
- Two attempts at the same failing test have not passed it.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
