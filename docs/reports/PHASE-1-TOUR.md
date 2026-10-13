# Phase 1 tour (interim): sign-in, standards, tags and document control

**Status: interim.** This tour covers what P1-I0, P1-I1 and P1-I2 added on top of the Phase 0 core. The final Phase 1 tour will extend this file at the Phase 1 exit, as the remaining increments land. Nothing here is a statement that Phase 1 is complete.

Purpose: show, with real screenshots and a plain account of today's practice, what the first three Phase 1 increments delivered: real accounts and sessions, the company standards registry with engineering tags, and the first document-control module. Every screenshot is generated: `uv run python dev/tour/phase1.py` builds a demo ledger, signs in as named people, drives the real terminal UI headless and runs the real commands, and writes the SVG files under `tour/phase-1/`. Written 2026-10-13. Read [PHASE-0-TOUR.md](PHASE-0-TOUR.md) first for the core these build on.

## What these three increments added

Phase 0 left the platform core without real authentication. **P1-I0** replaced the development identity stub with accounts, two roles (`admin` and `user`), signed-in sessions, agent tokens, an admin screen, and put the API, TUI, MCP server, simulator and every command group on either SQLite or PostgreSQL ([P1-I0 report](P1-I0.md), ADR-0009). **P1-I1** added the first domain module: a company standards registry (code lists, mnemonics, numbering patterns, tag classes) and engineering **tags** parsed and checked against it ([P1-I1 report](P1-I1.md), ADR-0010). **P1-I2** added **document control**: documents with registered numbers, revisions with a status class each, pinned links that go stale, transmittals, reviews and a legacy register import ([P1-I2 report](P1-I2.md), ADR-0011 and ADR-0012).

The demo project is made up: project `P123`, three people (`demo`, an admin; `amy` and `ana`, plain users), a locked-out `ben`, and one agent `triage`. Each `tl` command in the transcripts is run as a named person with their own session, and the prompt shows who (`amy$`). The clock is frozen at 2026-10-12, so dates are the same on every run.

**What is and is not enforced in Phase 1 so far.** There are two roles. Controlling acts (issuing a revision or a transmittal, loading standards, applying an import, managing accounts) need `admin`. Confidentiality is a recorded field (`confidentiality: -` in the screenshots), not an enforced rule, and there are no per-record access lists. A document-controller role that lets a person who is not an admin do the controlling acts is in progress (section 14).

