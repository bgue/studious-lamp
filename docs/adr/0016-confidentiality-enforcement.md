# ADR-0016 — Confidentiality is enforced on every read path, and an unknown class is hidden

Status: accepted 2026-10-17 by the orchestrator under ADR-0008 decision 6 ("confidentiality filters"), as written (proposed by the P1-I5 supervisor). Closes the known limit of ADR-0011 ("a confidentiality class is stored and shown; nothing filters by it yet").
Date: 2026-10-17
Deciders: P1-I5 supervisor (proposal); orchestrator (approval)
Brief sections: §9 M10 (confidentiality per domain; "Confidentiality rules apply to every view, including the master"), §18.3 (restricted classes emit thin payloads, only to cleared subscription owners), §18.10 (restricted classes are excluded from bulk and semantic exports), §8 (permissions), §25.5 (confidentiality filters are a human gate)

## Context
ADR-0011 let a document carry a free-text `confidentiality` label that nothing read, and said so in every place the label is shown. Correspondence (M10) makes the label matter: legal and commercial items are restricted by default, privileged advice is visible only to named people, and the brief says the rules hold for every view, the feed, the exports and AI retrieval. Phase 1 has three roles (`user`, `document_controller`, `admin`; ADR-0013), agents that only propose, and no per-record access lists. This ADR says what a class is, who may read which class, where the check lives, and what happens when anything is unclear.

## Decision

### 1. Three classes, closed
`internal`, `restricted`, `privileged`, in that order of strictness. A record's class is the `confidentiality` column of its module table (`Correspondence` always has one, default `internal`; a `Document` has one or NULL). NULL on a document means `internal`: it is what every existing document is. **Any other value is not a class and is hidden from everyone** (fail closed): an old free-text label such as `Confidential` makes the document unreadable until a controller sets a real class. Documents may be `internal` or `restricted`; `privileged` exists for correspondence only (a document has no clearance list).

### 2. Who reads what
| Viewer | `internal` | `restricted` | `privileged` |
|---|---|---|---|
| Agent (`agent:*`) | yes | no | no, and an agent can never be named |
| Person or simulated person with the `user` role | yes | no | only if named on the item |
| Document controller | yes | yes | only if named on the item |
| Admin | yes | yes | only if named on the item |
| System (projectors, rebuilds, the job worker, the sealer) | all | all | all |

"Named" is a row of `cur_correspondence_clearance` (record, account), written by `Correspondence.ClearanceGranted` and removed by `...Withdrawn`. An admin is not special for a privileged item: the brief says privileged items are seen only by named people. To avoid a lock-out, a document controller or an admin may grant clearance on a privileged item **by its id** without being able to read it (the command checks that the item exists, not that the actor may read it), the event names who did it, and the setter of the class is named automatically. The ids are listed by `tl corr clearance ls`, which shows ids and accounts and nothing of the item.

### 3. One module, one seam, a viewer that defaults to the lowest
`tl_core.confidentiality` holds the classes, the `Viewer` and the SQL fragment that hides records. A module declares what it makes confidential in its `ModuleSpec` (`confidential=(ConfidentialSource(...),)`): the table, its id column, its class column, what NULL means, an optional clearance table, and child tables whose rows belong to a parent (a revision to its document). The core reads those declarations; it never imports a module.

The viewer lives in a context variable (`use_viewer`). Its default is the **lowest clearance** (`internal`, no account), so code that forgets to set it hides too much, never too little. The faces set it from the authenticated principal: the API's authentication middleware (the one place that resolves a token), the MCP server on every tool and resource call (its identity is re-read on each call, L-P1-I0A-22), the embedded TUI client on every call, and the CLI from the session (a dev file without a session reads as the file's owner, restricted, but still not as a named person). Code that must see everything (projectors, rebuilds, the derivation worker, the sealer) does not call the filtered reads or runs under `system_view()`, a context manager no route, tool or command can enter.

