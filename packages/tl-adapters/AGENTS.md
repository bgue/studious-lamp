# AGENTS.md — tl-adapters

Read the root `AGENTS.md` first. These rules add to it.

- Dialect-specific SQL lives only here (and, as generated DDL text, in `tl_schema`).
- Never UPDATE or DELETE rows of `events`; the triggers reject it and no code may route around them.
- SQLite transactions go through `write_tx` / `read_tx`. Do not reintroduce pysqlite's implicit transaction handling.
- `append_in` needs a connection from `write_tx`. Commit and bus enqueue happen under one lock; subscribers run after it is released.
- Parity: anything here that the Postgres adapter will mirror must be covered by a test that can run against both (parity suite arrives in P0-I5).
- pyright strict applies to `src/`. No ignores.
