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
| `tl serve [--host H] [--port N] [--tokens PATH] [--insecure-dev]` | command | The REST API and event stream on the dev ledger (`--db`); loopback unless `--insecure-dev` (ADR-0005); same as `just serve` |
| `tl tui [--remote URL] [--token T] [--project ID] [--actor A]` | command | The TUI, embedded on the dev ledger by default; `--remote` (or `TL_REMOTE`) with a dev token (`TL_TOKEN`, preferred: arguments show in `ps`) runs it against `tl serve` |
| `tl dev token add ACTOR [--tokens PATH]` | command | Create a dev bearer token for `user:<id>` or `agent:<id>` in the token file (mode 0600, `TL_TOKENS`, default `./dev/data/tokens.json`); the token alone on stdout (ADR-0005) |
| `tl file put PATH --project ID --record KEY [--slot S] [--content-type T]` | command | Hash, upload (or dedupe) and attach a file; prints `file`, `slot`, `revision`, `status`, `size`, `sha256`, `deduplicated`, and `already attached` on a repeat |
| `tl file get FILE_ID --project ID --out PATH [--force]` | command | Write a file's bytes, checked against the recorded SHA-256 |
| `tl file ls --project ID --record KEY [--slot S] [--all]` | command | The current file per slot, or every file with `--all`; tab-separated `file_id, slot, revision, status, size, filename` |
| `tl webhook add --project ID --name N --url U [--mode M] [--event-type T]... [filters]` | command | Create a subscription; prints `subscription`, `secret_id`, `secret` (the secret once, on stdout) |
| `tl webhook ls [--project ID \| --company]` | command | One tab-separated line per subscription: id, status, mode, name, URL, delivered, pending, dead |
| `tl webhook test ID [--event-type T] [--allow-host H]...` | command | Send a signed catalog sample (header `webhook-test: 1`); exit 1 on a failure or a blocked target |
| `tl webhook replay ID (--from-seq N --to-seq M \| --since T --until T)` | command | Re-send a seq range or time range; prints `replayed <n>` |
| `tl webhook dlq ls [--subscription ID]`, `dlq redrive ID [--delivery D]...` | commands | List dead letters; re-enqueue them (runbook: `docs/runbooks/webhook-operations.md`) |
| `tl webhook disable \| enable \| rotate-secret ID (--project ID \| --company)` | commands | Pause, resume, or issue a new secret (printed once) with an overlap |
| `tl webhook run [--once] [--allow-host H]... [--threads N]` | command | The worker: dispatch and deliver; `--once` drains and prints a summary |
| `tl file reconcile [--verify]` | command | Ledger hashes versus the object store; exit 1 on a missing or corrupt object (runbook: `docs/runbooks/object-store-reconciliation.md`) |
| `tl_cli.main:app` | typer app | The `tl` entry point |

## Depends on / used by
- Depends on: `tl_core`, `tl_schema`, `tl_adapters`, `tl_api` (token file helper), `typer`, `rich`.
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
| `--dir PATH` / `TL_SCHEMA_DIR` | `schema/fixtures` | Package directory for `tl schema` commands; file slots are read from its `files/` folder |
| `TL_WEBHOOK_ALLOWLIST` | empty | Comma-separated egress allow-list for `tl webhook test` and `run` |
| `TL_OBJECT_STORE`, `TL_OBJECT_ROOT`, `TL_OBJECT_SECRET`, `TL_ENV`, `TL_S3_*` | `fs`, `./dev/data/objects`, none, unset | Object store for `tl file`; see `packages/tl-adapters/README.md`. `just` exports `TL_ENV=dev` |

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P0-I1; `schema` and `pset` groups added in P0-I2; `link` and `wf` groups, key numbering and `--segment` added in P0-I3; `file` group added in P0-I4 workstream B; `dev` group added in P0-I4 workstream C; `webhook` group added in P0-I5 workstream B. `--role` is a stub list (no auth yet).
