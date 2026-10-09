# tl-core (`tl_core`)

The dialect-neutral platform core: ledger types and hashing, the projector engine, unit-of-work and bus contracts, and the command and query services (§5.1 to §5.4, §16).

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_core.ledger`: `NewEvent`, `Event`, `AppendResult`, `ConcurrencyError`, `Ledger` | models, Protocol | The event envelope and the ledger contract (`append`, `read_stream`, `read_after`, `head_seq`, `stream_version`) |
| `tl_core.ledger`: `canonical_json`, `iso_utc`, `event_hash` | functions | Per-scope hash chain input and output |
| `tl_core.projection`: `Projector`, `ProjectorRegistry`, `InMemoryRegistry` | Protocols, class | Inline read-model builders; unique names; per-event lookup |
| `tl_core.projection.defaults.default_registry()` | function | Built-in projectors (`core_record`, `pset_values`) |
| `tl_core.projection.record.RecordProjector` | class | `Record.*` events to `cur_core_record`; rows are never deleted |
| `tl_core.projection.pset.PsetProjector` | class | `Pset.ValuesSet` and pset-carrying record events to `psets_json`, `cur_pset_values` and promoted columns; `None` values unset |
| `tl_core.projection.promoted.ensure_promoted_columns` | function | Add and backfill `pset__<pset>__<property>` columns for an effective schema |
| `tl_core.schema_provider`: `DirectorySchemaProvider`, `get_provider`, `use_provider` | class, functions | Effective schema per scope from `TL_SCHEMA_DIR`; notices edited files; `reload()` |
| `tl_core.uow.UnitOfWork` | Protocol | One transaction: append plus projectors, then publish on commit |
| `tl_core.bus`: `Bus`, `InProcessBus`, `OrderedPublisher` | Protocol, classes | Change feed with per-subscriber `seq` cursors and commit-order delivery |
| `tl_core.services.commands`: `CreateRecord`, `UpdateRecord`, `VoidRecord`, `CommandResult` | models | Command contracts shared by CLI, TUI, API, MCP |
| `tl_core.services.records`: `handle_create_record`, `handle_update_record`, `handle_void_record` | functions | The only business rules for `core.Record` |
| `tl_core.services.psets`: `SetPsetValues`, `handle_set_pset_values`, `form_metadata`, `conformance` | model, functions | Layer-aware pset writes (`Pset.ValuesSet`), form metadata and conformance for the TUI and CLI |
| `tl_core.services.schema_events`: `reload_and_record`, `schema_reload_subscriber` | functions | `Schema.EffectiveChanged` events (stream `schema:<scope>`) and the bus hook |
| `tl_core.services.queries`: `get_record`, `list_records` | functions | Envelope dictionaries from `cur_core_record` |
| `tl_core.services.errors` | exceptions | `ServiceError` and its subclasses |
| `tl_core.util`: `utcnow`, `new_ulid` | functions | Clock and id helpers |

## Depends on / used by
- Depends on: `tl_schema` (generated DDL, effective schema, conformance), `sqlalchemy` (Core only), `pydantic`, `python-ulid`.
- Used by: `tl_adapters`, `tl_cli`, later `tl_api`, `tl_mcp`, `tl_tui`.

## Commands
```
just test packages/tl-core
just test tests/services
```

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|
| `TL_SCHEMA_DIR` | `schema/fixtures` | Package directory for the default schema provider |

Adapters supply connections.

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P0-I1. Last interface change: P0-I2 workstream A (pset services, provider, projector; decisions in `docs/tickets/P0-I2/README-A.md`). Rebuild `core_record` and `pset_values` together (`docs/runbooks/rebuild-projections.md`).
