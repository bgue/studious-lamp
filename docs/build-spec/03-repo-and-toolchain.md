# Build spec 03 — Repository, toolchain, and Phase 0 core interfaces

## 1. Layout

A `uv` workspace monorepo (§14), one package per concern, so tickets have clean *Allowed paths*.

```
pyproject.toml            uv workspace root; shared tool config (ruff, pyright, pytest)
justfile                  the only command interface
schema/
  core/                   LinkML: record.yaml, ledger.yaml, links.yaml, psets.yaml, files.yaml,
                          workflow.yaml, feed.yaml, integration.yaml, settings.yaml
  modules/<m>/            Phase 1+: documents.yaml, engineering.yaml, …
  fixtures/               sample company/project packages (co.acme.engineering, x.P123, prj.P123)
packages/
  tl-schema/              schema runtime: package loader, SchemaView merge, effective schema,
                          generators (ddl, forms, mcp), generated/ (committed)
  tl-core/                ledger, uow, projections, links, psets, numbering, workflow, files,
                          feed, settings, auth, query language, services (command/query handlers)
  tl-adapters/            sqlite/, postgres/, objectstore/ (minio/s3), queue/, bus/
  tl-api/                 FastAPI app, ws/sse, webhooks (outbox, delivery), inbound
  tl-mcp/                 MCP server (tools, resources), MCP client glue, dev MCP server
  tl-tui/                 Textual app shell, widgets, screens, client interface (embedded/remote)
  tl-cli/                 `tl` command (typer)
  tl-sim/                 simulator orchestrator and actors (Phase 0 inc 6)
  tl-lake/                DuckLake sync, marts (Phase 0 inc 7)
  tl-modules/<m>/         Phase 1+: handlers, projections, workflows, reports, mcp, tui per module
tests/                    cross-package: parity/, e2e/, property/
dev/
  docker-compose.yml      MinIO (and Postgres for parity runs)
  seed/                   synthetic project generator inputs
  demos/<increment-id>.sh demo scripts wired to `just demo`
docs/                     brief, build spec, tickets, reports, ADRs, templates
```

Package import names: `tl_schema`, `tl_core`, `tl_adapters`, `tl_api`, `tl_mcp`, `tl_tui`, `tl_cli`, `tl_sim`, `tl_lake`.

## 2. Toolchain

| Tool | Version / note |
|---|---|
| Python | 3.12 (pin in `.python-version`) |
| `uv` | workspace, lockfile committed |
| `ruff` | lint + format; config at root |
| `pyright` | `strict` for `tl_core`, `tl_schema`, `tl_adapters`; `standard` elsewhere |
| `pytest` + `hypothesis` | property tests for projections, numbering, sync |
| `textual-dev` | snapshot tests (`pytest-textual-snapshot`) |
| `linkml`, `linkml-runtime` | generators and `SchemaView` |
| `pydantic` v2, `jsonschema` | validation |
| `sqlalchemy` 2.x Core | data access; no ORM models |
| `typer` | CLI |
| `python-ulid` | IDs |
| `structlog` | logging |
| Docker | MinIO, Postgres for parity |

Dependencies are added only by a ticket line that names the package and why.

## 3. `just` recipes

| Recipe | Does |
|---|---|
| `just gen` | Runs every generator from `schema/` into `packages/tl-schema/src/tl_schema/generated/` |
| `just check` | `ruff check`, `ruff format --check`, `pyright`, codegen drift (`just gen` then `git diff --exit-code` on generated/) |
| `just test` | `pytest` on SQLite |
| `just test-parity` | `pytest tests/parity -p sqlite` and `-p postgres` (needs `just dev up`) |
| `just test-tui` | snapshot tests |
| `just seed [scale]` | synthetic project into the dev ledger |
| `just serve` | API + workers on the dev ledger |
| `just tui` | TUI in embedded mode against the dev ledger |
| `just rebuild-projections [type]` | shadow rebuild from the ledger |
| `just dev up` / `just dev down` | docker compose (MinIO, Postgres) and a fresh dev ledger |
| `just demo <increment-id>` | runs `dev/demos/<increment-id>.sh` |

## 4. Generated-code policy

- Generated artefacts live only under `packages/tl-schema/src/tl_schema/generated/` and are committed.
- `just check` fails if `just gen` produces a diff. This is the codegen drift gate (§25.4).
- Generators are deterministic: sorted keys, no timestamps, fixed tool versions.
- A ticket that changes a generator must include the regenerated output in the same PR.

## 5. Naming

