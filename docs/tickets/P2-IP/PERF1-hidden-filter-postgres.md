# P2-IP-PERF1 — The hidden-record filter is fast on Postgres (same answers)

kind: piece
review: full (security: confidentiality core)
branch: p2/perf1-hidden-filter
worktree: /home/user/wt/ip4/perf1
Base: `p2/ip-r3` (all confidential sources installed: core, requisitions, quality, forms, qr, permits).
Labels: core, confidentiality, security, performance. APPROVALS line at merge (core interface behaviour unchanged; any index is additive).

## Why
`just gate-pg packages/tl-modules/permits/tests/test_iso_views.py` (and the T01 `test_views.py`) run for many minutes on Postgres;
SQLite is fast. `pg_stat_activity` shows each list statement taking about 13 s. The statement is
`... AND r.id NOT IN (<hidden_sql>)`, where `tl_core.confidentiality.hidden_sql` is a `UNION ALL` of one part per confidential
source, and each part joins `cur_core_record hr` to every `SUBJECT_LINKS` table twice (`_HOPS = 2`, 11 links: 22 `LEFT JOIN`s)
on `COALESCE(<earlier hop columns>, k.subject_id, hr.id)`. Postgres cannot use an index on a `COALESCE` join key, so every
part is a large hash or nested-loop join over all records, repeated per source. The cost grows with every module that adds a
source or a subject link.

## Goal
1. `hidden_sql`, `not_hidden`, `not_hidden_each`, `is_hidden`, `hidden_row_ids` and the page helpers return exactly the same ids
   as today for every viewer, on both adapters. Hidden must still look exactly like missing everywhere.
2. On Postgres, a list read over the permits T02 world (`packages/tl-modules/permits/tests/test_iso_views.py`) takes well under
   1 s per statement; `just gate-pg` on that file and on `packages/tl-modules/permits/tests/test_views.py` finishes in minutes.
3. Approach is yours; record it under Decisions. Candidates, cheapest first:
   - join each link table only for rows of its own record type (`... ON alias.id = <hop> AND <hop-type> = '<type>'`), so the
     planner prunes; resolve the hop through `cur_core_record` by id instead of a `COALESCE` chain;
   - one shared subject-chain CTE (`WITH governed AS (...)`) computed once, then each source part joins it by id;
   - `NOT EXISTS` anti-join instead of `NOT IN (UNION ALL ...)`;
   - an additive index on a link table's subject column if `EXPLAIN` shows it is used (additive only; say so for APPROVALS).
   No schema change to stored events; no projection rebuild; no new table unless additive and justified.
4. SQL stays portable (SQLite and Postgres through the same text); the module-declared names are the only names interpolated.

## Tests
- An equivalence test: for a seeded world with every source and both hops in play (reuse the confidentiality test worlds and
  the permits/forms/qr worlds), the new `hidden_sql` ids equal the old ones for each viewer kind (lowest, restricted, cleared
  account, author of a draft, agent, system). Keep the old builder only inside the test as the reference (copy it there).
- A Postgres timing guard is not required; put the before/after `EXPLAIN ANALYZE` totals for one T02 statement in the report.

## Gates (one call at a time; never `just check` or whole-repo pyright)
ruff check + format, `uv run pyright <changed .py>`; `just gate tests/confidentiality`; `just gate packages/tl-core/tests`;
`just gate-pg packages/tl-modules/permits/tests/test_iso_views.py`; `just gate-pg packages/tl-modules/permits/tests/test_views.py`;
`just gate-pg tests/confidentiality` (report its time); `just gate packages/tl-modules/forms/tests packages/tl-modules/qr/tests`;
`just gate packages/tl-api/tests/test_auth_review.py`. Mutation: sentinel + up to 5 targeted (drop a hop, drop a source part,
author exemption, draft rule, system viewer) and show the equivalence test kills each.

## Report
`docs/reports/P2-IP/PERF1.md`, at most 60 lines, no model names. Commit trailers exactly:
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4
