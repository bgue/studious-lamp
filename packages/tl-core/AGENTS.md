# AGENTS.md — tl-core

Read the root `AGENTS.md` first. These rules add to it.

- Dialect neutral: depend only on the Protocols (`Ledger`, `UnitOfWork`, `Bus`, `Projector`). SQL here uses SQLAlchemy `text()` with bound parameters and no dialect features.
- Projectors are deterministic: no clock, no generated ids, no outside calls. They never delete rows of history; `reset` clears only their own tables.
- Business rules live in `services/`. Clients (CLI, TUI, API, MCP) call handlers and queries and add none.
- Never write `cur_*`, `hist_*`, or `v_*` DDL here; load it from `tl_schema.ddl_loader`.
- Publish order equals commit order. Never publish while holding a lock a subscriber could need; use `OrderedPublisher`.
- Test-only helpers (`projection/testing.py`) are never registered by default.
- pyright strict applies to `src/`. No ignores.
- Pset events: `Pset.ValuesSet` payload is `pset, layer, values, effective_schema_hash, conformance, units`; the projector reads only the payload and the rows already in the database, never the schema provider. A `None` value in `values` is a ledgered clear.
- Services get the effective schema from `tl_core.schema_provider.get_provider()`; tests install a provider with `use_provider`.
- `psets.py` signatures (`SetPsetValues`, `handle_set_pset_values`, `form_metadata`, `conformance`) are a contract with the TUI; change them only through an orchestrator decision.
- Files: `files/types.py` is frozen (change only through an orchestrator decision). Never trust client-declared size or hash; verification happens in the store's `put` and in `FileService`. Dedupe without bytes only against an `available` file in the same scope. A quarantined file is readable only by its uploader. Supersession happens at `File.Processed`.
- File events live on a `core.File` stream (stream id = file id). Quarantine rules are in `files/lifecycle.py` alone; handlers and the projector both call it.
- Anything that serves file bytes (API) must send `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`; `content_type` is client-declared.
- Query language: SQL is built only from the allow-lists in `query/fields.py` and bound parameters; never splice caller text, a column name or an operator into SQL. Every compiled predicate must be two-valued (`col IS NOT NULL AND col = :v`), or `NOT` and `!=` silently drop rows with no value. A new envelope column is added to `ENVELOPE_FIELDS` (and the parser, compiler and reference page follow); a new AST node is an orchestrator decision.
- The parser raises only `QuerySyntaxError`, with a 0-based `position`; bound input length, nesting and node count. Property tests (`tests/query/test_query_properties.py`) must stay green.
- Change feed (`changefeed/`): delivery must follow commit (`seq`) order per subscriber and drop repeats by `seq`, because the bus and the poller feed one registry. Callbacks run under the registry lock: never block in one; use `subscribe_queue` for a consumer on another thread. Do not call this package `feed`: `Feed.*` events are the activity feed (P0-I6).
- Links: a link is its own stream (`core.Link`, stream id = link id, scope = the from-record's scope; the target is in that scope or `company`). Status changes go through `links.lifecycle.next_status` only; there is no broken-to-active route. Never add a delete.
- Numbering: allocate a key inside the transaction that creates the record (`allocate_key`), never before it; the counter stream's expected-version check is the second line of defence. `Pattern.parse` accepts only the canonical spelling of a sequence.
- Workflow: guards are evaluated against the target state; a guard failure raises `GuardFailedError` carrying every `GuardResult`. `expected_version` is checked after the state and guard checks. The roles list is caller-supplied (D12); never read roles from the database until auth exists.
- A new command that needs several writes to be atomic composes the existing handlers in one unit of work (see `services/edit.py`, L-P0-I3-10); do not add a second write path.
- Definitions (workflows, expected links, numbering patterns) are files under the schema directory; `schema/**` changes are human-gated.
- Webhooks (`tl_core.webhooks`): a secret is never logged, put in an event, an error message or a `repr` (`SigningSecret` hides it). The outbox projector is registered last and reads other projections' rows; a delivery body is built once and re-sent unchanged; ordering, signing and egress changes need orchestrator or human review. Read a stream's version inside the transaction (`subscriptions.current_version`), not through `uow.ledger`.
- A new event type needs a class in `schema/core/events.yaml` in the same change (a test fails otherwise); run `just gen`.
- Feed (`feed/`, `projection/feed.py`, `services/feed*.py`): `feed/types.py` is frozen. Card rules are in `feed/cards.py` alone and use only event fields, never the clock; the projector reads only its own tables so a feed-only rebuild equals a full one. A post is not a record: only the link service's `from` end accepts one. A hashtag never changes a record; the only write beyond the post is a *suggested* link, and `SuggestLink` refusals (duplicate, declined, voided) are skipped, not raised. `Feed.*` event types need catalog classes (`schema/core/feed.yaml`).
