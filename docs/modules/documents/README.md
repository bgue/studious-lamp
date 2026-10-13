# Module spec: documents (M1)

Status: accepted (built in P1-I2). Brief sections: §9 M1, §7.1 and §7.3 (pinned links), §6.4 (document numbers), §29.6
(legacy import). Decisions: ADR-0010 (module storage), ADR-0011 (permissions, superseded in part), ADR-0013 (the document controller role), ADR-0012 (class-aware stale pins).

## Purpose
The documents module is document control. A `Document` is registered once under its number; it has `Revision`s whose codes
follow a configurable scheme; a revision has `Rendition`s (native, PDF, markup, signed) that are files in the file
service; formal exchange is a `Transmittal` and a `ReviewCycle`. A document keeps one current revision per status class.
A link from a record can pin a revision or float; a pinned link goes stale when it should be looked at again, and the
re-pin shows what changed before it is confirmed. Operations are in the runbook
[documents](../../runbooks/documents.md); the increment report is `docs/reports/P1-I2.md`.

## Record types
| Type | Purpose | Table | Workflow |
|---|---|---|---|
| `documents.Document` | A controlled document: number, title, type, discipline, originator, confidentiality, revision scheme | `cur_documents_document` | `documents.document`: Draft, Registered, In Review, Issued, Superseded, Void |
| `documents.Revision` | One revision: code, issue status and its class, purpose, change note, dates | `cur_documents_revision` | `documents.revision`: Draft, In Review, Issued, Superseded, Void |
| `documents.Rendition` | A file of a revision in one kind (`native`, `pdf`, `markup`, `signed`) with hash, size, pages | `cur_documents_rendition` | none |
| `documents.Transmittal` | A formal exchange of issued revisions with named recipients, a purpose and a response | `cur_documents_transmittal`, `cur_documents_transmittal_item` | `documents.transmittal`: Draft, Issued, Acknowledged, Closed, Void |
| `documents.ReviewCycle` | A round of review of a draft revision: reviewers, due date, answers, outcome | `cur_documents_review_cycle`, `cur_documents_reviewer` | none (the state is a column) |

Every record is also a row of `cur_core_record` (ADR-0010). Keys: a document's key is its number (`ISO-1234`); a revision is
`<number>@<code>` (`ISO-1234@B`); a rendition `<number>@<code>/<kind>-<n>`; a transmittal its number
(`P123-TRN-0001`); a review cycle `<number>@<code>/RC<round>`. A caller-typed number may hold `/` but not `@`, which every
key the module builds holds (ADR-0010, second addendum). The flat views `v_documents_<class>` join the two tables.

Revision schemes (`schema/fixtures/documents/revision-schemes.yaml`): `alpha` (A, B, C, no I or O), `numeric` (0, 1, 2),
`staged` (P1, P2, C1, C2); which document types use which is the file's `assignment`. Issue statuses and their class:
IFR and IFA are `review`, IFC and AFC are `construction`, ASB is `record`; the classes are ordered
review < construction < record.

## Events
| Event type | Payload (see the catalog for the schema) | Projector |
|---|---|---|
| `Document.Defined` | number, title, type, discipline, originator, confidentiality, scheme, pattern, conformance | `documents_document` |
| `Document.Updated` | changed fields, reason (title, register fields, confidentiality) | `documents_document` |
| `Document.CurrentRevisionChanged` | per status class: the new current revision and the one it replaces | `documents_document` |
| `Document.Superseded` | the document that replaces it, reason | `documents_document` |
| `Revision.Defined` | document, code, ordinal, purpose, intended status, date | `documents_revision` |
| `Revision.Issued` | issue status, class, issue date, `date_reason` | `documents_revision` |
| `Revision.Superseded` | the revision that replaces it | `documents_revision` |
| `Rendition.Defined` | revision, kind, file, hash, size, pages, `replace_reason` | `documents_rendition` |
| `Rendition.Superseded` | the rendition that replaces it | `documents_rendition` |
| `Transmittal.Defined` | number, direction, purpose, recipients, items, due date | `documents_transmittal` |
| `Transmittal.Issued` | issue date, `date_reason` | `documents_transmittal` |
| `Transmittal.ResponseRecorded` | response code, note, date | `documents_transmittal` |
| `ReviewCycle.Defined` | revision, round, reviewers, due date | `documents_review_cycle` |
| `ReviewCycle.OutcomeRecorded` | reviewer, outcome, comment, `recorded_by` | `documents_review_cycle` |
| `ReviewCycle.Closed` | outcome, `worst_answer`, reason | `documents_review_cycle` |

Each `*.Defined` event follows `Record.Created` in the same append. The catalog is `schema/modules/documents/events.yaml`
(generated: `packages/tl-schema/src/tl_schema/generated/docs/event-catalog.md`).

## Who can do what (ADR-0013, ADR-0011)
Controlling acts are the document controller's, and an admin may run them too; everything that prepares work is open to a
signed-in person; an agent never changes a record directly (it proposes). A document controller is a person (or a sim
account) whom an admin gave the role `document_controller` (`tl admin user roles NAME --add document_controller`); it is not
an admin and has no `admin.*` action.

