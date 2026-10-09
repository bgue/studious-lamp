# tl-tui (`tl_tui`)

The Textual application shell, grid, record view, and forms; every screen reads and writes through `ClientInterface`, so the same screens run embedded or remote (§4, §10.1–§10.4, §10.6 sketches 1, 2, 11).

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_tui.client.ClientInterface` | Protocol | The only way a screen reads or writes. Contract from P0-I2; changes need an orchestrator decision |
| `tl_tui.embedded.EmbeddedClient` | class | `ClientInterface` over in-process `tl_core` services; `EmbeddedClient.for_sqlite(path)` |
| `tl_tui.errors.CLIENT_ERRORS`, `describe_error` | tuple, function | Expected failures a screen catches, and the one-line text to show |
| `tl_tui.messages` | module | Messages widgets post and the app routes (`OpenRecord`, `RecordHighlighted`, `SelectionChanged`, `RecordChanged`, `CloseRecord`, `StepRecord`, `StatusMessage`, `NavSelected`) |
| `tl_tui.paths.pset_value`, `relative_key` | functions | Layer-aware pset path lookup and `SetPsetValues` key derivation |
| `tl_tui.app.TlApp` | App | Shell: header, nav tree, main area, context panel, footer; F2/F3 panel collapse; overlays at 80 columns or less |
| `tl_tui.widgets.grid.RecordGrid` | widget | Virtualised grid: paging, cursor, sort, multi-select, TSV |
| `tl_tui.main.main` | function | `tl-tui` / `python -m tl_tui` entry point (embedded mode) |

## Depends on / used by
- Depends on: `textual`, `tl_core` (services), `tl_schema` (form metadata models), `tl_adapters` (only `EmbeddedClient.for_sqlite` and `just tui`).
- Used by: `just tui`, `dev/demos/P0-I2.sh`.

## Commands
```
just test-tui            # every test in this package, including snapshots
just tui                 # run the TUI on the dev ledger (TL_DB, TL_PROJECT)
uv run pytest packages/tl-tui/tests/test_grid.py -q
```

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|
| `TL_DB` | `./dev/data/tl.db` | SQLite ledger file for embedded mode |
| `TL_PROJECT` | `P123` | Project whose records the grid shows (scope `project:<id>`) |

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P0-I1 (skeleton). First interface: P0-I2 workstream B.
