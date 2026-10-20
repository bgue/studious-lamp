# AGENTS.md — tl-mod-correspondence

Read the root `AGENTS.md` first. These rules add to it.

- The current-state table of a record type is generated from `schema/modules/correspondence/`, never written by hand (root rule 4). A projector in this package owns only derived tables named `proj_correspondence_<name>`.
- Handlers append events through the unit of work and never update or delete one (root rule 3). Corrections are new events.
- No business logic in the TUI or the API route: they call the handlers here.
- Every handler and projector has a test beside it in `tests/`; a projector test replays the events twice and compares the rows.
- Read an item only through `registry`, `views`, `load_item` or `open_item`: they apply the viewer's class filter (ADR-0016). A raw `SELECT` on a `cur_correspondence_*` table is a leak. A hidden item, a foreign item and an unknown id raise the same `RecordNotFoundError` with the same text.
- No role guard, no `actor_roles` and no role-based routing in a workflow or a domain file (D6b). Who may run a command is its `access` word in `commands.py`; the API, CLI and MCP decide it from the authenticated principal.
- A clock's dates come from `clocks.py` replaying events against a versioned calendar. Never store a computed due date that the replay would not give, and never read a clock's date from the projection to decide a transition.
- Text that comes from outside (an email header, a subject, a file name) is checked with `textcheck.clean_text` before it becomes record text. The EML parser is bounded, refuses rather than truncates, and runs in the envelope; do not add a path that parses a message in the caller's process.
- Issuing a letter is a stub send (`delivery: stub`). Do not add a network call, an SMTP client or a fetch of anything named in a message.
- A test that sets a class owns the viewer for its whole body (`use_viewer`); the default viewer is the lowest class on purpose (L-P1-I5-2).
- Every Commercial command, and every command that touches a Commercial item or its clocks (generic link, file and property-set commands, and cancelling a time bar included), needs a controller viewer: the guards are `require_controller_for` and `controller_only`. A new command or a new generic guard must keep that.
- A feed card for a confidential stream is tagged through `subjects_of`. A new event type that makes a feed card is added to `POLICY_EVENT_TYPES` deliberately.
- The evidence trail and the register export are bounded. The trail is limited to depth 3, 200 nodes, 1000 links and 5000 events; the export to `MAX_ROWS` (5000). Do not raise `MAX_ROWS` or the trail bounds without an ADR.
