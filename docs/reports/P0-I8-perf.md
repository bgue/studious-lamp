# Performance report — P0-I8 workstream D (brief §15 targets at 100k records)

This report gives the measured numbers for the brief §15 targets on SQLite and Postgres at 100,000 records, what was slow, what was fixed with its before and after, and what still misses a target. Plan: `docs/tickets/P0-I8/README-D.md`; how to run it again: `docs/runbooks/performance-benches.md`; workstream report: `docs/reports/P0-I8-D.md`.

## Verdict
| Target (brief §15) | SQLite | Postgres |
|---|---|---|
| Grid scroll, p95 < 150 ms at 100k rows | met (worst 2.6 ms) | met (worst 14.4 ms) |
| Grid sort, p95 < 150 ms | NOT MET for one sort: pset property, 163 ms in run 1 and 129 ms in run 2 | met (worst 105 ms) |
| Grid filter, p95 < 150 ms | NOT MET for four filters (D1, D3) | NOT MET for three filters (D1) and one cold-cache outlier in run 1 (D4) |
| TUI grid render (headless pilot), p95 < 150 ms | met (worst 108 ms) | met (worst 72 ms) |
| Realtime, change visible to another client < 2 s | met (API path 9 ms, other process 254 ms) | met (API path 41 ms, other process 254 ms) |
| Rebuild, hours not days | met: 100k records in the table below | met: 100k records in the table below |

Where it misses, the cause and a proposed fix are in *Deviations*.

## Machine and runs
- `Intel(R) Xeon(R) Processor @ 2.80GHz`, 4 CPUs, 16479424 kB, kernel 6.18.44-fc-v114, Python 3.12.3, SQLite 3.45.1, Postgres 16 (native cluster, loopback, TLS off). Code: `7c5383e` (branch `p0/i8d` after the merge of `p0/i8`, which holds workstreams A, B and C).
- The container is shared with other agents. Final run 1: load average [1.87, 1.44, 1.17] at start and [1.3, 1.38, 1.3] at the end (low). Run 2 (repeat, same code): load average [0.99, 1.3, 1.28] at start. The load before every round is in the results files (`dev/data/bench/results/*-final-*.json`).
- Dataset: 100,000 `core.Record` with five pset values each, 199,980 links (about two per record), 60,475 workflow transitions on 30% of the records: 360,455 events, identical ledger head hash on both dialects.
- Method: 3 warm-up calls, then 3 rounds of 20 calls (10 for the filters and sorts); median and p95 over all timed calls of all rounds (nearest rank). The p95 of each round is in the results files. See the runbook.
- Run times: a full run of `just bench` (both dialects) takes 13 to 14 minutes. The repeated rebuilds run on a 5,000-record dataset; the 100k rebuild runs once per dialect on its own (`just bench-rebuild`).

## Results by target (run 1)
Informational rows (paging beyond the grid's 5000-row cap, the 5000-row reload, the pilot's own settle time, the POST alone) are shown but are not part of a verdict. The per-filter `count` and `page` rows are in the results files.

## Grid scroll (p95 target 150 ms)

| dialect | scenario | median ms | p95 ms | target ms | met |
| --- | --- | ---: | ---: | ---: | --- |
| sqlite | first_page | 1.8 | 2.6 | 150 | yes |
| sqlite | scroll_within_cap | 2.1 | 2.6 | 150 | yes |
| sqlite | page_beyond_cap | 15.2 | 1706.4 | - | info |
| sqlite | reload_5000_rows | 43.6 | 200.5 | - | info |
| postgres | first_page | 7.1 | 10.4 | 150 | yes |
| postgres | scroll_within_cap | 7.5 | 14.4 | 150 | yes |
| postgres | page_beyond_cap | 27.4 | 103.1 | - | info |
| postgres | reload_5000_rows | 140.8 | 340.8 | - | info |

Verdict sqlite: met (worst p95 2.6 ms)

