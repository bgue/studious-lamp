# User-facing performance (P1-UX)

What a person waits for in the terminal app, measured with the real TUI driven headless by Textual's pilot against a seeded project. Re-run with `just perf-ux`; every number is also in `P1-UX-perf.json`. The earlier backend benchmark is `docs/reports/P0-I8-perf.md` (queries and the bare grid widget, 100k records); this report measures whole screens.

## Machine and run
- Date 2026-10-31, code `59a01ba`.
- CPU `Intel(R) Xeon(R) Processor @ 2.80GHz`, 4 CPUs; RAM 15.7 GB; disk `/dev/vda` 271 GB, 21 GB free (virtual block device, kernel rotational flag 1).
- Linux 6.18.44-fc-v185, Python 3.12.3, SQLite 3.45.1, Postgres 16.15. Load average at the start [1.7, 2.32, 2.88] (a shared container: expect noise of some milliseconds).
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
| Open the RFI log (Ctrl+G) until rows are shown | 241 | 361 | 218 |
| RFI log: move the cursor one row until the panel shows the record | 5.6 | 6.5 | 5.2 |
| RFI log: Enter until the record's Details are shown | 204 | 340 | 272 |
| RFI record: switch to Properties | 63.7 | 77.4 | 69.7 |
| RFI log: type a filter, the last key narrows the list | 43.2 | 154 | 79.9 |
| Open the correspondence register (F5) until rows are shown | 324 | 380 | 343 |
| Open the document register (F7) until rows are shown | 239 | 338 | 242 |
| Launch the app until the record grid shows its first rows | 348 | 422 | 459 |
| Record grid: property-set filter, text (psets.valve_data.body_material=SS316L) | 345 | 420 | 387 |

## Before and after at 10,000 records (median ms; before: code `c395eb6`, 2026-10-31)

| Action | sqlite | postgres | remote |
|---|---:|---:|---:|
| Open the RFI log (Ctrl+G) until rows are shown | 1,413 -> 241 | 547 -> 361 | 1,521 -> 218 |
| RFI log: move the cursor one row until the panel shows the record | 4.4 -> 5.6 | 2.7 -> 6.5 | 14.2 -> 5.2 |
| RFI log: Enter until the record's Details are shown | 2,335 -> 204 | 919 -> 340 | 2,563 -> 272 |
| RFI record: switch to Properties | 45.0 -> 63.7 | 42.3 -> 77.4 | 42.9 -> 69.7 |
| RFI log: type a filter, the last key narrows the list | 1,131 -> 43.2 | 272 -> 154 | 1,192 -> 79.9 |
| Open the correspondence register (F5) until rows are shown | 1,483 -> 324 | 582 -> 380 | 1,536 -> 343 |
| Open the document register (F7) until rows are shown | 15,171 -> 239 | 14,542 -> 338 | 15,164 -> 242 |
| Launch the app until the record grid shows its first rows | 259 -> 348 | 241 -> 422 | 325 -> 459 |
| Record grid: property-set filter, text (psets.valve_data.body_material=SS316L) | 237 -> 345 | 125 -> 420 | 250 -> 387 |
| Correspondence: Enter until the letter's Details are shown | 2,381 -> 213 | 927 -> 358 | 2,555 -> 267 |
| Correspondence: type a filter, the last key narrows the list | 1,138 -> 24.5 | 274 -> 137 | 1,214 -> 64.0 |
| Documents: Enter until the document's Details are shown | 1,703 -> 182 | 1,073 -> 255 | 1,877 -> 218 |
| Documents: type a filter, the last key narrows the list | 13,992 -> 18.5 | 13,513 -> 35.1 | 13,654 -> 23.2 |

## Slow spots (median over 250 ms at 10,000 records)

