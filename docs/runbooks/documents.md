# Runbook — documents, revisions, stale links, transmittals, reviews and the legacy import

Purpose: run document control day to day: register and issue, handle stale pins, send transmittals, chase reviews, import a legacy register and recover from a mistake. Brief: §9 M1, §7.3, §29.6, §24.6.

## When to use
- A new project needs its document numbers and revision rules.
- A revision is ready to issue, or a link went stale and someone must look at it.
- A transmittal goes out, or a reviewer is overdue.
- A project brings a document register from another system.
- Something was registered, issued or signed in error.

## Before you start
- Access needed: a signed-in person registers, drafts, links, re-pins, answers reviews and previews an import. An admin session (`tl login <name>`) is needed to issue or supersede a revision, supersede or void a document, set the confidentiality class, register or replace a signed copy, issue a transmittal, record an answer for someone else, override a review outcome and apply an import (ADR-0011). Agents only read.
- Safe to run during business hours: yes. Each command is one unit of work. Two admins issuing the same revision at once are serialised by the writer lock; the second is refused.
- Commands take the ledger from `--db` or `TL_DB` (a SQLite file or a `postgresql://` URL) and the project from `--project`.
- Confidentiality is recorded but not enforced in Phase 1: every signed-in person and every agent can read all documents and transmittals of a project, including recipient emails.

## Steps
### Set up a project
1. `uv run tl standards load schema/fixtures/standards/co.acme.standards@1.0.0.yaml` then `... co.acme.documents@1.0.0.yaml` (admin; see `engineering-standards-and-tags.md`). The second adds the document number pattern. Without a pattern any number is accepted.
2. Revision schemes and the issue statuses with their class are in `schema/fixtures/documents/revision-schemes.yaml`. Change them with a reviewed commit, not at run time.

### Register, revise, issue
1. `uv run tl doc register ISO-1234 --project P123 --title "..." --type ISO --discipline PIP`. A number that breaks the pattern is refused with every problem.
2. `uv run tl doc rev create ISO-1234 --project P123 --purpose "..."` starts the next revision as a draft.
3. `uv run tl doc rendition add ISO-1234 A sheet.pdf --project P123 --kind pdf --pages 3`. The state of the revision decides which kinds it takes; a refused command uploads nothing.
4. Admin: `uv run tl doc rev issue ISO-1234 A --project P123 --status IFR`. A date before today needs `--date-reason`.
5. First signed copy (admin): `tl doc rendition register-signed ISO-1234 A signed.pdf --project P123`; a correction is `replace-signed ... --reason "..."`.

### Handle stale links
1. `uv run tl doc stale --project P123` lists links whose pin should be looked at: the record, the document, the pin, what is current, the link id.
2. A pin goes stale when a newer revision is issued in the pinned revision's status class or a later one (ADR-0012): an IFR issued after an IFC leaves the IFC pin alone. Voiding or superseding the document flags every link.
3. `uv run tl doc repin <link> --project P123` shows what changed (status, issue, files); `--apply` moves the pin. In the TUI: `F7`, highlight the document, `r`.
4. A link a rule wrote cannot be changed with the generic link commands; an admin recovers it with `AdminFlagLink` or `AdminRetractLink` (reason required) over the API.

### Transmittals and reviews
1. `uv run tl transmittal create --project P123 --subject "..." --purpose for_construction --to "Name:Organisation:email" --revision ISO-1234@B` drafts it; the TUI composer is `F7`, `t`. Admin: `tl transmittal issue <number>`. Record the response with `tl transmittal answer`.
2. `uv run tl review open ISO-2000 A --project P123 --reviewer user:ana --reviewer user:bo --due 2026-10-20`. Each reviewer answers as themselves: `tl review answer ISO-2000@A/RC1 --outcome approved --actor user:ana`. An admin records for someone else with `tl review on-behalf`.
3. `uv run tl doc report overdue --project P123` names the reviewers who have not answered after their date. Close a round with `tl review close` (its opener or the author); a close milder than the worst answer needs an admin `tl review override`.

### Import a legacy register
1. Pick the mapping (`dev/seed/templates/document-register-dms-export.yaml`) and preview: `uv run tl doc import register.csv --mapping template.yaml --project P123`. Read the counts and the `!` lines: each invalid row has its line and every reason. A file takes at most 1000 rows and 5 MiB; split a larger one.
2. Fix the file, or apply with `--skip-invalid` to leave those rows out: `uv run tl doc import register.csv --mapping template.yaml --project P123 --apply --job <name>` (admin). The import registers documents only; the old revision, status and date are a note in the description. Revisions with files come with the legacy loaders (P1-I8).
3. A number already in the project is listed as `exists` and left alone.

## Verify
- `uv run tl doc ls --project P123` and `tl doc show ISO-1234 --project P123` show the state, the current revision and the links; the TUI `F7` shows the same. `tl doc report register|history|stale|transmittals --project P123` read the ledger.
- Every event of an import has source `import:<job>` and one correlation id.

## Roll back
- Nothing is edited in place. A document registered in error is voided (`tl doc void`, admin: every link to it goes stale); a draft revision is voided (`tl doc rev void`); a replaced document is `tl doc supersede ... --by`. A wrong signed copy is replaced with a reason. A wrong import is corrected with those commands; the history stays.
- A projection that looks wrong is rebuilt from the ledger: `docs/runbooks/rebuild-projections.md`.

## Related
- ADR-0010 (module storage and its addenda), ADR-0011 (permissions), ADR-0012 (class-aware stale pins); module spec `docs/modules/documents/README.md`.
- `docs/runbooks/engineering-standards-and-tags.md`, `docs/runbooks/accounts-and-access.md`, `docs/runbooks/object-store-reconciliation.md`.