| # | Increment | Capability | Screenshots |
|---|---|---|---|
| 1 | P1-I0 | [Sign-in and sessions](#1-sign-in-and-sessions) | `01a` to `01c` |
| 2 | P1-I0 | [Accounts, roles and agent tokens](#2-accounts-roles-and-agent-tokens) | `02a` to `02c` |
| 3 | P1-I0 | [Account lockout](#3-account-lockout) | `03` |
| 4 | P1-I0 | [An agent with a service token](#4-an-agent-with-a-service-token) | `04` |
| 5 | P1-I0 | [The same services on PostgreSQL](#5-the-same-services-on-postgresql) | `05` |
| 6 | P1-I1 | [The company standards registry](#6-the-company-standards-registry) | `06` |
| 7 | P1-I1 | [Engineering tags checked against their class](#7-engineering-tags-checked-against-their-class) | `07` |
| 8 | P1-I1 | [The tag register and the legacy tag import](#8-the-tag-register-and-the-legacy-tag-import) | `08a` to `08c` |
| 9 | P1-I2 | [The document register: a status class per revision](#9-the-document-register-a-status-class-per-revision) | `09a`, `09b` |
| 10 | P1-I2 | [Stale pins and the re-pin diff](#10-stale-pins-and-the-re-pin-diff) | `10a` to `10c` |
| 11 | P1-I2 | [Transmittals and review rounds](#11-transmittals-and-review-rounds) | `11a` to `11c` |
| 12 | P1-I2 | [The legacy DMS register import](#12-the-legacy-dms-register-import) | `12` |
| 13 | P1-I2 | [What a plain user cannot do](#13-what-a-plain-user-cannot-do) | `13` |
| 14 | P1-I2b | [Document controller role (P1-I2b, in progress)](#14-document-controller-role-p1-i2b-in-progress) | none yet |

## 1. Sign-in and sessions

![The TUI sign-in screen, with the dev-setup hint](tour/phase-1/01a-sign-in.svg)

![A wrong password is refused, without saying which half was wrong](tour/phase-1/01b-sign-in-refused.svg)

![Sessions on the command line: who you are, and an admin-only command refused to a user](tour/phase-1/01c-sessions-cli.svg)

**Reproduce:** `just tui` (the sign-in screen), `uv run tl login amy`, `uv run tl whoami`. The dev account `demo` / `demo` exists only when `TL_ENV` is `dev`, `test` or `ci`.

**Standard activity.** Each tool has its own login, often a shared one for the site office, and external parties get a spreadsheet by email instead of an account. Who made a change is whatever the tool's audit log can say, if it keeps one.

**Novel approach.** One account store backs every door: the API, the TUI, the `tl` commands and the MCP server. A person signs in with a name and a password (kept as a salted scrypt hash, never in the ledger, a log or an event) and gets a session of twelve hours; the CLI keeps it in an owner-only file per ledger, the TUI holds it in memory. The sign-in screen refuses with one message whatever was wrong, and the actor on every event is the signed-in account. The identity layer is a seam (`IdentityProvider`) that an external provider such as Entra ID can replace (P1-I0, ADR-0009).

**Unique value.** "Who did this" is the answer to a sign-in, not a convention, on every entry point, and the same account works in the terminal, over HTTP and for scripts. Honest limits: this is password sign-in for a handful of accounts; single sign-on, MFA and permission rules finer than two roles are not built. The seeded `demo` account is a development convenience: the server refuses a non-loopback bind while it is enabled, and `tl init --dev` is refused with `TL_ENV=prod`.

## 2. Accounts, roles and agent tokens

![Creating a person and an agent, issuing a token (hidden), listing both](tour/phase-1/02a-accounts-cli.svg)

![F10: the accounts screen, admins only](tour/phase-1/02b-admin-accounts.svg)

![F10, t: the agent tokens: label, expiry and state, never the token itself](tour/phase-1/02c-admin-tokens.svg)

**Reproduce:** `uv run tl admin user add ben --display-name "Ben C" --password-stdin`, `tl admin user add triage --kind agent`, `tl admin token issue triage --label "triage assistant"`, `tl admin token ls`; in the TUI press `F10` as an admin. Runbook: `docs/runbooks/accounts-and-access.md`.

**Standard activity.** An administrator creates logins in each system, a shared service account is handed to whatever integration needs one, and nobody can say afterwards which of the account's actions came from a person and which from a script.

**Novel approach.** An account is a person, an agent or a simulator, with roles (`admin`, `user`), and sign-ins, failures and locks are written to an authentication audit log (`tl admin audit`). An agent has no password: an admin issues it a token that is shown once, stored only as a SHA-256 hash, has an expiry and a label, can be revoked at once, and is checked again on every call it makes. The accounts screen and the tokens view show who exists, in what state, and what tokens are live, and they are the same service calls the CLI and API use (P1-I0, ADR-0009).

**Unique value.** People and automation are separately named, separately revocable and separately accountable, and the last administrator cannot be removed by accident. Honest limits: two roles only; no groups, no per-project roles and no approval workflow for dangerous settings yet.

## 3. Account lockout

![Five wrong passwords lock the name; the right one is then refused too; an admin unlocks on the machine](tour/phase-1/03-lockout.svg)

**Reproduce:** run `uv run tl login ben --password-stdin` five times with a wrong password, then once with the right one; `uv run tl admin user ls`, `tl admin audit --username ben`, `tl admin unlock ben`.

**Standard activity.** A password guesser is stopped, if at all, by whatever the tool vendor built; a locked-out user phones the administrator, who has no record of what was tried.

**Novel approach.** Failed sign-ins are counted per name: after five the name is locked for a time and even the correct passphrase is refused, so guessing gains nothing. A limiter per source address adds a second brake on the API. The failures and the lock are audited (`tl admin audit` shows `sign_in_failed x5` and `locked`), the accounts list shows the lock, and clearing it is deliberately a local administrator command with no API route (P1-I0, ADR-0009).

**Unique value.** An attacker cannot walk through a password list, and the attempt leaves a record an administrator can read. Honest limits: the lock is flat per name (not escalating), so someone who knows a name can lock that person out for a while; there is no alert yet when it happens.

## 4. An agent with a service token

![An agent proposes over MCP, a person accepts, a revoked token is refused at the next call](tour/phase-1/04-agent-service-token.svg)

**Reproduce:** `TL_AGENT_TOKEN=... uv run python -m tl_mcp` with a token from `tl admin token issue`; call `update_psets`; review with `tl proposal ls` and `tl proposal accept <id>`; revoke with `tl admin token revoke <id>`.

**Standard activity.** An AI assistant is handed an API key that can do whatever the key's owner can, the key lives in a configuration file, and revoking it means finding every place it was pasted.

**Novel approach.** The agent is whoever its token says. It reads freely, but its write tools only propose: a proposal is a ledger event holding the exact command, and a person accepts it (here `ana`), so the change is attributed to the person and the agent is the source. The agent has no accept tool, and an explicit allow-list of MCP actions means a new tool is closed to agents until someone opens it. The token is checked on every call: the screenshot revokes it while the agent's server is still running, and the very next call is refused (`invalid or expired token`) (P1-I0, ADR-0009).

**Unique value.** An agent is useful, auditable and switchable off in one command, and nothing it suggests changes a record until a person decides. Honest limits: a per-agent budget and display name are not built (one daily proposal limit applies to every agent), and an agent's access is the fixed allow-list, not a per-agent grant.

## 5. The same services on PostgreSQL

![Evidence kept from the P1-I0 gates (stored, not re-run by this tour)](tour/phase-1/05-postgres-evidence.svg)

**Reproduce:** `just dev up`, then `just demo P1-I0` (about three minutes per backend) and `just test-parity` (about an hour). The figures in the screenshot are copied from the [P1-I0 report](P1-I0.md) and were not produced by the tour, which uses SQLite only.

**Standard activity.** A product is demonstrated on one database and installed on another; the first production data is the first test of the second.

**Novel approach.** In Phase 0 only the library and the restore reached PostgreSQL; the API server, the TUI, the MCP server, the simulator and every `tl` command group opened SQLite files. P1-I0 gave all of them one backend factory that takes a SQLite path or a `postgresql://` URL, a test pins that no entry point imports the SQLite adapter, and the demo runs the same clauses on both. On a PostgreSQL ledger the CLI always needs a signed-in session.

**Unique value.** The laptop demonstration and the server installation are the same code on different storage, with a parity suite that must pass on both. Honest limits: the tour itself did not run PostgreSQL, a long parity run is the release gate for adapters, and writers on PostgreSQL still queue on one advisory lock.

## 6. The company standards registry

![Load with a dry run first; loading again changes nothing; read the code lists and tag classes](tour/phase-1/06-standards-registry.svg)

**Reproduce:** `uv run tl standards load schema/fixtures/standards/co.acme.standards@1.0.0.yaml --dry-run`, then without `--dry-run`, `tl standards ls --kind code-list`, `tl standards values Area`, `tl standards class ls`. Runbook: `docs/runbooks/engineering-standards-and-tags.md`.

**Standard activity.** The company's naming rules, area and discipline codes, material codes and valve classes live in a PDF procedure and in a spreadsheet each project copies and edits. Projects drift, and nobody can say which project is using which edition.

**Novel approach.** The standards are data in the system of record: code lists (with a policy on whether a project may extend them, and crosswalks between code systems), mnemonics, numbering patterns and tag classes, loaded from one YAML edition by an admin. The load shows its plan first (counts of what it would create or skip), is idempotent (a second load creates nothing), and registry entries are versioned and closed rather than overwritten. A tag class names the property sets a tag of that class must carry (`ControlValve` requires `valve_data`) (P1-I1, ADR-0010).

**Unique value.** One company standard is readable by everyone through the same tools and is the thing that numbers, forms and checks are generated from, so a project cannot silently fork it. Honest limits: the sample code lists use placeholder labels; there is no publish-and-review workflow for a new edition, only an admin load; and the registry is not yet used by modules beyond tags and documents.

## 7. Engineering tags checked against their class

![Create a tag, see its segments and what its class requires, refuse a bad number with every problem, fix the data, rename by supersession](tour/phase-1/07-engineering-tags.svg)

**Reproduce:** `uv run tl tag create 47-FV-2001 --class ControlValve --service "Feed gas flow control" --project P123`, `tl tag create 47-XX-1 --project P123`, `tl pset set --project P123 47-FV-2001 valve_data manufacturer=Acme size_in=4`, `tl tag rename 47-FV-2001 47-FV-2002 --reason "..." --project P123`, `tl tag ls --all`.

**Standard activity.** A tag list is a spreadsheet: a number typed by hand, a class chosen from memory, and the data sheet for the valve filled in later or never. The same tag is keyed `47-FV-2001` in one system and `FV2001` in another, and a renumbering is an edit that erases the old number from history.

**Novel approach.** A tag number is parsed into typed segments against the registry's pattern (`area=47 mnemonic=FV seq=2001`) and a wrong number is refused with every problem at once (`'XX' is not a registered mnemonic`, `the sequence '1' must be written with 4 digits`). The class makes property sets mandatory: a new `ControlValve` is recorded as `nonconformant` with `valve_data class_required` until the data is entered, and then conforms. A rename creates a new tag that supersedes the old one, which stays in the ledger and keeps its number for good (P1-I1, ADR-0010).

**Unique value.** A tag's identity is checked at the door, its data requirements follow from its class, and its history survives renumbering. Honest limits: the demo uses a small sample standard (22 mnemonics, ten classes); split and merge are supersession too but are not shown; and the workflow guard that holds a tag back while its data is missing is not shown here.

## 8. The tag register and the legacy tag import

![A legacy instrument index: preview, refused to a user, applied by an admin, reported](tour/phase-1/08a-tag-import.svg)

![F8: the tag register, with class, status and what each tag lacks](tour/phase-1/08b-tag-register.svg)

![F8, v: only the tags that do not conform](tour/phase-1/08c-tag-register-violations.svg)

**Reproduce:** `uv run tl tag import dev/seed/legacy/instrument-index.csv --mapping dev/seed/templates/tag-list-instrument-index.yaml --project P123` (preview), add `--apply --skip-invalid` as an admin; `tl tag report summary|violations|missing --project P123`; in the TUI press `F8`, then `v`.

**Standard activity.** An instrument index arrives from the client or the old system as a spreadsheet. Someone fixes it by hand, pastes it into the new tool, and finds the bad numbers when a report fails, or never.

**Novel approach.** The import judges the file before it writes anything: the mapping maps columns to fields and the values to the standard's codes, and the preview lists every row that would be created, and every refused row with its line and reason (`line 13: duplicate of row 3`, `TYPE: 'ZZ' is not one of the mapped values`). Applying is an admin act. A legacy number that does not fit the pattern is kept, and marked as a violation, rather than silently fixed or dropped (`FV1009`, `47-XX-1010` in the violations report). The register shows each tag with its class, status and what it lacks, and `v` narrows it to the violations (P1-I1).

**Unique value.** A migration is done with the problems in view and nothing half imported, and the legacy numbers stay findable until the people who own them decide. Honest limits: the preview lists one tag the file does not mention (`- 47-FV-2002`, counted as `removed=1`) while the apply summary reports only created, changed and skipped, so read the runbook before relying on removals; and the import judges one list against the standard, it does not reconcile against other systems.

## 9. The document register: a status class per revision

![Registering a document: a wrong number is refused; revisions and renditions; issuing is an admin act](tour/phase-1/09a-documents-cli.svg)

![F7: the register, and one current revision per status class](tour/phase-1/09b-document-register.svg)

**Reproduce:** `uv run tl doc register ISO-1234 --project P123 --title "..." --type ISO --discipline PIP`, `tl doc rev create`, `tl doc rendition add`, `tl doc rev issue ISO-1234 A --status IFR` (admin), `tl doc show ISO-1234 --project P123`; in the TUI press `F7`. Runbook: `docs/runbooks/documents.md`.

**Standard activity.** A document register is a list in the DMS with one "latest revision" column. A revision issued for review and one issued for construction fight for that column, so the crew either builds from a drawing nobody has approved or from a superseded one.

**Novel approach.** A document number is checked against the company's pattern at registration (`ISO-12` is refused: four digits required). Revisions follow a configurable scheme (alpha here), carry a purpose, a status code with a class (`IFR` is `review`, `IFC` is `construction`) and renditions that are files in the file service. A document keeps one current revision per status class, so in the register `ISO-1234` shows `current D(IFC)` while revision C (`IFR`, for review) is also current in its own class and A and B are superseded. A user drafts; issuing is an admin's act (P1-I2, ADR-0011).

**Unique value.** The builder sees the revision to build from while the reviewers see theirs, and nobody argues over which one is "current". Honest limits: `confidentiality` is a recorded field and nothing enforces it; derived documents and document schemas are later (P1-I3).

## 10. Stale pins and the re-pin diff

![A pin goes stale when a construction revision is issued; the re-pin shows what changed and asks first](tour/phase-1/10a-stale-and-repin.svg)

![The stale rule knows revision classes: a review issue leaves a construction pin alone](tour/phase-1/10b-class-aware-stale.svg)

![F7, r: the re-pin dialog shows the diff before it asks](tour/phase-1/10c-repin-dialog.svg)

**Reproduce:** `uv run tl doc link 47-FV-1001 ISO-1234 --project P123 --pin A`, issue a later revision as an admin, then `tl doc stale --project P123`, `tl doc repin <link> --project P123` (shows the diff) and `--apply`; in the TUI press `F7`, highlight the document and press `r`.

**Standard activity.** A tag's data sheet points at "ISO-1234 rev A". When rev B is issued nobody tells the person who depends on A; the crew builds from the old isometric because the issue was not connected to the work that uses it (brief §0.1).

**Novel approach.** A link can pin a revision or float. Issuing a revision flags every pin that is behind as stale, by a class-aware rule (ADR-0012): a pin on an `IFC` revision is stale when a newer `IFC` is issued, not when an `IFR` is, so review drafts nobody builds from raise no alarm. The screenshot shows `IFR` C leaving the pins on B alone and `IFC` D flagging both. Re-pinning shows the diff first (status, what was issued and why, whether the file changed and its page count) and moves the pin only on a yes, in the CLI with `--apply` and in the TUI dialog.

**Unique value.** An engineer re-pins knowing what changed, and a crew is told when the drawing behind its work has moved, without being warned about drafts. Honest limits: a "newer revision in review" marker beside a healthy construction pin was the owner's option C and is a filed follow-up; in the tour, links are flagged at the moment a revision is issued.

## 11. Transmittals and review rounds

![A transmittal lists the exact issued revisions; issuing it is an admin's act](tour/phase-1/11a-transmittal.svg)

![A review round: who has not answered, and how late; the report drops a reviewer once they answer](tour/phase-1/11b-review-overdue.svg)

![F7, t: a transmittal draft with the current revision ticked](tour/phase-1/11c-transmittal-composer.svg)

**Reproduce:** `uv run tl transmittal create --project P123 --subject "..." --purpose for_construction --to "Site Office:Acme Construction:site@example.com" --revision ISO-1234@D`, `tl transmittal issue P123-TRN-0001` (admin), `tl transmittal show`; `tl review open ISO-2000 A --reviewer user:ana --due 2026-10-01`, `tl review answer ISO-2000@A/RC1 --outcome approved_with_comments`, `tl doc report overdue --on 2026-10-13`.

**Standard activity.** A transmittal is a form or an email with attachments, and the record of what was sent to whom is the sent folder. A review is a round of emails; who has not answered is found by reading the thread, and the deadline is in someone's calendar.

**Novel approach.** A transmittal's items are exact issued revisions (`ISO-1234@D`, with its status), numbered by the allocator (`P123-TRN-0001`), drafted by anyone and issued by an admin, and the response is recorded on the same record. A review round names its reviewers and a due date; each reviewer answers with an outcome and a comment, and the overdue report lists the reviewers who have not, with the days late (12 days at the report's date), and drops each one when they answer (P1-I2).

**Unique value.** "Which revision did we send them, and when" and "who still owes us an answer" are answered by a command, not by archaeology. Honest limits: recipients are names and email addresses recorded on the transmittal and the system sends no email (there is no mail sender in the code), and since confidentiality is not enforced a recipient list is not a permission list.

## 12. The legacy DMS register import

![A legacy register: previewed with every refusal explained, refused to a user, applied by an admin under a named job](tour/phase-1/12-dms-import.svg)

**Reproduce:** `uv run tl doc import dev/seed/legacy/dms-document-register.csv --mapping dev/seed/templates/document-register-dms-export.yaml --project P123` (preview), then `--apply --skip-invalid --job dms-2024` as an admin.

**Standard activity.** The old register is exported to a spreadsheet and loaded by script or by hand; rows with bad numbers or odd statuses are fixed in the spreadsheet, or dropped without anyone noticing, and the load leaves no trace of where the rows came from.

**Novel approach.** The file is judged against the live numbering pattern, the code lists and the command's own limits before anything is written. Every refused row says which line and why (`ISO-12: the sequence '12' must be written with 4 digits`, `'XYZ' is not a value of DocumentType`, `the title is blank`), applying is one unit of work, and the job's name is in the history of every document it created. The sample imports 9 documents and refuses 7 rows (P1-I2).

**Unique value.** A migration whose rejects are a to-do list rather than a surprise, with provenance on everything it wrote. Honest limits: this import registers documents; revisions with files and issue dates from a legacy register are a later loader (P1-I8), so imported documents show `current: -`.

## 13. What a plain user cannot do

![Five refusals: standards, issuing, transmittals, applying an import, account tokens](tour/phase-1/13-refused-acts.svg)

**Reproduce:** run any of the commands in the screenshot as a user with the role `user` (`uv run tl login amy`).

**Standard activity.** Who may issue a drawing or apply a bulk load is a convention written in a procedure; the tool lets any editor do it, and an audit finds out afterwards.

**Novel approach.** Every command and API route is checked against the signed-in role before it runs, with closed-by-default rules for agents (a new route or MCP tool is denied until someone allows it). The refusal is one fixed sentence: `forbidden: this command needs the admin role`. The same acts are refused over HTTP, and no one, an admin included, can change a document through the generic record commands: documents change only through the module's own commands (the P1-I2 demo, clause 8; `tests/auth`).

**Unique value.** The separation between drafting and controlling is enforced by the system, so a procedure is not the only thing standing between a draft and the field. Honest limits: the line is "admin or not" because there are two roles; a person who controls documents but should not manage accounts needs the document-controller role of the next section. Confidentiality (who may read a record) is recorded and not enforced, and there are no per-record access lists in Phase 1.

## 14. Document controller role (P1-I2b, in progress)

*This section is a placeholder.* A separate supervisor is building a document-controller role on `p1/i2b` (ADR-0011 filed it as a follow-up of P1-I2): a role that lets a person who is not an admin do the controlling acts of section 9 to 12, such as issuing a revision or a transmittal. It will be filled in after that work merges, with screenshots, a reproduce line and the three-part narrative. Until then the tour above is accurate for the two-role model: `admin` and `user`.

## What Phase 1 so far did not do

- **No permission model beyond two roles.** Confidentiality is recorded, not enforced; there are no per-record access lists; recipient emails on transmittals are data only.
- **No single sign-on or MFA**, and no escalating lockout or lockout alert.
- **Only two domain modules** (engineering data and document control); quality, piping, work packaging, materials and the rest of the brief's modules are later increments.
- **No derived documents or document schemas** (P1-I3), and no revisions with files or issue dates in the legacy import (P1-I8).
- **No "newer revision in review" marker** on a healthy construction pin (ADR-0012, option C).
- **The tour itself ran on SQLite.** The PostgreSQL evidence in section 5 is stored from the P1-I0 report.
- **This is an interim tour.** The increments after P1-I2 are not covered, and the final Phase 1 tour will replace this note.

The reports behind each section are [P1-I0](P1-I0.md), [P1-I1](P1-I1.md) and [P1-I2](P1-I2.md); the Phase 0 core they build on is shown in [PHASE-0-TOUR.md](PHASE-0-TOUR.md).
