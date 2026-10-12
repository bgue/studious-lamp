# AGENTS.md — tl-mod-engineering

Read the root `AGENTS.md` first. These rules add to it.

- The tables `cur_engineering_*` are generated from `schema/modules/engineering/` and never written by hand (root rule 4). The projectors here write their rows; no other code does.
- A record of this module is a row of `cur_core_record` (made by `Record.Created`) and a row of its own table (made by the `*.Defined` event of the same append). Create one through `create_module_record`, never with `CreateRecord`.
- Every projector moves the envelope row (`touch_record`: `version`, `last_seq`, `updated_at`, and the conformance and schema hash the event carries). A projector that forgets leaves a stale `version` and every `expected_version` check fails.
- Handlers append through the unit of work and never commit (root rule 3); a failed check raises a `ServiceError` before anything is appended. Corrections are new events.
- Registry and tag class writes are for admins; the entry point (CLI `require_admin`, API action `admin.command.<Name>`) enforces it, the handlers do not know the caller's role. Keeping a number that breaks the pattern (`RecordTag`, `tl tag import --apply`) is admin-only too. `TAG_GENERIC_COMMANDS` in `module.py` is the only list of generic commands a tag allows; registry records allow none (ADR-0010 addendum).
- A caller never sets a tag's `origin`: `CreateTag` has no such field (it forbids extras); only `handle_record_tag(..., origin="import")`, called by the import service, writes `import`.
- Every list, mapping and text of a command has a bound from `limits.py`; a new command field gets one too.
- No business logic in the TUI or the API route: they call the handlers and `registry` reads here.
- Never name a module `types.py` (L-P0-I5-B1). Test helper modules have unique names (`engworld.py`, L-P1-I0A-1).
- Every handler and projector has a test beside it in `tests/`; a projector test replays the events and compares the rows; tests use the `new_db` or `new_engine` fixtures so they run on both databases.