- **Open the RFI log (Ctrl+G) until rows are shown**: postgres 361 ms.
  - cProfile: SQL 126 ms in 1 calls, slowest 126 ms: SELECT x.id FROM cur_core_record x WHERE x.id IN (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
  - cProfile: SQL 102 ms in 3 calls, slowest 97 ms: SELECT i.id, i.record_type, i.scope, i.number, i.title, i.status, i.voided, i.version, i.direction, i.medium, i.received_via, i.external_ref, i.messag
  - cProfile: SQL 62 ms in 11 calls, slowest 7 ms: SELECT 1 FROM cur_core_record x WHERE x.id = %s AND x.id IN (SELECT hr.id FROM cur_core_record hr WHERE hr.type IN ('correspondence.CommercialItem', '
- **RFI log: Enter until the record's Details are shown**: postgres 340 ms, remote 272 ms.
  - cProfile: SQL 140 ms in 11 calls, slowest 40 ms: SELECT 1 FROM cur_core_record x WHERE x.id = %s AND x.id IN (SELECT hr.id FROM cur_core_record hr WHERE hr.type IN ('correspondence.CommercialItem', '
  - cProfile: SQL 66 ms in 1 calls, slowest 66 ms: SELECT l.link_id, l.relation, l.status, l.pin, l.note, l.source, l.confidence, l.reason, l.declined, l.verified_by, l.verified_at, l.created_at, l.ver
  - cProfile: SQL 51 ms in 10 calls, slowest 40 ms: SELECT a.account_id, a.username, a.display_name, a.kind, a.roles_json, a.status, a.created_at, a.last_seq, t.locked_until FROM cur_account a LEFT JOIN
- **Open the correspondence register (F5) until rows are shown**: sqlite 324 ms, postgres 380 ms, remote 343 ms.
  - cProfile: SQL 102 ms in 4 calls, slowest 102 ms: SELECT id, record_type, scope, number, title, status, voided, version, direction, medium, received_via, external_ref, message_id, in_reply_to, from_pa
  - cProfile: SQL 33 ms in 1 calls, slowest 33 ms: SELECT id, scope, key, title, description, status, voided, version, created_at, direction, purpose, due_date, issued_on, response_code, response_note,
  - cProfile: SQL 8 ms in 1 calls, slowest 8 ms: SELECT x.id FROM cur_core_record x WHERE x.id IN (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
- **Correspondence: Enter until the letter's Details are shown**: postgres 358 ms, remote 267 ms.
  - cProfile: SQL 121 ms in 11 calls, slowest 37 ms: SELECT 1 FROM cur_core_record x WHERE x.id = %s AND x.id IN (SELECT hr.id FROM cur_core_record hr WHERE hr.type IN ('correspondence.CommercialItem', '
  - cProfile: SQL 104 ms in 10 calls, slowest 102 ms: SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY
  - cProfile: SQL 45 ms in 1 calls, slowest 45 ms: SELECT l.link_id, l.relation, l.status, l.pin, l.note, l.source, l.confidence, l.reason, l.declined, l.verified_by, l.verified_at, l.created_at, l.ver
- **Open the document register (F7) until rows are shown**: postgres 338 ms.
  - cProfile: SQL 128 ms in 1 calls, slowest 128 ms: SELECT x.id FROM cur_core_record x WHERE x.id IN (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
  - cProfile: SQL 50 ms in 4 calls, slowest 45 ms: SELECT id, scope, key, title, description, status, voided, version, conformance, doc_type, discipline, originator, confidentiality, revision_scheme, p
  - cProfile: SQL 45 ms in 6 calls, slowest 8 ms: SELECT 1 FROM cur_core_record x WHERE x.id = %s AND x.id IN (SELECT hr.id FROM cur_core_record hr WHERE hr.type IN ('correspondence.CommercialItem', '
- **Documents: Enter until the document's Details are shown**: postgres 255 ms.
  - cProfile: SQL 128 ms in 8 calls, slowest 44 ms: SELECT 1 FROM cur_core_record x WHERE x.id = %s AND x.id IN (SELECT hr.id FROM cur_core_record hr WHERE hr.type IN ('correspondence.CommercialItem', '
  - cProfile: SQL 46 ms in 8 calls, slowest 38 ms: SELECT a.account_id, a.username, a.display_name, a.kind, a.roles_json, a.status, a.created_at, a.last_seq, t.locked_until FROM cur_account a LEFT JOIN
  - cProfile: SQL 35 ms in 3 calls, slowest 33 ms: SELECT id, key, type, scope, title, description, status, psets_json, voided, version, last_seq, effective_schema_hash, conformance, created_at, update
- **Launch the app until the record grid shows its first rows**: sqlite 348 ms, postgres 422 ms, remote 459 ms.
  - cProfile: SQL 139 ms in 1 calls, slowest 139 ms: SELECT id, key, type, scope, title, description, status, psets_json, voided, version, last_seq, effective_schema_hash, conformance, created_at, update
  - cProfile: SQL 9 ms in 1 calls, slowest 9 ms: SELECT t.scope, t.path, t.reason, t.approver, t.expires FROM cur_schemareg_waiver t JOIN cur_core_record r ON r.id = t.id WHERE r.status = 'Approved' 
  - cProfile: SQL 1 ms in 36 calls, slowest 0 ms: SELECT v.id, v.scope, v.code_list, v.code, v.label, v.meaning, v.crosswalk, v.origin, v.sort_order, v.effective_from, v.effective_to, v.lifecycle, v.s
- **Record grid: property-set filter, text (psets.valve_data.body_material=SS316L)**: sqlite 345 ms, postgres 420 ms, remote 387 ms.
  - cProfile: SQL 161 ms in 1 calls, slowest 161 ms: SELECT COUNT(*) FROM cur_core_record r WHERE r.scope = ? AND r.voided = ? AND r.id IN (SELECT pv1.record_id FROM cur_pset_values pv1 WHERE pv1.path = 
  - cProfile: SQL 143 ms in 1 calls, slowest 143 ms: SELECT r.id, r.key, r.type, r.scope, r.title, r.description, r.status, r.psets_json, r.voided, r.version, r.last_seq, r.effective_schema_hash, r.confo
  - cProfile: SQL 0 ms in 2 calls, slowest 0 ms: SELECT a.account_id, a.username, a.display_name, a.kind, a.roles_json, a.status, a.created_at, a.last_seq, t.locked_until FROM cur_account a LEFT JOIN
- **Record grid: property-set filter, number (psets.valve_data.size_in>=12)**: sqlite 357 ms, postgres 410 ms, remote 384 ms.
  - cProfile: SQL 156 ms in 1 calls, slowest 156 ms: SELECT COUNT(*) FROM cur_core_record r WHERE r.scope = ? AND r.voided = ? AND r.id IN (SELECT pv1.record_id FROM cur_pset_values pv1 WHERE pv1.path = 
  - cProfile: SQL 139 ms in 1 calls, slowest 139 ms: SELECT r.id, r.key, r.type, r.scope, r.title, r.description, r.status, r.psets_json, r.voided, r.version, r.last_seq, r.effective_schema_hash, r.confo
  - cProfile: SQL 0 ms in 2 calls, slowest 0 ms: SELECT a.account_id, a.username, a.display_name, a.kind, a.roles_json, a.status, a.created_at, a.last_seq, t.locked_until FROM cur_account a LEFT JOIN
- **Record grid: property-set filter, code (psets.valve_data.fail_action=FC)**: sqlite 343 ms, postgres 406 ms, remote 388 ms.
  - cProfile: SQL 159 ms in 1 calls, slowest 159 ms: SELECT COUNT(*) FROM cur_core_record r WHERE r.scope = ? AND r.voided = ? AND r.id IN (SELECT pv1.record_id FROM cur_pset_values pv1 WHERE pv1.path = 
  - cProfile: SQL 134 ms in 1 calls, slowest 134 ms: SELECT r.id, r.key, r.type, r.scope, r.title, r.description, r.status, r.psets_json, r.voided, r.version, r.last_seq, r.effective_schema_hash, r.confo
  - cProfile: SQL 0 ms in 2 calls, slowest 0 ms: SELECT a.account_id, a.username, a.display_name, a.kind, a.roles_json, a.status, a.created_at, a.last_seq, t.locked_until FROM cur_account a LEFT JOIN

## Results by action

### Open the RFI log (Ctrl+G) until rows are shown

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 219 | 775 | 262 | 187 |
| 1,000 | postgres | 25 | 297 | 988 | 332 | 294 |
| 1,000 | remote | 25 | 261 | 752 | 253 | 124 |
| 10,000 | sqlite | 25 | 241 | 320 | 336 | 241 |
| 10,000 | postgres | 25 | 361 | 906 | 466 | 361 |
| 10,000 | remote | 25 | 218 | 844 | 382 | 218 |

### RFI log: move the cursor one row until the panel shows the record

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 4.9 | 6.7 | 37.9 | 4.9 |
| 1,000 | postgres | 25 | 5.1 | 7.3 | 106 | 5.1 |
| 1,000 | remote | 25 | 5.2 | 16.5 | 50.3 | 5.2 |
| 10,000 | sqlite | 25 | 5.6 | 48.2 | 40.5 | 5.6 |
| 10,000 | postgres | 25 | 6.5 | 9.2 | 152 | 6.5 |
| 10,000 | remote | 25 | 5.2 | 12.6 | 71.9 | 5.2 |

### RFI log: Enter until the record's Details are shown

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 170 | 197 | 228 | 72.6 |
| 1,000 | postgres | 25 | 252 | 338 | 318 | 158 |
| 1,000 | remote | 25 | 230 | 285 | 289 | 120 |
| 10,000 | sqlite | 25 | 204 | 842 | 255 | 95.0 |
| 10,000 | postgres | 25 | 340 | 1,173 | 461 | 233 |
| 10,000 | remote | 25 | 272 | 365 | 454 | 157 |

### RFI record: switch to Properties

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 56.5 | 71.8 | 55.5 | 10.0 |
| 1,000 | postgres | 25 | 70.8 | 833 | 67.5 | 22.5 |
| 1,000 | remote | 25 | 67.5 | 75.4 | 88.9 | 19.4 |
| 10,000 | sqlite | 25 | 63.7 | 74.8 | 55.3 | 12.3 |
| 10,000 | postgres | 25 | 77.4 | 92.6 | 62.2 | 26.7 |
| 10,000 | remote | 25 | 69.7 | 102 | 66.7 | 25.4 |

### RFI log: type a filter, the last key narrows the list

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 26.4 | 39.6 | 8.3 | 26.4 |
| 1,000 | postgres | 25 | 98.1 | 127 | 6.4 | 98.1 |
| 1,000 | remote | 25 | 60.9 | 74.6 | 8.9 | 60.8 |
| 10,000 | sqlite | 25 | 43.2 | 57.3 | 9.3 | 43.2 |
| 10,000 | postgres | 25 | 154 | 189 | 5.7 | 154 |
| 10,000 | remote | 25 | 79.9 | 107 | 8.9 | 79.9 |

### Open the correspondence register (F5) until rows are shown

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 220 | 1,051 | 210 | 165 |
| 1,000 | postgres | 25 | 305 | 985 | 340 | 305 |
| 1,000 | remote | 25 | 272 | 991 | 356 | 138 |
| 10,000 | sqlite | 25 | 324 | 395 | 321 | 324 |
| 10,000 | postgres | 25 | 380 | 462 | 508 | 380 |
| 10,000 | remote | 25 | 343 | 1,174 | 1,259 | 343 |

### Correspondence: move the cursor one row until the panel shows the record

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 5.1 | 6.8 | 36.6 | 5.1 |
| 1,000 | postgres | 25 | 5.4 | 7.4 | 115 | 5.4 |
| 1,000 | remote | 25 | 6.7 | 22.2 | 52.6 | 6.7 |
| 10,000 | sqlite | 25 | 5.5 | 8.6 | 28.5 | 5.5 |
| 10,000 | postgres | 25 | 5.3 | 40.1 | 140 | 5.3 |
| 10,000 | remote | 25 | 6.7 | 56.8 | 54.2 | 6.7 |

### Correspondence: Enter until the letter's Details are shown

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 181 | 218 | 186 | 72.9 |
| 1,000 | postgres | 25 | 267 | 1,152 | 346 | 162 |
| 1,000 | remote | 25 | 238 | 1,081 | 1,248 | 126 |
| 10,000 | sqlite | 25 | 213 | 1,114 | 239 | 102 |
| 10,000 | postgres | 25 | 358 | 1,245 | 385 | 220 |
| 10,000 | remote | 25 | 267 | 1,200 | 463 | 160 |

### Letter record: switch to Properties

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 55.8 | 848 | 56.8 | 10.6 |
| 1,000 | postgres | 25 | 72.2 | 79.6 | 62.0 | 23.9 |
| 1,000 | remote | 25 | 70.9 | 82.3 | 73.3 | 20.6 |
| 10,000 | sqlite | 25 | 57.6 | 901 | 61.5 | 11.2 |
| 10,000 | postgres | 25 | 82.5 | 104 | 74.2 | 31.6 |
| 10,000 | remote | 25 | 72.5 | 129 | 103 | 23.3 |

### Correspondence: type a filter, the last key narrows the list

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 22.7 | 35.0 | 8.2 | 22.7 |
| 1,000 | postgres | 25 | 94.4 | 116 | 6.5 | 94.4 |
| 1,000 | remote | 25 | 61.3 | 75.6 | 9.7 | 61.3 |
| 10,000 | sqlite | 25 | 24.5 | 44.6 | 6.4 | 24.5 |
| 10,000 | postgres | 25 | 137 | 168 | 10.1 | 137 |
| 10,000 | remote | 25 | 64.0 | 89.1 | 13.6 | 64.0 |

### Open the document register (F7) until rows are shown

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 252 | 1,066 | 305 | 167 |
| 1,000 | postgres | 25 | 326 | 1,174 | 392 | 314 |
| 1,000 | remote | 25 | 249 | 1,101 | 336 | 152 |
| 10,000 | sqlite | 25 | 239 | 1,130 | 246 | 217 |
| 10,000 | postgres | 25 | 338 | 1,172 | 330 | 307 |
| 10,000 | remote | 25 | 242 | 1,188 | 314 | 162 |

### Documents: move the cursor one row until the panel shows the document

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 5.1 | 7.9 | 11.2 | 5.1 |
| 1,000 | postgres | 25 | 5.7 | 8.0 | 37.2 | 5.7 |
| 1,000 | remote | 25 | 5.7 | 8.0 | 22.7 | 5.7 |
| 10,000 | sqlite | 25 | 7.0 | 53.1 | 16.1 | 7.0 |
| 10,000 | postgres | 25 | 5.5 | 7.9 | 34.3 | 5.5 |
| 10,000 | remote | 25 | 5.8 | 8.0 | 22.8 | 5.8 |

### Documents: Enter until the document's Details are shown

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 184 | 881 | 168 | 68.4 |
| 1,000 | postgres | 25 | 264 | 1,293 | 319 | 153 |
| 1,000 | remote | 25 | 206 | 944 | 308 | 94.7 |
| 10,000 | sqlite | 25 | 182 | 247 | 214 | 71.9 |
| 10,000 | postgres | 25 | 255 | 1,105 | 402 | 140 |
| 10,000 | remote | 25 | 218 | 1,078 | 405 | 105 |

### Document record: switch to Properties

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 55.4 | 90.4 | 56.4 | 10.2 |
| 1,000 | postgres | 25 | 79.4 | 98.3 | 70.7 | 26.3 |
| 1,000 | remote | 25 | 70.9 | 88.6 | 72.2 | 20.5 |
| 10,000 | sqlite | 25 | 58.1 | 79.8 | 58.1 | 11.1 |
| 10,000 | postgres | 25 | 73.0 | 86.1 | 85.3 | 22.4 |
| 10,000 | remote | 25 | 72.8 | 86.7 | 72.3 | 21.9 |

### Documents: type a filter, the last key narrows the list

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 13.0 | 18.0 | 7.2 | 13.0 |
| 1,000 | postgres | 25 | 33.9 | 45.1 | 7.2 | 33.9 |
| 1,000 | remote | 25 | 17.4 | 23.4 | 7.2 | 17.4 |
| 10,000 | sqlite | 25 | 18.5 | 23.9 | 15.0 | 18.5 |
| 10,000 | postgres | 25 | 35.1 | 50.7 | 10.5 | 35.0 |
| 10,000 | remote | 25 | 23.2 | 48.0 | 15.4 | 23.2 |

### Launch the app until the record grid shows its first rows

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 206 | 559 | 452 | 138 |
| 1,000 | postgres | 25 | 400 | 736 | 665 | 336 |
| 1,000 | remote | 25 | 300 | 682 | 515 | 236 |
| 10,000 | sqlite | 25 | 348 | 676 | 570 | 284 |
| 10,000 | postgres | 25 | 422 | 835 | 756 | 340 |
| 10,000 | remote | 25 | 459 | 842 | 714 | 394 |

### Record grid: reload (r) until the rows are back

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 25.7 | 39.7 | 28.1 | 16.3 |
| 1,000 | postgres | 25 | 44.1 | 55.5 | 39.7 | 33.8 |
| 1,000 | remote | 25 | 34.7 | 44.2 | 39.0 | 23.8 |
| 10,000 | sqlite | 25 | 148 | 197 | 139 | 138 |
| 10,000 | postgres | 25 | 119 | 152 | 162 | 108 |
| 10,000 | remote | 25 | 181 | 215 | 226 | 171 |

### Record grid: property-set filter, text (psets.valve_data.body_material=SS316L)

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 75.6 | 466 | 59.8 | 49.8 |
| 1,000 | postgres | 25 | 97.1 | 124 | 116 | 83.6 |
| 1,000 | remote | 25 | 93.4 | 415 | 91.7 | 56.2 |
| 10,000 | sqlite | 25 | 345 | 388 | 312 | 326 |
| 10,000 | postgres | 25 | 420 | 499 | 239 | 373 |
| 10,000 | remote | 25 | 387 | 730 | 384 | 361 |

### Record grid: property-set filter, number (psets.valve_data.size_in>=12)

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 71.0 | 102 | 86.9 | 44.6 |
| 1,000 | postgres | 25 | 103 | 153 | 567 | 79.3 |
| 1,000 | remote | 25 | 88.8 | 114 | 108 | 66.2 |
| 10,000 | sqlite | 25 | 357 | 809 | 335 | 324 |
| 10,000 | postgres | 25 | 410 | 586 | 404 | 379 |
| 10,000 | remote | 25 | 384 | 788 | 455 | 376 |

### Record grid: property-set filter, code (psets.valve_data.fail_action=FC)

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 76.5 | 102 | 48.7 | 47.1 |
| 1,000 | postgres | 25 | 96.3 | 118 | 116 | 78.7 |
| 1,000 | remote | 25 | 101 | 116 | 90.0 | 45.5 |
| 10,000 | sqlite | 25 | 343 | 416 | 332 | 336 |
| 10,000 | postgres | 25 | 406 | 521 | 457 | 382 |
| 10,000 | remote | 25 | 388 | 515 | 364 | 362 |

## Seeding

| Records | Backend | Seconds | Events |
|---:|---|---:|---:|
| 1,000 | sqlite | 91.4 | 20336 |
| 1,000 | postgres | 114.8 | 20336 |
| 1,000 | remote | 91.4 | 20336 |
| 10,000 | sqlite | 6155.8 | 201385 |
| 10,000 | postgres | 1113.6 | 201385 |
| 10,000 | remote | 6155.8 | 201385 |