Verdict postgres: met (worst p95 14.4 ms)

## Grid sort (p95 target 150 ms)

| dialect | scenario | median ms | p95 ms | target ms | met |
| --- | --- | ---: | ---: | ---: | --- |
| sqlite | sort key asc | 1.8 | 2.0 | 150 | yes |
| sqlite | sort key desc | 1.9 | 2.2 | 150 | yes |
| sqlite | sort title asc | 39.6 | 41.8 | 150 | yes |
| sqlite | sort status asc | 40.0 | 46.1 | 150 | yes |
| sqlite | sort type asc | 38.3 | 44.5 | 150 | yes |
| sqlite | sort created_at desc | 2.2 | 2.5 | 150 | yes |
| sqlite | sort updated_at desc | 2.3 | 2.7 | 150 | yes |
| sqlite | sort version desc | 38.6 | 68.9 | 150 | yes |
| sqlite | sort psets.valve_data.size_in asc | 120.3 | 162.7 | 150 | NO |
| postgres | sort key asc | 7.5 | 8.3 | 150 | yes |
| postgres | sort key desc | 7.5 | 12.9 | 150 | yes |
| postgres | sort title asc | 38.5 | 44.8 | 150 | yes |
| postgres | sort status asc | 38.0 | 48.6 | 150 | yes |
| postgres | sort type asc | 36.8 | 41.9 | 150 | yes |
| postgres | sort created_at desc | 8.2 | 9.1 | 150 | yes |
| postgres | sort updated_at desc | 8.3 | 16.1 | 150 | yes |
| postgres | sort version desc | 23.7 | 28.0 | 150 | yes |
| postgres | sort psets.valve_data.size_in asc | 91.5 | 104.7 | 150 | yes |

Verdict sqlite: NOT MET (worst p95 162.7 ms in sort psets.valve_data.size_in asc)

Verdict postgres: met (worst p95 104.7 ms)

## Grid filter (p95 target 150 ms)

| dialect | scenario | median ms | p95 ms | target ms | met |
| --- | --- | ---: | ---: | ---: | --- |
| sqlite | filter status = Approved: apply (count + page) | 23.6 | 26.6 | 150 | yes |
| sqlite | filter status != Approved: apply (count + page) | 23.8 | 24.1 | 150 | yes |
| sqlite | filter type = core.Record: apply (count + page) | 22.9 | 24.0 | 150 | yes |
| sqlite | filter text search (key, title): apply (count + page) | 170.9 | 194.4 | 150 | NO |
| sqlite | filter pset text = (20% match): apply (count + page) | 63.7 | 75.5 | 150 | yes |
| sqlite | filter pset text = (one record): apply (count + page) | 1.2 | 2.1 | 150 | yes |
| sqlite | filter pset number >=: apply (count + page) | 101.0 | 107.7 | 150 | yes |
| sqlite | filter pset + pset + status: apply (count + page) | 98.2 | 107.5 | 150 | yes |
| sqlite | filter linked(references): apply (count + page) | 312.7 | 364.8 | 150 | NO |
| sqlite | filter count(linked) >= 3: apply (count + page) | 951.5 | 1016.6 | 150 | NO |
| sqlite | filter missing(link): apply (count + page) | 357.0 | 407.9 | 150 | NO |
| sqlite | filter created_at >= date: apply (count + page) | 8.3 | 8.7 | 150 | yes |
| postgres | filter status = Approved: apply (count + page) | 29.3 | 36.7 | 150 | yes |
| postgres | filter status != Approved: apply (count + page) | 31.3 | 37.4 | 150 | yes |
| postgres | filter type = core.Record: apply (count + page) | 32.9 | 47.4 | 150 | yes |
| postgres | filter text search (key, title): apply (count + page) | 92.4 | 116.0 | 150 | yes |
| postgres | filter pset text = (20% match): apply (count + page) | 65.9 | 93.7 | 150 | yes |
| postgres | filter pset text = (one record): apply (count + page) | 3.6 | 162.1 | 150 | NO |
| postgres | filter pset number >=: apply (count + page) | 42.1 | 47.2 | 150 | yes |
| postgres | filter pset + pset + status: apply (count + page) | 83.1 | 98.6 | 150 | yes |
| postgres | filter linked(references): apply (count + page) | 342.2 | 406.9 | 150 | NO |
| postgres | filter count(linked) >= 3: apply (count + page) | 838.0 | 904.6 | 150 | NO |
| postgres | filter missing(link): apply (count + page) | 345.9 | 398.9 | 150 | NO |
| postgres | filter created_at >= date: apply (count + page) | 35.0 | 48.4 | 150 | yes |

