# tl-mod-legacy (`tl_mod_legacy`)

The legacy loaders module: a load run takes one spreadsheet or CSV export of an incumbent system through open, extract, profile, plan, load and reconcile, and can be compensated (§29.6). Decisions: `docs/tickets/P1-I8/FANOUT.md` D6 to D9. Spec: `docs/modules/legacy/README.md`. Runbook: `docs/runbooks/legacy-load.md`.

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_mod_legacy.module.spec` | function | The entry point `throughline.modules` / `legacy` |
| `tl_mod_legacy.service.LoadService` | class | The stages: `open`, `extract`, `profile`, `bronze`, `plan`, `load`, `reconcile`, `compensate`, `void` and the reads |
| `tl_mod_legacy.model` | module | `LoaderDef`, `Grid`, `load_loaders()` (entry-point group `throughline.loaders`), `use_loaders()` for tests |
| `tl_mod_legacy.targets` | module | `TagTarget` and `DocumentTarget`: plan, create-only apply, compare, reversals |
| `tl_mod_legacy.extract` | module | `read_grid`: the file read in the resource envelope |
| `tl_mod_legacy.profile` | module | `profile_grid`: the DuckDB profile of a grid |
| `tl_mod_legacy.bronze` | module | `write_bronze`: the lake table `legacy_<system>_<table>` |
| `tl_mod_legacy.source_layer` | module | `write_source_layer`, `clean_values`: the Python-only write of `src.legacy-<system>.<table>` |
| `tl_mod_legacy.registry` | module | Reads of runs |
| `tl_mod_legacy.testing` | module | `LegacyWorld`, two test loaders and `tag_csv` for tests of this and other packages |

## Depends on / used by
- Depends on: `tl_core` (services, files, derivation envelope), `tl_schema`, `tl_adapters`, `tl_lake` (bronze), `tl_mod_engineering` and `tl_mod_documents` (the imports it reuses).
- Used by: `tl_cli` (`tl load`); the loader packages that add entry points to `throughline.loaders`.

## Commands
```
just test -- packages/tl-modules/legacy
```

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|
| `TL_LAKE_DIR` | `./dev/data/lake` | Only for the bronze stage |

The bounds are constants in `limits.py` and `service.py` (50 MiB a file; 20 000 records a load).

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P1-I8. Last interface change: P1-I8.
