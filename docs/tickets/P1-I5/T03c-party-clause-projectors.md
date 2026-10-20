# P1-I5-T03c — ClauseProjector and PartyProjector: clause, party and contact events into their tables

Status: ready
Tier: haiku
Labels: core, module
Depends on: — (the schema, names, `_common.py` and the generated DDL are in the tree at the branch point)
Branch: `p1/i5-t03c-party-clause-projectors`

## Goal
`ClauseProjector` writes `cur_correspondence_contract_clause` from `ContractClause.Defined` and `Retired`; `PartyProjector` writes `cur_correspondence_party` and `cur_correspondence_contact_role` from `Party.Defined`, `ContactAdded`, `ContactEnded` and `Retired`. The classes, `name`, `handles` and `ddl` are written; `apply`, `reset` and `_contact` raise `NotImplementedError`. You implement them by their STEPS comments. One provided test file must pass on SQLite and on Postgres.

## Brief references (pasted)
> **Parties and contacts (M10).** A party is an organisation with a role on the project; its contact roles are the people who act for it, for one domain or for every domain. `Party.Defined` carries the first contacts as a list (positions 1, 2, ... in list order); `ContactAdded` carries one more with the position it takes; a position is never reused. A retired party keeps its contacts.
>
> **Contract clauses.** A clause says where a time bar comes from (contract, clause number, days allowed, who must be told, how). `Retired` clears `is_active`; the row stays.

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
`packages/tl-modules/correspondence/src/tl_mod_correspondence/projectors/clause.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
"""ClauseProjector: the ``ContractClause.*`` events into ``cur_correspondence_contract_clause``.

``Defined`` inserts the clause; ``Retired`` clears ``is_active``. Deterministic. Register it after
``RecordProjector``.

STUB (P1-I5-T03c): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_correspondence.names import CLAUSE_DEFINED, CLAUSE_RETIRED, CLAUSE_TABLE, CLAUSE_VIEW
from tl_mod_correspondence.projectors._common import ddl_for, json_text, touch_record


class ClauseProjector:
    name = "correspondence_clause"
    handles = frozenset({CLAUSE_DEFINED, CLAUSE_RETIRED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(CLAUSE_TABLE, dialect) + ddl_for(CLAUSE_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        # STEPS
        # 1. CLAUSE_DEFINED: INSERT into CLAUSE_TABLE: id (`event.stream_id`), scope
        #    (`event.scope`), contract, clause_number (required keys), time_bar_days,
        #    time_bar_day_type, notice_requirements, service_method, contract_document_id (all
        #    `p.get`), `required_recipients_json` = `json_text(p.get("required_recipients") or [])`,
        #    `domains_json` = `json_text(p.get("domains") or [])`, is_active True (a Python bool),
        #    last_seq.
        # 2. CLAUSE_RETIRED: UPDATE is_active = False (a Python bool) and last_seq WHERE id = :id; a
        #    row count of 0 raises `LookupError(f"no {CLAUSE_TABLE} row for stream
        #    {event.stream_id}")`.
        # 3. Any other event type: `raise ValueError(f"ClauseProjector cannot apply event type:
        #    {event.event_type}")`. After the branches call `touch_record(conn, event)`.
        raise NotImplementedError

    def reset(self, conn: Connection) -> None:
        # STEPS
        # 1. `DELETE FROM` the CLAUSE_TABLE.
        raise NotImplementedError
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/projectors/party.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
"""PartyProjector: the ``Party.*`` events into the party and contact tables.

``Defined`` inserts the party and its first contacts (positions 1, 2, ... in list order);
``ContactAdded`` inserts one more at the position the event states; ``ContactEnded`` clears the
contact's ``is_active``; ``Retired`` clears the party's. The code, the title and the email domains
come from the event as written. Deterministic. Register it after ``RecordProjector``.

STUB (P1-I5-T03c): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_correspondence.names import (
    CONTACT_TABLE,
    PARTY_CONTACT_ADDED,
    PARTY_CONTACT_ENDED,
    PARTY_DEFINED,
    PARTY_RETIRED,
    PARTY_TABLE,
    PARTY_VIEW,
)
from tl_mod_correspondence.projectors._common import ddl_for, json_text, touch_record


class PartyProjector:
    name = "correspondence_party"
    handles = frozenset({PARTY_DEFINED, PARTY_CONTACT_ADDED, PARTY_CONTACT_ENDED, PARTY_RETIRED})

    def ddl(self, dialect: str) -> list[str]:
        return (
            ddl_for(PARTY_TABLE, dialect)
            + ddl_for(CONTACT_TABLE, dialect)
            + ddl_for(PARTY_VIEW, dialect)
        )

    def apply(self, conn: Connection, event: Event) -> None:
        # STEPS
        # 1. `p = event.payload`, `et = event.event_type`. Named parameters; table names from the
        #    constants PARTY_TABLE and CONTACT_TABLE. Booleans are Python bools.
        # 2. PARTY_DEFINED: INSERT into PARTY_TABLE: id (`event.stream_id`), scope (`event.scope`),
        #    code, project_role (required keys), `email_domains_json` =
        #    `json_text(p.get("email_domains") or [])`, is_active True, last_seq. Then, for each
        #    contact of `p.get("contacts") or []` with position 1, 2, ... in list order, call
        #    `self._contact(conn, event, position, contact)`.
        # 3. PARTY_CONTACT_ADDED: `self._contact(conn, event, p["position"], p)` (the event payload
        #    is the contact).
        # 4. PARTY_CONTACT_ENDED: UPDATE CONTACT_TABLE SET is_active False, last_seq WHERE party_id
        #    = `event.stream_id` AND position = `p["position"]`; a row count of 0 raises
        #    `LookupError(f"no contact {p['position']} for party {event.stream_id}")`.
        # 5. PARTY_RETIRED: UPDATE PARTY_TABLE SET is_active False, last_seq WHERE id =
        #    `event.stream_id`; a row count of 0 raises LookupError like the contact case. The
        #    contacts stay.
        # 6. Any other event type: `raise ValueError(f"PartyProjector cannot apply event type:
        #    {et}")`. After the branches call `touch_record(conn, event)`.
        raise NotImplementedError

    @staticmethod
    def _contact(conn: Connection, event: Event, position: int, contact: dict[str, Any]) -> None:
        # STEPS
        # 1. INSERT into CONTACT_TABLE: contact_id = `f"{event.stream_id}:{position:03d}"`, scope
        #    (`event.scope`), party_id (`event.stream_id`), position, name (required:
        #    `contact["name"]`), email, title, domain (`contact.get`), is_authorised =
        #    `bool(contact.get("is_authorised", False))`, is_active True, last_seq (`event.seq`).
        raise NotImplementedError

    def reset(self, conn: Connection) -> None:
        # STEPS
        # 1. `DELETE FROM` CONTACT_TABLE, then PARTY_TABLE.
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

`packages/tl-schema/src/tl_schema/generated/ddl/sqlite/cur_correspondence_contract_clause.sql` (the stub you complete; the whole file):
```sql
CREATE TABLE IF NOT EXISTS cur_correspondence_contract_clause (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  contract TEXT NOT NULL,
  clause_number TEXT NOT NULL,
  time_bar_days INTEGER,
  time_bar_day_type TEXT,
  notice_requirements TEXT,
  required_recipients_json TEXT NOT NULL DEFAULT '{}',
  service_method TEXT,
  contract_document_id TEXT,
  domains_json TEXT NOT NULL DEFAULT '{}',
  is_active INTEGER NOT NULL DEFAULT 1,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_contract_clause_scope_contract ON cur_correspondence_contract_clause (scope, contract);
```

`packages/tl-schema/src/tl_schema/generated/ddl/sqlite/cur_correspondence_party.sql` (the stub you complete; the whole file):
```sql
CREATE TABLE IF NOT EXISTS cur_correspondence_party (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  code TEXT NOT NULL,
  project_role TEXT NOT NULL,
  email_domains_json TEXT NOT NULL DEFAULT '{}',
  is_active INTEGER NOT NULL DEFAULT 1,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_party_scope_role ON cur_correspondence_party (scope, project_role);
```

`packages/tl-schema/src/tl_schema/generated/ddl/sqlite/cur_correspondence_contact_role.sql` (the stub you complete; the whole file):
```sql
CREATE TABLE IF NOT EXISTS cur_correspondence_contact_role (
  contact_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  party_id TEXT NOT NULL,
  position INTEGER NOT NULL,
  name TEXT NOT NULL,
  email TEXT,
  title TEXT,
  domain TEXT,
  is_authorised INTEGER NOT NULL DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 1,
  last_seq INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_contact_role_email ON cur_correspondence_contact_role (scope, email);

CREATE INDEX IF NOT EXISTS ix_cur_correspondence_contact_role_party ON cur_correspondence_contact_role (party_id);
```

## Context (read these, nothing else)
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/projectors/clause.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/projectors/party.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/names.py`
- `packages/tl-schema/src/tl_schema/generated/ddl/sqlite/cur_correspondence_contact_role.sql`
- `docs/tickets/P1-I5/provided/t03c-test_projectors_party_clause.py.txt`
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/projectors/clause.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/projectors/party.py`
- `packages/tl-modules/correspondence/tests/test_projectors_party_clause.py (create: the provided test, byte for byte)`
- `docs/reports/P1-I5/P1-I5-T03c.md` (create: your report; commit it)

## Steps
1. Copy the provided test: `cp docs/tickets/P1-I5/provided/t03c-test_projectors_party_clause.py.txt packages/tl-modules/correspondence/tests/test_projectors_party_clause.py`. Do not edit the copy.
2. Implement `ClauseProjector` and `PartyProjector` (including the helper `_contact`) by their STEPS comments.
3. Delete the `STUB` paragraph of the module docstring, every `# STEPS` comment and the `# ruff: noqa` line at the top of each stub file you completed.
4. Run the acceptance commands, write the report, commit with `P1-I5-T03c: <imperative summary>`.

## Acceptance
```
just check
uv run pytest packages/tl-modules/correspondence/tests/test_projectors_party_clause.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test TL_REQUIRE_POSTGRES=1 uv run pytest packages/tl-modules/correspondence/tests/test_projectors_party_clause.py -q --adapters sqlite,postgres
```
Expected: `just check` clean; 9 passed on SQLite; 18 passed with both adapters (every case runs once per adapter).

## Tests to add
- `packages/tl-modules/correspondence/tests/test_projectors_party_clause.py` is provided; it is the whole test of this ticket. Add no other test file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved to `docs/reports/P1-I5/P1-I5-T03c.md` and committed. State the SQLite count and the both-adapters count you got, and say whether the `STUB` paragraph, the STEPS comments and the `ruff: noqa` line are gone.

## Escalation triggers
- A column the STEPS name does not exist in the DDL pasted above.
- The provided test cannot pass without editing it, a file outside *Allowed paths*, or a pasted interface.
- Two attempts at the same failing test have not passed it.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
