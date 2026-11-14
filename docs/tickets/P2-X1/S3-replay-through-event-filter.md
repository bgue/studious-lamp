# P2-X1 S3 — A replay passes the same event filter as /events (SR-X1 F1, F2, F7)

kind: piece
review: full
branch: p2/x1-s3-replay-filter
worktree: /home/user/wt/x1/s3

## Why (SR-X1, 2026-11-14)
- F1 HI `tl_core/services/idempotency.py:179-186` `replay_result` hides the replay only when the stream id itself is a hidden
  record (`hidden_among` on `cur_core_record`). The stored events are returned raw: no `filter_events` /
  `hidden_event_streams` (`tl_core/confidentiality.py:395,508`), no `redact_for_viewer` (`tl_core/intent.py:292`). Proof
  (scratch probe `/tmp/claude-0/-home-user-studious-lamp/c1e9f617-74c2-581f-aa0c-d2601bd9e1da/scratchpad/probe/p1.py`):
  ALICE `AddLink` A->B with key K1; B becomes privileged; `GET /records/B` is 404 and `/events` no longer names B; replay
  of K1 returns 200 with `Link.Added.to_ref` = B. Same path at `tl_api/commands.py:361` and `:540`. Also PostToFeed,
  thread messages and intent refs.
- F2 MD `tl_mcp/write_tools.py:87-91`: `IdempotencyKey` keeps `max_length=128`; a key of 129+ chars comes back truncated in
  the ToolError (`string_too_long [input_value='SECRETPREFIX-...-SECRETSUFFIX']`). Probe `.../scratchpad/probe/p2.py`.
- F7 LO: with `expected_version` out of the hash, a reused key with a newer version replays the older result.

## Goal
1. A replay's events pass exactly the filter and redaction `/events` applies for the same viewer: drop events of streams the
   viewer cannot see (`hidden_event_streams` / `filter_events`), then `redact_for_viewer` on the rest. If the command's own
   stream is hidden, keep today's answer (`RecordNotFoundError`, text of an absent record). If filtering removes an event
   the original answer had, the replay answers exactly as `/events` would for those events (dropped or redacted), never
   with the raw id. Use the existing functions; do not write a second filter.
2. MCP `IdempotencyKey`: no `max_length` (and no other constraint FastMCP echoes); command validation (`KEY_PATTERN`,
   `KEY_REFUSED`) refuses an over-long key without echo. Test: a 129-char and a 1000-char key with distinctive prefix and
   suffix; neither prefix nor suffix appears in the error text.
3. F7: one paragraph in `docs/runbooks/api-retries.md`: a key names one intent; to re-apply after someone else changed the
   record, use a new key.

## Allowed paths
- `packages/tl-core/src/tl_core/services/idempotency.py` (`replay_result` and helpers only)
- `packages/tl-mcp/src/tl_mcp/write_tools.py` (the `IdempotencyKey` alias only)
- `packages/tl-core/tests/test_idempotency_replay_filter.py` (create)
- `packages/tl-mcp/tests/test_mcp_idempotency.py` (add the over-long key tests)
- `docs/runbooks/api-retries.md` (one paragraph)
- `docs/reports/P2-X1/S3.md` (create)

## Tests to add (test_idempotency_replay_filter.py)
1. The F1 probe as a test: AddLink A->B keyed; B made unreadable (test-only `ConfidentialSource`, as in
   `packages/tl-mcp/tests/test_idempotency_walk.py`); the replay's events equal what `/events` shows that viewer for those
   event ids (B's id absent or redacted exactly as there); A's own replay still 200.
2. A replay of a command whose events name only readable records is byte-identical to before (no regression).
3. A replay whose own stream became hidden answers as an absent record (unchanged).
4. One event with an intent ref to a hidden record: redacted as `/events` redacts it.

## Gate
`just check` (with `NODE_OPTIONS=--max-old-space-size=6144`); `just gate packages/tl-core/tests/test_idempotency_replay_filter.py packages/tl-core/tests/test_idempotency.py packages/tl-core/tests/test_idempotency_submit_order.py packages/tl-api/tests/test_idempotency_walk.py packages/tl-mcp/tests/test_idempotency_walk.py packages/tl-mcp/tests/test_mcp_idempotency.py`.
Mutation: one sentinel plus at most 3 targeted mutants (filter skipped, redaction skipped, hidden-stream check inverted), 3 lines in the report.

## Report
Builder return ≤ 15 lines; report ≤ 60 lines; commit `P2-X1-S3: ...` with the session trailers; no model names in committed text.
