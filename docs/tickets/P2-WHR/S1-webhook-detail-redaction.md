# P2-WHR S1 — Webhook bodies redact payload references to hidden records (SR-X1 F3)

kind: piece
review: full
branch: p2/whr-s1
worktree: /home/user/wt/whr/s1

## Why (SR-X1 F3 MD, pre-existing; DEFERRED row 2026-11-14)
`tl_core/webhooks/envelope.py:112` copies `row.data["detail"]` (the ledger payload, set in `webhooks/outbox.py:226`) into
`delta` and `full` bodies raw. The dispatcher (`webhooks/dispatch.py:360-415`, `_enqueue`) drops a row whose subject or
stream is hidden from the subscription owner, but never applies `PAYLOAD_REFS` redaction to the detail. So an owner who
may read the subject receives the ids of other records hidden from them, for example `MTO.Defined` document ids
(`tl_core/intent.py` `PAYLOAD_REFS`, entries from P2-I6). `/events` and the X1 replay redact the same fields through
`redact_for_viewer` / `redacted_payload` (`tl_core/intent.py:360-420`). Rule: hidden must look exactly like missing.

## Goal
1. `Dispatcher.render_body` (`webhooks/dispatch.py:417`) passes the detail through the existing redaction for the
   subscription owner before `build_envelope`: ids from `payload_ref_ids(row.stream_type, row.event_type, detail)`,
   `hidden = confidentiality.hidden_among(conn, ids, viewer)` with the viewer `_enqueue` already sets (`use_viewer(owner)`;
   read it with `confidentiality.current_viewer()`), then `redacted_payload(...)`. Use the existing functions; write no
   second filter. Keep `build_envelope` pure: pass the redacted detail in (a new keyword argument `detail=` defaulting to
   the row's), or a redacted copy of the row; your choice, say which in the report.
2. Treat the restricted (thin) audience the same: `_enqueue` sends `thin` (no detail) when the subject is restricted; no
   change needed there; confirm in the report.
3. `data.changes` (`event_changes`, `webhooks/outbox.py`): if a change can carry a field `PAYLOAD_REFS` names for that
   event type, redact it the same way (null, same keys). If none can, say so in the report with the grep that shows it.
4. Out of scope: redrive of an already stored body (`dispatch.py:276`, it resends the stored text); note it in the report
   as a follow-up only if a stored body can predate the hiding.

## Allowed paths
- `packages/tl-core/src/tl_core/webhooks/dispatch.py` (`render_body` and a private helper)
- `packages/tl-core/src/tl_core/webhooks/envelope.py` (`build_envelope` signature and docstring only)
- `packages/tl-core/tests/test_webhook_detail_redaction.py` (create)
- `tests/confidentiality/test_twin_walk.py` and `tests/confidentiality/conftest.py` (add one twin case, below)
- `docs/reports/P2-WHR/S1.md` (create)

## Tests to add
test_webhook_detail_redaction.py:
1. A `delta` and a `full` subscription; an event whose `PAYLOAD_REFS` field names record B; B hidden from the owner
   (test-only `ConfidentialSource`, as in `packages/tl-mcp/tests/test_idempotency_walk.py`): the body's `data.detail`
   has B's field null with the same keys, and B's id appears nowhere in the body text.
2. The same event with B readable: body byte-identical to before the change (regression guard).
3. `thin` subscription: unchanged (no detail).
twin walk: one case where world A has B hidden and world B has no B at all, an event naming B in a `PAYLOAD_REFS` field;
the webhook bodies of every mode are equal across the twins (the walk's existing comparison).

## Gate
`just check` (with `NODE_OPTIONS=--max-old-space-size=6144`); `just gate packages/tl-core/tests/test_webhook_detail_redaction.py
packages/tl-core/tests/test_webhook_envelope.py packages/tl-core/tests/test_webhook_wiring.py packages/tl-core/tests/test_payload_refs_phase2.py
tests/confidentiality tests/contract/test_dispatch_contract.py tests/contract/test_webhook_catalog_contract.py`.
Mutation: one sentinel plus at most 3 targeted mutants (redaction skipped; viewer swapped to LOWEST; hidden set ignored),
3 lines in the report.

## Report
Builder return ≤ 15 lines; report ≤ 60 lines; commit `P2-WHR-S1: ...` with the session trailers; no model names in
committed text.
