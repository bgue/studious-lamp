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
| `just check` | clean on `ac72f81` (ruff, format, pyright 0 errors, codegen and OpenAPI drift, licences) |
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
