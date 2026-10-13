# ADR-0011 — Document control permissions in Phase 1

Status: accepted 2026-10-13 by the orchestrator (interim decision, ADR-0008 decision 6); confirmation pending the security re-review of 05fa38e, 0229814, 3b2823f and d6dd50f
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
Until a document controller role exists, **the controlling acts are the admin's**, each a command gated by
`admin.command.<Name>` in the API and `require_admin` in the CLI. Everything that prepares work stays with any
signed-in person. An agent never runs either kind: its call is a proposal.

| Admin (controlling acts) | User (preparing and taking part) |
|---|---|
| `IssueRevision`, `SupersedeRevision` | `RegisterDocument`, `UpdateDocument` (title, description, type, discipline, originator) |
| `SupersedeDocument`, `VoidDocument` | `CreateRevision`, `VoidRevision` (a draft only) |
| `SetDocumentConfidentiality` (any change to the class) | `AttachRendition` (native, PDF and markup in the states that take them) |
| `ReplaceSignedRendition` | `LinkToDocument`, `RepinDocumentLink` |
| `IssueTransmittal` | `CreateTransmittal`, `RecordTransmittalResponse`, `CloseTransmittal`, `VoidTransmittal` (a draft) |
| `RecordReviewOutcomeOnBehalf`, `OverrideReviewOutcome` | `OpenReviewCycle`, `RecordReviewOutcome` (one's own answer), `CloseReviewCycle` (not milder than the worst answer) |

`SupersedeDocument` does not require the replacement to have the same document type: a document may be replaced by one of another type (a sketch by a general arrangement drawing), and the admin who supersedes states the reason, which the event keeps.

The class of a new document is set when it is registered; changing it afterwards is the admin's. `tests/` pins the table
(`packages/tl-api/tests/test_api_documents.py`, `EXPECTED_ACCESS`): a change to it is a decision recorded here, not a
refactor.

The review rules that go with it:
- A reviewer answers for themselves only. An admin can record an answer for someone else, with a mandatory comment, and
  the event keeps who recorded it (`recorded_by`).
- A cycle's reviewers are active person accounts, and at least one is not the revision's author.
- Closing a cycle with an outcome milder than the worst recorded answer, or closing one nobody answered with anything but
  `rejected` (withdrawn), is the admin's `OverrideReviewOutcome`, with a reason. The event keeps the worst answer.

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

## Alternatives considered
| Option | Why not |
|---|---|
| Keep every command open to any signed-in person | A person could issue, supersede and transmit with no second pair of eyes; the review rated it MEDIUM |
| Add a document controller role now | Needs the role model of the SSO increment; ADR-0008 fixes two roles for Phase 1 |
| Check ownership of the draft (author only) | There is no ownership model in Phase 1; a colleague taking over a draft would be locked out |
