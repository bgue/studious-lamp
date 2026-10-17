# tl-extract (`tl_extract`)

The extractors of the derivation pipeline: plugins that read the bytes of a source file (CSV, XLSX, PDF, image) and return an
`ExtractionResult` as defined by `tl_core.derivation.types` (brief §9 M1; ADR-0008 decision 8: stubs only, no LLM, no spend).

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_extract.tabular.TabularExtractor` | class | Entry point `tabular`. CSV and XLSX into `rows`, `columns`, `profiles` (`status="ok"`) |
| `tl_extract.pdf.PdfExtractor` | class | Entry point `pdf`. Real PDF metadata; content stubbed (`metadata_only`) |
| `tl_extract.ocr.OcrExtractor` | class | Entry point `ocr`. Image format, size and header text; no OCR (`metadata_only`) |
| `tl_extract.options.TableOptions` | model | The options of the tabular extractor: `sheet`, `header_row`, `delimiter`, `header_map`, `normalise_headers`, `duplicate_headers` |
| `tl_extract.kinds.file_kind` | function | Which extractor family a `SourceFile` belongs to, by extension first and content type second |
| `tl_extract.reading` | module | The shared limits, `Refusal`, `run_guarded`, `read_exact`, text cleaning, `RawGrid` |
| `tl_extract.table.build_table` | function | Headers, mapping hints, duplicates, rows and column profiles from a `RawGrid` |
| `tl_extract.csvgrid.read_csv` | function | CSV bytes to a `RawGrid` (encoding, delimiter, quotes, limits) |
| `tl_extract.xlsxgrid.read_xlsx` | function | XLSX bytes to a `RawGrid`: end-record check, archive guards, XML scan, then streaming parsers (`tl_extract.xlsxxml`); no workbook library |
| `tl_extract.pdfinfo.read_pdf_info` | function | A byte scan, then page count (`/Root/Pages/Count`) and information dictionary with pypdf (strict, limits lowered); `pdf_date_to_iso` |
| `tl_extract.imagehdr.read_image_header` | function | PNG, JPEG, TIFF format and size from the header, by hand |

The pipeline finds the plugins through the entry-point group `throughline.extractors` (`pyproject.toml`); nothing imports this package
directly. Each result follows the contract: every bound of `tl_core.derivation` holds, a bad file is `failed` with problems (no
paths, no stack traces), and the same bytes give the same result.

## What each extractor returns
| File | Status | Holds |
|---|---|---|
| CSV, XLSX | `ok` | `columns`, `rows` (text or None), `profiles`, `problems` per row, `notes`; XLSX also `sheet`, `sheet_names`, title/author/dates |
| PDF | `metadata_only` | page count, title, author, producer, created, modified; a note naming ADR-0008 |
| PNG, JPEG, TIFF | `metadata_only` | title, author, producer, dates where the header has them; `image_format`, `width` and `height`; the ADR-0008 note |
| anything unreadable | `failed` | a problem with a code: `not_utf8`, `too_many_rows`, `duplicate_header`, `unknown_option`, `zip_bomb`, `unsafe_xlsx`, `encrypted_xlsx`, `too_many_blank_rows`, `encrypted_pdf`, `damaged_pdf`, `pdf_too_complex`, `broken_image`, ... |

## Depends on / used by
- Depends on: `tl_core.derivation` (the contract), `pydantic`, `pypdf` (BSD-3-Clause). `openpyxl` (MIT) is a test dependency only (the tests and the golden script write workbooks).
- Used by: the derivation pipeline in `tl_core` finds the plugins by entry point. Tests: `tests/contract/test_extractor_contract.py` is called by each extractor's test.

## Commands
```
just test packages/tl-extract
uv run python packages/tl-extract/tests/golden/make_golden.py --check   # the golden sources and expected results still match
```

## Fixtures
- Document schemas (JSON Schema, version, sample, header aliases) are under `schema/fixtures/document-schemas/`; see its README.
- The golden sources and their expected results are under `packages/tl-extract/tests/golden/`.

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P1-I3 (workstream B). No interface change since.
