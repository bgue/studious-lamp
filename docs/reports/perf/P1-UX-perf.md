# User-facing performance (P1-UX)

What a person waits for in the terminal app, measured with the real TUI driven headless by Textual's pilot against a seeded project. Re-run with `just perf-ux`; every number is also in `P1-UX-perf.json`. The earlier backend benchmark is `docs/reports/P0-I8-perf.md` (queries and the bare grid widget, 100k records); this report measures whole screens.

## Machine and run
- Date 2026-10-31, code `d82ba08`.
- CPU `Intel(R) Xeon(R) Processor @ 2.80GHz`, 4 CPUs; RAM 15.7 GB; disk `/dev/vda` 271 GB, 20 GB free (virtual block device, kernel rotational flag 1).
- Linux 6.18.44-fc-v185, Python 3.12.3, SQLite 3.45.1, Postgres 16.15. Load average at the start [2.11, 2.59, 2.67] (a shared container: expect noise of some milliseconds).
- Terminal 170x45 (columns x rows): the panel sits beside the list.

## How to read the numbers
- Milliseconds. **Median** and **p95** (nearest rank) over the timed repetitions of one action (**n**, at least 20) after untimed warm-up repetitions; **first** is the very first repetition in a fresh process (cold caches and connections). A figure of 1,000 ms or more is shown without decimals.
- A time runs from the key press to the moment the screen holds the answer *and* has been drawn (the app's screen refresh after it). The *state* median (answer held, not yet drawn) is the last column of each table. The harness's own cost, a key nothing is bound to, is under 1 ms (`floor` in the JSON).
- Backends: **sqlite** embedded SQLite file; **postgres** embedded, local Postgres (loopback, TLS off); **remote** the API in its own process on loopback over the same SQLite file, the TUI over HTTP. The live-update feed is off: only the screens are measured. No pytest, no mocks: the real app, the real services, the real database.
- Data per size: that many core records with property sets (the bulk writer of the benches), and that many RFIs, letters and documents through the command handlers (half of the RFIs submitted, half of the documents with a draft revision). The RFI log and the correspondence register list at most 500 lines and the document register 5,000 (it opens on its first 500 and reads the rest when the cursor nears the end or a filter is typed): at 10,000 records the list is cut, but the server still has the whole project.
- The filter rows time the **last** key of the filter; the earlier keys are typed with the rows held back (the document register has read its whole list by then, as the first key of a filter makes it). Every key filters the rows held and redraws the list (no key reads the log again), so a filter of n keys costs about n times the figure.
- The pilot normally waits for every animation after a key (a tab's underline takes 0.3 s); that wait is off here, since a person does not wait for it.

## Headline: median ms at 10,000 records

| Action | sqlite | postgres | remote |
|---|---:|---:|---:|
| Open the RFI log (Ctrl+G) until rows are shown | 227 | 365 | 234 |
| RFI log: move the cursor one row until the panel shows the record | 5.1 | 6.1 | 6.9 |
| RFI log: Enter until the record's Details are shown | 182 | 365 | 244 |
| RFI record: switch to Properties | 56.3 | 75.2 | 73.0 |
| RFI log: type a filter, the last key narrows the list | 43.5 | 183 | 72.5 |
| Open the correspondence register (F5) until rows are shown | 314 | 386 | 262 |
| Open the document register (F7) until rows are shown | 267 | 274 | 247 |
| Launch the app until the record grid shows its first rows | 200 | 340 | 292 |
| Record grid: property-set filter, text (psets.valve_data.body_material=SS316L) | 121 | 150 | 125 |

## Before and after at 10,000 records (median ms; before: code `c395eb6`, 2026-10-31)

| Action | sqlite | postgres | remote |
|---|---:|---:|---:|
| Open the RFI log (Ctrl+G) until rows are shown | 1,413 -> 227 | 547 -> 365 | 1,521 -> 234 |
| RFI log: move the cursor one row until the panel shows the record | 4.4 -> 5.1 | 2.7 -> 6.1 | 14.2 -> 6.9 |
| RFI log: Enter until the record's Details are shown | 2,335 -> 182 | 919 -> 365 | 2,563 -> 244 |
| RFI record: switch to Properties | 45.0 -> 56.3 | 42.3 -> 75.2 | 42.9 -> 73.0 |
| RFI log: type a filter, the last key narrows the list | 1,131 -> 43.5 | 272 -> 183 | 1,192 -> 72.5 |
| Open the correspondence register (F5) until rows are shown | 1,483 -> 314 | 582 -> 386 | 1,536 -> 262 |
| Open the document register (F7) until rows are shown | 15,171 -> 267 | 14,542 -> 274 | 15,164 -> 247 |
| Launch the app until the record grid shows its first rows | 259 -> 200 | 241 -> 340 | 325 -> 292 |
| Record grid: property-set filter, text (psets.valve_data.body_material=SS316L) | 237 -> 121 | 125 -> 150 | 250 -> 125 |
| Correspondence: Enter until the letter's Details are shown | 2,381 -> 189 | 927 -> 374 | 2,555 -> 268 |
| Correspondence: type a filter, the last key narrows the list | 1,138 -> 24.3 | 274 -> 153 | 1,214 -> 60.0 |
| Documents: Enter until the document's Details are shown | 1,703 -> 171 | 1,073 -> 297 | 1,877 -> 228 |
| Documents: type a filter, the last key narrows the list | 13,992 -> 16.2 | 13,513 -> 41.2 | 13,654 -> 22.0 |

## Slow spots (median over 250 ms at 10,000 records)

- **Open the RFI log (Ctrl+G) until rows are shown**: postgres 365 ms. Postgres: the list statement and the hidden-record check of its 500 rows (500 ids through the pure-Python driver) take about 60 ms each, the panel's statements 100 ms; Textual draws about 100 ms on every backend.
  - cProfile: SQL 98 ms in 3 calls, slowest 88 ms: SELECT i.id, i.record_type, i.scope, i.number, i.title, i.status, i.voided, i.version, i.direction, i.medium, i.received_via, i.external_ref, i.messag
  - cProfile: SQL 72 ms in 11 calls, slowest 8 ms: SELECT 1 FROM cur_core_record x WHERE x.id = %s AND x.id IN (SELECT hr.id FROM cur_core_record hr WHERE hr.type IN ('correspondence.CommercialItem', '
  - cProfile: SQL 59 ms in 1 calls, slowest 59 ms: SELECT x.id FROM cur_core_record x WHERE x.id IN (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
- **RFI log: Enter until the record's Details are shown**: postgres 365 ms. Postgres: about 50 statements of 2-8 ms each (the pure-Python driver, a viewer lookup and a visibility check on every client call), then the seven-tab screen is composed and drawn (about 100 ms on every backend).
  - cProfile: SQL 116 ms in 11 calls, slowest 36 ms: SELECT 1 FROM cur_core_record x WHERE x.id = %s AND x.id IN (SELECT hr.id FROM cur_core_record hr WHERE hr.type IN ('correspondence.CommercialItem', '
  - cProfile: SQL 63 ms in 1 calls, slowest 63 ms: SELECT l.link_id, l.relation, l.status, l.pin, l.note, l.source, l.confidence, l.reason, l.declined, l.verified_by, l.verified_at, l.created_at, l.ver
  - cProfile: SQL 43 ms in 10 calls, slowest 34 ms: SELECT a.account_id, a.username, a.display_name, a.kind, a.roles_json, a.status, a.created_at, a.last_seq, t.locked_until FROM cur_account a LEFT JOIN
- **Open the correspondence register (F5) until rows are shown**: sqlite 314 ms, postgres 386 ms, remote 262 ms. The register is a view over every letter and RFI sorted by number: SQLite reads every wide core record of the scope for it (about 100 ms, no ANALYZE statistics) and the transmittal sources add 35 ms; Postgres adds the driver's cost to the same.
  - cProfile: SQL 110 ms in 4 calls, slowest 109 ms: SELECT id, record_type, scope, number, title, status, voided, version, direction, medium, received_via, external_ref, message_id, in_reply_to, from_pa
  - cProfile: SQL 39 ms in 1 calls, slowest 39 ms: SELECT id, scope, key, title, description, status, voided, version, created_at, direction, purpose, due_date, issued_on, response_code, response_note,
  - cProfile: SQL 7 ms in 1 calls, slowest 7 ms: SELECT x.id FROM cur_core_record x WHERE x.id IN (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
- **Correspondence: Enter until the letter's Details are shown**: postgres 374 ms, remote 268 ms. As the RFI record; remote: about 11 HTTP calls of 4-17 ms and the same drawing.
  - cProfile: SQL 144 ms in 11 calls, slowest 43 ms: SELECT 1 FROM cur_core_record x WHERE x.id = %s AND x.id IN (SELECT hr.id FROM cur_core_record hr WHERE hr.type IN ('correspondence.CommercialItem', '
  - cProfile: SQL 52 ms in 1 calls, slowest 52 ms: SELECT l.link_id, l.relation, l.status, l.pin, l.note, l.source, l.confidence, l.reason, l.declined, l.verified_by, l.verified_at, l.created_at, l.ver
  - cProfile: SQL 49 ms in 10 calls, slowest 39 ms: SELECT a.account_id, a.username, a.display_name, a.kind, a.roles_json, a.status, a.created_at, a.last_seq, t.locked_until FROM cur_account a LEFT JOIN
- **Open the document register (F7) until rows are shown**: sqlite 267 ms, postgres 274 ms. The first 500 rows take about 190 ms to read and draw; the paint adds the rest.
  - cProfile: SQL 8 ms in 1 calls, slowest 8 ms: SELECT x.id FROM cur_core_record x WHERE x.id IN (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
  - cProfile: SQL 5 ms in 4 calls, slowest 4 ms: SELECT id, scope, key, title, description, status, voided, version, conformance, doc_type, discipline, originator, confidentiality, revision_scheme, p
  - cProfile: SQL 3 ms in 6 calls, slowest 1 ms: SELECT 1 FROM cur_core_record x WHERE x.id = ? AND x.id IN (SELECT hr.id FROM cur_core_record hr WHERE hr.type IN ('correspondence.CommercialItem', 'c
- **Documents: Enter until the document's Details are shown**: postgres 297 ms. Postgres: as the RFI record (about 45 statements).
  - cProfile: SQL 110 ms in 8 calls, slowest 41 ms: SELECT 1 FROM cur_core_record x WHERE x.id = %s AND x.id IN (SELECT hr.id FROM cur_core_record hr WHERE hr.type IN ('correspondence.CommercialItem', '
  - cProfile: SQL 34 ms in 1 calls, slowest 34 ms: SELECT file_id, scope, record_id, slot, revision, sha256, size, content_type, filename, status, deduplicated, superseded_by, reason, uploaded_by, uplo
  - cProfile: SQL 17 ms in 8 calls, slowest 9 ms: SELECT a.account_id, a.username, a.display_name, a.kind, a.roles_json, a.status, a.created_at, a.last_seq, t.locked_until FROM cur_account a LEFT JOIN
- **Launch the app until the record grid shows its first rows**: postgres 340 ms, remote 292 ms. Launch reads the code lists and standards in 56 small statements (Postgres, remote: 3-4 ms each) before the first page.
  - cProfile: SQL 54 ms in 36 calls, slowest 3 ms: SELECT v.id, v.scope, v.code_list, v.code, v.label, v.meaning, v.crosswalk, v.origin, v.sort_order, v.effective_from, v.effective_to, v.lifecycle, v.s
  - cProfile: SQL 29 ms in 20 calls, slowest 3 ms: SELECT s.id, s.scope, s.kind, s.code, s.label, s.definition, s.edition, s.owner, s.adoption, s.value_list_policy, s.effective_from, s.effective_to, s.
  - cProfile: SQL 13 ms in 1 calls, slowest 13 ms: SELECT x.id FROM cur_core_record x WHERE x.id IN (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
- **Record grid: property-set filter, number (psets.valve_data.size_in>=12)**: sqlite 254 ms, postgres 276 ms, remote 264 ms. A filter that matches more than 3,000 records counts them with the hidden records listed once (NOT IN, 170-190 ms); a narrower filter tests each match and is under 150 ms.
  - cProfile: SQL 200 ms in 2 calls, slowest 171 ms: SELECT COUNT(*) FROM cur_core_record r WHERE r.scope = ? AND r.voided = ? AND r.id IN (SELECT pv1.record_id FROM cur_pset_values pv1 WHERE pv1.path = 
  - cProfile: SQL 3 ms in 1 calls, slowest 3 ms: SELECT x.id FROM cur_core_record x WHERE x.id IN (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
  - cProfile: SQL 2 ms in 1 calls, slowest 2 ms: SELECT r.id, r.key, r.type, r.scope, r.title, r.description, r.status, r.psets_json, r.voided, r.version, r.last_seq, r.effective_schema_hash, r.confo
- **Record grid: property-set filter, code (psets.valve_data.fail_action=FC)**: postgres 303 ms, remote 269 ms. A filter that matches more than 3,000 records counts them with the hidden records listed once (NOT IN, 170-190 ms); a narrower filter tests each match and is under 150 ms.
  - cProfile: SQL 201 ms in 2 calls, slowest 187 ms: SELECT COUNT(*) FROM cur_core_record r WHERE r.scope = %s AND r.voided = %s AND r.id IN (SELECT pv1.record_id FROM cur_pset_values pv1 WHERE pv1.path 
  - cProfile: SQL 28 ms in 1 calls, slowest 28 ms: SELECT r.id, r.key, r.type, r.scope, r.title, r.description, r.status, r.psets_json, r.voided, r.version, r.last_seq, r.effective_schema_hash, r.confo
  - cProfile: SQL 13 ms in 1 calls, slowest 13 ms: SELECT x.id FROM cur_core_record x WHERE x.id IN (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 

## Results by action

### Open the RFI log (Ctrl+G) until rows are shown

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 244 | 867 | 614 | 184 |
| 1,000 | postgres | 25 | 255 | 853 | 928 | 254 |
| 1,000 | remote | 25 | 262 | 821 | 238 | 113 |
| 10,000 | sqlite | 25 | 227 | 740 | 711 | 226 |
| 10,000 | postgres | 25 | 365 | 659 | 427 | 331 |
| 10,000 | remote | 25 | 234 | 818 | 324 | 227 |

### RFI log: move the cursor one row until the panel shows the record

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 4.9 | 50.6 | 27.5 | 4.9 |
| 1,000 | postgres | 25 | 4.9 | 6.8 | 115 | 4.9 |
| 1,000 | remote | 25 | 5.3 | 6.9 | 42.8 | 5.3 |
| 10,000 | sqlite | 25 | 5.1 | 46.0 | 38.5 | 5.1 |
| 10,000 | postgres | 25 | 6.1 | 36.8 | 170 | 6.1 |
| 10,000 | remote | 25 | 6.9 | 53.8 | 86.6 | 6.9 |

### RFI log: Enter until the record's Details are shown

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 176 | 252 | 212 | 77.1 |
| 1,000 | postgres | 25 | 269 | 328 | 1,053 | 169 |
| 1,000 | remote | 25 | 219 | 310 | 971 | 115 |
| 10,000 | sqlite | 25 | 182 | 232 | 249 | 83.2 |
| 10,000 | postgres | 25 | 365 | 511 | 424 | 256 |
| 10,000 | remote | 25 | 244 | 1,040 | 455 | 144 |

### RFI record: switch to Properties

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 57.1 | 74.6 | 58.4 | 12.8 |
| 1,000 | postgres | 25 | 72.1 | 86.3 | 74.9 | 22.2 |
| 1,000 | remote | 25 | 69.1 | 83.2 | 69.3 | 20.5 |
| 10,000 | sqlite | 25 | 56.3 | 738 | 49.2 | 10.3 |
| 10,000 | postgres | 25 | 75.2 | 101 | 72.5 | 28.1 |
| 10,000 | remote | 25 | 73.0 | 87.4 | 73.6 | 22.3 |

### RFI log: type a filter, the last key narrows the list

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 26.8 | 35.0 | 5.5 | 26.8 |
| 1,000 | postgres | 25 | 98.1 | 124 | 8.8 | 98.1 |
| 1,000 | remote | 25 | 56.7 | 69.0 | 5.8 | 56.7 |
| 10,000 | sqlite | 25 | 43.5 | 60.2 | 5.9 | 43.5 |
| 10,000 | postgres | 25 | 183 | 208 | 6.9 | 183 |
| 10,000 | remote | 25 | 72.5 | 94.8 | 9.6 | 72.5 |

### Open the correspondence register (F5) until rows are shown

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 237 | 862 | 230 | 156 |
| 1,000 | postgres | 25 | 273 | 1,012 | 1,091 | 270 |
| 1,000 | remote | 25 | 228 | 959 | 223 | 117 |
| 10,000 | sqlite | 25 | 314 | 1,131 | 372 | 314 |
| 10,000 | postgres | 25 | 386 | 1,191 | 388 | 356 |
| 10,000 | remote | 25 | 262 | 1,056 | 1,177 | 262 |

### Correspondence: move the cursor one row until the panel shows the record

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 5.9 | 9.3 | 21.1 | 5.9 |
| 1,000 | postgres | 25 | 6.2 | 8.9 | 95.7 | 6.1 |
| 1,000 | remote | 25 | 5.1 | 7.8 | 51.4 | 5.1 |
| 10,000 | sqlite | 25 | 5.3 | 7.5 | 22.3 | 5.3 |
| 10,000 | postgres | 25 | 7.7 | 70.9 | 190 | 7.7 |
| 10,000 | remote | 25 | 7.9 | 53.7 | 77.1 | 7.4 |

### Correspondence: Enter until the letter's Details are shown

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 172 | 252 | 186 | 69.2 |
| 1,000 | postgres | 25 | 255 | 362 | 391 | 155 |
| 1,000 | remote | 25 | 214 | 1,016 | 295 | 116 |
| 10,000 | sqlite | 25 | 189 | 238 | 213 | 87.2 |
| 10,000 | postgres | 25 | 374 | 1,295 | 427 | 234 |
| 10,000 | remote | 25 | 268 | 1,329 | 535 | 149 |

### Letter record: switch to Properties

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 56.5 | 852 | 55.8 | 10.5 |
| 1,000 | postgres | 25 | 71.3 | 938 | 62.2 | 22.2 |
| 1,000 | remote | 25 | 69.2 | 82.4 | 56.0 | 20.0 |
| 10,000 | sqlite | 25 | 55.9 | 80.1 | 54.2 | 10.8 |
| 10,000 | postgres | 25 | 80.5 | 104 | 78.8 | 28.2 |
| 10,000 | remote | 25 | 75.5 | 100 | 75.4 | 23.8 |

### Correspondence: type a filter, the last key narrows the list

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 24.1 | 35.5 | 8.2 | 24.1 |
| 1,000 | postgres | 25 | 91.0 | 124 | 9.3 | 90.9 |
| 1,000 | remote | 25 | 53.2 | 63.6 | 6.0 | 53.2 |
| 10,000 | sqlite | 25 | 24.3 | 33.7 | 6.2 | 24.3 |
| 10,000 | postgres | 25 | 153 | 183 | 6.3 | 153 |
| 10,000 | remote | 25 | 60.0 | 71.5 | 8.4 | 60.0 |

### Open the document register (F7) until rows are shown

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 238 | 1,017 | 1,183 | 154 |
| 1,000 | postgres | 25 | 275 | 1,124 | 318 | 260 |
| 1,000 | remote | 25 | 248 | 1,086 | 316 | 128 |
| 10,000 | sqlite | 25 | 267 | 1,174 | 1,398 | 186 |
| 10,000 | postgres | 25 | 274 | 1,312 | 331 | 272 |
| 10,000 | remote | 25 | 247 | 1,129 | 1,222 | 136 |

### Documents: move the cursor one row until the panel shows the document

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 5.0 | 7.7 | 11.0 | 5.0 |
| 1,000 | postgres | 25 | 5.4 | 43.3 | 25.5 | 5.4 |
| 1,000 | remote | 25 | 5.0 | 7.5 | 16.6 | 5.0 |
| 10,000 | sqlite | 25 | 7.1 | 42.6 | 12.0 | 7.1 |
| 10,000 | postgres | 25 | 6.8 | 33.8 | 36.6 | 6.8 |
| 10,000 | remote | 25 | 5.6 | 8.0 | 17.0 | 5.6 |

### Documents: Enter until the document's Details are shown

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 163 | 1,009 | 181 | 69.2 |
| 1,000 | postgres | 25 | 242 | 313 | 375 | 130 |
| 1,000 | remote | 25 | 188 | 985 | 279 | 91.8 |
| 10,000 | sqlite | 25 | 171 | 218 | 217 | 67.6 |
| 10,000 | postgres | 25 | 297 | 361 | 433 | 174 |
| 10,000 | remote | 25 | 228 | 1,103 | 290 | 112 |

### Document record: switch to Properties

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 57.4 | 71.4 | 56.9 | 10.3 |
| 1,000 | postgres | 25 | 72.9 | 91.1 | 77.2 | 23.7 |
| 1,000 | remote | 25 | 69.9 | 86.0 | 71.6 | 18.3 |
| 10,000 | sqlite | 25 | 56.4 | 940 | 56.8 | 10.6 |
| 10,000 | postgres | 25 | 83.8 | 108 | 78.0 | 26.2 |
| 10,000 | remote | 25 | 72.4 | 86.5 | 74.0 | 21.5 |

### Documents: type a filter, the last key narrows the list

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 13.0 | 18.4 | 9.6 | 13.0 |
| 1,000 | postgres | 25 | 34.2 | 44.0 | 8.1 | 34.0 |
| 1,000 | remote | 25 | 18.1 | 22.5 | 8.2 | 18.0 |
| 10,000 | sqlite | 25 | 16.2 | 25.4 | 10.3 | 16.2 |
| 10,000 | postgres | 25 | 41.2 | 50.3 | 10.6 | 41.2 |
| 10,000 | remote | 25 | 22.0 | 28.3 | 16.1 | 22.0 |

### Launch the app until the record grid shows its first rows

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 194 | 520 | 397 | 131 |
| 1,000 | postgres | 25 | 320 | 647 | 514 | 256 |
| 1,000 | remote | 25 | 263 | 659 | 509 | 204 |
| 10,000 | sqlite | 25 | 200 | 540 | 426 | 144 |
| 10,000 | postgres | 25 | 340 | 670 | 544 | 277 |
| 10,000 | remote | 25 | 292 | 686 | 516 | 238 |

### Record grid: reload (r) until the rows are back

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 18.2 | 41.7 | 15.7 | 8.8 |
| 1,000 | postgres | 25 | 34.9 | 47.8 | 40.6 | 24.7 |
| 1,000 | remote | 25 | 24.9 | 31.4 | 24.8 | 15.8 |
| 10,000 | sqlite | 25 | 19.8 | 47.5 | 21.1 | 10.5 |
| 10,000 | postgres | 25 | 42.4 | 60.9 | 42.0 | 30.9 |
| 10,000 | remote | 25 | 28.7 | 42.0 | 27.0 | 18.5 |

### Record grid: property-set filter, text (psets.valve_data.body_material=SS316L)

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 64.0 | 82.3 | 41.5 | 35.0 |
| 1,000 | postgres | 25 | 81.6 | 114 | 68.6 | 52.6 |
| 1,000 | remote | 25 | 76.6 | 111 | 54.3 | 30.1 |
| 10,000 | sqlite | 25 | 121 | 146 | 92.0 | 86.8 |
| 10,000 | postgres | 25 | 150 | 221 | 129 | 122 |
| 10,000 | remote | 25 | 125 | 184 | 118 | 100 |

### Record grid: property-set filter, number (psets.valve_data.size_in>=12)

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 72.1 | 451 | 71.0 | 19.5 |
| 1,000 | postgres | 25 | 86.7 | 449 | 106 | 62.7 |
| 1,000 | remote | 25 | 74.4 | 108 | 61.2 | 34.3 |
| 10,000 | sqlite | 25 | 254 | 304 | 262 | 237 |
| 10,000 | postgres | 25 | 276 | 662 | 320 | 267 |
| 10,000 | remote | 25 | 264 | 620 | 226 | 253 |

### Record grid: property-set filter, code (psets.valve_data.fail_action=FC)

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 70.5 | 90.7 | 82.7 | 24.4 |
| 1,000 | postgres | 25 | 86.4 | 121 | 78.8 | 53.6 |
| 1,000 | remote | 25 | 71.7 | 417 | 85.3 | 51.3 |
| 10,000 | sqlite | 25 | 238 | 259 | 204 | 210 |
| 10,000 | postgres | 25 | 303 | 354 | 330 | 285 |
| 10,000 | remote | 25 | 269 | 324 | 240 | 229 |

## Seeding

| Records | Backend | Seconds | Events |
|---:|---|---:|---:|
| 1,000 | sqlite | 91.4 | 20336 |
| 1,000 | postgres | 114.8 | 20336 |
| 1,000 | remote | 91.4 | 20336 |
| 10,000 | sqlite | 6155.8 | 201385 |
| 10,000 | postgres | 1113.6 | 201385 |
| 10,000 | remote | 6155.8 | 201385 |
