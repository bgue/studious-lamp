"""The PDF extractor: real metadata, content stubbed (P1-I3B-T10; ADR-0008 decision 8).

Reports the page count, title, author, producer and dates of a PDF. No text, table or image is
read: the result is ``metadata_only`` with an empty ``rows`` and a note naming the decision. An
encrypted or damaged PDF is ``failed`` with a problem.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, BinaryIO

from tl_core.derivation import ExtractionResult, SourceFile

from tl_extract.kinds import file_kind
from tl_extract.pdfinfo import read_pdf_info
from tl_extract.reading import STUBBED_NOTE, metadata_for, read_exact, run_guarded


class PdfExtractor:
    name = "pdf"
    version = "1"

    def accepts(self, source: SourceFile) -> bool:
        return file_kind(source) == "pdf"

    def extract(
        self, source: SourceFile, data: BinaryIO, options: Mapping[str, Any]
    ) -> ExtractionResult:
        def body() -> ExtractionResult:
            info = read_pdf_info(read_exact(source, data))
            notes = [STUBBED_NOTE.format(what="the text and tables of the PDF")]
            if info.page_count is None:
                notes.append("the page count could not be read")
            return ExtractionResult(
                extractor=self.name,
                extractor_version=self.version,
                status="metadata_only",
                metadata=metadata_for(
                    source,
                    page_count=info.page_count,
                    title=info.title,
                    author=info.author,
                    created=info.created,
                    modified=info.modified,
                    producer=info.producer,
                ),
                notes=notes,
            )

        return run_guarded(self.name, self.version, source, body)
