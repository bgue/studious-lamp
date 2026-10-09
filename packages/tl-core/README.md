# tl-core (`tl_core`)

The dialect-neutral platform core: ledger types and hashing, the projector engine, unit-of-work and bus contracts, and the command and query services (§5.1 to §5.4, §16).

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_core.ledger`: `NewEvent`, `Event`, `AppendResult`, `ConcurrencyError`, `Ledger` | models, Protocol | The event envelope and the ledger contract (`append`, `read_stream`, `read_after`, `head_seq`, `stream_version`) |
| `tl_core.ledger`: `canonical_json`, `iso_utc`, `event_hash` | functions | Per-scope hash chain input and output |
| `tl_core.projection`: `Projector`, `ProjectorRegistry`, `InMemoryRegistry` | Protocols, class | Inline read-model builders; unique names; per-event lookup |
| `tl_core.projection.defaults.default_registry()` | function | Built-in projectors (`core_record`, `pset_values`, `links`, `numbering`, `workflow`), in dependency order |
| `tl_core.projection.record.RecordProjector` | class | `Record.*` events to `cur_core_record`; rows are never deleted |
| `tl_core.projection.pset.PsetProjector` | class | `Pset.ValuesSet` and pset-carrying record events to `psets_json`, `cur_pset_values` and promoted columns; `None` values unset |
| `tl_core.projection.promoted.ensure_promoted_columns` | function | Add and backfill `pset__<pset>__<property>` columns for an effective schema |
| `tl_core.schema_provider`: `DirectorySchemaProvider`, `get_provider`, `use_provider` | class, functions | Effective schema per scope from `TL_SCHEMA_DIR`; notices edited files; `reload()` |
| `tl_core.uow.UnitOfWork` | Protocol | One transaction: append plus projectors, then publish on commit |
| `tl_core.bus`: `Bus`, `InProcessBus`, `OrderedPublisher` | Protocol, classes | Change feed with per-subscriber `seq` cursors and commit-order delivery |
| `tl_core.services.commands`: `CreateRecord`, `UpdateRecord`, `VoidRecord`, `CommandResult` | models | Command contracts shared by CLI, TUI, API, MCP |
| `tl_core.services.records`: `handle_create_record`, `handle_update_record`, `handle_void_record` | functions | The only business rules for `core.Record` |
| `tl_core.services.psets`: `SetPsetValues`, `handle_set_pset_values`, `form_metadata`, `conformance` | model, functions | Layer-aware pset writes (`Pset.ValuesSet`), form metadata and conformance for the TUI and CLI |
| `tl_core.services.edit`: `EditRecord`, `PsetEdit`, `handle_edit_record` | model, function | One atomic edit: field changes and pset batches in a single unit of work, one `expected_version`, one correlation id |
| `tl_core.projection.links.LinkProjector`, `numbering.NumberingProjector`, `workflow.WorkflowProjector` | classes | `Link.*` to `cur_links` and `cur_link_counts`; `Numbering.*` to `cur_numbering`; `Workflow.Transitioned` to `cur_workflow_state` and the record's `status` |
| `tl_core.links`: `next_status`, `default_vocabulary`, `default_relation`, `RelationVocabulary`, `missing_expected_links`, `ExpectedLinkRegistry` | functions, classes | Link lifecycle rules (suggested, active, stale, broken, retracted), the relation vocabulary with inverses and per-type defaults, and expected links (`tl:expects_link`) read from `<schema dir>/links/*.yaml` |
| `tl_core.services.links`: `AddLink`, `SuggestLink`, `AcceptLink`, `DeclineLink`, `RepinLink`, `VerifyLink`, `FlagLink`, `RetractLink`, `handle_*_link`, `handle_mark_pins_stale` | models, functions | Link commands; a link is its own stream (`core.Link`), links are never deleted |
| `tl_core.services.link_queries`: `links_of`, `link_counts`, `search_linkable`; `link_trace`: `trace`, `TraceNode` | functions, model | Both directions with labels as read from the record, counts, picker search, and the n-hop trace tree |
| `tl_core.numbering`: `parse_pattern`, `get_numbering`, `allocate_key`, `detect_keys`, `suggest_chips` | functions | Key patterns (`{project}-REC-{seq:4}`), allocation in the creating transaction (gap-free), and key detection in text for suggestion chips |
| `tl_core.workflow`: `WorkflowDefinition`, `load_workflows`, `evaluate_guards`; `tl_core.services.workflow`: `TransitionWorkflow`, `handle_transition_workflow`, `workflow_status` | models, functions | Declarative workflows from `<schema dir>/workflows/*.yaml`; guards (required psets, conformance, required and expected links, roles); a blocked transition names every failing guard |
| `tl_core.services.schema_events`: `reload_and_record`, `schema_reload_subscriber` | functions | `Schema.EffectiveChanged` events (stream `schema:<scope>`) and the bus hook |
| `tl_core.services.queries`: `get_record`, `list_records` | functions | Envelope dictionaries from `cur_core_record` |
| `tl_core.services.errors` | exceptions | `ServiceError` and its subclasses (record, pset, link, numbering and workflow refusals) |
| `tl_core.util`: `utcnow`, `new_ulid` | functions | Clock and id helpers |

## Depends on / used by
- Depends on: `tl_schema` (generated DDL, effective schema, conformance), `sqlalchemy` (Core only), `pydantic`, `python-ulid`.
- Used by: `tl_adapters`, `tl_cli`, `tl_tui` (embedded client), later `tl_api`, `tl_mcp`.

## Commands
```
just test packages/tl-core
just test tests/services
```

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|
| `TL_SCHEMA_DIR` | `schema/fixtures` | Package directory for the default schema provider; also holds `workflows/`, `links/` and `numbering/` (read on first use; tests install their own with `use_workflows`, `use_expected_links`, `use_numbering`) |

Adapters supply connections.

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P0-I1. Last interface change: P0-I3 (links, numbering, workflow, atomic edit; decisions D1 to D25 in `docs/tickets/P0-I3/README.md`). Earlier: P0-I2 workstream A (pset services; `docs/tickets/P0-I2/README-A.md`). Rebuild all projections together (`docs/runbooks/rebuild-projections.md`). Known limits: Postgres guard reads need row locks (P0-I5); the roles guard trusts the caller's role list until auth exists; voiding a record does not flag its links stale; `reserve_range` is a stub; the idempotency key is ignored.
