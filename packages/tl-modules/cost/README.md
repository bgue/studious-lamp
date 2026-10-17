# tl-mod-cost (`tl_mod_cost`)

The cost module (M11): a read-only mirror of the cost system's codes and period snapshots, imported from a CSV export (§9 M11). Decisions: ADR-0015, ADR-0010. Spec: `docs/modules/cost/README.md`.

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_mod_cost.module.spec` | function | The entry point `throughline.modules` / `cost` |
| `tl_mod_cost.names` | module | Record types, event types, tables, units and measures |
| `tl_mod_cost.projectors` | package | `CostCodeProjector`, `CostSnapshotProjector` |
| `tl_mod_cost.handlers.snapshots` | module | `ImportCostSnapshot` and `handle_import_cost_snapshot` (one correlated batch) |
| `tl_mod_cost.imports` | package | `reader.read_cost_csv` (bounded, strict, no clock), `plan.plan_import` (what would be created, revised or refused), `model` |
| `tl_mod_cost.registry` / `views` | module | Reads: codes, snapshots, one code's history; the views the API, TUI and MCP return |
| `tl_mod_cost.commands` | module | `API_COMMANDS`: `ImportCostSnapshot` with access `admin` |
| `tl_mod_cost.limits` | module | Size limits of the file and the commands |
| `tl_mod_cost.testing` | module | A ledger and the cost commands for tests of other packages |

## Depends on / used by
- Depends on: `tl_core` (ledger, services, `tl_core.text`), `tl_schema` (generated DDL), `tl_adapters`, `pydantic`, `sqlalchemy`.
- Used by: the platform through its entry point; `tl_cli` (`tl cost`), `tl_api`, `tl_tui`, `tl_mcp`.

## Commands
```
just test -- packages/tl-modules/cost
uv run tl cost import cost.csv --project P123 --period 2026-09 --as-of 2026-09-30            # preview
uv run tl cost import cost.csv --project P123 --period 2026-09 --as-of 2026-09-30 --apply    # admin
```

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|
| none | | The bounds are constants in `limits.py` (10 MiB, 20 000 rows) |

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P1-I4. Last interface change: P1-I4 (ADR-0015).
