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
| `tl record create --project ID --title TITLE [--key KEY] [--segment NAME=VALUE]...` | command | Without `--key` the numbering pattern allocates the key (`P123-REC-0001`) |
| `tl link add|suggest --project ID FROM TO [--relation R] [--pin P] [--note N]` | command | Create an active link, or a suggestion with `--confidence`; prints the link id, relation and status |
| `tl link list --project ID KEY [--all]` | command | Links in both directions (`out`/`in`, label, other key, status, pin, id) and the expected links still missing |
| `tl link accept|decline|verify|repin|retract|flag --project ID LINK_ID ...` | command | Link lifecycle; `retract` and `flag` need `--reason`; a declined suggestion is not made again |
| `tl link trace --project ID KEY [--depth N] [--direction out|in|both]` | command | Records reachable through links, as an indented tree with stale and broken marks |
| `tl wf show --project ID KEY [--role R]...` | command | Workflow state and, for each transition, whether its guards pass |
| `tl wf transition --project ID KEY NAME [--role R]... [--reason T]` | command | Run a transition; a blocked one prints every guard and exits 1 |
| `tl lake sync` | command | Calls `sync_lake`; copies new ledger events into the lake as one snapshot, prints the seq range and silver row counts |
| `tl lake rebuild --yes` | command | Deletes the lake's files and loads everything again from the ledger; refuses without `--yes` |
| `tl lake status` | command | Seq the lake reflects, the snapshot, the sync count and the row count of each table |
| `tl lake tables` | command | Lake tables and their columns |
| `tl lake query [--limit N] [--json] SQL` | command | Calls `LakeQueryService.query`; one read-only SELECT, refused queries exit 1 |
| `tl_cli.main:app` | typer app | The `tl` entry point |

## Depends on / used by
- Depends on: `tl_core`, `tl_schema`, `tl_adapters`, `typer`, `rich`.
- Used by: `just demo P0-I1`, `just demo P0-I2`, `just demo P0-I3`, `just rebuild-projections`, developers.

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
Introduced in P0-I1; `schema` and `pset` groups added in P0-I2; `link` and `wf` groups, key numbering and `--segment` added in P0-I3. `--role` is a stub list (no auth yet).