Verdict sqlite: NOT MET (worst p95 1016.6 ms in filter count(linked) >= 3: apply (count + page))

Verdict postgres: NOT MET (worst p95 904.6 ms in filter count(linked) >= 3: apply (count + page))

## Grid render in the headless pilot (p95 target 150 ms)

| dialect | scenario | median ms | p95 ms | target ms | met |
| --- | --- | ---: | ---: | ---: | --- |
| sqlite | load page | 2.1 | 3.9 | 150 | yes |
| sqlite | apply filter | 62.1 | 108.2 | 150 | yes |
| sqlite | filter to painted | 89.2 | 135.7 | - | info |
| sqlite | pilot settle alone | 20.9 | 22.0 | - | info |
| sqlite | paint visible rows | 3.5 | 6.2 | 150 | yes |
| postgres | load page | 8.0 | 11.3 | 150 | yes |
| postgres | apply filter | 41.6 | 72.4 | 150 | yes |
| postgres | filter to painted | 69.2 | 100.0 | - | info |
| postgres | pilot settle alone | 21.1 | 22.2 | - | info |
| postgres | paint visible rows | 3.5 | 6.6 | 150 | yes |

Verdict sqlite: met (worst p95 108.2 ms)

Verdict postgres: met (worst p95 72.4 ms)

## Realtime (p95 target 2000 ms)

| dialect | scenario | median ms | p95 ms | target ms | met |
| --- | --- | ---: | ---: | ---: | --- |
| sqlite | api write to sse | 4.8 | 8.9 | 2000 | yes |
| sqlite | api write (the POST alone) | 5.7 | 10.2 | - | info |
| sqlite | other process write to sse | 251.0 | 253.9 | 2000 | yes |
| postgres | api write to sse | 15.8 | 40.8 | 2000 | yes |
| postgres | api write (the POST alone) | 17.0 | 42.0 | - | info |
| postgres | other process write to sse | 252.7 | 253.7 | 2000 | yes |

Verdict sqlite: met (worst p95 253.9 ms)

Verdict postgres: met (worst p95 253.7 ms)

## Rebuild (no hard target: hours, not days)

| dialect | scenario | median ms | p95 ms | target ms | met |
| --- | --- | ---: | ---: | ---: | --- |
| sqlite | full rebuild (5000 records) | 15286.2 | 15471.1 | - | n/a |
| postgres | full rebuild (5000 records) | 110432.8 | 111623.4 | - | n/a |

Reading the rebuild table: *rebuild only X* is a real `tl projections rebuild --only X`, which scans the whole ledger and applies one projector; it includes the ledger read (about 0.4 s per 18,000 events on SQLite).

## Before and after
Before: the first run of the harness on the code of S60 (SQLite at load average 4 to 10, Postgres at load 3 to 5; files `*baseline-*`). After: run 1 and run 2 of the final code. Both dialects, 100k records, p95 in ms. The cold-start outliers noted below show in the difference between the two runs.

