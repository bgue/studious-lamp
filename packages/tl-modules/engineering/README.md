# tl-mod-engineering (`tl_mod_engineering`)

The engineering module (M2): the company standards registry (code lists, mnemonics, numbering patterns), tag classes and
tags, with the projectors, commands, import and reports that serve them (§6.4, §9 M2, §27.5). Decision: ADR-0010.

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_mod_engineering.module.spec` | function | The entry point `throughline.modules` / `engineering`: returns the `ModuleSpec` the core loads |
| `tl_mod_engineering.names` | module | Record types, event types and table names as constants |
| `tl_mod_engineering.projectors` | package | `StandardProjector`, `CodeValueProjector`, `TagClassProjector`, `TagProjector`: write the four generated tables and move the envelope row |
| `tl_mod_engineering.registry` | module | Reads: `get_standard`, `find_standards`, `active_standard`, `find_code_value`, `code_values`, `get_tag_class`, `find_tag_classes`, `active_tag_class`, `get_tag`, `find_tag` (frozen rows joined with `cur_core_record`) |
| `tl_mod_engineering.errors` | module | The module's `ServiceError` subclasses |
| `tl_mod_engineering.document` | module | The standards file: `StandardsDoc`, `parse_standards`, `load_standards_file` |
| `tl_mod_engineering.handlers.tag_class` | module | `DefineTagClass`, `ReviseTagClass`, `CloseTagClass` and their handlers (T07) |
| `tl_mod_engineering.imports` | package | Tag-list import: `mapping` (template and CSV reader, T10a), `diff` (plan, T10b), `model` (the values they pass) |

## Depends on / used by
- Depends on: `tl_core` (ledger, services, `tl_core.modules`), `tl_schema` (generated DDL, conformance), `tl_adapters` (tests), `pydantic`, `pyyaml`, `sqlalchemy`.
- Used by: the platform through its entry point; later `tl_cli`, `tl_api`, `tl_tui`, `tl_mcp`, `tl_sim`.

## Commands
```
just test packages/tl-modules
uv run pytest packages/tl-modules -q --adapters sqlite,postgres   # needs TL_PG_URL
```

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|
| `TL_SCHEMA_DIR` | `schema/fixtures` | Where the effective schema is read (the psets a class binds must exist there) |

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P1-I1. Module spec: `docs/modules/engineering/README.md`; schema: `schema/modules/engineering/`; plan: `docs/tickets/P1-I1/README.md`.
