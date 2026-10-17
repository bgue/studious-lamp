# AGENTS.md — tl-extract

Read the root `AGENTS.md` first. These rules add to it. Everything here reads **untrusted bytes**.

- An extractor is pure: no ledger, no unit of work, no network, no clock, no randomness, no file path taken from the source. The only input is the stream and `SourceFile`; the same bytes and options give the same result (`tests/contract/test_extractor_contract.py`).
- `extract` never raises. Wrap the body in `reading.run_guarded`: a `Refusal` or any other exception becomes a `failed` result. Messages hold fixed text and, at most, a cleaned short excerpt of the file (`reading.shown`). Never `str(exc)`, never a path, never a stack trace.
- Refuse, never truncate (D4): more than `MAX_SOURCE_BYTES`, `MAX_ROWS`, `MAX_COLUMNS` or `MAX_CELL_CHARS` is a `failed` result. The package adds `MAX_CELLS`, `MAX_TOTAL_CHARS`, `MAX_BLANK_RUN` and `MAX_PROBLEMS` to keep memory and time bounded; do not raise them without a test and a note in the report.
- A cell with a control character (other than tab, CR, LF) or a lone surrogate is left empty and is a problem of its row, as in the P1-I2 import: a NUL crashes Postgres and a surrogate poisons the driver connection (L-P1-I2-17, L-P1-I0A-14). Metadata text goes through `reading.clean_metadata_text`.
- XLSX: never evaluate a formula (`data_only=True`), never open an external link (`keep_links=False`), stream the sheet (`read_only=True`), check the archive's declared sizes and the XML parts for a document type or an entity **before** openpyxl parses anything. A new reader of a ZIP-based format needs the same three steps and the same tests (`tests/test_xlsxgrid.py`).
- PDF: only the information dictionary and the page count are read (pypdf). No page is parsed and no stream is decoded. An encrypted PDF is refused without a password attempt. Do not add pdfplumber, Camelot or a text extractor here: ADR-0008 decision 8 keeps content extraction stubbed.
- Images: only the header is read, by hand. There is no decoder, so an image costs nothing to "open". Do not add Pillow or an OCR engine to read pixels without a pixel limit, a test of a decompression bomb and an ADR.
- A row problem's `row` is the place of the row among the kept data rows (the first is 1), so it indexes `rows`; blank rows are skipped and counted in a note.
- Text that starts with `=`, `+`, `-` or `@` is returned as it is. Anything that writes it back into a spreadsheet or CSV for a person must escape it; extractors do not.
- Options are checked strictly (`options.TableOptions`, unknown keys refused). Add an option by adding a field, a test and a line in the README.
- Never name a module `types.py` (L-P0-I5-B1). Test helper modules have unique names (`extractsupport.py`); tests build every file in memory (`extractsupport`), they do not read fixture files except the golden dataset and the document schemas.
- Every extractor's tests call `check_extractor_contract` and cover: an oversize file, too many rows and columns, a long cell, malformed input, and determinism.
