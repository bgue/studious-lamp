# Increment plan — P1-I3 workstream B (extractors)

Status: done
Supervisor session: 2026-10-17
Brief sections: §9 M1 (derivation pipeline), §24.5 (correlated imports), §16 Phase 1 exit; ADR-0008 decision 8 (stubs only, no LLM, no spend)
Branch: `p1/i3b` (base `p1/i3`; the orchestrator merges it into `p1/i3` when it is DONE). Fanout plan: [FANOUT.md](FANOUT.md) (decisions D1 to D8). Workstream A (pipeline) runs on `p1/i3a`.

## Objective
A new workspace package `packages/tl-extract` (`tl_extract`) whose three extractors are plugins under the entry-point group
`throughline.extractors`: `tabular` (CSV and XLSX into rows, with header mapping and column profiles), `pdf` (real metadata,
content stubbed) and `ocr` (image format and size, no OCR). Every extractor passes `tests/contract/test_extractor_contract.py`,
refuses what is over the bounds of the contract (D4) instead of truncating it, and treats the file as hostile. Plus the document
schema fixtures (instrument index with the 40-tag demo sample and a one-row-invalid variant, line list, equipment list) and a
golden dataset of three sources with exact expected results.

## Demo
Workstream A owns `just demo P1-I3`. What B hands over, and how to see it work once the tickets are merged:
```
uv run pytest packages/tl-extract -q
uv run python packages/tl-extract/tests/golden/make_golden.py --check
uv run pytest packages/tl-extract/tests/test_fixtures_through_extractor.py -q
```
The last test is the demo path up to the publish: `instrument-index@1.0.0.sample.csv` extracts to 40 rows that all pass the schema,
the `.invalid.csv` variant fails on exactly row 6 (`fail_action` is `OPEN`), and a person's own headers map to the schema's names.

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S1 `d5ed091` | Package, shared limits and helpers (`reading`, `kinds`, `options`), `build_table` (headers, hints, duplicates, profiles) | Every reader's safety rules live here; extractors read untrusted bytes (D7) | orchestrator security review | done |
| S2 `6418d83`, S2b `36447c0` | Reference readers (csv, xlsx, pdf, image) and the three extractor shells | The reference for the stub-plus-provided-test tickets and the takeover path | orchestrator security review | done |
| S3 `034b650` | T13 document schema fixtures (a `schema` fixture ticket; no LinkML, no generated file) | `schema/**` is outside the Haiku checklist (item 6) | orchestrator (SCHEMA_APPROVALS) | done |
| S4 `864ff3e` | Stubs of the four readers, provided tests, held tests | Tests as spec (02 §3) | n/a | done |
| S5 `1dc3813` | T12 golden dataset and its evaluation test; package README and AGENTS | Sources and expected results are one design; a ticket would write both from the same code (checklist item 7) | orchestrator | done |

## Tickets
T09 of the plan is split: the table logic and the shell are S1 and S2, the two readers are tickets.

| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| T09a | CSV reader (`csvgrid.py`) | H | S1, S2b, S4 | merged | pass at attempt 1; `2619f72`, merge `3c4e029` |
| T09b | XLSX reader (`xlsxgrid.py`): archive guards, XML scan, openpyxl read-only | H | S1, S2b, S4 | merged | pass at attempt 1; `4f9aa91`, merge `b040e72` |
| T10 | PDF properties with pypdf (`pdfinfo.py`) | H | S1, S2b, S4 | merged | pass at attempt 1; `5944172`, merge `1f2b507` |
| T11 | Image format and size from the header (`imagehdr.py`) | H | S1, S2b, S4 | merged | pass at attempt 1; `5f0ff38`, merge `9be94d0` |
| T12 | Golden dataset | S | T09a, T09b, T10 | built (S5); test joined in S10 | `make_golden.py --check` ok |
| T13 | Document schema fixtures | S | none | built (S3) | approved, APPROVALS.md |

Haiku-ability checklist (`01-tiers.md` §6), 1 to 7: files ≤ 6 / interfaces in the repo / test to pass / diff ≤ 400 lines in ≤ 5 files / avoids the Sonnet table / avoids schema, migrations, dependencies / verifiable from diff and commands.

| Ticket | 1 | 2 | 3 | 4 | 5 | 6 | 7 | Verdict |
|---|---|---|---|---|---|---|---|---|
| T09a | yes (5) | yes | yes (33 tests) | yes (about 90 lines, 2 files) | yes | yes | yes | ticket |
| T09b | yes (5) | yes | yes (76 tests) | yes (about 190 lines, 2 files) | yes (parsing of untrusted input is not on the list) | yes | yes | ticket |
| T10 | yes (4) | yes | yes (55 tests) | yes (about 90 lines, 2 files) | yes | yes (`pypdf` is already added by S1) | yes | ticket |
| T11 | yes (4) | yes | yes (40 tests) | yes (about 170 lines, 2 files) | yes | yes | yes | ticket |
| T12 | yes | yes | yes | yes | yes | yes | no: the generator and the expected files are one hand | supervisor |
| T13 | yes | yes | yes | yes | yes | no: `schema/**` | yes | supervisor |
| T09 table and shell | yes | yes | yes | yes | yes | yes | yes | supervisor: shared by both readers, and the rules of every reader live in it (it is the part a security review reads first) |

Each ticket was verified against the reference at `36447c0` (the provided test passes), and the tests were checked by mutation: removing a
guard from the reference makes a test fail, except where two guards cover the same case (the JPEG segment length, the TIFF bounds
that `struct.error` also catches). The tickets were generated from the stubs, and a search found no line of a reference body in them.

## Order of work
1. Round 1 (this relay): S1 to S5 done; dispatch T09a, T09b, T10, T11 (disjoint Allowed paths, none depends on another).
2. Round 2: merge the four tickets after reviews; move the held tests into the package (`docs/tickets/P1-I3/held/*.py.txt` to `packages/tl-extract/tests/*.py`); run `make_golden.py --check`; full gates; learnings; the workstream report `docs/reports/P1-I3-B.md`; DONE.

## Risks and escalation triggers
- **XLSX parsing** is the largest attack surface. If a reviewer finds a way around the archive guard or the XML scan, the ticket is taken over by the supervisor (the reference is at `36447c0`).
- **No time limit.** Extractors are pure functions without a clock. A pypdf or openpyxl input that loops would hold a worker until its lease expires. The job runner (workstream A, T02) should run `extract` somewhere it can be abandoned; this is a note for the orchestrator, not a change here.
- **Contract gap (closed).** `FileMetadata` had no width, height or format field. The orchestrator added optional `image_format`, `width` and `height` (916b5a8) and `ocr` version 2 fills them.
- **Memory.** The contract allows 20 000 rows by 200 columns (4 million cells). The package adds `MAX_CELLS` = 1 000 000 and `MAX_TOTAL_CHARS` = 64 MiB; a larger table is refused. Workstream A's job result store should expect up to about 1 million cells.
- **Escalate** if a ticket fails review twice (two-strikes: the supervisor finishes it), or if the contract needs to change.

## Blocked / Decision
(none)