| Thing | Convention | Example |
|---|---|---|
| Record type | `<module>.<Class>` | `core.Record` (Phase 0 generic), `piping.Weld` |
| Event type | `<Class>.<PastTenseVerb>` | `Record.Created`, `Pset.ValuesSet`, `Link.Added` |
| Command | `<Verb><Class>` | `CreateRecord`, `SetPsetValues`, `AddLink`, `TransitionWorkflow` |
| Current-state table | `cur_<module>_<class>` | `cur_core_record` |
| IDs | ULID strings | |
| Scope | `company` or `project:<id>` | `project:P123` |
| Source | `tui`, `api`, `mcp:<agent>`, `cli`, `import:<job>`, `sim:<run>` | |

## 6. Dialect isolation

- `tl_core` sees only the `Ledger`, `UnitOfWork`, `ProjectionStore`, `ObjectStore`, `Bus`, `Queue` Protocols.
- `tl_adapters.sqlite` and `tl_adapters.postgres` implement them. Any SQL that differs by dialect lives there, and only there.
- The parity suite (`tests/parity/`) runs every adapter test against both and is the gate for Postgres (§15).

## 7. Phase 0 core interfaces

These are the contracts supervisors paste into tickets. They are the first things built in increment 1 (ticket T05) and are frozen for Phase 0 except by an orchestrator ADR. Pydantic models here are hand-written in increment 1 and replaced by LinkML-generated ones in increment 2 (same field names, so handlers do not change).

```python
# packages/tl-core/src/tl_core/ledger/types.py
from __future__ import annotations
from datetime import datetime
from typing import Any, Protocol, Sequence
from pydantic import BaseModel

class NewEvent(BaseModel):
    """What a command handler emits. The ledger fills seq, stream_version, hashes, recorded_at."""
    event_type: str                 # e.g. "Record.Created"
    schema_version: int = 1
    payload: dict[str, Any]
    effective_at: datetime | None = None   # defaults to recorded_at

class Event(NewEvent):
    seq: int
    event_id: str                   # ULID
    stream_id: str
    stream_type: str
    stream_version: int
    scope: str                      # "company" | "project:<id>"
    actor: str                      # "user:<id>" | "svc:<name>" | "agent:<id>" (+ on_behalf_of in payload)
    recorded_at: datetime
    effective_at: datetime
    correlation_id: str
    causation_id: str | None
    source: str
    prev_hash: str | None
    hash: str

class AppendResult(BaseModel):
    events: list[Event]
    new_version: int
    last_seq: int

class ConcurrencyError(Exception):
    """expected_version did not match the stream's current version."""

class Ledger(Protocol):
    def append(
        self,
        *,
        stream_id: str,
        stream_type: str,
        scope: str,
        expected_version: int,          # 0 for a new stream
        events: Sequence[NewEvent],
        actor: str,
        source: str,
        correlation_id: str,
        causation_id: str | None = None,
    ) -> AppendResult: ...
    def read_stream(self, stream_id: str, *, from_version: int = 1) -> list[Event]: ...
    def read_after(self, seq: int, *, scope: str | None = None, limit: int = 1000) -> list[Event]: ...
    def head_seq(self) -> int: ...
    def stream_version(self, stream_id: str) -> int: ...   # 0 if absent
```

```python
# packages/tl-core/src/tl_core/ledger/hashing.py
def event_hash(prev_hash: str | None, event_id: str, stream_id: str, stream_version: int,
               event_type: str, payload_canonical_json: str, recorded_at_iso: str) -> str:
    """SHA-256 hex over the concatenation with '\n' separators; prev_hash '' when None.
    Chain is per scope: prev_hash is the hash of the previous event in the same scope."""
```

```python
# packages/tl-core/src/tl_core/projection/types.py
from typing import Protocol, Iterable
from sqlalchemy import Connection

class Projector(Protocol):
    name: str
    handles: frozenset[str]                      # event types
    def ddl(self, dialect: str) -> list[str]: ...  # idempotent CREATE statements (generated)
    def apply(self, conn: Connection, event: "Event") -> None: ...
    def reset(self, conn: Connection) -> None: ...

class ProjectorRegistry(Protocol):
    def for_event(self, event_type: str) -> Iterable[Projector]: ...
    def all(self) -> Iterable[Projector]: ...
```

```python
# packages/tl-core/src/tl_core/uow.py
class UnitOfWork(Protocol):
    """One transaction: ledger append + inline projectors + outbox rows, then bus publish on commit."""
    ledger: Ledger
    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, *exc) -> None: ...
    def append(self, **kwargs) -> AppendResult: ...   # same signature as Ledger.append; also runs projectors
    def conn(self) -> Connection: ...
```

