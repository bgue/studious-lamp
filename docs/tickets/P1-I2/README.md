# Increment plan — P1-I2 M1 Document control core

Status: in-progress
Supervisor session: 2026-10-13
Brief sections: §9 M1 (record types, revision control concepts, workflows), §7.1 and §7.3 (pinned and floating links, stale pins, re-pin), §15 (base reports), §20.1 (file slots), §8 (numbering), §9 M10 (Document-control domain: transmittals), §29.8 (module definition of done)
Branch: `p1/i2` (base: trunk `claude/wizardly-allen-m2v96s` at `1541eb4`, the P1-I1 merge)
Decisions: ADR-0008 (Phase 1 owner decisions), ADR-0009 (authentication), ADR-0010 (module record storage, with the generic-command addendum)

## Objective
Build the second module, `documents` (M1 document control core), on the seam P1-I1 set. A `Document` is registered under its number; it has `Revision`s whose codes follow a configurable scheme (A/B/C, 0/1/2, P1/C1); a revision has `Rendition`s (native, PDF, markup, signed) that are files in the file service; a document keeps **one current revision per status class**; a link can **pin a revision or float**, a pinned link goes **stale** when a newer revision is issued, and **re-pin** shows what changed between the two revisions before it is confirmed; `Transmittal`s and `ReviewCycle`s record the formal exchange and the review of revisions. The derived-document pipeline (`DerivedDocument`, `DocumentSchema`) is P1-I3, not here.

## Demo
`just demo P1-I2` (SQLite and Postgres). The commands a person types:
```
tl login demo                                   # password demo
tl standards load schema/fixtures/standards/co.acme.standards@1.0.0.yaml
tl standards load schema/fixtures/standards/co.acme.documents@1.0.0.yaml     # the document number pattern
tl doc register ISO-1234 --project P123 --type ISO --discipline PIP --title "Isometric, line 47-P-101" --first-revision
tl doc rendition add ISO-1234 A sheet-A.pdf --project P123 --kind pdf --pages 3
tl doc rev issue ISO-1234 A --project P123 --status IFR
tl doc link 47-FV-1001 ISO-1234 --project P123 --pin A          # a tag pinned to rev A
tl doc rev create ISO-1234 --project P123 --purpose "Issued for construction"
tl doc rendition add ISO-1234 B sheet-B.pdf --project P123 --kind pdf --pages 5
tl doc rev issue ISO-1234 B --project P123 --status IFC         # the tag's link goes stale
tl doc stale --project P123                                     # 47-FV-1001 -> ISO-1234 pinned A, current B
tl doc repin <link> --project P123                              # shows the diff summary; --apply confirms
tl transmittal create --project P123 ... && tl transmittal issue ...   # the transmittal lists rev B
```
Then: a rejected document number (`ISO-12`); a review cycle with an overdue reviewer in the report; a user cannot void a document or change a revision through a generic command; the API, the TUI register and an agent's MCP tools read the same documents.

