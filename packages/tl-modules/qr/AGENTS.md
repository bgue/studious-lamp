# AGENTS.md: tl-mod-qr

Rules of the root `AGENTS.md` apply. Local rules:

- Table `cur_qr_scan_code` is generated; never hand-write DDL (use `ddl_for`).
- No event, field, log line or error text holds a code, only its hash (`code_hash`).
- A scan code is hidden through its target record (`target_id`), never by a class of its own.
- Events are immutable; a revoked code is a `ScanCode.Revoked` event, never an edit.
- The card contract is `tl_core.qr.types` (frozen once merged); this package does not redefine it.
- Tests live in `tests/`.
- Code functions come from `tl_core.qr.codes`; define none here. The secret code leaves only through
  `service.issue` and `service.rotate`; the generic command handler drops it.
- `resolve` is one exit for every miss and never writes; its first statement is the hash lookup.
- A label prints only what `labels.label_fields` returns.
- Hooks name this package only (`tl_mod_qr.*`); do not add `tl-api`, `tl-mcp` or `tl-cli` as dependencies.
