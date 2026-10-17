# Report — P1-I3 workstream B (extractors)

Branch `p1/i3b` (base `p1/i3`, with `p1/i3` at 916b5a8 merged in). Plan: [docs/tickets/P1-I3/README-B.md](../tickets/P1-I3/README-B.md). Fanout: [docs/tickets/P1-I3/FANOUT.md](../tickets/P1-I3/FANOUT.md). Package: `packages/tl-extract` (README and AGENTS.md there).

## Outcome
Objective met: yes. The package `tl_extract` ships three extractors as plugins under the entry-point group `throughline.extractors`:
`tabular` (CSV and XLSX into rows with header hints and column profiles, `status="ok"`), `pdf` (real page count, title, author, producer
and dates; content stubbed, `metadata_only`) and `ocr` (image format, pixel size and header text; no OCR, `metadata_only`). Each passes
`tests/contract/test_extractor_contract.py`, refuses what is over the bounds of the contract (50 MiB, 20 000 rows, 200 columns, 10 000
characters per cell) instead of truncating it, and returns `failed` with a coded problem, never an exception, a path or a stack trace.
The document schema fixtures (instrument index with the 40-tag demo sample and a one-row-invalid variant, line list, equipment list) and
a golden dataset of three sources with exact expected results are in.

Demo (workstream A owns `just demo P1-I3`): `uv run python packages/tl-extract/tests/golden/make_golden.py --check` and
`uv run pytest packages/tl-extract/tests/test_fixtures_through_extractor.py -q`.

## Tickets
| ID | Outcome | Review rounds | Notes |
|---|---|---|---|
| T09a CSV reader | merged (`2619f72`, merge `3c4e029`) | 1 (pass) | 33 tests; no deviation |
| T09b XLSX reader | merged (`4f9aa91`, merge `b040e72`) | 1 (pass) | 76 tests; read "either part missing" as a refusal, which was the intent; pinned by S9 |
| T10 PDF properties | merged (`5944172`, merge `1f2b507`) | 1 (pass) | 55 tests; two type-checker-driven rewrites of equivalent code |
| T11 image header | merged (`5f0ff38`, merge `9be94d0`) | 1 (pass) | 40 tests; "first wins" means "while the field is still empty" |
| T12 golden dataset | built by the supervisor (S5, test joined in S10) | n/a | The generated sources and the expected files are one design (checklist item 7) |
| T13 document schema fixtures | built by the supervisor (S3) | n/a | `schema/**` is outside the Haiku checklist (item 6) |
| T09 table builder and shell | built by the supervisor (S1, S2) | n/a | Shared by both readers |

No ticket was taken over or abandoned. Supervisor commits: S1 `d5ed091`, S2 `6418d83`, S3 `034b650`, S2b `36447c0`, S4 `864ff3e`, S5 `1dc3813`,
S6 `c2a27fc`, S7 `9aa212f`, S8 `dc54172`, S9 `e53e962`, S10 `78503fc`, merge of `p1/i3` `3b19af6`, S11 `ac72f81`.

## Gates
| Gate | Result |
|---|---|
| `just check` | clean on `ac72f81` and again after the review fixes (see the relay) |
| `uv run pytest packages/tl-extract` | 387 passed |
| `make_golden.py --check` | golden dataset ok |
| `dev/tools/audit_docs.py --package tl-extract` | 0 findings |
| `just test` | 7641 passed, 1 skipped, 16 deselected, 34 snapshots passed, in 42 min on `ac72f81` (SQLite) |
| `just test-parity` | not run: no adapter, ledger or database code was touched |

## Deviations from plan
- T09 was split: the table logic and the shell are supervisor pieces; the two readers are tickets (T09a, T09b).
- T12 was built by the supervisor, not given to an implementer.
- The contract was extended after the first batch (916b5a8, accepted by the orchestrator): `FileMetadata` gained optional `image_format`, `width` and `height`. `ocr` is version 2 and fills them; its note line was dropped.

