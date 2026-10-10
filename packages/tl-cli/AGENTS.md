# AGENTS.md — tl-cli

Read the root `AGENTS.md` first. These rules add to it.

- No business logic. Each subcommand parses options, makes one call into `tl_core.services` or `tl_adapters`, and prints. Rules, validation, and error classification belong in the services.
- Catch only `ServiceError` and `ConcurrencyError` (print `error: <message>` to stderr, exit 1). The `schema`, `pset`, `link` and `wf` groups also catch `PackageError` and `SchemaCompileError`; `link` and `wf` also catch `ExpectedLinkError`, pydantic `ValidationError` (printed as `field: message`), and `wf` prints the guard lines of a blocked transition. Let every other exception surface.
- Every command passes `source="cli"`. The database comes from `--db` or `TL_DB`; never hard-code a path.
- Output formats are part of the demo and tests: change a line only with its test.
- `tl file` builds its `FileService` from the environment (`make_object_store`, `object_secret`); a missing secret is an `error:` line, never a default. Hashing a local file for the declaration is client work and stays here; verification is the service's.
- `tl webhook` prints a signing secret exactly once (`add`, `rotate-secret`), on stdout as `secret <value>` with a hint on stderr; no other command, log line or error message may print one. Egress is fail-closed: a target is allowed only through `--allow-host` or `TL_WEBHOOK_ALLOWLIST`.
