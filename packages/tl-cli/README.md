# tl-cli (`tl_cli`)

The `tl` command: a thin typer front end over the `tl_core` command and query services and the SQLite adapter (§25.2, §29.4).

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl init` | command | Create the ledger file and its schema |
| `tl record create --project ID --key KEY --title TITLE` | command | Calls `handle_create_record`; prints stream id, key, version |
| `tl record show --project ID KEY` | command | Calls `get_record`; prints the current-state row |
| `tl record void --project ID KEY --reason R` | command | Calls `handle_void_record` with the record's current version |
| `tl events tail --project ID [-n N]` | command | Last N ledger events of the scope with their hashes |
| `tl projections rebuild [--only NAME]` | command | Reset projectors and replay the ledger |
| `tl_cli.main:app` | typer app | The `tl` entry point |

## Depends on / used by
- Depends on: `tl_core`, `tl_adapters`, `typer`, `rich`.
- Used by: `just demo P0-I1`, `just rebuild-projections`, developers.

## Commands
```
uv run tl --help
just test packages/tl-cli
just demo P0-I1
```

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|
| `--db PATH` / `TL_DB` | `./dev/data/tl.db` | The SQLite ledger file (git-ignored under `dev/data/`) |
| `--actor` | `user:dev` | Actor recorded on events |

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P0-I1. Numbering is not available yet, so `--key` is required (Increment 3).