| dialect | scenario | before p95 ms | after p95 ms (run 1) | after p95 ms (run 2) |
| --- | --- | ---: | ---: | ---: |
| sqlite | first_page | 88.0 | 2.6 | 1.9 |
| sqlite | scroll_within_cap | 76.0 | 2.6 | 2.3 |
| sqlite | page_beyond_cap | 281.8 | 1706.4 | 24.0 |
| sqlite | reload_5000_rows | 412.0 | 200.5 | 209.4 |
| sqlite | sort key asc | 127.1 | 2.0 | 2.0 |
| sqlite | sort key desc | 479.5 | 2.2 | 2.2 |
| sqlite | sort title asc | 108.6 | 41.8 | 52.4 |
| sqlite | sort status asc | 118.0 | 46.1 | 45.9 |
| sqlite | sort type asc | 95.6 | 44.5 | 44.2 |
| sqlite | sort created_at desc | 532.1 | 2.5 | 2.7 |
| sqlite | sort updated_at desc | 524.2 | 2.7 | 2.4 |
| sqlite | sort version desc | 94.9 | 68.9 | 39.4 |
| sqlite | sort psets.valve_data.size_in asc | 281.4 | 162.7 | 128.6 |
| sqlite | filter status = Approved: apply (count + page) | 143.8 | 26.6 | 23.0 |
| sqlite | filter status != Approved: apply (count + page) | 132.9 | 24.1 | 34.8 |
| sqlite | filter type = core.Record: apply (count + page) | 144.9 | 24.0 | 22.6 |
| sqlite | filter text search (key, title): apply (count + page) | 308.9 | 194.4 | 171.6 |
| sqlite | filter pset text = (20% match): apply (count + page) | 602.9 | 75.5 | 66.9 |
| sqlite | filter pset text = (one record): apply (count + page) | 548.0 | 2.1 | 0.8 |
| sqlite | filter pset number >=: apply (count + page) | 559.1 | 107.7 | 137.5 |
| sqlite | filter pset + pset + status: apply (count + page) | 227.4 | 107.5 | 136.8 |
| sqlite | filter linked(references): apply (count + page) | 1742.3 | 364.8 | 344.5 |
| sqlite | filter count(linked) >= 3: apply (count + page) | 5498.1 | 1016.6 | 1054.2 |
| sqlite | filter missing(link): apply (count + page) | 1002.0 | 407.9 | 400.4 |
| sqlite | filter created_at >= date: apply (count + page) | 181.4 | 8.7 | 11.3 |
| sqlite | load page | 100.8 | 3.9 | 2.8 |
| sqlite | apply filter | 474.1 | 108.2 | 107.6 |
| sqlite | filter to painted | 544.9 | 135.7 | 139.3 |
| sqlite | paint visible rows | 7.7 | 6.2 | 6.4 |
| sqlite | api write to sse | 16.4 | 8.9 | 8.8 |
| sqlite | api write (the POST alone) | 17.4 | 10.2 | 9.8 |
| sqlite | other process write to sse | 256.5 | 253.9 | 251.7 |
| postgres | first_page | 31.8 | 10.4 | 12.0 |
| postgres | scroll_within_cap | 33.3 | 14.4 | 8.5 |
| postgres | page_beyond_cap | 121.3 | 103.1 | 40.7 |
| postgres | reload_5000_rows | 415.2 | 340.8 | 361.9 |
| postgres | sort key asc | 50.9 | 8.3 | 7.9 |
| postgres | sort key desc | 71.0 | 12.9 | 11.1 |
| postgres | sort title asc | 57.2 | 44.8 | 57.6 |
| postgres | sort status asc | 76.7 | 48.6 | 49.6 |
| postgres | sort type asc | 63.0 | 41.9 | 49.4 |
| postgres | sort created_at desc | 131.7 | 9.1 | 8.4 |
| postgres | sort updated_at desc | 167.6 | 16.1 | 7.6 |
| postgres | sort version desc | 91.9 | 28.0 | 35.5 |
| postgres | sort psets.valve_data.size_in asc | 193.1 | 104.7 | 107.9 |
| postgres | filter status = Approved: apply (count + page) | 74.3 | 36.7 | 36.1 |
| postgres | filter status != Approved: apply (count + page) | 81.8 | 37.4 | 32.3 |
| postgres | filter type = core.Record: apply (count + page) | 102.6 | 47.4 | 44.6 |
| postgres | filter text search (key, title): apply (count + page) | 87.8 | 116.0 | 115.3 |
| postgres | filter pset text = (20% match): apply (count + page) | 186.9 | 93.7 | 95.5 |
| postgres | filter pset text = (one record): apply (count + page) | 100.1 | 162.1 | 3.4 |
| postgres | filter pset number >=: apply (count + page) | 165.5 | 47.2 | 49.9 |
| postgres | filter pset + pset + status: apply (count + page) | 130.5 | 98.6 | 108.1 |
| postgres | filter linked(references): apply (count + page) | 1392.7 | 406.9 | 396.0 |
| postgres | filter count(linked) >= 3: apply (count + page) | 3766.7 | 904.6 | 881.4 |
| postgres | filter missing(link): apply (count + page) | 1409.6 | 398.9 | 382.0 |
| postgres | filter created_at >= date: apply (count + page) | 81.2 | 48.4 | 40.2 |
| postgres | load page | 45.6 | 11.3 | 13.0 |
| postgres | apply filter | 143.3 | 72.4 | 74.7 |
| postgres | filter to painted | 170.8 | 100.0 | 102.2 |
| postgres | paint visible rows | 6.3 | 6.6 | 4.7 |
| postgres | api write to sse | 23.6 | 40.8 | 19.8 |
| postgres | api write (the POST alone) | 25.2 | 42.0 | 22.2 |
| postgres | other process write to sse | 254.2 | 253.7 | 256.5 |

