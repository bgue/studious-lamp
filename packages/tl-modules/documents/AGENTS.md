# AGENTS.md — tl-mod-documents

Read the root `AGENTS.md` first. These rules add to it.

- The tables `cur_documents_*` are generated from `schema/modules/documents/` and never written by hand (root rule 4). The projectors here write their rows; no other code does.
- A record of this module is a row of `cur_core_record` (made by `Record.Created`) and a row of its own table (made by the `*.Defined` event of the same append). Create one through `create_module_record`, never with `CreateRecord`. A key the module builds holds `@` and passes `composed_key=True`; a key a caller types may not hold `@` (ADR-0010).
- Every projector moves the envelope row (`touch_record`). Handlers append through the unit of work and never commit (root rule 3); a failed check raises a `ServiceError` before anything is appended. Corrections are new events.
- Controlling acts belong to the document controller (and the admin) at the entry point (CLI `require_controller`, API access `controller`, action `control.command.<Name>`, ADR-0013), the handlers do not know the caller's role: issue, supersede, void a document, confidentiality, signed copies, issue a transmittal, on-behalf and override. A new command goes into `API_COMMANDS` with its access, and the access table in `tests/test_api_documents.py` (`EXPECTED_ACCESS`) is the pin: changing it is a decision (ADR-0013, which replaced ADR-0011's admin-only table). The link recovery commands stay the admin's.
- `by_module=True` on a core handler is for this module's own code paths only; a handler or CLI command must never pass it on behalf of a client. The system link sources (`rule`, `enricher`, `import`, `mapping`) are written only with it.
- The generic commands a record type allows are in `module.py` (`*_GENERIC_COMMANDS`) and checked by the guards in `guards.py`; a title, a register field, a workflow state or a void is never generic.
- The stale rule is `affects_pin` in `resolver.py` (ADR-0012). `flag_stale_on_issue`, `resolve_pin` and the reports all use it; do not copy the rule elsewhere.
- Every list, mapping and text of a command has a bound from `limits.py`; the import checks the same limits through `field_problems`, which builds `RegisterDocument` itself, so the plan cannot call a row new that apply refuses.
- A check that needs no file runs before an upload (`preflight_rendition`), so a refused command leaves no orphan file.
- No business logic in the TUI, the CLI or the API route: they call the handlers and `registry`/`views` reads here.
- Never name a module `types.py` (L-P0-I5-B1). Test helper modules have unique names (`docworld.py`).
- Every handler and projector has a test beside it in `tests/`; a projector test replays the events and compares the rows; tests use the `new_db` or `world` fixtures so they run on both databases. Dates in tests are past dates with a reason, or left out (L-P1-I2-9).
