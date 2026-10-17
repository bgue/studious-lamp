# Increment plan — P1-I5 M10 correspondence core, clock engine, General and Document-control domains

Status: in-progress
Supervisor session: 2026-10-17
Brief sections: §9 M10 (correspondence core, domain layer, domain definitions, cross-domain behaviour), §18.3 (restricted classes emit thin payloads), §18.10 (restricted classes are left out of exports), §8 (permissions), §7.2 (links), §20 (file slots), §9 M1 (the transmittal is a Document-control domain item)
Branch: `p1/i5` (trunk `claude/wizardly-allen-m2v96s`). Parallel increment: P1-I4 (`p1/i4`), which merges first.
Decisions: ADR-0010 (+ addenda), ADR-0011, ADR-0013, ADR-0014, and the new [ADR-0016](../../adr/0016-confidentiality-enforcement.md) (confidentiality; a delegated human gate).

## Objective
Build the correspondence core of M10 as a new module, `correspondence` (package `tl-modules/correspondence`, schema `schema/modules/correspondence/`): items (letters, emails, minutes) received or issued, threads, parties and contact roles, contract clauses and response clocks that count calendar or working days on a project calendar; a domain layer in which each domain is a compiled definition file (General and Document control now); one master register in which the I2 transmittals appear as Document-control items; and the **enforcement of confidentiality** that ADR-0011 left as a known limit: every read path filters by the item's class and fails closed. The clock engine is deterministic and recomputes from the ledger. "Send" is a stub: nothing leaves the machine.

