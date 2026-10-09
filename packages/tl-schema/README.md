# tl-schema (`tl_schema`)

The schema runtime: generators that turn the LinkML sources in `schema/` into Pydantic models, JSON Schema, and current-state DDL for SQLite and Postgres (§5.4, §6.1, §14).

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_schema.generate` (`python -m tl_schema.generate [--check]`) | module / command | Runs every generator; `--check` fails when committed output differs (codegen drift gate, §25.4) |
| `tl_schema.generate.GENERATORS`, `outputs()` | list, function | The registered generators and their combined `{path: text}` output |
| `tl_schema.generators.pydantic_gen`, `jsonschema_gen` | modules | LinkML to Pydantic v2 and JSON Schema (run inside `schema/core` so no absolute paths leak) |
| `tl_schema.generators.ddl.generate` | function | Classes annotated `tl:current_state` to `cur_<module>_<class>` DDL per dialect |
| `tl_schema.generators.ddl_types.column_type`, `sql_literal` | functions | LinkML built-in type to SQL type and DEFAULT literal, table driven |
| `tl_schema.ddl_loader.statements(table, dialect)` | function | Reads the committed generated DDL at runtime, one string per statement |
| `tl_schema.generated.*` | package | Generated output. Never edit by hand |

## Depends on / used by
- Depends on: `schema/core/*.yaml` (LinkML sources), `linkml`, `linkml-runtime`, `pydantic`, `jsonschema`.
- Used by: `tl_core` (the Record projector loads its DDL through `ddl_loader`).

## Commands
```
just gen
just check
just test packages/tl-schema
```

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|
| `--out DIR`, `--schema-dir DIR` | `generated/`, `schema/core` | Test hooks for `tl_schema.generate` |

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P0-I1. Last interface change: P0-I1 (plan decisions D2, D5, D11, D12 in `docs/tickets/P0-I1/README.md`).
