# User-facing performance (P1-UX)

What a person waits for in the terminal app, measured with the real TUI driven headless by Textual's pilot against a seeded project. Re-run with `just perf-ux`; every number is also in `P1-UX-perf.json`. The earlier backend benchmark is `docs/reports/P0-I8-perf.md` (queries and the bare grid widget, 100k records); this report measures whole screens.

## Machine and run
- Date 2026-10-31, code `c395eb6` (the working tree had uncommitted changes).
- CPU `Intel(R) Xeon(R) Processor @ 2.10GHz`, 4 CPUs; RAM 15.7 GB; disk `/dev/vda` 271 GB, 20 GB free (virtual block device, kernel rotational flag 1).
- Linux 6.18.44-fc-v185, Python 3.12.3, SQLite 3.45.1, Postgres 16.15. Load average at the start [1.19, 1.71, 1.77] (a shared container: expect noise of some milliseconds).
- Terminal 170x45 (columns x rows): the panel sits beside the list.

## How to read the numbers
- Milliseconds. **Median** and **p95** (nearest rank) over the timed repetitions of one action (**n**, at least 20) after untimed warm-up repetitions; **first** is the very first repetition in a fresh process (cold caches and connections). A figure of 1,000 ms or more is shown without decimals.
- A time runs from the key press to the moment the screen holds the answer *and* has been drawn (the app's screen refresh after it). The *state* median (answer held, not yet drawn) is the last column of each table. The harness's own cost, a key nothing is bound to, is under 1 ms (`floor` in the JSON).
- Backends: **sqlite** embedded SQLite file; **postgres** embedded, local Postgres (loopback, TLS off); **remote** the API in its own process on loopback over the same SQLite file, the TUI over HTTP. The live-update feed is off: only the screens are measured. No pytest, no mocks: the real app, the real services, the real database.
- Data per size: that many core records with property sets (the bulk writer of the benches), and that many RFIs, letters and documents through the command handlers (half of the RFIs submitted, half of the documents with a draft revision). The RFI log and the correspondence register list at most 500 lines and the document register 5,000: at 10,000 records the list is cut, but the server still has the whole project.
- The filter rows time the **last** key of the filter; the earlier keys are typed with the rows held back. Every key filters and redraws the whole list, so a filter of n keys costs about n times the figure.
- The pilot normally waits for every animation after a key (a tab's underline takes 0.3 s); that wait is off here, since a person does not wait for it.

## Headline: median ms at 10,000 records

| Action | sqlite | postgres | remote |
|---|---:|---:|---:|
| Open the RFI log (Ctrl+G) until rows are shown | 1,413 | 547 | 1,521 |
| RFI log: move the cursor one row until the panel shows the record | 4.4 | 2.7 | 14.2 |
| RFI log: Enter until the record's Details are shown | 2,335 | 919 | 2,563 |
| RFI record: switch to Properties | 45.0 | 42.3 | 42.9 |
| RFI log: type a filter, the last key narrows the list | 1,131 | 272 | 1,192 |
| Open the correspondence register (F5) until rows are shown | 1,483 | 582 | 1,536 |
| Open the document register (F7) until rows are shown | 15,171 | 14,542 | 15,164 |
| Launch the app until the record grid shows its first rows | 259 | 241 | 325 |
| Record grid: property-set filter, text (psets.valve_data.body_material=SS316L) | 237 | 125 | 250 |

## Slow spots (median over 250 ms at 10,000 records)

- **Open the RFI log (Ctrl+G) until rows are shown**: sqlite 1,413 ms, postgres 547 ms, remote 1,521 ms.
  - cProfile: 1485 ms cumulative, 0 ms own, 75 calls  sqlalchemy/engine/base.py:1407(execute)
  - cProfile: 1485 ms cumulative, 0 ms own, 75 calls  sqlalchemy/sql/elements.py:524(_execute_on_connection)
  - cProfile: 1484 ms cumulative, 1 ms own, 75 calls  sqlalchemy/engine/base.py:1621(_execute_clauseelement)
- **RFI log: Enter until the record's Details are shown**: sqlite 2,335 ms, postgres 919 ms, remote 2,563 ms.
  - cProfile: 2086 ms cumulative, 0 ms own, 143 calls  sqlalchemy/engine/base.py:1407(execute)
  - cProfile: 2081 ms cumulative, 0 ms own, 143 calls  sqlalchemy/sql/elements.py:524(_execute_on_connection)
  - cProfile: 2080 ms cumulative, 2 ms own, 143 calls  sqlalchemy/engine/base.py:1621(_execute_clauseelement)
- **RFI log: type a filter, the last key narrows the list**: sqlite 1,131 ms, postgres 272 ms, remote 1,192 ms.
  - cProfile: 1078 ms cumulative, 0 ms own, 31 calls  sqlalchemy/engine/base.py:1407(execute)
  - cProfile: 1078 ms cumulative, 0 ms own, 31 calls  sqlalchemy/sql/elements.py:524(_execute_on_connection)
  - cProfile: 1078 ms cumulative, 0 ms own, 31 calls  sqlalchemy/engine/base.py:1621(_execute_clauseelement)
- **Open the correspondence register (F5) until rows are shown**: sqlite 1,483 ms, postgres 582 ms, remote 1,536 ms.
  - cProfile: 1370 ms cumulative, 0 ms own, 74 calls  sqlalchemy/engine/base.py:1407(execute)
  - cProfile: 1370 ms cumulative, 0 ms own, 74 calls  sqlalchemy/sql/elements.py:524(_execute_on_connection)
  - cProfile: 1370 ms cumulative, 1 ms own, 74 calls  sqlalchemy/engine/base.py:1621(_execute_clauseelement)
- **Correspondence: Enter until the letter's Details are shown**: sqlite 2,381 ms, postgres 927 ms, remote 2,555 ms.
  - cProfile: 2269 ms cumulative, 0 ms own, 144 calls  sqlalchemy/engine/base.py:1407(execute)
  - cProfile: 2215 ms cumulative, 1 ms own, 143 calls  sqlalchemy/sql/elements.py:524(_execute_on_connection)
  - cProfile: 2187 ms cumulative, 2 ms own, 143 calls  sqlalchemy/engine/base.py:1621(_execute_clauseelement)
- **Correspondence: type a filter, the last key narrows the list**: sqlite 1,138 ms, postgres 274 ms, remote 1,214 ms.
  - cProfile: 1021 ms cumulative, 0 ms own, 30 calls  sqlalchemy/engine/base.py:1407(execute)
  - cProfile: 1021 ms cumulative, 0 ms own, 30 calls  sqlalchemy/sql/elements.py:524(_execute_on_connection)
  - cProfile: 1021 ms cumulative, 0 ms own, 30 calls  sqlalchemy/engine/base.py:1621(_execute_clauseelement)
- **Open the document register (F7) until rows are shown**: sqlite 15,171 ms, postgres 14,542 ms, remote 15,164 ms.
  - cProfile: 90704 ms cumulative, 30 ms own, 10000 calls  tl-tui/src/tl_tui/widgets/document_register.py:144(row_cells)
  - cProfile: 90613 ms cumulative, 39 ms own, 10000 calls  tl-tui/src/tl_tui/document_text.py:71(row_cells)
  - cProfile: 90440 ms cumulative, 73 ms own, 10003 calls  tl-tui/src/tl_tui/document_text.py:45(status_labels)
- **Documents: Enter until the document's Details are shown**: sqlite 1,703 ms, postgres 1,073 ms, remote 1,877 ms.
  - cProfile: 1647 ms cumulative, 0 ms own, 122 calls  sqlalchemy/engine/base.py:1407(execute)
  - cProfile: 1646 ms cumulative, 0 ms own, 122 calls  sqlalchemy/sql/elements.py:524(_execute_on_connection)
  - cProfile: 1646 ms cumulative, 1 ms own, 122 calls  sqlalchemy/engine/base.py:1621(_execute_clauseelement)
- **Documents: type a filter, the last key narrows the list**: sqlite 13,992 ms, postgres 13,513 ms, remote 13,654 ms.
  - cProfile: 45840 ms cumulative, 15 ms own, 5001 calls  tl-tui/src/tl_tui/widgets/document_register.py:144(row_cells)
  - cProfile: 45800 ms cumulative, 20 ms own, 5001 calls  tl-tui/src/tl_tui/document_text.py:71(row_cells)
  - cProfile: 45708 ms cumulative, 9 ms own, 5002 calls  tl-tui/src/tl_tui/document_text.py:62(current_words)
- **Launch the app until the record grid shows its first rows**: sqlite 259 ms, remote 325 ms.
  - cProfile: 123 ms cumulative, 0 ms own, 72 calls  sqlalchemy/engine/base.py:1407(execute)
  - cProfile: 123 ms cumulative, 0 ms own, 72 calls  sqlalchemy/sql/elements.py:524(_execute_on_connection)
  - cProfile: 122 ms cumulative, 1 ms own, 72 calls  sqlalchemy/engine/base.py:1621(_execute_clauseelement)
- **Record grid: property-set filter, number (psets.valve_data.size_in>=12)**: remote 252 ms.
  - cProfile: 254 ms cumulative, 0 ms own, 2 calls  tl-tui/src/tl_tui/remote.py:249(tracked)
  - cProfile: 254 ms cumulative, 0 ms own, 2 calls  tl-api/src/tl_api/client/base.py:168(_get_json)
  - cProfile: 253 ms cumulative, 0 ms own, 2 calls  tl-api/src/tl_api/client/base.py:108(_send)
- **Record grid: property-set filter, code (psets.valve_data.fail_action=FC)**: remote 254 ms.
  - cProfile: 254 ms cumulative, 0 ms own, 2 calls  tl-tui/src/tl_tui/remote.py:249(tracked)
  - cProfile: 254 ms cumulative, 0 ms own, 2 calls  tl-api/src/tl_api/client/base.py:168(_get_json)
  - cProfile: 253 ms cumulative, 0 ms own, 2 calls  tl-api/src/tl_api/client/base.py:108(_send)

## Results by action

### Open the RFI log (Ctrl+G) until rows are shown

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 283 | 722 | 282 | 275 |
| 1,000 | postgres | 25 | 402 | 772 | 666 | 402 |
| 1,000 | remote | 25 | 342 | 690 | 369 | 342 |
| 10,000 | sqlite | 25 | 1,413 | 1,778 | 1,635 | 1,403 |
| 10,000 | postgres | 25 | 547 | 922 | 3,695 | 547 |
| 10,000 | remote | 25 | 1,521 | 1,889 | 1,808 | 1,521 |

### RFI log: move the cursor one row until the panel shows the record

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 4.7 | 44.5 | 122 | 4.5 |
| 1,000 | postgres | 25 | 2.7 | 41.7 | 139 | 2.7 |
| 1,000 | remote | 25 | 3.8 | 43.8 | 156 | 3.8 |
| 10,000 | sqlite | 25 | 4.4 | 40.3 | 1,099 | 4.4 |
| 10,000 | postgres | 25 | 2.7 | 28.9 | 202 | 2.7 |
| 10,000 | remote | 25 | 14.2 | 25.9 | 1,194 | 2.8 |

### RFI log: Enter until the record's Details are shown

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 353 | 893 | 365 | 276 |
| 1,000 | postgres | 25 | 522 | 616 | 953 | 428 |
| 1,000 | remote | 25 | 502 | 576 | 619 | 428 |
| 10,000 | sqlite | 25 | 2,335 | 2,830 | 2,813 | 2,256 |
| 10,000 | postgres | 25 | 919 | 976 | 947 | 847 |
| 10,000 | remote | 25 | 2,563 | 3,041 | 2,450 | 2,481 |

### RFI record: switch to Properties

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 43.9 | 48.9 | 44.0 | 3.5 |
| 1,000 | postgres | 25 | 44.4 | 56.4 | 43.3 | 2.9 |
| 1,000 | remote | 25 | 44.8 | 54.8 | 45.2 | 3.3 |
| 10,000 | sqlite | 25 | 45.0 | 56.2 | 33.9 | 3.4 |
| 10,000 | postgres | 25 | 42.3 | 56.0 | 455 | 3.0 |
| 10,000 | remote | 25 | 42.9 | 60.8 | 41.8 | 3.5 |

### RFI log: type a filter, the last key narrows the list

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 172 | 205 | 45.8 | 136 |
| 1,000 | postgres | 25 | 162 | 192 | 35.8 | 124 |
| 1,000 | remote | 25 | 196 | 240 | 32.3 | 163 |
| 10,000 | sqlite | 25 | 1,131 | 1,243 | 73.0 | 1,104 |
| 10,000 | postgres | 25 | 272 | 314 | 44.4 | 229 |
| 10,000 | remote | 25 | 1,192 | 1,235 | 44.8 | 1,160 |

### Open the correspondence register (F5) until rows are shown

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 305 | 838 | 356 | 278 |
| 1,000 | postgres | 25 | 333 | 789 | 813 | 333 |
| 1,000 | remote | 25 | 321 | 859 | 315 | 321 |
| 10,000 | sqlite | 25 | 1,483 | 2,002 | 1,922 | 1,483 |
| 10,000 | postgres | 25 | 582 | 1,126 | 807 | 582 |
| 10,000 | remote | 25 | 1,536 | 2,130 | 1,454 | 1,536 |

### Correspondence: move the cursor one row until the panel shows the record

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 3.7 | 41.9 | 138 | 3.6 |
| 1,000 | postgres | 25 | 3.5 | 33.5 | 118 | 3.5 |
| 1,000 | remote | 25 | 5.9 | 47.1 | 145 | 3.9 |
| 10,000 | sqlite | 25 | 4.8 | 43.3 | 1,181 | 4.5 |
| 10,000 | postgres | 25 | 3.8 | 39.8 | 244 | 3.7 |
| 10,000 | remote | 25 | 7.2 | 36.7 | 1,113 | 3.6 |

### Correspondence: Enter until the letter's Details are shown

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 355 | 398 | 392 | 279 |
| 1,000 | postgres | 25 | 478 | 974 | 461 | 400 |
| 1,000 | remote | 25 | 516 | 1,084 | 528 | 437 |
| 10,000 | sqlite | 25 | 2,381 | 2,948 | 2,413 | 2,299 |
| 10,000 | postgres | 25 | 927 | 1,502 | 871 | 854 |
| 10,000 | remote | 25 | 2,555 | 3,187 | 2,662 | 2,480 |

### Letter record: switch to Properties

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 44.6 | 60.1 | 45.0 | 3.4 |
| 1,000 | postgres | 25 | 44.6 | 50.9 | 43.6 | 2.9 |
| 1,000 | remote | 25 | 43.8 | 57.0 | 46.9 | 3.4 |
| 10,000 | sqlite | 25 | 44.8 | 55.7 | 48.1 | 3.5 |
| 10,000 | postgres | 25 | 35.9 | 49.6 | 47.5 | 3.1 |
| 10,000 | remote | 25 | 42.3 | 61.9 | 43.0 | 3.6 |

### Correspondence: type a filter, the last key narrows the list

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 154 | 196 | 46.9 | 138 |
| 1,000 | postgres | 25 | 173 | 218 | 9.9 | 129 |
| 1,000 | remote | 25 | 190 | 242 | 48.2 | 168 |
| 10,000 | sqlite | 25 | 1,138 | 1,226 | 37.9 | 1,088 |
| 10,000 | postgres | 25 | 274 | 307 | 45.8 | 230 |
| 10,000 | remote | 25 | 1,214 | 1,308 | 6.4 | 1,177 |

### Open the document register (F7) until rows are shown

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 3,258 | 3,790 | 3,210 | 3,025 |
| 1,000 | postgres | 25 | 3,023 | 3,509 | 3,033 | 2,918 |
| 1,000 | remote | 25 | 3,063 | 3,712 | 3,121 | 2,979 |
| 10,000 | sqlite | 20 | 15,171 | 15,750 | 15,034 | 15,171 |
| 10,000 | postgres | 20 | 14,542 | 15,177 | 15,680 | 14,499 |
| 10,000 | remote | 20 | 15,164 | 15,881 | 14,994 | 15,119 |

### Documents: move the cursor one row until the panel shows the document

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 8.7 | 19.5 | 34.6 | 8.4 |
| 1,000 | postgres | 25 | 6.3 | 10.5 | 47.1 | 6.3 |
| 1,000 | remote | 25 | 10.8 | 36.9 | 40.8 | 7.4 |
| 10,000 | sqlite | 25 | 8.5 | 39.1 | 345 | 7.7 |
| 10,000 | postgres | 25 | 9.4 | 34.3 | 277 | 8.8 |
| 10,000 | remote | 25 | 11.8 | 24.3 | 342 | 7.2 |

### Documents: Enter until the document's Details are shown

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 313 | 927 | 319 | 238 |
| 1,000 | postgres | 25 | 424 | 497 | 1,036 | 344 |
| 1,000 | remote | 25 | 442 | 457 | 415 | 361 |
| 10,000 | sqlite | 25 | 1,703 | 1,826 | 1,661 | 1,632 |
| 10,000 | postgres | 25 | 1,073 | 1,238 | 1,162 | 978 |
| 10,000 | remote | 25 | 1,877 | 2,056 | 1,966 | 1,786 |

### Document record: switch to Properties

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 44.2 | 53.8 | 39.4 | 3.6 |
| 1,000 | postgres | 25 | 44.5 | 53.4 | 38.1 | 3.2 |
| 1,000 | remote | 25 | 44.0 | 643 | 46.1 | 3.6 |
| 10,000 | sqlite | 25 | 48.2 | 57.7 | 35.9 | 3.6 |
| 10,000 | postgres | 25 | 44.3 | 52.4 | 51.8 | 3.3 |
| 10,000 | remote | 25 | 43.7 | 50.4 | 55.1 | 3.7 |

### Documents: type a filter, the last key narrows the list

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 2,724 | 2,904 | 2,702 | 2,686 |
| 1,000 | postgres | 25 | 2,721 | 2,808 | 2,719 | 2,676 |
| 1,000 | remote | 25 | 2,706 | 2,941 | 2,967 | 2,673 |
| 10,000 | sqlite | 20 | 13,992 | 14,391 | 13,596 | 13,975 |
| 10,000 | postgres | 20 | 13,513 | 14,186 | 13,314 | 13,472 |
| 10,000 | remote | 20 | 13,654 | 14,268 | 14,241 | 13,603 |

### Launch the app until the record grid shows its first rows

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 162 | 479 | 320 | 115 |
| 1,000 | postgres | 25 | 318 | 510 | 438 | 265 |
| 1,000 | remote | 25 | 226 | 504 | 388 | 172 |
| 10,000 | sqlite | 25 | 259 | 527 | 405 | 207 |
| 10,000 | postgres | 25 | 241 | 449 | 401 | 193 |
| 10,000 | remote | 25 | 325 | 558 | 474 | 272 |

### Record grid: reload (r) until the rows are back

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 25.3 | 34.8 | 20.2 | 15.3 |
| 1,000 | postgres | 25 | 111 | 177 | 114 | 105 |
| 1,000 | remote | 25 | 26.3 | 34.1 | 27.0 | 18.9 |
| 10,000 | sqlite | 25 | 124 | 178 | 107 | 115 |
| 10,000 | postgres | 25 | 59.5 | 71.6 | 60.5 | 52.3 |
| 10,000 | remote | 25 | 126 | 151 | 156 | 120 |

### Record grid: property-set filter, text (psets.valve_data.body_material=SS316L)

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 39.9 | 93.0 | 54.7 | 39.3 |
| 1,000 | postgres | 25 | 229 | 311 | 259 | 229 |
| 1,000 | remote | 25 | 49.0 | 351 | 50.4 | 48.9 |
| 10,000 | sqlite | 25 | 237 | 334 | 239 | 232 |
| 10,000 | postgres | 25 | 125 | 153 | 126 | 122 |
| 10,000 | remote | 25 | 250 | 511 | 270 | 246 |

### Record grid: property-set filter, number (psets.valve_data.size_in>=12)

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 45.9 | 294 | 43.6 | 40.5 |
| 1,000 | postgres | 25 | 80.7 | 343 | 271 | 80.1 |
| 1,000 | remote | 25 | 49.4 | 319 | 47.9 | 47.7 |
| 10,000 | sqlite | 25 | 236 | 308 | 481 | 236 |
| 10,000 | postgres | 25 | 193 | 235 | 240 | 192 |
| 10,000 | remote | 25 | 252 | 286 | 254 | 252 |

### Record grid: property-set filter, code (psets.valve_data.fail_action=FC)

| Records | Backend | n | median | p95 | first | state median |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | sqlite | 25 | 39.9 | 247 | 38.6 | 39.9 |
| 1,000 | postgres | 25 | 69.9 | 130 | 77.2 | 68.1 |
| 1,000 | remote | 25 | 51.0 | 355 | 45.1 | 50.0 |
| 10,000 | sqlite | 25 | 232 | 291 | 226 | 231 |
| 10,000 | postgres | 25 | 224 | 482 | 225 | 224 |
| 10,000 | remote | 25 | 254 | 314 | 244 | 250 |

## Seeding

| Records | Backend | Seconds | Events |
|---:|---|---:|---:|
| 1,000 | sqlite | 66.4 | 20336 |
| 1,000 | postgres | 66.5 | 20336 |
| 1,000 | remote | 66.4 | 20336 |
| 10,000 | sqlite | 4606.0 | 201385 |
| 10,000 | postgres | 676.8 | 201385 |
| 10,000 | remote | 4606.0 | 201385 |