## Design decisions (supervisor, this increment)
| ID | Decision | Why | Where |
|---|---|---|---|
| D1 | Five record types, each a row of `cur_core_record` plus a row of its own table (ADR-0010): `Document`, `Revision`, `Rendition`, `Transmittal`, `ReviewCycle`. A transmittal's items and a review cycle's reviewers are sub-tables (`cur_documents_transmittal_item`, `cur_documents_reviewer`), not records. | Links, psets, workflow and the feed need the envelope row; items and reviewers need no identity of their own. | `schema/modules/documents/` |
| D2 | Flat views `v_<module>_<class>` are generated for every module record class and the module reads through them. | ADR-0010 made the view a condition of the first consumer that needs a flat row; the register, history and transmittal log are that consumer. | `tl_schema.generators.ddl.view_ddl`, `registry.py`, `reports.py` |
| D3 | A document number is its record key. It is checked against the registry numbering pattern for `documents.Document` **when the company has one**; the type and discipline against `DocumentType` and `Discipline` **when those lists are registered**. Without a registry anything is accepted. The Acme pattern is a second edition file, `co.acme.documents@1.0.0.yaml`, because a standards file must be complete on its own. | The tag module works the same way; a project without standards must still be able to register documents. | `handlers/documents.py`, `schema/fixtures/standards/` |
| D4 | Revision schemes are data: `schema/fixtures/documents/revision-schemes.yaml` (three kinds: alpha with skipped letters, numeric, staged; the issue statuses and their classes; which scheme numbers a document by project and type). | "Configurable per project and document type" (§9 M1). The file is read per call like the workflows. | `schemes.py` |
| D5 | **Status classes**: `review` (IFR, IFA), `construction` (IFC, AFC), `record` (ASB). Issuing a revision makes it current for its class and supersedes the one that was; the document row mirrors the newest current revision (`current_revision_*`). Different classes coexist (A stays the current IFR while B is the current IFC). | §9 M1: "only one current revision per status class". | `handlers/revisions.py`, `invariants.py` |
| D6 | **Stale pins**: issuing any revision flags every active link pinned to another revision of the document (the core's `MarkPinsStale`); voiding or superseding a document flags every active link to it, pinned or floating (§7.3). A floating link is never stale because of a new revision. "Owners are notified" means the `Link.Flagged` events: they are catalogued, so webhook subscribers and the feed projector see them; a per-user notification setting is a later increment. | §7.3. No change to the core link interfaces. | `resolver.py` |
| D7 | A pin is the revision **code** on the link (`cur_links.pin`). `LinkToDocument` and `RepinDocumentLink` check that the pin names an issued revision; `current` pins the revision that is current now. The generic `AddLink` with a free pin remains possible and resolves as `unknown`. | The core link model already has a free-text pin; only the module knows the codes. | `resolver.py` |
| D8 | **Renditions**: the four file slots are on the Revision (`schema/fixtures/files/documents-revision.yaml`); a person uploads into a slot (generic `AttachFile`, allowed on Revision) and `AttachRendition` registers the available file as the controlled rendition. What a revision accepts depends on its state (Draft: native, pdf, markup; In Review: markup; Issued and Superseded: markup, signed; Void: none), checked at the upload by a generic guard (ADR-0010 second addendum) and again by `AttachRendition`. A newer native, pdf or markup rendition supersedes the older of its kind (markup is additive: each stays). The signed copy is an admin's act from the first copy (`RegisterSignedRendition`), write-once, and corrected only by `ReplaceSignedRendition` with a reason; `AttachRendition` refuses `signed`. At most 20 markups per revision. | The file service already does quarantine, scan, dedupe and slots; the module adds the control. | `handlers/renditions.py` |
| D9 | Three workflows, moved only by the module's commands (`handle_transition_workflow(..., by_module=True)`, a Python-only argument): `documents.document`, `documents.revision`, `documents.transmittal`. The generic `TransitionWorkflow` is closed to these types. | Issuing, voiding and superseding carry invariants a bare transition would skip. | `schema/fixtures/workflows/`, `tl_core/services/workflow.py` |
| D10 | Generic commands (ADR-0010 addendum): Document allows `SetPsetValues`, `AddLink`, `SuggestLink`; Revision allows `AddLink`, `SuggestLink`, `AttachFile`; Transmittal allows `AddLink`, `SuggestLink`, `AttachFile` (all three only as a draft, by a guard); Rendition and ReviewCycle allow none. Document, Revision and Transmittal also allow the six link-life commands at the end a link starts at. `UpdateRecord`, `VoidRecord` and `TransitionWorkflow` are never allowed. A link a module wrote by rule is flagged or retracted only by the module; the relation `supersedes` onto a module record is written only by the module. | The title, the state and a void are controlled changes. | `module.py`, `tests/test_generic_commands.py` |
| D11 | Access levels (ADR-0011, interim): the controlling acts are the admin's: `IssueRevision`, `SupersedeRevision`, `SupersedeDocument`, `VoidDocument`, `SetDocumentConfidentiality`, `RegisterSignedRendition`, `ReplaceSignedRendition`, `IssueTransmittal`, `RecordReviewOutcomeOnBehalf`, `OverrideReviewOutcome`, and the core recovery commands `AdminFlagLink` and `AdminRetractLink` (action `admin.command.<Name>`; CLI `require_admin`). Everything that prepares work is open to a signed-in person. Agents stay propose-only; no new agent action beyond the read tools. | ADR-0008 has two roles; there is no document controller role in Phase 1. No per-record ACLs, so ownership of a draft is not checked. | `commands.py`, `test_api_documents.py` |
| D12 | A document has at most one revision being prepared or reviewed (Draft or In Review); codes only go forward and a void revision keeps its code; a revision needs a PDF or native rendition to be issued; an issued revision is superseded, never voided. | Keeps "next code", "the open revision" and the history unambiguous. | `handlers/revisions.py` |
| D13 | A revision is In Review exactly while a review cycle on it is open; closing a cycle returns it to Draft with the outcome on the cycle. The document is In Review during the first review only. | One place decides what "in review" means. | `handlers/reviews.py` |
| D14 | Transmittal numbers are typed in or allocated by the numbering pattern `documents.Transmittal` (`P123-TRN-0001`). A transmittal carries issued revisions (Issued or Superseded), once each; only a draft can be voided. | A transmittal is a record of what was sent. | `handlers/transmittals.py`, `schema/fixtures/numbering/patterns.yaml` |
| D16 | Review cycle rules (ADR-0011): reviewers are active person accounts and at least one is not the revision's author; a reviewer records their own answer only; an admin records one on behalf with a comment (`recorded_by` in the event); a person cannot close with an outcome milder than the worst answer, only the opener or the revision's author closes, and a round nobody answered closes as `withdrawn` (not a rejection); an admin overrides with a reason (`worst_answer` in the event). | Closes the review's MEDIUM-4: the review record is evidence. | `handlers/reviews.py` |
| D17 | Issue, transmittal-issue and answer dates default to the server date; a future date is refused; an earlier date needs a reason that the event keeps (`date_reason`). A typed transmittal number must fit the project's `documents.Transmittal` pattern; `revision_date` and due dates are within a year ahead and 50 years back. A number or key part a caller types may not hold `@` or `/`; the system link sources (`rule`, `enricher`, `import`, `mapping`) cannot be claimed over the API. | Review L1 and L4. | `handlers/common.py` (`resolve_date`), `handlers/transmittals.py` |
| D15 | `confidentiality` of a document is stored and shown; filtering by it is not built (ADR-0008 has no per-record ACLs in Phase 1). | Scope. | follow-ups |

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S1 | `v_<module>_<class>` view generator; engineering projectors create their views | Generator core (01-tiers §3) | orchestrator | done |
| T02 | `schema/modules/documents/*.yaml` (five record classes, two sub-tables, fifteen event classes); fixtures: workflows, file slots, revision schemes, document standards edition, transmittal numbering pattern | Schema, human gate (ADR-0008 decision 6) | orchestrator | done |
| S3 | Package `tl-mod-documents`: projectors, registry reads, scheme engine (T05), document/revision/rendition commands (T04), pin and stale resolver (T07), invariants, API command table, test world | Invariants across streams; resolver semantics (01-tiers §3) | reviewer | done |
| S4 | API wiring (23 commands, error rows), `by_module` keyword on the transition and link handlers | Security surface | orchestrator | done |
| S6 | Security fixes after the fresh-context review (ADR-0011, ADR-0010 second addendum): `generic_guards`, link-life commands, reserved keys, signed write-once, supersede checks, review rules, dates and number pattern, access levels | Security surface, core | orchestrator and re-review | in re-review |
| S10 | Document read models (`tl_mod_documents.views`), seven GET routes (`document.read`, open to agents), the API client, the `ClientInterface` reads with the embedded client and the in-memory fake, `tl doc confidentiality` (admin) | Security surface (a read action for agents); the client interface | orchestrator | done |
| S11 | Reference implementations of T09e, T09f and T10b, kept in the history for a takeover | Takeover path | — | done |
| S5 | Reference implementations of T08a, T08b, T09a, T11a, kept in the history of `p1/i2` (`1734486`; the T11a reference was refreshed at `5abf509`) for a takeover; the tree holds stubs until each ticket merges | Takeover path | — | done |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| T01 | Revision scheme fixture and document type list | H (schema label, data) | — | merged (supervisor) | built with the engine because it needs it; the document type list is the existing `DocumentType` list |
| T08a | Transmittal commands | H | S3 | merged (batch 1, first attempt) | `4a18c1c`; the date rules, the number pattern and the draft-only guard were added after the merge (S6) |
| T08b | Review cycle commands | H | S3 | merged (batch 1, first attempt) | `63f116f`; the reviewer-is-caller rule, the on-behalf and override commands, account and author checks were added after the merge (S6), with changes to the provided tests |
| T09a | `tl doc`: register, show, ls, update, supersede, void | H | S3 | merged (batch 1, first attempt) | `a016649`; `supersede` is admin and `update` lost `--confidentiality` after the merge (S6) |
| T11a | Base reports (module functions) | H | S3 | merged (batch 1, first attempt) | `d568e36`; the test dates changed to past dates with a reason (S6) |
| T09b | `tl doc rev`: create, issue (admin), supersede (admin), void, ls | H | S3, S6 | merged (batch 2, first attempt) | `7238790` |
| T09c | `tl doc rendition`: add, replace-signed (admin), ls | H | S3, S6 | merged (batch 2, first attempt) | `3f3bfe9`; adapted after the merge (S13): `add --kind signed` is refused before any upload, `register-signed` (admin) is new, the provided test changed |
| T09d | `tl doc link`, `stale`, `diff`, `repin` | H | S3, S6 | merged (batch 2, first attempt) | `9a067ca, report 5de129d` |
| T11b | `tl doc report`: register, history, overdue, transmittals, stale | H | T11a | merged (batch 2, first attempt) | `6393e4d` |
| T09e | `tl transmittal`: create, issue (admin), answer, close, void, ls, show | H | S3, S6, T08a | ready (batch 3) | |
| T09f | `tl review`: open, answer, on-behalf (admin), close, override (admin), ls | H | S3, S6, T08b | ready (batch 3) | |
| T10b | MCP read tools for documents (seven tools, each an explicit `MCP_ACTIONS` entry) | H | S10 | ready (batch 3) | |

Merge adaptation after batch 2 (S13, because the third security pass changed the rules under the running tickets): T09c's `add --kind signed` is refused (the first signed copy is `RegisterSignedRendition`, an admin's). The module has a file-free `check_rendition` / `preflight_rendition`, and the CLI runs it before it uploads, so a refused `rendition add`, `register-signed` or `replace-signed` leaves no orphan file; `tl doc rendition register-signed` (admin) is new.

