# AGENTS.md — tl-core

Read the root `AGENTS.md` first. These rules add to it.

- Dialect neutral: depend only on the Protocols (`Ledger`, `UnitOfWork`, `Bus`, `Projector`). SQL here uses SQLAlchemy `text()` with bound parameters and no dialect features.
- Projectors are deterministic: no clock, no generated ids, no outside calls. They never delete rows of history; `reset` clears only their own tables.
- Business rules live in `services/`. Clients (CLI, TUI, API, MCP) call handlers and queries and add none.
- Never write `cur_*`, `hist_*`, or `v_*` DDL here; load it from `tl_schema.ddl_loader`.
- Publish order equals commit order. Never publish while holding a lock a subscriber could need; use `OrderedPublisher`.
- Test-only helpers (`projection/testing.py`) are never registered by default.
- pyright strict applies to `src/`. No ignores.