## Demo
`just demo P1-I5` (SQLite and Postgres; `dev/demos/P1-I5.sh`, driver `dev/demos/p1_i5_demo.py`), one PASS line per clause:
1. receive a letter by upload (`tl corr receive`): item `P123-COR-0001`, state Received, the file in slot `original`;
2. triage proposes domain General (the suggestion engine reads the domain files; an agent's `propose_triage` is only a proposal) and a person confirms it (`tl corr triage`);
3. issue a reply (`tl corr issue`, a document controller's act): a PDF rendition from the General template is stored, the send is a stub, and a 14-calendar-day clock starts on the project calendar `P123-default@1`;
4. the clocks screen (TUI `F12`, `tl corr clock ls`) shows it with 14 days left and its warning thresholds;
5. a working-day clock skips weekends and the project holidays; pause and resume move the due date; the same ledger rebuilt gives the same clocks (recompute from the ledger);
6. the I2 transmittal appears in the master register (`tl corr ls`, TUI `F12` register tab) as a Document-control item;
7. confidentiality: a `restricted` item is invisible to a plain user and visible to a controller; a `privileged` item only to the accounts named on it; an item with an unknown class is hidden from everyone; the same holds over the API, MCP, the feed and the event stream;
8. email-in: a `.eml` file with an attachment is ingested (`tl corr mail ingest`) into an item with the attachment in a slot; a hostile message is refused.

## Design decisions (supervisor, within the plan)
| # | Decision |
|---|---|
| D1 | One module `correspondence`, ADR-0010 seam. Record types: `Correspondence`, `CorrespondenceThread`, `ResponseClock`, `ContractClause`, `Party`. `ContactRole` and the confidentiality `Clearance` are rows of side tables written by events of their parent record. `CorrespondenceDomain` is a stand-alone definition format (like `PublishMapping` in P1-I3), not a table: its JSON Schema is generated from the LinkML class and the compiler (`tl_mod_correspondence.domains`) refuses what it does not describe. |
| D2 | One workflow `correspondence.correspondence` (Draft, Received, Triaged, Issued, Responded, Closed, Void) serves every domain of this increment. A domain names its workflow by id (`workflow_ref`) and the compiler checks the id exists; per-domain workflows arrive with the first domain that needs one (P1-I6 Technical and Commercial). |
| D3 | The master register is one query over `Correspondence` rows plus **code-defined register sources**. `documents.transmittal` is the first: it maps `cur_documents_transmittal` rows to register rows with domain `document_control`, subtype `transmittal`. A domain file names a source by name; it never carries SQL. |
| D4 | Clocks: every figure of a clock comes from its events and from the calendar version named in its first event (`ResponseClock.Started` carries `calendar = code@version`, `due_on` and every parameter). The handler computes `due_on` with the engine; the projector copies it. `tl_mod_correspondence.clocks.replay` recomputes a clock from its events and the test suite compares it with the row. "Expired" depends on today's date, so it is read (`effective_state(row, today)`) and the sweep (`sweep_clocks`) records `Warned` and `Expired` events. Time comes only from the injectable clock (`tl_core.util.utcnow`). |
| D5 | Calendars are fixtures: `schema/fixtures/calendars/<code>@<version>.yaml`; a version never changes; a count that would leave the covered range is refused (fail closed, not assumed to be working time). |
| D6 | Access (ADR-0011/0013/0014 style, one word per command in `commands.py`): **user**: receive, update a draft or received item, triage confirmation, reclassify before issue, draft a reply, record a response, close, link, add a clock to one's own item, pause or resume or restart or cancel a clock, void a draft. **controller** (document controller or admin): issue (the external act), set confidentiality, grant or withdraw clearance, void a received item, supersede, register parties and clauses, sweep clocks. **Agents propose only**: `propose_triage` (the `ConfirmTriage` command) is the first correspondence proposal; an agent can also read what its clearance allows. The suggestion engine is a read, available to every reader. |
| D7 | Confidentiality: ADR-0016. A class is `internal` (any signed-in person and agent), `restricted` (document controller and admin; no agent), `privileged` (only the accounts named on the item; nobody else, an admin included). Any other value, and a record whose class cannot be read, is **hidden from everyone** (fail closed). The filter lives in `tl_core.confidentiality` and is applied in the shared read layer so the API, MCP, TUI and CLI inherit it; a test walks every read route and tool. Documents get the same classes (internal, restricted). |
| D8 | Email-in parses untrusted input: stdlib `email` with `policy.default`, every count and size bounded, refuse rather than truncate, decoding in the D9 envelope of P1-I3, no HTML rendering, no remote fetch, no URL followed, attachments through the file service with the module's upload guard. Header text that becomes record text goes through `tl_core.text.clean_text` (P1-I4; a compatible copy is written here if the trunk does not have it yet). |
| D9 | "Send" is a stub: `Correspondence.Issued` carries `delivery = "stub"`, the PDF is rendered by `letter.py` (no library, deterministic), and nothing leaves the machine; there is no SMTP. |
| D10 | No new dependency. Licences named: none added (the PDF writer, the EML parser and the calendars use the standard library and PyYAML, already locked, MIT). |

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S1 | This plan, T02 LinkML (`schema/modules/correspondence/`), names, limits, generated DDL and catalog | Schema (human-gated: SCHEMA_APPROVALS) | orchestrator | done |
| S2 | References of T03a–c (projectors), T08a (threading keys), T07d (letter PDF), workflow, file slots, numbering and calendar and party fixtures (T01) | Interfaces first | — | done |
| S3 | T04 clock engine: calendars, `compute`, `replay`, handlers, sweep | Contractual clocks (§3 table) | orchestrator | planned |
| S4 | T05 domain compiler | Defines what a domain may configure | orchestrator | planned |
| S5 | T06 confidentiality: ADR-0016, `tl_core.confidentiality`, filters on every read path, walking tests | Security (§3 table; a delegated human gate) | orchestrator, security review | planned |
| S6 | Module reads, `views.py`, master register with sources, commands (receive, triage, issue, response, clocks, parties), API routes and `ApiClient`, MCP tools, client interface | Interfaces, access, agent actions | orchestrator, security review | planned |
| S7 | T11a EML parser bounds and the envelope call | Parser of untrusted input | orchestrator, security review | planned |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| T01 | Project calendar fixture (working days, holidays) and party fixtures | S (trivial) | — | done | S2 |
| T02 | LinkML `schema/modules/correspondence/*`: `Correspondence`, `CorrespondenceThread`, `ResponseClock`, `ContractClause`, `Party`, `ContactRole`, `CorrespondenceDomain` | S | — | done | S1 |
| T03a | Projector `CorrespondenceProjector` (item and clearance tables) | H | T02 | ready | |
| T03b | Projectors `ThreadProjector`, `ClockProjector` | H | T02 | ready | |
| T03c | Projectors `ClauseProjector`, `PartyProjector` (party and contacts) | H | T02 | ready | |
| T04 | Clock engine | S | T03b | planned | S3 |
| T05 | Domain definition compiler | S | T02 | planned | S4 |
| T06 | Confidentiality classes and filters on every read path | S | T03a | planned | S5 |
| T07a | Commands: receive, update, reclassify, record response, close, void | H | S6 | planned | |
| T07b | Triage: suggestion engine, `ConfirmTriage`, proposal | H | S6 | planned | |
| T07c | Issue: template to PDF rendition, stub send, clocks started, `IssueCorrespondence` | H | S6, T04 | planned | |
| T07d | Letter template filling and deterministic PDF (`letter.py`) | H | — | ready | |
| T08a | Threading keys: subject, message ids, item numbers, `match_thread` | H | — | ready | |
| T08b | Threading wiring: threads from headers, subject and keys; `responds to` and `superseded by` links | H | T07a, T08a | planned | |
| T09 | General and Document-control domain definition files, letter templates | H | T05 | planned | |
| T10a–d | TUI: master register, item view, triage inbox, clocks screen | H | S6 | planned | |
| T11a | EML parser (bounded, `policy.default`) | H | — | planned | |
| T11b | Email ingest command and `tl corr mail ingest` | H | T07a, T11a | planned | |
| T12 | Reports (master register, responses due or overdue, running clocks), demo, report | H/S | T10 | planned | |
| CLI | `tl corr` groups: item, triage, issue, clock, party, clause, report | H | S6 | planned | |

## Order of work
1. Plan, schema, names, projectors (references), pure helpers (threading keys, letter PDF): done. Stubs, provided tests and tickets for T03a–c, T07d, T08a; first relay.
2. While those run: T04 clock engine, T05 compiler, then T06 and ADR-0016.
3. S6: module reads, commands, API, MCP, client interface. Then the second relay: T07, T08b, T09, T10, T11, CLI.
4. Merge P1-I4 when the orchestrator says it has landed (merge commit, regenerate generated files and `uv.lock`, resolve conflicts).
5. Demo, docs, reports, gates, security review, report.

## Risks and escalation triggers
- **Confidentiality reaches every read path.** The risk is a path nobody listed. Mitigation: the filter sits in the shared read layer, defaults to the lowest clearance when no viewer is set, and a walking test enumerates routes and tools (as `test_api_reserved_identifiers` does).
- **P1-I4 conflicts.** The shared registries are edited additively, in their own lines and blocks.
- **Email parser.** Bounds and the envelope are the supervisor's; the reviewer and the security review repeat the hostile cases.
- Stop and escalate if a core contract (`ModuleSpec`, `Principal`, the proposal table) must change in a way another workstream consumes, or the class model needs a role that does not exist.

## Blocked / Decision
None yet.