## Hot spots found and fixed
Each fix has its before and after number (SQLite and Postgres where both were measured). Numbers are p95 of the harness unless a one-call figure is named.

| # | Hot spot | Found by | Fix | Before to after |
|---|---|---|---|---|
| 1 | Default page, count and filters scanned `cur_core_record` through the unique `(scope, key)` index and sorted the table | `EXPLAIN` (SQLite `USE TEMP B-TREE FOR ORDER BY`; Postgres sequential scan and sort) | Index `(scope, voided, created_at, id)` through `tl:ix_*` in `schema/core/record.yaml` (S61) | first page SQLite 88 to 2.6 ms; Postgres 32 to 10 ms |
| 2 | Newest-first sorts (created, updated, key descending) sorted 100k rows; the cost of a top-N sort on SQLite depends on the arrival order and newest-first is its worst case | the harness (480 to 530 ms) | Indexes on `updated_at`, and on the expression `(key IS NULL OR key = '')` for key ascending and descending (S61); no `IS NULL` term in front of NOT NULL columns (S62) | SQLite key desc 480 to 2.2 ms, created desc 532 to 2.5 ms, updated desc 524 to 2.7 ms; Postgres 71, 132, 168 to 13, 9, 16 ms |
| 3 | Pset filters probed `cur_pset_values` once per record (correlated `EXISTS`) | `EXPLAIN` | Covering indexes `(path, value_text, record_id)` and `(path, value_num, record_id)`; the compiler builds `id IN (set)` (S61, S62) | one-record filter SQLite 548 to 2 ms, Postgres 100 to 162 (cold outlier) or 3.4 ms (run 2); 20% filter 603 to 75 ms and 187 to 94 ms; number filter 559 to 108 ms and 166 to 47 ms |
| 4 | Link filters probed `cur_links` and the record table once per record | `EXPLAIN` and the harness | Indexes `(relation, status, from_id, to_id)` and `(relation, status, to_id, from_id)`; sets instead of probes; `count(linked)` that excludes zero groups the link ends once (S61, S62) | linked SQLite 1742 to 365 ms, Postgres 1393 to 407 ms; count(linked)>=3 5498 to 1017 ms and 3767 to 905 ms; missing(link) 1002 to 408 ms and 1410 to 399 ms. Still above 150 ms: D1 |
| 5 | `list_records` ordered by `created_at` or `updated_at` failed on Postgres (a timestamp compared with `''`) | the Postgres sort bench | The "empty sorts last" term only for text columns (S60) | an error to 9 ms (parity test added) |
| 6 | Postgres sessions spoke TLS on loopback, a quarter of the statement cost | profile of a Postgres seed | `?sslmode=disable` mapped in the adapter URL; every supported `sslmode` is mapped explicitly and the others are refused (S60, S61) | seed of 1,067 events 13.6 s to 9.7 s |
| 7 | `PsetProjector`: nine statements per new record | statement count | One multi-row insert; no reads for a new record (T61) | 9 to 2 statements; `rebuild only pset_values` SQLite 9.1 to 7.4 s (10k records), Postgres 38.5 to 17.3 s |
| 8 | `LinkProjector`: seven to nine statements per link event | statement count | One `INSERT ... SELECT ... ON CONFLICT DO UPDATE` per record end (T62) | 7–9 to 3 statements; `rebuild only links` SQLite 11.6 to 4.2 s (10k records), Postgres 76.8 to 54.5 s |
| 9 | **Feed projector: a rebuild on Postgres grew quadratically.** The open card lived under a unique index on one key; each closed card left a dead entry that a rebuild (one transaction) could not remove, so every lookup and unique check read them all | per-statement timing of one projector over a rebuild | The open card is the newest card of the scope, read through `(scope, first_seq)` with `first_seq < :seq`; no unique key on `open_scope` (S65, decision D-S65) | Postgres rebuild of 10k records 570 s to 229 s; the feed's share 418 s to 98 s. At 100k records the old shape would have taken hours |