## Escalations and decisions
- Contract gap (no place for image width and height): proposed in the first relay, accepted and applied as described above.
- Open points of the first batch, decided here and pinned by tests (S9): `check_archive` refuses a ZIP that lacks either `xl/workbook.xml` or `[Content_Types].xml`; a PDF page tree that points at itself, forms a cycle or nests 5000 deep ends in milliseconds with `page_count` None, with or without a `/Count`.
- The CSV reader does not stop at a run of blank records (`MAX_BLANK_RUN` is the XLSX reader's guard): a CSV is bounded by its size, and a provided test requires 30 000 blank lines to be read.
- A TIFF that repeats a text tag: the last entry wins. No test pins it; it is harmless.
- Time: extractors are pure and have no clock. The orchestrator told workstream A that the job runner will run `extract` under a wall-clock limit.

## Security review round 1 (b1c4e60) and the fixes
The review asked for changes; all are made on `p1/i3b` (commits S13 `137bd80`, S14 `a33078b`, after the merge of `p1/i3` at d2a4850, `c7dcbf3`).
Each fix has a crafted-file test of a few hundred kilobytes at most that finishes well inside a second.

| Item | Fix |
|---|---|
| H1 PDF page count and object streams | `/Root/Pages/Count` only; byte scan before pypdf (object streams, `startxref`, `/Length` values and one past the end of the file, any string of a megabyte); `strict=True`; pypdf's decompression limits lowered per call; AGENTS.md corrected |
| H2 XLSX in openpyxl | openpyxl removed from the extractors; stdlib `iterparse` readers (`xlsxxml.py`) count elements, depth, shared strings, cells and characters as they stream and drop each row; sheets capped at 256 |
| H3 metadata cost | text is cut to four times the limit before it is cleaned; the PDF byte scan refuses a string of a megabyte |
| M1 to M3 | only parts that were scanned and end in `.xml` are read; the end-of-central-directory record is checked before `zipfile` loads the directory; core properties come from `docProps/core.xml` and a missing field stays None |
| M4 CSV cost | decoded and parsed as a stream; control-character checks run in C; MAX_CELLS is the contract's and counts data cells. Measured: 41 MB CSV of 1 million cells 2.7 s and 124 MB over the interpreter (was 6.4 s and 409 MB) |
| M5, M6 | strict PDF reading with the junk before the header cut away (`damaged_pdf`); JPEG fill bytes capped at 64 |
| L1 to L8 | TIFF sizes capped at 2**31-1; data after 1000 blank rows is refused (`too_many_blank_rows`) instead of dropped; pdf and ocr refuse any option, tabular refuses unknown ones (`unknown_option`); two `header_map` keys for one header are a `duplicate_header`; a compound document is `encrypted_xlsx`; sheet count and name length capped; MAX_CELLS aligned (20 000 x 50 fits, 20 000 x 200 does not); pypdf log records dropped while it runs and no file content goes into logs |

Deviations from the review text: the sheet limit is 48 MiB uncompressed and the shared-strings limit 24 MiB (not "a few MiB"): a table of 20 000 x 50
cells is about 40 MB of sheet XML, and the real bounds are the element, cell, string and character counts taken while streaming. The largest legal XLSX
(20 000 x 50 numeric cells) costs 8 s and 34 MB over the interpreter. The full `just test` was not re-run for this round, as asked.

## Security re-review (d1e2b7a) and the second round of fixes
The re-review passed every original finding and found three new problems in the rewrite; all are fixed (S16 `c021ce8`, S17 below).

| Item | Fix |
|---|---|
| N2 unbounded XML tree | `events()` clears and detaches each element at its end event, counts attributes and elements a worksheet does not have; `run_guarded` builds the failed result after the except clauses end. The 97 KB file with 4.9 million elements fails with `unsafe_xlsx` under a 1 GiB address-space limit (a subprocess test) |
| N1 regex memory | the regular expressions on strings are gone; pypdf reads through a stream that counts its operations (600 000 allowed), which bounds a 47 MB title, a huge `/Kids` array and a long `/Prev` chain alike |
| N3 PDF pre-scan bypasses | `/Prev`, `/XRef` and `startxref` counted together (any `#xx` spelling), `/Size` capped, decompression limits 2 MiB (an xref stream of 400 000 objects). Replaced, with the same effect: "string bytes per file" and "bytes of Root, Pages and Info" are bounded by the operation budget instead of by a second parse |
| L2 to L4, L1 | `sheet_too_large` for an honest sheet over its limit, `zip_bomb` for a part that claims more than deflate can (ratio 1100); `bad_shared_string`, `bad_cell_ref`, `bad_row_number` (never echoed); numbers by strict regex; a sheet over 40 s is `sheet_too_slow` |

A flat `/Kids` array of more than about 100 000 pages and a PDF with more than about 400 000 objects are now refused (`pdf_too_complex`, `damaged_pdf`); the job runner's limits are the backstop for the rest.

## Security third pass (9ab071f) and the D10 merge
Fixed in S19 (below) after merging `p1/i3` at d95abf1 (FANOUT D10; S18 `e2b8efb` uses the contract's limits and cuts notes, problem lists and suffixed names to them).

| Item | Fix |
|---|---|
| F1 pypdf I/O | `_BudgetStream` charges every operation and every byte handed out (4 times the file plus 4 MiB); `getbuffer`, `getvalue` and `readlines`, which pypdf's repair path calls once per bad xref line, raise. A 2000-line bad table is `pdf_too_complex` in milliseconds |
| F2 element budget | only elements a sheet lacks are charged for their attributes; the largest tables in Excel's form (20 000 x 50 and 5 000 x 200) are read (9 s and 9.5 s of reading each); the refusal is `sheet_too_complex` with a message |
| L1, L2, L4 | no clock in the reader (D9's wall clock is the time limit); `<row>` elements capped at a sheet's rows; refusals name the sheet and the cell or row |

## Security
Extractors read untrusted bytes. The commits to read are listed in the relay (SECURITY_REVIEW). The rules, each with a test: refuse before parsing
(declared sizes of ZIP parts, member count, encrypted parts, unsafe names); scan every XML part for a document type or entity, including
UTF-16; openpyxl read-only, values only, links not followed; pypdf for the information dictionary only, encrypted PDFs refused without a
password attempt, loops in a page tree bounded; images parsed by hand with every offset checked and every walk bounded, no decoder; cells with
a control character or a lone surrogate are left empty and reported (a NUL crashes Postgres); `extract` never raises. Residual: no time limit
inside an extractor, and the memory ceiling is `MAX_CELLS` (1 000 000 cells) and 64 MiB of cell text.

## Learnings
Appended: L-P1-I3B-1 to 5. Proposed by implementers and accepted as process notes only: a pasted excerpt of a module in a ticket should say it is
abridged (T11); list `docs/templates/haiku-report.md` in Context (T10); STEPS should say "if either A or B is missing" (T09b). Declined: the
`UV_NATIVE_TLS` warning (noise, not a fact worth a learning).

## Docs
Created: `packages/tl-extract/README.md` and `AGENTS.md`, `schema/fixtures/document-schemas/README.md`, the plan `docs/tickets/P1-I3/README-B.md`, the
four tickets, and this report. `docs/reports/APPROVALS.md` has the schema fixtures and the pypdf licence. No runbook: no operational command or alert
was added.

## Follow-ups filed
- Workstream A: run `extract` under a wall-clock limit; expect up to about 1 million cells in a job result.
- A real provider behind the plugin interface (PDF tables, OCR) is a later increment (ADR-0008 decision 8).
- Escape cells that start with `=`, `+`, `-` or `@` in any exporter that writes extracted text back to a spreadsheet.

## Showcase
1. **A messy spreadsheet becomes a validated list.**
   - Where: `uv run pytest packages/tl-extract/tests/test_fixtures_through_extractor.py -q`; the sources are in `packages/tl-extract/tests/golden/sources/` and the results in `packages/tl-extract/tests/golden/expected/`.
   - Standard activity: re-keying an instrument index from a spreadsheet and checking it by eye.
   - Novel approach: the extractor reads the person's own headers through a mapping (`header_map`, built from the schema's aliases), keeps what is wrong as a problem of its row instead of dropping the file, and the schema check then names the one bad cell.
   - Unique value: row 6 of 40 says `fail_action` is `OPEN`; the other 39 pass and nothing is lost or guessed.
2. **A file that cannot hurt the system.**
   - Where: `uv run pytest packages/tl-extract/tests/test_xlsxgrid.py -q` (zip bomb, entity bomb, UTF-16 trick, formulas, links).
   - Standard activity: opening an uploaded spreadsheet.
   - Novel approach: the archive is judged by what it declares before anything is parsed, formulas are never run and links never followed.
   - Unique value: an upload can be refused with a plain reason ("the workbook declares a document type or an entity") instead of hanging a worker.
3. **Honest stubs.**
   - Where: `uv run pytest packages/tl-extract/tests/test_pdf.py packages/tl-extract/tests/test_ocr.py -q`.
   - Standard activity: a PDF or scan arrives and its page count, author and dates are filled in by hand.
   - Novel approach: real metadata is read, and the content is explicitly left unread with a note that names the owner decision.
   - Unique value: a register shows what the file says about itself today, and the content step can be added later without changing the plugin interface.

## Cost notes
Four implementer tickets and four first-attempt reviews, one relay round of dispatch. The supervisor wrote the references, the stubs, the tests and
the fixtures.