### 4. The filtered read paths (the list is a test, not a promise)
| Path | Rule |
|---|---|
| `GET /records`, `/records/count`, `/records/lookup`, `/records/{id}` and its `/body`, `/conformance`, `/history`, `/workflow`, `/files`, `/expected-links`; the query language and every list that joins `cur_core_record` | a hidden record is absent: a list leaves it out, a get answers 404 `record_not_found` |
| `/records/{id}/links`, `/trace`, `/links/counts`, `/links/search`, `/keys/detect` | a link is hidden when either end is; counts leave hidden ends out; key detection does not resolve a hidden key |
| `/events`, `/stream`, the change feed | an event is hidden when its stream is a hidden record, a link with a hidden end, or a file of a hidden record; cursors are by `seq`, so gaps are normal |
| `/feed`, `/feed/complete`, `/feed/posts/{id}` | a card or post about a hidden record is hidden; completions do not offer a hidden record |
| `/files/{id}`, `/files/{id}/content`, uploads and downloads | the file's record decides; a hidden record's file answers 404 |
| `/projects/{p}/documents`, `/transmittals`, `/derived-*`, `/stale-links`, `/overdue-reviews`, document diffs | the document decides; a revision, rendition, review, derived document or transmittal item of a hidden document is hidden; a transmittal item that names a hidden revision is left out and the count says so |
| `/proposals` | a proposal that carries a record id the viewer cannot read is hidden |
| `/projects/{p}/correspondence`, `/correspondence/{number}`, `/clocks`, `/threads`, the master register | the item decides; a clock, thread entry or register row of a hidden item is hidden |
| MCP tools and resources | the same functions, the same viewer; an agent holds `internal` only |
| `lake_query` and the lake sync | the sync leaves out the events and rows of every record that is not `internal` (a reclassification is applied at the next sync and the next lake rebuild; rows copied earlier stay until then) |
| Webhooks (§18.3) | the delivery policy never sends `privileged` or unknown records, sends `restricted` records as `thin` and only to subscriptions whose owner is cleared for `restricted`, and sends `internal` as the subscription asked |
| Bulk and semantic exports (§18.10) | `internal` only; an authorised export definition (Phase 3) can add classes |

A test walks `app.openapi()` and the MCP tool list the way `test_api_reserved_identifiers` walks the API: for every GET route and every read tool it makes a fixture item for each class (and a bogus class), asks as a user, a controller and an agent, and fails when a secret word of a hidden item appears in any answer, or when a route is neither exercised nor on a short, named list of routes that carry no record data. A route added later must be classified or the test fails.

### 5. Writes: a hidden record does not exist
Core handlers that take a record id (`require_generic`, the link handlers, `AttachFile` and the upload path) and every module command call `require_visible`; a record the actor cannot read answers as if it did not exist, so a write cannot be used to probe. Changing a class (`SetCorrespondenceConfidentiality`, `SetDocumentConfidentiality`) and granting or withdrawing clearance are document controller acts (`control.command.<Name>`); an agent proposes nothing of this kind.

### 6. What does not change
Events stay immutable and complete in the ledger and in the archive; the archive, restore and backup tools are operator tools that read the whole ledger and are not read paths for principals. A class change is an event, not a rewrite: copies made earlier (a webhook delivery, a lake row, a TUI screen) are not recalled.

## Consequences
- Contracts changed: `ModuleSpec` gains an optional `confidential` field (default empty); `tl_core.confidentiality` is new; `Principal` is unchanged. The read functions of `tl_core.services` (records, links, trace, feed), `FileService`, the API events and stream routes, the lake sync and the webhook dispatcher gain the filter; the documents module's reads gain it. Document `confidentiality` is validated: `internal`, `restricted` or none.
- Existing data: a document with a free-text label other than the two classes becomes unreadable (fail closed) until a controller sets a class; none of the committed fixtures or tests use one. NULL stays `internal`.
- Tickets re-issued: none; P1-I2's `CONFIDENTIALITY_NOTE` text and the three places that say "recorded but not enforced" are replaced.
- Gates affected: this ADR is the delegated confidentiality gate (ADR-0008 decision 6); every commit that adds or changes a filter is listed under `SECURITY_REVIEW`.

