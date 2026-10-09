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
- Links: a link is its own stream (`core.Link`, stream id = link id, scope = the from-record's scope; the target is in that scope or `company`). Status changes go through `links.lifecycle.next_status` only; there is no broken-to-active route. Never add a delete.
- Numbering: allocate a key inside the transaction that creates the record (`allocate_key`), never before it; the counter stream's expected-version check is the second line of defence. `Pattern.parse` accepts only the canonical spelling of a sequence.
- Workflow: guards are evaluated against the target state; a guard failure raises `GuardFailedError` carrying every `GuardResult`. `expected_version` is checked after the state and guard checks. The roles list is caller-supplied (D12); never read roles from the database until auth exists.
- A new command that needs several writes to be atomic composes the existing handlers in one unit of work (see `services/edit.py`, L-P0-I3-10); do not add a second write path.
- Definitions (workflows, expected links, numbering patterns) are files under the schema directory; `schema/**` changes are human-gated.
