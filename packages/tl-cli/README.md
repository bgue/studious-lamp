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
| `tl schema hash TARGET` | command | Content hash of a scope's effective schema (`company`, `P123` or `project:P123`) |
| `tl schema lint` | command | Lint rules L001 to L007 over the package files; exit 1 on an error |
| `tl schema validate [TARGET...]` | command | Cross-package checks, compile and LinkML render of each scope |
| `tl schema reload` | command | Record `Schema.EffectiveChanged` for scopes whose effective schema changed |
| `tl pset set --project ID KEY PSET NAME=VALUE... [--layer L]` | command | Calls `handle_set_pset_values`; `NAME=null` unsets a value |
| `tl pset get --project ID KEY [PSET]` | command | Psets, stored schema hash and live conformance with issues |
| `tl_cli.main:app` | typer app | The `tl` entry point |

## Depends on / used by
- Depends on: `tl_core`, `tl_schema`, `tl_adapters`, `typer`, `rich`.
- Used by: `just demo P0-I1`, `just demo P0-I2`, `just rebuild-projections`, developers.

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
| `--dir PATH` / `TL_SCHEMA_DIR` | `schema/fixtures` | Package directory for `tl schema` commands |

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P0-I1; `schema` and `pset` groups added in P0-I2. Numbering is not available yet, so `--key` is required (Increment 3).
