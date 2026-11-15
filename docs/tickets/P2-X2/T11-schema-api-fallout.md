# P2-X2-T11: DONE-gate fallout of S1/S3/S3c in tl-schema and tl-api tests

Branch p2/x2-t11-schema-api-fallout, base p2/x2@6e70ffa4. Tests, fixtures and pins only; no product code unless a bug is proven.

## Failing
- tl-schema test_ddl / test_generate: pinned DDL file lists lack `cur_agent_stop.sql` (S3 table), both dialects.
- tl-api test_api_proposal_access, test_api_proposals (agent token), test_api_threads: `no scope 'project:P123'` (S1: an agent files only under an explicit admin grant).
- tl-api test_activity_walk select-count (sqlite): read the cause (S1 grant setup, S3c projector, or adapter BEGIN).
- tl-api groups run in three batches (OOM otherwise); settings count 33 -> 34 etc.

## Do
- Add the pin lines; use harness ensure_agent / grant helper in fixtures; no assertion weakened.

## Gate
`just check`; `just gate` on the touched tests; groups of tl-api files.
Report docs/reports/P2-X2/T11.md.
