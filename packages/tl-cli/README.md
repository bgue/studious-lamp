# tl-cli (`tl_cli`)

The `tl` command: a thin typer front end over the `tl_core` command and query services and the SQLite and Postgres adapters (§25.2, §29.4). The database is the root `--db` / `TL_DB`: a SQLite file or a `postgresql://` URL, read through `tl_adapters.db.as_target` into `ctx.obj`.

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl init [--dev]` | command | Create the ledger file and its schema; `--dev` also creates the dev account `demo` / `demo` (admin) where `TL_ENV` is dev, demo or test |
| `tl login USERNAME [--password-stdin]`, `tl logout`, `tl whoami` | commands | Sign in to the ledger (`--db`): the password from a hidden prompt or one line of stdin, never an option. The session token is kept in `TL_SESSION_FILE` (default `~/.config/throughline/session.json`, mode 0600, one entry per ledger, 12 hours). `logout` ends it in the ledger; `whoami` prints the actor and roles (`tl_cli.login`, `tl_cli.session`) |
| `tl admin user ls|show|add|roles|disable|enable|reset-password`, `tl admin token ls|issue|revoke` | commands | Accounts and agent tokens; each needs a signed-in admin (`tl_cli.admin_user`, `tl_cli.admin_token`). A token is printed once, alone on stdout. `roles NAME` replaces the roles (`--role`, repeat) or changes one (`--add`, `--remove`); the roles are `admin`, `user` and `document_controller` (ADR-0013) |
| `tl admin bootstrap --username N`, `unlock NAME`, `audit [--event E] [--username N] [--limit N] [--json]` | commands | Local recovery, no sign-in (`tl_cli.admin`): create the first admin or reset an existing admin's password and lock, clear a sign-in lock, read the authentication audit. They write the OS user to the audit row |
| `tl_cli.actor_hook`, `tl_cli.session.check_actor` | module | The default `--actor` of every command is the signed-in user; a named actor is honoured only for the session's own actor, or in a dev, test or ci setup on a ledger file. A `--db` with `scheme://` always needs a session (ADR-0009 section 7) |
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
| `tl tag create NUMBER --project ID [--class C] [--service S] [--pset PSET.PROP=VALUE] [--allow-violation]` | command | Create an engineering tag: the number is checked against the registry pattern (every problem is listed), the class binds psets; prints the segments, the conformance and what is missing. `--allow-violation` keeps a number that breaks the pattern as a violation and needs the admin role (T09b) |
| `tl tag import FILE --mapping TEMPLATE --project ID [--apply] [--skip-invalid] [--job NAME]` | command | Preview a legacy tag list as a plan (`new`, `changed`, `unchanged`, `removed`, `invalid`, each invalid row with its reason); `--apply` writes it in one unit of work with source `import:<job>` and needs the admin role (T10c) |
| `tl standards load FILE [--dry-run]`, `ls`, `show`, `values`, `add-value`, `close`, `close-value` | commands | The company standards registry: load an edition (idempotent), list and show entries, a code list's values as a scope sees them, add or close a value. Writes need the admin role, except a project value (`--project`) the list's policy allows (T09a) |
| `tl standards class define|ls|show|revise|close` | commands | Tag classes and the property sets they require; define, revise and close need the admin role (T09e) |
| `tl tag show|ls|reclassify|rename|split|merge ...` | command | Show a tag, list tags with filters, move a tag to another class, replace it by one or several (the old tag is superseded) or merge several into one (T09b) |
| `tl tag report summary|missing|violations --project ID [--json]` | command | Tags by class and state, tags lacking what their class requires, numbers that break the pattern (T11) |
| `tl doc register|show|ls|update|supersede|void|confidentiality ...` | command | Register a document under its number (checked against the registry pattern), show it with its revisions and links, list the register, change register fields; `supersede`, `void` and `confidentiality` need the document controller or admin role (`require_controller`, P1-I2-T09a, ADR-0013) |
| `tl doc rev create|issue|supersede|void|ls ...` | command | Start the next revision as a draft, list them; `issue` and `supersede` need the document controller or admin role and flag the links the class-aware rule names (T09b) |
| `tl doc rendition add|register-signed|replace-signed|ls ...` | command | Upload a file into a revision and register it as a rendition; the checks that need no file run before the upload; the signed copy is a controller's (T09c) |
| `tl doc link|stale|diff|repin ...` | command | Link a record to a document floating or pinned, list stale links, show what changed between two revisions, re-pin after the diff (`--apply` confirms) (T09d) |
| `tl doc report register|history|overdue|transmittals|stale --project ID [--json]` | command | The base document reports (T11b) |
| `tl doc import FILE --mapping TEMPLATE --project ID [--apply] [--skip-invalid] [--job NAME]` | command | Preview a legacy DMS register as a plan (`new`, `exists`, `invalid` with reasons; at most 1000 rows and 5 MiB); `--apply` registers the new documents in one unit of work with source `import:<job>` and needs the document controller or admin role (T12e) |
| `tl transmittal create|issue|answer|close|void|ls|show ...` | command | Draft a transmittal of issued revisions to named recipients, issue it (controller), record the response, close or void it (T09e) |
| `tl review open|answer|on-behalf|close|override|ls ...` | command | Open a review round on a draft revision, answer as yourself, close it; `on-behalf` and `override` need the document controller or admin role (T09f) |
| `tl link accept|decline|verify|repin|retract|flag --project ID LINK_ID ...` | command | Link lifecycle; `retract` and `flag` need `--reason`; a declined suggestion is not made again |
| `tl link trace --project ID KEY [--depth N] [--direction out|in|both]` | command | Records reachable through links, as an indented tree with stale and broken marks |
| `tl feed post --project ID BODY [--importance low|normal|high] [--actor A]` | command | Post to the project feed; prints the post id, its tags and how many links were suggested (a `#KEY` tag suggests a `references` link, nothing else changes) |
| `tl feed ls --project ID [--record KEY [--linked]] [--tag T] [--posts|--events] [-n N]` | command | The feed newest first: `id  kind  time  author  text`, cards with their records, posts with their reactions; a retracted post reads `[retracted]` |
| `tl feed retract --project ID POST_ID --reason R`, `tl feed react --project ID POST_ID [--reaction ack|+1|resolved] [--off]` | command | Tombstone a post; set or clear an acknowledgement |
| `tl proposal ls (--project ID \| --company) [--status pending\|accepted\|rejected\|failed\|all] [--agent A] [-n N]` | command | The review queue of agent proposals, oldest first: `id  status  agent  tool  summary` |
| `tl proposal show ID` | command | One proposal and the command it would run (`command CreateRecord`, then `  field json` lines) |
| `tl proposal accept ID [--role R]... [--actor user:ID]` | command | Run the proposal's command as you, tagged with the agent as source, with the workflow roles of your session (`--role` is a claim honoured only where `--actor` is: a ledger file in a dev, test or ci setup; elsewhere it must name a role your session holds); a command that cannot be applied prints `failed ID` and `error: ...`, exits 1, and changes nothing; an `agent:` actor is refused |
| `tl proposal reject ID --reason R [--actor user:ID]` | command | Close a pending proposal; the command never runs |
| `tl wf show --project ID KEY [--role R]...` | command | Workflow state and, for each transition, whether its guards pass, judged with the roles of your session (`--role`: dev-path claim only, as for `proposal accept`; `tl_cli.session.workflow_roles_of`) |
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
| `tl sim create|advance|inject|status|assert|run|seed` | command | The simulator (`tl_sim.cli`): create a seeded simulated project, play working days through the API, queue events, show the ground-truth digest, check the suite against the log (exit 1 on a difference); `seed --scale xs|s|m` is what `just seed` runs. See `docs/runbooks/simulator.md` |
| `tl webhook add --project ID --name N --url U [--mode M] [--event-type T]... [filters]` | command | Create a subscription; prints `subscription`, `secret_id`, `secret` (the secret once, on stdout) |
| `tl webhook ls [--project ID \| --company]` | command | One tab-separated line per subscription: id, status (`needs_secret` for an active subscription without a signing secret, as after a restore), mode, name, URL, delivered, pending, dead |
| `tl webhook test ID [--event-type T] [--allow-host H]...` | command | Send a signed catalog sample (header `webhook-test: 1`); exit 1 on a failure or a blocked target |
| `tl webhook replay ID (--from-seq N --to-seq M \| --since T --until T)` | command | Re-send a seq range or time range; prints `replayed <n>` |
| `tl webhook dlq ls [--subscription ID]`, `dlq redrive ID [--delivery D]...` | commands | List dead letters; re-enqueue them (runbook: `docs/runbooks/webhook-operations.md`) |
| `tl webhook disable \| enable \| rotate-secret ID (--project ID \| --company)` | commands | Pause, resume, or issue a new secret (printed once) with an overlap |
| `tl webhook run [--once] [--allow-host H]... [--threads N]` | command | The worker: dispatch and deliver; `--once` drains and prints a summary |
| `tl file reconcile [--verify]` | command | Ledger hashes versus the object store; exit 1 on a missing or corrupt object (runbook: `docs/runbooks/object-store-reconciliation.md`) |
| `tl archive keygen [--key PATH] [--force]` | command | Create the Ed25519 signing key pair (private PEM 0600 plus `.pub` hex); refuses to replace one |
| `tl archive seal [--archive DIR] [--key PATH] [--db TARGET] [--max-events N]` | command | Seal every event not yet archived; prints one line per segment and `record outside the archive: last_seq N manifest_sha256 SHA` (keep that line elsewhere) |
| `tl archive verify [--archive DIR] [--public-key FILE] [--db TARGET] [--deep] [--all] [--expect-last-seq N] [--expect-manifest SHA]` | command | Verify the archive (and a database); prints `divergence: <kind> segment=.. seq=..: <detail>` and exits 1 on the first divergence (runbook: `docs/runbooks/ledger-archive-and-verify.md`) |
| `tl ledger verify [--db TARGET]` | command | Recompute every event hash and check every scope chain in the database alone |
| `tl restore --from-archive DIR --db TARGET [--public-key FILE]` | command | Rebuild an empty SQLite file or Postgres database from the archive alone (runbook: `docs/runbooks/restore-from-archive.md`); warnings on stderr |
| `tl backup sqlite --to FILE` | command | Online snapshot of the SQLite ledger (runbook: `docs/runbooks/sqlite-backup-and-litestream.md`); refuses a Postgres target and points to pgBackRest and `tl archive seal` |
| `tl_cli.file_reconcile` | module | `tl file reconcile`: compare the ledger's file rows with the object store |
| `tl_cli.webhook_common` | module | Helpers shared by the `tl webhook` commands: the unit-of-work factory, scope and error output |
| `tl_cli.webhook_ops` | module | The second half of `tl webhook`: `dlq ls`, `dlq redrive`, `disable`, `enable`, `rotate-secret` |
| `tl new module NAME`, `tl new record-type MODULE.Class`, `tl new projector MODULE.name [--event T]...` | commands | Scaffold from templates (`--root DIR`, `--dry-run`): a module package, with its schema header and spec page; a record type (schema stub, create handler, tests, spec page); a projector for a derived `proj_<module>_<name>` table. Never overwrites, writes nothing when any file exists; the output passes `just check` and its own tests. The kinds not built yet (correspondence-domain, action, rule, enricher, connector, report, extractor) are follow-ups |
| `tl_cli.scaffold` | package | The engine behind `tl new`: names (`names.py`), `Plan` and `write_plan` (`engine.py`), one planner per kind and the text templates under `templates/` |
| `tl types sync ROOT [--strict]`, `ls [--status S]`, `show REF`, `validate PATH`, `lock PATH`, `deprecate REF --reason`, `watch ROOT` | commands | Extension record types (brief 31; `tl_cli.extypes`): register or quarantine every package under ROOT (a repeat prints `up to date`), list, show, check one package, write `type.lock`, retire a version, poll a directory. Runbook: `docs/runbooks/extension-types.md` |
| `tl types quarantine ls`, `recheck RECORD_ID` | commands | `tl_cli.extypes_quarantine`: what the registry refused (packages, conflicts, damaged record bodies) and a second verification of a damaged body |
| `tl config ls|get|history|set|reset|lock|revert|diff|export|import` | commands | about:config (P0-I8 workstream A): `tl_cli.config` (read, change, lock, undo) and `tl_cli.config_exchange` (diff, YAML export and import) in one group. `--project`, `--user` or `--company` picks the layer; `--reason`, `--accept-risk` and `--at` as the key needs. Runbook: `docs/runbooks/settings.md` |
| `tl_cli.actors` | module | `refuse_agent`: the write commands of `tl config` refuse `--actor agent:...` (exit 1, `agent_must_propose`); an agent proposes through MCP |
| `tl lake sync --watch` | option | Keep syncing, waiting `lake.sync.interval` (read again before every wait; `tl_cli.lake.watch_loop`) until Ctrl+C; a failed sync prints `error:` and the watcher goes on |
| `tl projections rebuild` | command | Also records that the `rebuild` and `reindex` setting effects were carried out when it rebuilds every projector |
| `tl_cli.main:app` | typer app | The `tl` entry point |
| `tl derive schema register|ls|show|retire`, `tl derive open|content|start|ls|jobs|cancel|worker`, `tl derive show|report|rows|diff|check|validate`, `tl derive publish|compensate` | commands | Derived documents (P1-I3, ADR-0014; modules `derive`, `derive_schema`, `derive_run`, `derive_read`, `derive_publish`, shared helpers in `derive_support`). Registering schemas, publishing tags and compensating need an admin, publishing documents a controller (`require_admin`, `require_controller`); every writing command declares `--actor` with the hooked default and checks it again (`acting`). `worker --once` runs the queue (`--requeue` after a restore). Runbook: `docs/runbooks/derivation-pipeline.md` |

