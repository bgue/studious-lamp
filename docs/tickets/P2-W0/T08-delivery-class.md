# P2-W0-OC-T4 — `core.InboundDelivery` gets an offline class (`none`)

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: schema, codegen
Depends on: OC-S1 (merged)
Branch: `p2/w0-t08-delivery-class`
Approver (schema): the orchestrator under P2-Q10 (decision Q5: deliveries are online only in the MVP); line in `docs/reports/APPROVALS.md` at merge

## Goal
The ledger stream `core.InboundDelivery` (`DELIVERY_STREAM_TYPE` in `tl_core/integration/streams.py`) is listed in `OFFLINE_STREAMS`
as `none`, like the other integration streams (`core.InboundEndpoint`, `core.Rule`...), so no stream of the integration layer is untagged.
`stream_class("core.InboundDelivery")` already answers `none` for an unknown stream; the change makes it declared, not defaulted.

## Brief references (pasted)
> OC-S1 report, open question: "`core.InboundDelivery` is not in the spec's section 4 integration list, so it is untagged and not in
> `OFFLINE_STREAMS`. Add as `none` in a follow-up." Orchestrator decision Q5 (round 4): `none`, deliveries are online only in the MVP.

## Interfaces (verbatim from repo at the branch point)
```yaml
# schema/core/integration_ops.yaml (existing, lines 98-105)
  InboundDelivery:
    description: One accepted inbound POST and what became of it. The raw body is an object, never a column.
    annotations:
      tl:current_state: true
      tl:table: int_delivery
# schema/core/integration.yaml lines 711-714: how a stream class is tagged
    annotations:
      tl:offline: none
      tl:stream_type: core.InboundEndpoint
      tl:current_state: true
```
Change: add `tl:offline: none` and `tl:stream_type: core.InboundDelivery` as the first two lines of the `InboundDelivery` `annotations:`
block, then `just gen` (writes `generated/offline_classes.py` and `generated/docs/offline-classes.md`; nothing else may change).

## Context (read these, nothing else)
- `docs/templates/haiku-report.md`
- `schema/core/integration_ops.yaml` (lines 95-110)
- `schema/core/integration.yaml` (lines 705-720)
- `schema/core/annotations.yaml` (the `tl:offline` and `tl:stream_type` entries, lines 34-45)
may explore: (none)

## Allowed paths
- `schema/core/integration_ops.yaml` (modify: those two lines)
- `packages/tl-schema/src/tl_schema/generated/offline_classes.py` (generated)
- `packages/tl-schema/src/tl_schema/generated/docs/offline-classes.md` (generated)
- `docs/reports/P2-W0/OC-T4.md` (create)

## Acceptance (run these, once; do NOT run pytest, tests are deferred to the increment's end run)
```
just gen
git status --short
grep -n "InboundDelivery" packages/tl-schema/src/tl_schema/generated/offline_classes.py
just check
```
Expected: `git status` lists only the three files above plus the report; the grep shows `"core.InboundDelivery": "none"` in `OFFLINE_STREAMS`; `just check` clean.

## Tests to add
None. The end run's `packages/tl-schema/tests/test_offline_classes.py` pins the stream table; list in the report whether it pins the stream count or names (read it, do not edit; a pin that breaks only because of this one new stream is a consequential pin: say which line).

## Report requirements
Standard report plus the pasted outputs and a line that no pytest was run.

## Escalation triggers
- Stop and report *Blocked* if `just gen` changes any file outside the allowed list, or the generator refuses the class (for example it wants `tl:record_types`).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
