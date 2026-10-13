# AGENTS.md — tl-mod-documents

Read the root `AGENTS.md` first. These rules add to it.

- The current-state table of a record type is generated from `schema/modules/documents/`, never written by hand (root rule 4). A projector in this package owns only derived tables named `proj_documents_<name>`.
- Handlers append events through the unit of work and never update or delete one (root rule 3). Corrections are new events.
- No business logic in the TUI or the API route: they call the handlers here.
- Every handler and projector has a test beside it in `tests/`; a projector test replays the events twice and compares the rows.