## Depends on / used by
- Depends on: `tl_core`, `tl_schema`, `tl_adapters`, `tl_api` (token file helper), `typer`, `rich`.
- Used by: `just demo P0-I8-B` (`tl types`), `just demo P0-I8-C` (scaffolders), `just demo P0-I1`, `just demo P0-I2`, `just demo P0-I3`, `just rebuild-projections`, developers.

## Commands
```
uv run tl --help
just test packages/tl-cli
just demo P0-I1
```

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|
| `--db TARGET` / `TL_DB` | `./dev/data/tl.db` | The ledger: a SQLite file (git-ignored under `dev/data/`) or a `postgresql://` URL (`?sslmode=`, `?options=-csearch_path=<schema>`). Prefer `TL_DB` for a URL: a command line is visible in the process list. A value that is not a target (another `scheme://`, no user, an unescaped `@`, an unsupported `sslmode`) is `error: ...`, exit 2; an unreachable server, a wrong password or a missing database is one `error: cannot reach the database ...` line, exit 1, from every command. Output shows the URL without its password |
| `--actor` | the signed-in user (`user:dev` in a dev setup without a session) | Actor recorded on events; see `tl_cli.actor_hook` |
| `TL_SESSION_FILE` | `~/.config/throughline/session.json` | Where `tl login` keeps the session token (mode 0600) |
| `TL_SIM_AGENT_TOKEN` | unset | An agent token for the simulated assistant outside a dev setup (`tl_cli.sim_agent` makes one in dev) |
| `--dir PATH` / `TL_SCHEMA_DIR` | `schema/fixtures` | Package directory for `tl schema` commands; file slots are read from its `files/` folder |
| `TL_WEBHOOK_ALLOWLIST` | empty | Comma-separated egress allow-list for `tl webhook test` and `run` |
| `TL_ARCHIVE_DIR`, `TL_ARCHIVE_KEY`, `TL_ARCHIVE_PUBLIC_KEY` | `./dev/data/archive`, `dev/data/archive-signing.key`, `dev/data/archive-signing.pub` | Archive directory and keys for `tl archive` and `tl restore` |
| `TL_OBJECT_STORE`, `TL_OBJECT_ROOT`, `TL_OBJECT_SECRET`, `TL_ENV`, `TL_S3_*` | `fs`, `./dev/data/objects`, none, unset | Object store for `tl file`; see `packages/tl-adapters/README.md`. `just` exports `TL_ENV=dev` |

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Identity commands (`login`, `logout`, `whoami`, `admin ...`, `init --dev`, the actor hook, `sim_agent`) added in P1-I0 workstream A (`docs/tickets/P1-I0/README-A.md`; operations: `docs/runbooks/accounts-and-access.md`). Introduced in P0-I1; `config` group, `lake sync --watch` and the effect record of `projections rebuild` added in P0-I8 workstream A; `schema` and `pset` groups added in P0-I2; `link` and `wf` groups, key numbering and `--segment` added in P0-I3; `file` group added in P0-I4 workstream B; `dev` group added in P0-I4 workstream C; `webhook` group added in P0-I5 workstream B; `new` group (scaffolders) added in P0-I8 workstream C; `feed` group added in P0-I6 workstream A; `proposal` group added in P0-I6 workstream B; `backup`, `archive`, `ledger` groups and `restore` added in P0-I7 workstream A. Workflow roles come from the session; `--role` is a dev-path claim only (P1-SEC1, ADR-0013 addendum). `types` group added in P0-I8 workstream B (`docs/tickets/P0-I8/README-B.md`); `tl tui --type`.
