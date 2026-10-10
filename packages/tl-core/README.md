# tl-core (`tl_core`)

The dialect-neutral platform core: ledger types and hashing, the projector engine, unit-of-work and bus contracts, and the command and query services (§5.1 to §5.4, §16).

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_core.ledger`: `NewEvent`, `Event`, `AppendResult`, `ConcurrencyError`, `Ledger` | models, Protocol | The event envelope and the ledger contract (`append`, `read_stream`, `read_after`, `head_seq`, `stream_version`) |
| `tl_core.ledger`: `canonical_json`, `iso_utc`, `event_hash` | functions | Per-scope hash chain input and output |
| `tl_core.projection`: `Projector`, `ProjectorRegistry`, `InMemoryRegistry` | Protocols, class | Inline read-model builders; unique names; per-event lookup |
| `tl_core.projection.defaults.default_registry()` | function | Built-in projectors (`core_record`, `pset_values`, `links`, `numbering`, `workflow`, `files`), in dependency order |
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
| `tl_core.services.queries`: `get_record`, `list_records`, `envelope_from_row` | functions | Envelope dictionaries from `cur_core_record` |
| `tl_core.query`: `parse`, `run_query`, `count_query`, `QuerySpec`, `QuerySyntaxError`, `to_text`, `use_clock` | functions, model | The shared filter language (brief 10.2, 7.5): text to AST, AST to allow-listed SQL over `cur_core_record`, `cur_pset_values` and `cur_links`. Reference: `docs/reference/query-language.md` |
| `tl_core.query.ast` | dataclasses | `Compare`, `Text`, `Linked`, `CountLinked`, `MissingLink`, `And`, `Or`, `Not`, `RelativeDate` (frozen contract) |
| `tl_core.changefeed`: `SubscriptionFilter`, `SubscriptionRegistry`, `ChangePoller`, `fetch_changes`, `ChangePage` | classes, function | The change feed (brief 5.3, 18.2): filters by scope, event type glob and record id; one fan-out registry fed by the bus (`registry.attach(bus)`) and by a seq-cursor poller; paged filtered reads for `/events?after=`; at-least-once, resumable from the last `seq` |
| `tl_core.files.types`: `ObjectStore`, `object_key`, `ObjectNotFound` | Protocol, functions | Frozen object-store contract (build spec 03 §7); keys are `sha256/<aa>/<bb>/<digest>` |
| `tl_core.files.service`: `FileService`, `RegisterUpload`, `CompleteUpload`, `AttachFile`, `UploadTicket`, `FileResult` | class, models | Upload flow: server-side hash and size verification, scope-local dedupe, quarantine, `File.*` events with the `cur_files` row in one unit of work; `open_file`, `scan_pending`. Signatures: `docs/tickets/P0-I4/README-B.md` |
| `tl_core.files.queries`: `get_file`, `list_files`, `FileInfo` | functions, model | Read side of `cur_files` (the current file per slot is `available` and not superseded) |
| `tl_core.files.lifecycle`: `next_file_status` | function | The quarantine state machine (`quarantined` to `available` or `rejected`) |
| `tl_core.files.slots`: `FileSlot`, `FileSlotRegistry`, `default_file_slots()` | models, function | `tl:file_slots` declarations from LinkML YAML (`schema/fixtures/files/`) |
| `tl_core.files.required`: `missing_required_files` | function | Required slots still empty for a record (a workflow guard) |
| `tl_core.files.reconcile`: `reconcile_objects` | function | Ledger hashes versus the store: missing, corrupt, orphans, staging (read-only) |
| `tl_core.files.scan`: `Scanner`, `PassScanner` | Protocol, class | Malware-scan seam; Phase 0 passes everything |
| `tl_core.projection.files.FileProjector` | class | `File.*` events to `cur_files`; rows are never deleted |
| `tl_core.services.errors` | exceptions | `ServiceError` and its subclasses (record, pset, link, numbering, workflow, file and lock refusals) |
| `tl_core.util`: `utcnow`, `new_ulid` | functions | Clock and id helpers |

## Webhooks (`tl_core.webhooks`, P0-I5 workstream B)
Outbox, signed delivery and the event catalog. Plan and decisions: `docs/tickets/P0-I5/README-B.md`.

| Name | Kind | Purpose |
|---|---|---|
| `outbox.OutboxProjector` | projector (`handles_all`) | One `outbox_events` row per event, in the event's transaction |
| `subscriptions.*` | commands | Create, update, enable, disable, `rotate_secret` (secrets never enter the ledger) |
| `dispatch.Dispatcher` | class | Fan-out to subscriptions; `replay`, `replay_between`, `redrive` |
| `delivery.DeliveryEngine` | class | `claim`, `attempt`, `settle`; per-subject order, retries, DLQ, auto-disable; `send_test` |
| `signing`, `egress`, `transport` | modules | Standard Webhooks signing; SSRF policy with DNS pinning; httpx transport |
| `queries`, `wiring`, `worker` | modules | Read views for the CLI; engine wiring; the worker loop |

A subscription without a usable signing secret (after a restore) is held back: its deliveries stay pending, `tl webhook ls` shows `needs_secret`, and `tl webhook rotate-secret` releases them.

A test send (`tl webhook test`, `send_test`) carries the header `webhook-test: 1`; real deliveries never do. It is refused for a
disabled or expired subscription.

## Ledger archive (`tl_core.archive`, P0-I7 workstream A)
The ledger is sealed into signed, hash-chained segments that do not depend on the database (brief 24.3, 24.4, 24.5). The contract is `archive/types.py` (frozen). Runbooks: `docs/runbooks/ledger-archive-and-verify.md`, `docs/runbooks/restore-from-archive.md`.

| Symbol | Kind | Purpose |
|---|---|---|
| `seal_segment(conn, store, signer, max_events=10000)` | function | Seal the events after the last sealed seq into `segments/<first>-<last>/` (`events.ndjson`, `events.parquet`, `manifest.json`); crash-idempotent (the manifest is the commit marker); refuses a database that diverged from what is sealed |
| `verify_archive(store, public_key=..., conn=None, deep=False, stop_at_first=True, expect_last_seq=None, expect_manifest_sha256=None)` | function | Files, signatures, manifest chain, gap-free seq, event hashes, scope chains, and with `conn` the database; `deep` recomputes database hashes and compares every field. Returns the first divergence as a `VerifyIssue` |
| `verify_ledger(conn)` | function | The database alone: gap-free seq, hashes recomputed from stored fields, per-scope chains |
| `iter_segment_events(store)`, `read_events(conn, first, last)`, `archive_scopes(store)`, `summarize_archive(store)` | functions | Read the archive or the ledger table (portable SQL) |
| `Signer`, `Ed25519Signer`, `generate_signer`, `write_keypair`, `load_signer`, `load_public_key`, `key_id_of`, `public_key_path` | Protocol, class, functions | Ed25519 signing from `cryptography`; the dev key is `dev/data/archive-signing.key` (git-ignored); production custody is a later, human decision |
| `ArchiveError`, `ArchiveExistsError`, `RestoreError` | exceptions | `RestoreError.issue` carries the first divergence when verification caused the refusal |

Restore is not here: it inserts events verbatim through `tl_adapters.<dialect>.admin.restore_events` (`tl_adapters.restore.restore_from_archive`). `events.parquet` uses the ledger `events` column names, so the lake can load a segment directly.

## Depends on / used by
- Depends on: `tl_schema` (generated DDL, effective schema, conformance), `sqlalchemy` (Core only), `pydantic`, `python-ulid`, `duckdb==1.5.5` (MIT; writes the archive Parquet, imported lazily), `cryptography` (Apache-2.0/BSD; Ed25519).
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
| `TL_ARCHIVE_DIR`, `TL_ARCHIVE_KEY`, `TL_ARCHIVE_PUBLIC_KEY` | `./dev/data/archive`, `dev/data/archive-signing.key`, `dev/data/archive-signing.pub` | Read by the `tl archive` and `tl restore` commands |
| `TL_WEBHOOK_ALLOWLIST` | empty | Comma-separated egress allow-list (`webhooks.egress.allowlist`): hosts, `host:port`, IPs or CIDRs that may resolve to private addresses |

Adapters supply connections.

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P0-I1. Last interface changes: P0-I4 workstream A (query language and change feed; `docs/tickets/P0-I4/README-A.md`) and workstream B (`tl_core.files`; `files/types.py` is a frozen contract; `docs/tickets/P0-I4/README-B.md`). Before that: P0-I2 workstream A (pset services, provider, projector; `docs/tickets/P0-I2/README-A.md`). Rebuild `core_record` and `pset_values` together (`docs/runbooks/rebuild-projections.md`). Earlier: P0-I3 (links, numbering, workflow, atomic edit; decisions D1 to D25 in `docs/tickets/P0-I3/README.md`). Archive, verifier and signer (`tl_core.archive`) added in P0-I7 workstream A (`docs/tickets/P0-I7/A-PLAN.md`).
