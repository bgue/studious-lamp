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
- Query language: SQL is built only from the allow-lists in `query/fields.py` and bound parameters; never splice caller text, a column name or an operator into SQL. Every compiled predicate must be two-valued (`col IS NOT NULL AND col = :v`), or `NOT` and `!=` silently drop rows with no value. A new envelope column is added to `ENVELOPE_FIELDS` (and the parser, compiler and reference page follow); a new AST node is an orchestrator decision.
- The parser raises only `QuerySyntaxError`, with a 0-based `position`; bound input length, nesting and node count. Property tests (`tests/query/test_query_properties.py`) must stay green.
- Change feed (`changefeed/`): delivery must follow commit (`seq`) order per subscriber and drop repeats by `seq`, because the bus and the poller feed one registry. Callbacks run under the registry lock: never block in one; use `subscribe_queue` for a consumer on another thread. Do not call this package `feed`: `Feed.*` events are the activity feed (P0-I6).
