# AGENTS.md — tl-cli

Read the root `AGENTS.md` first. These rules add to it.

- No business logic. Each subcommand parses options, makes one call into `tl_core.services` or `tl_adapters`, and prints. Rules, validation, and error classification belong in the services.
- Catch only `ServiceError` and `ConcurrencyError` (print `error: <message>` to stderr, exit 1). The `schema` and `pset` groups also catch `PackageError` and `SchemaCompileError`. Let every other exception surface.
- Every command passes `source="cli"`. The database comes from `--db` or `TL_DB`; never hard-code a path.
- Output formats are part of the demo and tests: change a line only with its test.