## Rebuild at 100k records (run once per dialect)
Full projection rebuild of the 100k dataset (360,455 events), in one transaction, from the ledger:

| dialect | records | events | seconds | events/s | in projectors (s) |
| --- | ---: | ---: | ---: | ---: | --- |
| sqlite | 100000 | 360455 | 332 | 1086 | feed 112, pset_values 67, outbox 61, links 56, core_record 9, workflow 8 |
| postgres | 100000 | 360455 | 2299 | 157 | feed 979, links 532, outbox 426, pset_values 189, workflow 80, core_record 63 |

Repeated rebuild of the 5,000-record dataset (18,023 events), 3 rounds, run 1:

| dialect | median s | p95 s | events/s | seconds in each projector (first round) |
| --- | ---: | ---: | ---: | --- |
| sqlite | 15.3 | 15.5 | 1179 | feed 5.3, pset_values 3.2, outbox 3.0, links 2.1 |
| postgres | 110.4 | 111.6 | 163 | feed 45.8, links 24.8, outbox 19.9, pset_values 8.6, workflow 3.8, core_record 2.9 |

Before the work of this workstream a full rebuild of 10,000 records took 52.9 s on SQLite (725 events/s) and about 570 s on Postgres (65 events/s). At 10,000 records the final code takes 32 s on SQLite (T61, T62; measured before S65, which does not change SQLite) and 229 s on Postgres. Per-projector rebuilds work (the table above) and cost one ledger scan plus that projector. The Postgres rate is bound by statements (about 0.4 ms each, a pure-Python driver and a round trip), so the remaining time is where the statements are: the feed (about 2.5 ms per event), the links, the outbox (one row per event, a read and an insert) and the pset projector. Brief R1 asked for "hours, not days": met on both dialects at 100k records, with the Postgres figure in the table above.

