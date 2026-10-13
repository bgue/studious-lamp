# ADR-0012 — Class-aware stale pins

Status: accepted 2026-10-13
Date: 2026-10-13
Deciders: the repository owner, recorded by the orchestrator
Brief sections: §7.3, §9 M1

## Context
Brief §7.3 says that when a new revision is issued, pinned links to the document go stale. P1-I2 built the rule as
written (D6). The documents module keeps one current revision per status class (D5): a revision issued for review (IFR,
IFA) and one issued for construction (IFC, AFC) are both current at once. Read literally, the rule flags a pin on the
IFC revision B when an IFR revision C is issued later, although C is a draft for review that nobody builds from. The
builder's pin is healthy and the report says it is stale. The supervisor raised this as an open question.

## Decision
The status classes are ordered **review < construction < record** (the `classes` list of
`schema/fixtures/documents/revision-schemes.yaml`). A link pinned to a revision goes stale only when a newer revision is
issued **in the same class as the pinned revision or in a later class**.

- B is IFC and C is issued IFR: B's pins stay healthy.
- C (or a later revision) is issued IFC, or any revision is issued as a record (ASB): B's pins go stale. A pin on an older
  IFR goes stale on a newer IFR.
- A pin on a revision with no status class (never issued, or unknown to the scheme file) keeps the old behaviour: any
  issue flags it.
- Voiding or superseding the document still flags every link, pinned or floating (§7.3 health checks, unchanged).
- A floating link is never stale because of a new revision (unchanged).

The rule lives in `tl_mod_documents.resolver` (`affects_pin`): `flag_stale_on_issue` selects the affected links and flags
each with the core's `FlagLink` (module path), and `resolve_pin` reports the same newer revisions, so `tl doc stale`, the
stale report, the re-pin diff and the TUI follow without change. The core link interfaces are untouched.

## Consequences
- Contracts changed: none in the core. `flag_stale_on_issue` takes the status class of the issued revision.
- `Link.Flagged` events from an issue are the same events with the same reason (`revision <code> issued`), fewer of them.
- A stale pin's "current" revision in the report is the document's current one, which for a pin made stale by a later
  class is that later revision.
- Later refinement, not built: an informational marker on a pin, "a newer revision is in review" (the owner's option C),
  for a pin that is healthy but has an IFR waiting. It needs no change to the rule.

## Alternatives considered
| Option | Why not |
|---|---|
| A. Keep the literal §7.3 rule | Flags builders' pins on every review issue; the stale report fills with noise |
| C. Class-aware plus a "newer in review" marker | Right idea, more screens; listed as a later refinement |
