# Runbook — correspondence: receive, triage, reply, clocks, email in, confidentiality and the register export

Purpose: run project correspondence day to day: log what arrives, triage it, issue a reply, keep the response clocks honest, read in an email, restrict a sensitive letter and hand out the register. Brief: §9 M10, §18.10, §24.6.

## When to use
- A letter or email arrived, or a letter must go out.
- A response clock is due, overdue or wrong.
- An email must be filed with its attachments and its thread.
- An item must be hidden from most people, or its readers named.
- Someone needs the register as a spreadsheet.

## Before you start
- Access needed: a signed-in person (`tl login <name>`) receives, updates, drafts, triages, answers, closes, voids a draft, assigns a thread and runs the clock commands. A document controller or admin session is needed to issue a letter, void a received item, replace an item, set a class or name readers, run the sweep, register or retire parties and clauses, and to include a class in the register export (ADR-0013). A refusal says `needs the document_controller or admin role`. An agent only reads and proposes (`propose_triage`); a person accepts the proposal (`proposal-review-queue.md`).
- Safe to run during business hours: yes. Each command is one unit of work. Issuing a letter stores a PDF and records `delivery: stub`: nothing is sent anywhere. Send the stored PDF yourself.
- Commands take the ledger from `--db` or `TL_DB` and the project from `--project`. Items are named by number, for example `P123-COR-0001`. Files go to the object store at `TL_OBJECT_ROOT`.
- Confidentiality is enforced (ADR-0016): an item above your clearance is "no item" for you. A controller sees `restricted`; a `privileged` item is read by the accounts named on it.

## Steps
### Log a letter that arrived
1. `uv run tl corr receive --project P123 --subject "Revised programme" --from "Acme Construction" --file letter.pdf` numbers the item, marks it Received and stores the file as `original`. A date in `--received-on` after today is refused.
2. `uv run tl corr suggest P123-COR-0001 --project P123` shows the domain and subtype the engine proposes and why. It only proposes.
3. `uv run tl corr triage P123-COR-0001 --project P123 --accept` confirms it (or `--domain general --subtype letter`). Triage starts the clocks the subtype defines for receipt and links records named with `--ref`. In the TUI: `F12`, key `2`, `a`.
4. Wrong domain? `uv run tl corr reclassify P123-COR-0001 --project P123 --domain document_control --subtype submittal --reason "..."` before it is issued.

### Reply
1. `uv run tl corr draft --project P123 --subject "Re: Revised programme" --to "Acme:ann@acme.example" --reply-to P123-COR-0001 --domain general --subtype letter --body-file reply.txt` starts a Draft in the thread of the letter it answers.
2. Controller: `uv run tl corr issue P123-COR-0002 --project P123` stores the PDF, records the stub send, answers the parent and starts the clocks of the subtype (the General letter: 14 calendar days). A date before today needs `--date-reason`.
3. `tl corr respond|close|void|supersede` record an answer, close, void a draft or a received item filed in error, or replace an item.

### Clocks
1. `uv run tl corr clock ls --project P123` lists open clocks, soonest first: key, state, due date, days left (negative once overdue), length, type, warnings. `--overdue`, `--all` and `--due-to` narrow it. The TUI shows the same on `F12`, key `3`.
2. `tl corr clock start|pause|resume|restart|meet|cancel` change one clock. Every change is an event with a reason; a clock is replayed from its events, so a mistake is corrected by another event.
3. Controller: `uv run tl corr clock sweep --project P123` records `Warned` and `Expired`. Run it once a day (a scheduled job calls the same handler). It is safe to repeat.
4. A clock counts on the calendar named in its first event (`P123-default@1`). A calendar file never changes; a new version is a new file.

### Email in
1. `uv run tl corr mail ingest message.eml --project P123` reads the message in a child process with a clock and a memory limit. Refused messages say why in a fixed text: over a size or count bound, a hostile character, or a Message-ID already in the register. Nothing is cut short: a refused message is not partly filed.
2. The item is Received by email, the party is matched from the sender's address or domain, it joins the thread its headers, item numbers or subject point to, the whole message is kept in the module-only slot `message`, and each attachment goes through the upload guard and the file scan.
3. HTML is never rendered or fetched. A message with only an HTML part gets a placeholder text; read the original.

### Threads, parties and clauses
1. `tl corr thread ls|show` read threads; `tl corr thread assign P123-COR-0007 --thread P123-THR-0001 --answers P123-COR-0003` fixes a wrong placement by hand.
2. Controller: `tl corr party add|contact-add|contact-end|retire` and `tl corr clause add|retire` keep the registers. An email domain belongs to one active party. Contact positions count from 1 and are never reused.

### Restrict an item and export the register
1. Controller: `uv run tl corr class set P123-COR-0007 --project P123 --to restricted --reason "..."` (or `privileged` with `--grant user:NAME`). `tl corr class grant|withdraw|ls` change who is named.
2. `uv run tl corr report register --project P123 > register.csv` writes internal items only. A controller adds `--include-class restricted`. `--json` and `--out FILE` are available. A cell that starts with `=`, `+`, `-` or `@` is written with a leading quote.
3. `uv run tl corr report due --project P123 [--within 7]` lists answers owed; `tl corr report clocks [--json]` the clocks.

## Verify
- `uv run tl corr ls --project P123` is the master register: items, and the document-control transmittals as `[transmittal]` lines. The API (`GET /projects/P123/correspondence`), the TUI (`F12`) and the MCP tool `list_correspondence` list the same lines for the same reader.
- `uv run tl corr show <number> --project P123` shows the state, clocks, files and thread. `tl events` for a stream shows each change with its actor.
- `just demo P1-I5` runs the whole path on SQLite and Postgres.

## Roll back
- Nothing is edited in place. A wrong class: set the right one. A wrong thread: `thread assign`. A wrong clock: `clock cancel` and `clock start`. A received item filed in error: controller `tl corr void`. A letter issued in error cannot be unissued: `tl corr supersede` it with the corrected letter and say why.
- A restored ledger: rebuild projections (`rebuild-projections.md`); clocks and threads come back from their events.

## Related
- ADR-0010, ADR-0013, ADR-0016; `docs/modules/correspondence/README.md`; `documents.md` (transmittals and the register source); `accounts-and-access.md`; `proposal-review-queue.md`.
