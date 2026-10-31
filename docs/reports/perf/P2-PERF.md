# P2-PERF: the everyday screens at 10,000 records

Branch `p2/perf`; code measured `0e25090` (the commits were re-written once to add the trailers; the trees are the same). Numbers: `P1-UX-perf.md` (before and after table), `P1-UX-perf.json`, `P1-UX-perf-before.json`. No pytest was run (owner policy); `just check` is clean.

## Headline (median ms at 10,000 records, before -> after; sqlite / postgres / remote)
| Action | sqlite | postgres | remote |
|---|---:|---:|---:|
| Open RFI log | 1,413 -> 227 | 547 -> 365 | 1,521 -> 234 |
| RFI Enter (Details) | 2,335 -> 182 | 919 -> 365 | 2,563 -> 244 |
| RFI type a filter (last key) | 1,131 -> 44 | 272 -> 183 | 1,192 -> 73 |
| Open correspondence register | 1,483 -> 314 | 582 -> 386 | 1,536 -> 262 |
| Open document register | 15,171 -> 267 | 14,542 -> 274 | 15,164 -> 247 |
| Document filter (last key) | 13,992 -> 16 | 13,513 -> 41 | 13,654 -> 22 |
| Grid: launch / text filter | 259 -> 200 / 237 -> 121 | 241 -> 340 / 125 -> 150 | 325 -> 292 / 250 -> 125 |

## Causes (profile first) and fixes
1. **Document register 15 s**: `status_labels()` parsed the revision-scheme YAML for every row (10,000 times). Cached per file edit; the register opens on its first 500 rows and reads the rest (up to 5,000) when the cursor nears the end or a filter is typed; the table draws 120 rows and takes chunks (Textual measures every cell: 0.6 s for 5,000 rows).
2. **Every confidentiality check built the whole hidden set**: `is_hidden`, `hidden_among`, `hidden_event_streams`, `get_record(_by_id)`, link reads and the lists each listed every hidden record (about 100 ms on SQLite and 250 ms on Postgres at 31,000 confidential records), 13 times per Enter. Now the id is pushed into the test (`hidden_sql(only=...)`), a record is found by key and then tested, links tested per row (`not_hidden_each`), and the first page of each list is read and its hidden rows looked up (`visible_rows`; same rows, same order, hidden rows use no place). Proved equal to the old SQL by differential scripts on SQLite and Postgres (all kinds of viewer, links across hidden records, 400-700 hidden rows among the newest).
3. **Workflow and link definitions re-parsed on every call** (13 YAML files, 120 ms; the record header asks): parsed again only when a file changes (`tl_core.filesig`).
4. **RFI/letter timeline read every clock of the project** (and only the first 1,000): uses the item's own clocks.
5. **Record screen read all seven tabs on open**: Properties, Links, Trace and Thread read when first shown; repeated reads of one refresh answered once (`tl_tui.reads.Reads`); labels kept per client for 20 s (`labels_load`, `forget_labels`).
6. **Filter keys**: cells are worked out once per read of the rows, the panel and bar follow the list and a run of keys reads one panel (no key reads the log from the database; none did, but each re-drew every row and re-read the panel).
7. `find_*` by number scanned the scope (no index on `number`): the key (indexed, equal to the number) is tried first. Grid: first page and filtered counts of up to 3,000 rows no longer list every hidden record.

## Still over 250 ms (cause)
- **Postgres** RFI/letter open (365-386) and Enter (365-374), document Enter (297), grid launch (340): the driver is pure Python (pg8000), 2-8 ms a statement, about 50 statements an Enter and 500 ids to check on an open; plus a viewer lookup per client call (kept: a revoked role must apply to the next call). Textual's compose and paint is about 100 ms of every figure.
- **Correspondence register open**: sqlite 314, remote 262 (view over 20,000 letters and RFIs sorted by number; SQLite has no ANALYZE statistics and reads every wide core record: an ANALYZE of the ledger made the RFI list query a third faster in a test, an index on `cur_core_record(type)` would help the hidden test; both are outside this piece).
- Within noise of the line: document register open (sqlite 267, postgres 274), grid number/code filters (254-303, count of more than 3,000 matches), remote Enter (244-268).
- Not a P2 effect: the grid was already 320-370 on the branch before this work on this machine (P1 measured 237-259 on older code); this work brings it to 200-340.

## Stale pins (not run; expect these to need a one-line change)
- Tests that read the Properties, Links, Trace or Thread tab without switching to it (`test_properties_tab`, `test_psets_tab`, `test_trace_tab`, `test_thread_tab`, `test_record_view`, `test_record_screen`, `test_links_tab`, `test_links_thread_plain`, `test_keymap`, `test_embedded_real_services`): switch first (`view.show_tab(...)`).
- Tests that read `#log-panel-text` or the actions bar right after the rows load: they now follow after the first refresh (one more `pilot.pause()`).
- Tests that count `list_clocks` calls from a record's timeline; tests that count table rows above 120 (none found).
- New, unrun tests: `packages/tl-core/tests/test_definition_cache.py`, `tests/confidentiality/test_core.py::test_visible_rows_*`, `packages/tl-tui/tests/test_reads_and_labels.py`, three in `test_log_screen.py`.

## Not reached
Postgres statement count (batching a record screen into one call); `ANALYZE` for SQLite ledgers; seeding at 10,000 takes 100 minutes (every command reads the whole register: letters 2,779 s, documents 3,012 s) so `just perf-ux` now has `--seed-dir` to keep seeded ledgers. The bench also needed two repairs for the P1-UX3 layout (`widget_text` read a panel's drawn form; the list-ready test counted every row).

## Candidate learnings
- The hidden-record test as one `OR` of `NOT EXISTS` is twice as fast on SQLite and 20 times slower on Postgres than `UNION ALL` parts (Postgres turns each part into an anti-join, not an `OR`); measure both before changing SQL shared by the two.
- A query that names its ids once is cheaper than one that repeats the list per part (5,500 binds cost 60 ms more in the Postgres driver); test each row by a correlated lookup instead.
