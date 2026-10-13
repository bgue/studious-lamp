# ADR-0011 — Document control permissions in Phase 1

Status: accepted 2026-10-13 by the orchestrator (interim decision, ADR-0008 decision 6); confirmation pending the security re-review of 05fa38e, 0229814, 3b2823f and d6dd50f. **Superseded in part by ADR-0013** (2026-10-13): the controlling acts below are the document controller's, and an admin keeps them; the table's left column reads "controller" and the sentence "until a document controller role exists" no longer applies. Everything else here stands
Date: 2026-10-13
Deciders: orchestrator, after the fresh-context security review of P1-I2 round 1 (7 MEDIUM, 6 LOW); drafted by the P1-I2 supervisor
Brief sections: §9 (M1), §25.2, §27

## Context
ADR-0008 and ADR-0009 give Phase 1 two roles, `user` and `admin`, and agents that only propose. Document control has
acts that carry weight outside the system: an issued revision is what a contractor builds from, a transmittal is the
record of what was sent, a supersession changes which document is live. Round 1 of P1-I2 let any signed-in person do
all of them. The review found that a person could issue, supersede and transmit, change a confidentiality class, and
record a review answer in another reviewer's name.

A document controller role does not exist yet (Entra groups arrive with SSO, brief §27).

## Decision
*ADR-0013 replaced this opening: the controlling acts are the document controller's (an admin may run them too), each a
command gated by `control.command.<Name>` in the API and `require_controller` in the CLI. The text below is the original.*

Until a document controller role exists, **the controlling acts are the admin's**, each a command gated by
`admin.command.<Name>` in the API and `require_admin` in the CLI. Everything that prepares work stays with any
signed-in person. An agent never runs either kind: its call is a proposal.

| Admin (controlling acts) | User (preparing and taking part) |
|---|---|
| `IssueRevision`, `SupersedeRevision` | `RegisterDocument`, `UpdateDocument` (title, description, type, discipline, originator) |
| `SupersedeDocument`, `VoidDocument` | `CreateRevision`, `VoidRevision` (a draft only) |
| `SetDocumentConfidentiality` (any change to the class) | `AttachRendition` (native, PDF and markup in the states that take them; at most 20 markups per revision; never a signed copy) |
| `RegisterSignedRendition` (the first signed copy), `ReplaceSignedRendition` (a correction, with a reason) | `LinkToDocument`, `RepinDocumentLink` |
| `IssueTransmittal` | `CreateTransmittal`, `RecordTransmittalResponse`, `CloseTransmittal`, `VoidTransmittal` (a draft) |
| `RecordReviewOutcomeOnBehalf`, `OverrideReviewOutcome` | `OpenReviewCycle`, `RecordReviewOutcome` (one's own answer), `CloseReviewCycle` (its opener or the revision's author; not milder than the worst answer) |

`SupersedeDocument` does not require the replacement to have the same document type: a document may be replaced by one of another type (a sketch by a general arrangement drawing), and the admin who supersedes states the reason, which the event keeps.

The class of a new document is set when it is registered; changing it afterwards is the admin's. `tests/` pins the table
(`packages/tl-api/tests/test_api_documents.py`, `EXPECTED_ACCESS`): a change to it is a decision recorded here, not a
refactor.

The review rules that go with it:
- A reviewer answers for themselves only. An admin can record an answer for someone else, with a mandatory comment, and
  the event keeps who recorded it (`recorded_by`).
- A cycle's reviewers are active person accounts, and at least one is not the revision's author.
- A round nobody answered closes as `withdrawn`, which is not a rejection and is the only outcome it can have. Only the
  person who opened a cycle or wrote the revision closes it (anyone else gets 403 `not_your_review`); an admin closes any
  cycle with `OverrideReviewOutcome`.
- Closing a cycle with an outcome milder than the worst recorded answer is the admin's `OverrideReviewOutcome`, with a
  reason. The event keeps the worst answer.
- The signed copy is evidence, so registering the first one is the admin's too (`AttachRendition` refuses `signed` for
  everyone); a correction is `ReplaceSignedRendition` with a reason.
- The system sources of a link (`rule`, `enricher`, `import`, `mapping`) cannot be claimed over the API. An admin
  recovers a link a module wrote, or any link, with `AdminFlagLink` and `AdminRetractLink` (a reason is required).

## Consequences
- Contracts changed: two commands are added to the documents module (`RecordReviewOutcomeOnBehalf`,
  `OverrideReviewOutcome`); `RecordReviewOutcome.reviewer` is optional and must be the caller; `UpdateDocument` loses
  `confidentiality`. The signed copy has its own admin command, `ReplaceSignedRendition`.
- When a document controller role exists, the left column moves to it (an admin keeps it too), and a project-level
  assignment of the role can be added. Nothing else changes: the gate is one word per command in
  `tl_mod_documents/commands.py`.
- A small team in which the admin is also the document controller sees no change. A team with many controllers waits
  on the role; that is the cost of the interim.
- Phase 1 has no per-record access lists. A person who may prepare may prepare any document of a project; "ownership" of
  a draft is not checked. Document this wherever a command is described.
- Gates affected: none. Schema approvals: none beyond the optional event attributes recorded in APPROVALS.md.

## Known limits (Phase 1)
- **No ownership of links.** A link from a core record to a document has no owner a check could use, so any signed-in
  person can flag, re-pin, retract or verify it. The events name the actor, so the history shows who did it. A link
  a module wrote by rule is the exception: only the module's commands or the admin recovery commands change it.
- **`IssueRevision` is the one gate that stops a bad revision date.** The issue date is checked by the command (never in
  the future, a reason for an earlier one); a revision's own `revision_date` and a due date are bounded to a year ahead
  and 50 years back. While issuing stays an admin's act, a person cannot put a revision into the register as issued.
- **Concurrency.** "One current native or PDF", "one signed copy" and "one current revision per status class" rest on the
  ledger's writer lock: a write unit of work takes it before its first statement on both adapters, so two commands
  never check and append at the same time. No unique index backs them.
- A confidentiality class is stored and shown; nothing filters by it yet (no per-record access lists).

## Alternatives considered
| Option | Why not |
|---|---|
| Keep every command open to any signed-in person | A person could issue, supersede and transmit with no second pair of eyes; the review rated it MEDIUM |
| Add a document controller role now | Rejected here; **overtaken by ADR-0013** (owner request, 2026-10-13), which adds the role without the SSO role model |
| Check ownership of the draft (author only) | There is no ownership model in Phase 1; a colleague taking over a draft would be locked out |
