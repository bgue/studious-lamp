# AGENTS.md — tl-mod-schemareg

Read the root `AGENTS.md` first. These rules add to it.

- The tables `cur_schemareg_*` are generated from `schema/modules/schemareg/` and written only by the projectors. A record is made with `create_module_record` (ADR-0010), never with `CreateRecord`. Keys are built here and hold `@` or `/`: pass `composed_key=True`.
- Package content is untrusted text: it is bounded (256 KiB), parsed with `parse_package` and checked to compose before any report is made. A report stored in an event is bounded too (1 MiB).
- Every transition goes through `common.transition` (`by_module=True`); the generic `TransitionWorkflow` is closed for these types. Never add a generic command to `generic_commands` for a package without a state guard.
- Roles are in `commands.API_COMMANDS` (`user` or `admin`). The handlers also bind work on a draft to the actor that drafted it, and refuse approval by the author, the submitter or the requester of a waiver. A new command picks its access on purpose; there is no default.
- An approval is for what was read: `Approved` carries the classification digest and `Publish` compares it; an adoption that is not additive carries the digest of the impact report and the handler computes it again. Do not accept a report a client sends.
- The registry source never fails the schema: a ledger without the tables, or a package that does not parse, is an empty or a smaller state, logged.
- Impact counts read the ledger as the lowest reader (`confidentiality.LOWEST`): the report is stored for every reader.
- No business logic in the CLI, the API route or the TUI: they call the handlers and the `registry` / `analysis` reads.
- Tests use `RegistryWorld` and run on both databases. Synthetic data only.