| Action | Entry points | Access |
|---|---|---|
| Register or update a document; start or void a draft revision; attach a PDF, native or markup; link and re-pin; draft a transmittal, record a response, close or void it; open a review, answer for yourself, close a round | `tl doc register|update`, `tl doc rev create|void`, `tl doc rendition add`, `tl doc link|repin`, `tl transmittal create|answer|close|void`, `tl review open|answer|close`, `POST /commands/<Name>`, TUI `F7` | any signed-in person |
| Issue or supersede a revision; supersede or void a document; set the confidentiality class; register or replace the signed copy; issue a transmittal; record a reviewer's answer on their behalf; override a review outcome | `tl doc rev issue|supersede`, `tl doc supersede|void|confidentiality`, `tl doc rendition register-signed|replace-signed`, `tl transmittal issue`, `tl review on-behalf|override`, the matching `POST /commands/<Name>` | document controller or admin (`require_controller`, API action `control.command.<Name>`) |
| Recover a link a module wrote, or any link (the core commands `AdminFlagLink`, `AdminRetractLink`) | the matching `POST /commands/<Name>` | admin only (`admin.command.<Name>`): it repairs the whole link graph, not only documents |
| Import a legacy DMS register | `tl doc import FILE --mapping M` | the preview: any signed-in person; `--apply`: document controller or admin |
| Read documents, revisions, links, stale links, overdue reviews, transmittals, the diff of two revisions | `tl doc ls|show|diff|stale`, `tl doc report ...`, `GET /projects/{p}/documents`, `/documents/{number}`, `/document-diffs/{number}`, `/stale-links`, `/overdue-reviews`, `/transmittals`, MCP `list_documents`, `get_document`, `get_document_diff`, `list_stale_links`, `list_overdue_reviews`, `list_transmittals`, `get_transmittal` | any signed-in person; agents may read (`document.read`) |
| Change a document, revision, rendition or review cycle with a generic command | none | refused for everyone, an admin and a document controller too: only property sets, links and uploads are allowed on the types that need them, and the module's guards check state (ADR-0010 addenda) |

Rules the commands enforce: a reviewer answers as themselves (a controller records for someone else with `on-behalf`); reviewers
are active person accounts and at least one is not the author; only the opener or the revision's author closes a round; a
close milder than the worst answer needs a controller's override; the first signed copy and any replacement are the controller's; a
rendition kind must fit the revision's state (an issued revision takes markup and signed only); an issue, transmittal or
answer date defaults to today, is never in the future and needs a reason if earlier (`date_reason`); the system sources of
a link (`rule`, `enricher`, `import`, `mapping`) are the server's and a client cannot claim them.

## Pinned links and stale (brief §7.3, ADR-0012)
A link from a record to a document either floats (it means the current revision) or pins a revision. A pin goes stale when
a newer revision is issued **in the same status class as the pinned revision or a later one**. An IFR issued after an IFC
leaves the IFC pins healthy; an IFC issued after an IFC flags them; an as-built flags both. A pin on a revision with no
class keeps the old rule (any issue flags it). Voiding or superseding the document flags every link. A floating link never
goes stale from a new revision. `tl doc stale` (also the TUI register and `GET /stale-links`) lists the stale links with the
revisions that did it; `tl doc repin LINK` shows the diff of the two revisions and `--apply` moves the pin. The rule is
`affects_pin` in `tl_mod_documents.resolver`; the core link interfaces are unchanged.

## Legacy import
`tl doc import` reads a CSV export of an incumbent DMS through a mapping template
(`dev/seed/templates/document-register-dms-export.yaml`; a sample file is `dev/seed/legacy/dms-document-register.csv`),
prints what would happen (`new`, `exists`, `invalid`, each invalid row with its line and reasons), and with `--apply`
registers the new documents in one unit of work with source `import:<job>`. It registers **documents only**: the old
register's revision, status and date are kept as a note in the description, and the revisions with their files arrive with
the P1-I8 legacy loaders. Limits: 1000 rows and 5 MiB per file; a cell with a control character, or a number with a line
break, is an invalid row; every field limit of `RegisterDocument` is checked in the preview, so apply refuses nothing the
preview called new. The code is `tl_mod_documents.imports` (`mapping`, `diff`, `apply`).

## Confidentiality in Phase 1
In Phase 1 confidentiality is recorded but not enforced: every signed-in person and every agent can read all documents and transmittals of a project, including recipient emails. Setting the class (`SetDocumentConfidentiality`, `tl doc confidentiality`) is an admin act and is kept in the ledger, so the class is ready when access lists arrive.

## Limits
Lists and texts in a command are bounded (`tl_mod_documents.limits`: 128 characters in a number, 500 in a title, 2000 in a
reason, 10 000 in a description, 200 items on a transmittal, 100 recipients, 50 reviewers, 20 current markups per revision,
100 000 pages); the API refuses a `/commands/` body over 1 MiB (413). No command takes a NUL in any text (core `Command`).

## Open questions and follow-ups
- A "newer revision in review" marker beside a healthy construction pin (the owner's option C in ADR-0012).
- The document controller role is company-wide; a project-level assignment waits for the SSO increment (ADR-0013, known limits). The simulator's people hold `user` only, so the simulator never issues.
- Enforcing confidentiality (per-record access lists), including recipient emails on transmittals.
- Revisions with their files and issue dates from a legacy register (P1-I8 loaders); `DerivedDocument` and `DocumentSchema` (P1-I3).
- Two controllers issuing the same revision at once are serialised by the single writer lock (ADR-0011, known limits).
