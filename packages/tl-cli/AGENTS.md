# AGENTS.md — tl-cli

Read the root `AGENTS.md` first. These rules add to it.

- No business logic. Each subcommand parses options, makes one call into `tl_core.services` or `tl_adapters`, and prints. Rules, validation, and error classification belong in the services.
- Catch only `ServiceError` and `ConcurrencyError` (print `error: <message>` to stderr, exit 1). The `schema`, `pset`, `link` and `wf` groups also catch `PackageError` and `SchemaCompileError`; `link` and `wf` also catch `ExpectedLinkError`, pydantic `ValidationError` (printed as `field: message`), and `wf` prints the guard lines of a blocked transition. Let every other exception surface.
- The `lake` group catches `GuardError` (printed as `error: refused: <why>`) and `LakeError`; it opens the ledger only through `_ledger_snapshot`, the one place the database changes when Postgres arrives. Build all output before printing, so a failed command prints nothing on stdout.
- Every command passes `source="cli"`. The database comes from `--db` or `TL_DB`; never hard-code a path.
- Output formats are part of the demo and tests: change a line only with its test.
- `tl file` builds its `FileService` from the environment (`make_object_store`, `object_secret`); a missing secret is an `error:` line, never a default. Hashing a local file for the declaration is client work and stays here; verification is the service's.
- `tl webhook` prints a signing secret exactly once (`add`, `rotate-secret`), on stdout as `secret <value>` with a hint on stderr; no other command, log line or error message may print one. Egress is fail-closed: a target is allowed only through `--allow-host` or `TL_WEBHOOK_ALLOWLIST`.
- `tl feed` prints one line per item in a fixed column layout (`item_line`); the demo `dev/demos/P0-I6-A.sh` and `tests/test_cli_feed.py` depend on it. Tags and links are the service's work: the command prints what `handle_post` returned.
- `tl proposal` decides for the `--actor` (default `user:dev`) with `source="cli"`; accepting goes through `proposals.accept_or_fail`, which opens its own units of work, so the command never opens one around it. A failed accept prints `failed <id>` on stdout and `error:` on stderr and exits 1. The CLI never proposes (agents propose through MCP) and never decides for an `agent:` actor (the service refuses).
- `tl archive`, `tl ledger`, `tl restore` and `tl backup` catch only the archive, restore and backup errors (`ArchiveError`, `RestoreError`, `BackupError`) and print `error: <message>` to stderr with exit 1; a divergence is printed on stdout as `divergence: ...` with exit 1. Never print a Postgres password (use `display_target`), a private key or a signature value. The sealing, verification and restore rules live in `tl_core.archive` and `tl_adapters.restore`.