The `doc_rev`, `doc_rendition`, `doc_link` and `doc_report` modules are wired in `tl_cli/main.py` by the supervisor so the four tickets have disjoint paths; each ticket's stub has its reference in the history (the commit before the stub commit).

Later batches, written as their bases merge: `tl transmittal` and `tl review` (T09e, T09f; the review commands record the caller's own answer, with `on-behalf` and `override` as admin commands), API read models and client (T10a), MCP read tools as explicit `MCP_ACTIONS` entries (T10b), the TUI register and record views, the re-pin dialog and the transmittal composer, the simulator actor and the legacy DMS mapping template, and `tl doc confidentiality` (admin).

## Order of work
1. Round 1: S1, T02, S3, S4, S5 built and green; batch 1 dispatched (T08a, T08b, T09a, T11a).
2. Round 2: merge batch 1; build the client interface and API read models; batch 2.
3. Later rounds: the remaining entry points, the simulator actor and mapping template, the demo, the gates, the report.

## Brief coverage map (L-P0-I8E-3)
| Brief item | Where |
|---|---|
| §9 M1 `Document` (number pattern, type, discipline, originator, confidentiality, current revision, status) | T02, `handlers/documents.py`, T09a |
| §9 M1 `Revision` (code per scheme, date, purpose, status IFR/IFC/AFC/As-Built/Void, reviewer comments) | T02, `schemes.py`, `handlers/revisions.py`; reviewer comments are the review outcome and a markup rendition |
| §9 M1 `Rendition` (hash, filename, MIME, size, page count, native/PDF/markup) | T02, `handlers/renditions.py` |
| §9 M1 `Transmittal`, `ReviewCycle` | T08a, T08b |
| §9 M1 `DerivedDocument`, `DocumentSchema`, extract/validate/publish | P1-I3 |
| §9 M1 revision schemes configurable per project and type | D4 |
| §9 M1 one current revision per status class; superseded retained and visibly superseded | D5, `invariants.py` |
| §9 M1 links pin a revision or float | D7 |
| §7.3 stale pins on issue, owners notified, re-pin with a diff before confirming | D6, `resolver.py`, T09c (CLI), TUI re-pin dialog |
| §7.3 target voided or superseded -> stale | D6 |
| §9 M1 workflow Draft -> Registered -> In Review -> Issued -> Superseded/Void | D9 |
| §15 base reports: register, revision history, overdue reviews, transmittal log, documents by status/discipline, stale pinned revisions | T11a, T11b; the derived-document validation status belongs to P1-I3 |
| §20.1 file slots native, pdf, markup, signed | D8 |
| §9 M10 Document-control domain: transmittal and review return as items of one register | T08a (transmittals); the correspondence core is P1-I5 |

### Module definition of done (§29.8) for `documents`
| Item | Plan |
|---|---|
| LinkML reviewed, artefacts current, tables and views generated | T02, S1, `just gen` |
| Workflows, required psets, file slots, spatial paths | three workflows; four file slots; no required psets; no spatial context |
| TUI screens, forms, API, MCP, webhooks | batch 2/3; webhooks by the catalog |
| Merge policies, settings keys, expected links | none declared (merge policies are Phase 3); no settings; no expected links |
| Base reports | T11a, T11b |
| Simulation actors | document controller actor (batch 3) |
| Legacy mapping template | DMS export template (batch 3) |
| Parity, contract, snapshot, permission and restore tests | every module test uses the parity fixtures; webhook scenario covers the new events; snapshots with the TUI tickets; permission: `test_generic_commands.py` and API tests; restore: `test_rebuild.py` |

## Risks and escalation triggers
- The pin and stale resolver needs no change to the 03 §7 core interfaces: it uses the core's `MarkPinsStale`, `FlagLink`, `AddLink`, `RepinLink` as they are. If a later ticket needs the core to validate a pin itself (a `ModuleSpec` hook), that is a change to `ModuleSpec` and goes to the orchestrator.
- `by_module=True` on `handle_transition_workflow` is a new Python argument of a core service. It is not reachable from HTTP (the command model has no such field) and it skips only the generic-command allow-list, not the guards.
- A file in a revision slot is an unregistered upload until `AttachRendition` runs. The upload itself is now refused when the revision's state does not take that kind (S6), so an issued revision takes no new PDF or native file at all. The review judged the earlier rule MEDIUM.
- Two classes of status coexist, so a pin on an IFC revision goes stale when an IFR revision is issued later. That follows §7.3 literally ("when a new revision is issued, pinned links go stale"); a class-aware rule is an open question.

## Schema approvals requested (ADR-0008 decisions 6 and 7a)
| Path | Class | Ticket |
|---|---|---|
| `schema/modules/documents/module.yaml`, `document.yaml`, `revision.yaml`, `transmittal.yaml`, `review_cycle.yaml`, `events.yaml` | additive (a new module) | T02 |
| `schema/fixtures/workflows/documents-document.yaml`, `documents-revision.yaml`, `documents-transmittal.yaml` | additive (new workflows) | T02 |
| `schema/fixtures/files/documents-revision.yaml` | additive (new file slots) | T02 |
| `schema/fixtures/documents/revision-schemes.yaml` | additive (a new fixture) | T01 |
| `schema/fixtures/standards/co.acme.documents@1.0.0.yaml` | additive (a new fixture) | T01 |
| `schema/fixtures/numbering/patterns.yaml` (one pattern added) | additive | S3 |

## Blocked / Decision
Open question for the orchestrator (not a block): the class-aware stale rule. The literal §7.3 rule is built, so issuing an IFR revision flags a link pinned to the current IFC revision. A rule that compares status classes would flag only pins in the same class (or a later one). Decide before the TUI re-pin dialog is built; the change is local to `resolver.py` and `invariants.py`.
