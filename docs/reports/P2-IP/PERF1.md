# P2-IP-PERF1 report: the hidden-record filter is fast on Postgres (same answers)

Deviations: none outside scope. One existing assertion changed (`test_the_check_is_pushed_into_the_statement`
counted parts by ` UNION ALL `; the link tables are now a UNION inside each hop, so it counts `SELECT hr.id FROM`).
No schema change, no index, no new table, no projection rebuild: APPROVALS needs only "core interface behaviour unchanged".

## Cause
`hidden_sql` repeated, for each of about 13 parts, a join of `cur_core_record` to 22 link tables on `COALESCE` keys.
Postgres also under-sized the result, so `id NOT IN (...)` was not hashed and was re-scanned for every outer row (and JIT ran).

## Decisions
1. Whole-ledger form (`not_hidden`, no `only`): one `WITH _cf_chain AS (...)` at the head of `hidden_sql`, computed once
   with the same flat per-table LEFT JOINs (the planner knows each key is unique, so it sizes the result right); every
   part reads `_cf_chain` (`id, subj, rid, rtype`). A single link-union derived table was tried first and rejected: the
   planner guessed 197M rows and fell back to a non-hashed `NOT IN` (30 s at 26k records).
2. `only` form (`not_hidden_each`, `is_hidden`, `hidden_among`): unchanged chain text (inline flat joins). Key-lookup
   scalar subqueries were tried and rejected: no faster on Postgres at 26k records and 10x slower on SQLite.
3. `_own_draft` is `hr.id IN (SELECT d.id ...)`, not a correlated `EXISTS` (the planner priced the EXISTS at 5e5 and JIT
   compiled for 3 s; same ids, `hr.id` is never NULL).
4. Not done: NOT EXISTS rewrite (would change NULL behaviour of `not_hidden`); an index (plans use the primary keys).
Text is portable (SQLite and Postgres); only module-declared names are interpolated; `WITH` sits inside the caller's
`NOT IN (...)`.

## Before / after (Postgres, scratch schema, equivalence world x N, ANALYZE run, viewer `ann`)
| statement | records | before | after |
|---|---|---|---|
| whole `NOT IN` over cur_core_record | 1,807 | 33.9 s | 22 ms, peak backend RSS 38 MB |
| whole | 25,887 | not run (grows with records and parts) | 0.35 s, 239 MB |
| one record, bound id (`only`) | 25,887 | plan 175 ms, exec 6 ms | unchanged (same text) |
| `not_hidden_each` over 5 rows (the card lookup shape) | 25,887 | plan 176 ms, exec 6 ms | unchanged |
`not_hidden_each` over all 26k rows at once is slow before and after (about 2.5 ms a row); no reader does that. SQLite whole form: 0.28 s before and after (it was never slow).
Not measured: the real QR demo ledger (backend memory there was 7.5 GB; the likely cause is the non-hashed `NOT IN` over a 12M-row estimate, gone here). The per-statement planning cost of the `only` form (88 kB of text) is untouched.

## Tests
`tests/confidentiality/test_hidden_sql_equal_old.py` (new, SQLite and Postgres): world written straight into the `cur_*`
tables: all 4 sources and their children, all 14 link types, one and two hops, a chain of three, dangling and missing
subjects, a missing source row, a NULL class, drafts of two authors, an author's restricted draft, a draft with no author,
constraints. Old builder copied in as reference. For 7 viewers (lowest, user named on a privileged item, other user,
restricted controller, restricted and named, agent, restricted agent): whole set equal, correlated `only` over every id
equal, bound `only` on a sample equal, `is_hidden`, `not_hidden`, `not_hidden_each`, `hidden_among` equal to old;
a test shows the viewers differ; system viewer hides nothing.

## Mutation
Sentinel (`<=` to `<` in `_allowed`): killed. Targeted, all killed by the equivalence test: `_HOPS` 2 to 1; last source part
dropped; author exemption removed; draft parts removed; system viewer check off.

## Gates
See `.gate/summary.txt` lines below. `test_offline_capture.py` (2 tests) fails on the base commit as well (checked with
my change stashed); unrelated.

## Candidate learnings
- A derived table over `UNION ALL` has no key statistics: the join estimate explodes and a `NOT IN` loses its hash.
  Keep the flat per-table joins, or use key lookups.
- A correlated `EXISTS` inside a `NOT IN` branch can price a plan high enough to start JIT.
- Equivalence world through `cur_*` inserts needs per-dialect "required column" discovery (pg8000 breaks SQLAlchemy reflection).
