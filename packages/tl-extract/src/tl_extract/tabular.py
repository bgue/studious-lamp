"""The tabular extractor: CSV and XLSX into rows (P1-I3B; FANOUT D1).

A CSV or XLSX that a person attaches as the derived content of a document is data entry, not
content extraction, so it is read deterministically and fills ``rows`` (``status="ok"``). No
formula is evaluated (XLSX cells are read as the values the file stored), no external link is
followed, and every bound of the contract holds (``tl_extract.reading``).

Options (``tl_extract.options.TableOptions``): ``sheet``, ``header_row``, ``delimiter``,
``header_map``, ``normalise_headers``, ``duplicate_headers``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, BinaryIO

from tl_core.derivation import ExtractionResult, SourceFile

from tl_extract.csvgrid import read_csv
from tl_extract.kinds import file_kind
from tl_extract.options import parse_options
from tl_extract.reading import metadata_for, read_exact, run_guarded
from tl_extract.table import build_table
from tl_extract.xlsxgrid import read_xlsx


class TabularExtractor:
    name = "tabular"
    version = "1"

    def accepts(self, source: SourceFile) -> bool:
        return file_kind(source) in ("csv", "xlsx")

    def extract(
        self, source: SourceFile, data: BinaryIO, options: Mapping[str, Any]
    ) -> ExtractionResult:
        def body() -> ExtractionResult:
            opts = parse_options(options)
            raw = read_exact(source, data)
            grid = read_xlsx(raw, opts) if file_kind(source) == "xlsx" else read_csv(raw, opts)
            table = build_table(grid, opts)
            return ExtractionResult(
                extractor=self.name,
                extractor_version=self.version,
                status="ok",
                metadata=metadata_for(
                    source,
                    sheet_names=grid.sheet_names,
                    title=grid.meta.title,
                    author=grid.meta.author,
                    created=grid.meta.created,
                    modified=grid.meta.modified,
                ),
                sheet=grid.sheet,
                columns=table.columns,
                rows=table.rows,
                profiles=table.profiles,
                problems=table.problems,
                notes=table.notes,
            )

        return run_guarded(self.name, self.version, source, body)