## Refinements after the security review of P1-I5
- **Webhooks judge the stream, not only the subject.** A link with a hidden end, a file of a hidden record and a post that tags a hidden record are streams of their own. A delivery for one is dropped when the owner (or the thin audience) may not read an end, and is `thin` when the plain reader may not.
- **Files.** The hash of a file counts for dedupe only when the file belongs to a record the reader may read; the text of an incomplete upload is the same whether or not the store holds the bytes.
- **Lock-out (section 2) is implemented by id.** `GrantClearance` and `WithdrawClearance` work for a controller-level actor on a privileged item they cannot read: the handler checks existence in the scope and the class, shows nothing of the item, and `tl corr clearance ls` lists item ids with their accounts. Setting the class still reads the item through the viewer.
- **Links, generic edits, posts.** The link lifecycle commands, `RepinDocumentLink` and the admin pair answer "no such link" for a link with a hidden end; a generic edit of a hidden record says "no such record" before it says anything about its type; a post that tags a hidden record reads as absent to react, edit or retract.
- **The sweep** reads every clock as the system, in pages, and reports the clocks it could not judge. A scheduled run belongs to the integration runner (P1-I7); until then a controller runs `tl corr clock sweep` daily.
- **D6 refinement: time bars.** Restarting or cancelling a clock of kind `time_bar`, or one that cites a clause, is a document controller's act (`ForbiddenError` otherwise). The handler reads the level of the viewer the entry point set from the authenticated principal; it reads no role. Pause, resume and meet stay open to any signed-in person, and so does `ReclassifyCorrespondence` until the item is issued (D6 as written).
- **A reply is no lower than what it answers.** A received item (an email, a letter) that joins a thread or answers an item takes the class of the highest item it was matched with and, for `privileged`, their named accounts plus the person who ran the command (`inherit_from_matches`), as a draft reply does (`inherited_class`). A reader who could not read the matched item never matches it, so this only raises the class for a reader who could. This is for NEW items only (an email ingest, a received item or a draft). An EXISTING item that is filed in a thread of a higher class, or made to answer an item of a higher class, by `AssignThread` never takes the class silently: a plain user is refused (`ForbiddenError`, nothing is appended, the item is unchanged) so that a person named on a privileged thread cannot take anyone's item out of its readers' sight (section 5: a class change is a controller act). A document controller or admin may do it, and the move records a `ConfidentialityChanged` event (with the named accounts, as `SetCorrespondenceConfidentiality` does).
- **The sweep and the lock-out path answer with what the caller may read.** The events a sweep recorded are filtered for the caller and the rest only counted; `GrantClearance` and `WithdrawClearance` answer an uncleared controller with the one "no such record" for everything that is not a privileged item, and carry no item number.
- **Known and accepted:** a caller-chosen `post_id` that is taken says it is taken. It needs a 26-character id to guess.
- **MCP sets the viewer** on every tool and resource call (`guarded`), to the lowest clearance, instead of relying on the default.

## Known limits (Phase 1)
- The model has no project-level or domain-level roles: "commercial roles plus the PM" and "named legal roles" are approximated by `restricted` (document controllers and admins) and by naming accounts on an item. Entra groups (§27) can map to the same two levels later.
- A document controller sees every `restricted` item of every project (the role is company-wide, ADR-0013).
- A `privileged` item can be read by an admin only after an admin names themselves; the event records it.
- A hidden record can still be seen to exist by someone who knows its id through the shape of an answer that depends on it (a counter, a gap in `seq`). Counts leave hidden records out; sequence gaps remain.
- The feed policy of a domain (`full`, `minimal`, `none`) is compiled and shown but does not yet change the cards; the class filter does.
- The archive, backup and restore tools see everything and are protected by who may run them.
- CLI on a dev ledger file reads as the owner of the file; the file itself is the boundary (ADR-0009 section 7).

## Alternatives considered
| Option | Why not |
|---|---|
| A viewer argument on every read function | A hundred signatures and every test would change; a forgotten argument would be a silent hole. The context variable fails closed when unset and the walking test finds a face that forgets to set it |
| Filter in the faces only (API, MCP, TUI each) | Four copies of the rule; the CLI and the embedded client would drift; the shared read layer is one place |
| Per-record access lists for every class | Phase 1 has no ownership model (ADR-0011); named accounts are needed only for `privileged` |
| Treat an unknown label as `internal` | An old free-text label like `Secret` would become public; the brief's default is the safe side |
| Database row-level security | Postgres only; SQLite has none; the adapters must stay behaviourally equal |
| Let an admin read privileged items | The brief says named legal roles only; an admin can name themselves and the event shows it |