## Deviations
| # | What | Measured | Cause | Proposed fix |
|---|---|---|---|---|
| D1 | `count(linked)` filters, and the `linked` and `missing(link)` filters, over 150 ms at 100k records | SQLite `count(linked)>=3` 1017 ms, `linked(references)` 365 ms, `missing(link)` 408 ms; Postgres 905, 407 and 399 ms. Postgres, `count(linked)>1` about 435 ms and `count(linked)=0` about 720 ms (reviewer, same dataset) | The result is a count or a set over 200,000 link rows (400,000 link ends), and a link counts only when the record at its other end exists, so each end is joined to the record table. Grouping 400,000 ends costs 0.3 to 1 s | Answer these from `cur_link_counts` (maintained per record by the link projector, one row per record). It changes which table answers the query, which the documentation puts over `cur_links`, and the query tests seed `cur_links` alone, so it needs a contract decision and its own parity proof; it was tried and reverted. Or add a counts column that includes the existence rule |
| D2 | Grid sort on a pset property over 150 ms on SQLite | 163 ms (run 1), 129 ms (run 2); Postgres 105 ms | The sort joins `cur_pset_values` once and orders by its three typed value columns, so no index serves it | The grid knows the property's type from the form metadata: sort on `value_num` or `value_text` alone, which `(path, value_num, record_id)` and `(path, value_text, record_id)` can serve |
| D3 | Text search on SQLite over 150 ms | 194 ms (run 1), 172 ms (run 2); Postgres 116 ms | `LIKE '%x%'` over key, title and description is a scan of 100k rows | The compiler's own comment: FTS5 on SQLite and a trigram or full-text index on Postgres (Phase 1) |
| D4 | Cold-start outliers | SQLite `page_beyond_cap` 1706 ms in run 1, 24 ms in run 2; Postgres one-record pset filter 162 ms in run 1, 3.4 ms in run 2 | The first touches of pages after a different dataset ran: the file or relation cache was cold; the median in both runs is 15 ms and 3.7 ms | None needed; the repeat shows it. `page_beyond_cap` is also outside the grid's 5000-row cap and is not part of a verdict |
| D5 | Reloading 5000 rows (what a live update does once a user has paged to the cap) takes 200 ms on SQLite and 340 ms on Postgres | informational | The grid re-reads every loaded row on each change (`END_CAP` rows) | Re-read only the changed rows by id; a grid ticket |
| D6 | Repeated measurements: the full 100k rebuild is one measurement per dialect | see the table | A rebuild of 100k records on Postgres takes tens of minutes | The spread is shown by the 5,000-record rebuild repeated three times (p95 within 2% of the median on both dialects) |

## Notes
- **Statistics matter on SQLite.** A one-record pset filter took 0.2 ms with the table statistics (`ANALYZE`) and 12 ms without them. The bench datasets were analysed; run `ANALYZE` (or `PRAGMA optimize`) after a bulk load or a rebuild.
- **Negations.** An explicit `-x`, `NOT` or `-linked(x)` compiles to `NOT (id IN (set))`, which is correct because ids are never NULL. On Postgres it is a hashed SubPlan, which degrades only when the set outgrows `work_mem`. `!=`, `= null` on a pset and `missing(...)` use a correlated `NOT EXISTS`.
- **Existing databases keep the old unique index on `cur_feed_items.open_scope`.** They stay correct and are slow on a rebuild until `ux_cur_feed_items_open_scope` is dropped or the database is rebuilt into a fresh one; that is a migration, filed as a follow-up under the data-migration gate.
- **Re-applying an event without a reset.** After S65, applying an event that is already applied hits the primary key of the card or tag row; before, it double-counted. Neither is a supported path (a rebuild resets first).
- **Index annotations** (`tl:ix_*`) add four indexes to `cur_core_record`, two to `cur_pset_values`, two to `cur_links` and one to `cur_feed_items`. Build spec 03 §9 lists only the unique key; the orchestrator amended it.
- **Realtime.** The in-process path (the API writes, the bus delivers) takes 9 ms on SQLite and 20 to 41 ms on Postgres. A write from another process reaches the stream through the change-feed poller and takes the poll interval (0.25 s) plus a few ms. Postgres `LISTEN/NOTIFY` wake-ups exist for the poller but the API's feed hub does not use them yet; the 2 s target does not need it.