```python
# packages/tl-core/src/tl_core/bus.py
class Bus(Protocol):
    def publish(self, events: Sequence[Event]) -> None: ...
    def subscribe(self, callback: Callable[[Event], None], *, after_seq: int | None = None,
                  scope: str | None = None, event_types: Sequence[str] | None = None) -> Subscription: ...
```

```python
# packages/tl-core/src/tl_core/services/commands.py
class Command(BaseModel):
    actor: str
    source: str
    scope: str
    correlation_id: str | None = None
    causation_id: str | None = None
    idempotency_key: str | None = None

class CreateRecord(Command):
    record_type: str            # Phase 0: "core.Record"
    title: str
    description: str | None = None
    key: str | None = None      # None → numbering service (inc 3); inc 1 requires an explicit key
    psets: dict[str, Any] = {}

class CommandResult(BaseModel):
    stream_id: str
    key: str | None
    version: int
    events: list[Event]

def handle_create_record(uow: UnitOfWork, cmd: CreateRecord) -> CommandResult: ...
```

```python
# packages/tl-core/src/tl_core/files/types.py  (increment 4)
class ObjectStore(Protocol):
    def put(self, key: str, data: BinaryIO, *, size: int, sha256: str, content_type: str) -> None: ...
    def get(self, key: str) -> BinaryIO: ...
    def exists(self, key: str) -> bool: ...
    def presign_put(self, key: str, *, expires_s: int) -> str: ...
    def presign_get(self, key: str, *, expires_s: int) -> str: ...
```

## 8. Phase 0 event catalog (initial)

Payload fields are the minimum; LinkML in `schema/core/ledger.yaml` is authoritative from increment 2.

| Event type | Payload | Introduced |
|---|---|---|
| `Record.Created` | `record_type, key, title, description, psets{}` | I1 |
| `Record.Updated` | `changes{field: [old, new]}` | I1 |
| `Record.Voided` | `reason` | I1 |
| `Record.Corrected` | `changes{}, reason` | I1 |
| `Pset.ValuesSet` | `pset, layer, values{}, effective_schema_hash` | I2 |
| `Link.Suggested / Added / Accepted / Declined / Repinned / Verified / Flagged / Retracted` | `link_id, from_ref, to_ref, relation, pin, source, confidence, note, reason` | I3 |
| `Workflow.Transitioned` | `from_state, to_state, transition, guards_evaluated[], signature?` | I3 |
| `Numbering.Allocated` | `pattern, key, sequence` | I3 |
| `File.Uploaded / Processed / Rejected` | `file_id, slot, sha256, size, content_type, filename, status, report?` | I4 |
| `Feed.Posted / Edited / Retracted` | `post_id, body, mentions[], hashtags[], record_refs[]` | I6 |
| `Setting.Changed` | `key, scope, old, new, reason` | I2 (v0), I8 |
| `SchemaPackage.Published`, `Schema.EffectiveChanged` | `package, version, effective_schema_hash` | I2 |
| `Webhook.Delivered / Failed` (ops) | `subscription_id, event_id, status, attempt` | I5 |

## 9. Current-state table shape (Phase 0 generic record)

Generated by `tl_schema.generators.ddl` from the LinkML class; shown here so increment 1 tickets can target it by hand before the generator exists (the generator must reproduce exactly this for `core.Record`).

```sql
CREATE TABLE cur_core_record (
  id                    TEXT PRIMARY KEY,
  key                   TEXT,
  type                  TEXT NOT NULL,
  scope                 TEXT NOT NULL,
  title                 TEXT NOT NULL,
  description           TEXT,
  status                TEXT,
  psets_json            TEXT NOT NULL DEFAULT '{}',   -- JSONB on Postgres
  voided                INTEGER NOT NULL DEFAULT 0,   -- BOOLEAN on Postgres
  version               INTEGER NOT NULL,
  last_seq              INTEGER NOT NULL,
  effective_schema_hash TEXT,
  conformance           TEXT NOT NULL DEFAULT 'ok',
  created_at            TEXT NOT NULL,                -- TIMESTAMPTZ on Postgres
  updated_at            TEXT NOT NULL
);
CREATE UNIQUE INDEX ux_cur_core_record_scope_key ON cur_core_record(scope, key);
```

## 10. Testing conventions

- Unit tests live beside the package: `packages/<pkg>/tests/`.
- Cross-package and adapter tests live in `tests/`. Parity tests are parametrised by adapter fixture.
- Property tests (`hypothesis`) for: projection determinism (replay twice → identical tables), hash-chain continuity, numbering uniqueness, sync convergence (Phase 3).
- Snapshot tests for every TUI screen listed in a ticket.
- Fixtures: `conftest.py` at root provides `sqlite_ledger`, `uow`, `seeded_project(scale="xs")`.
