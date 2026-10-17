"""The image extractor ("ocr"): real file properties, no OCR (P1-I3B-T11; ADR-0008 decision 8).

Reports the format and pixel size of a PNG, JPEG or TIFF, and the text properties its header
carries. No engine reads the pixels: the result is ``metadata_only`` with an empty ``rows`` and a
note naming the decision. The contract's ``FileMetadata`` has no width or height field, so they
are written to a note in a fixed form, ``image: format=png width=800 height=600``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, BinaryIO

from tl_core.derivation import ExtractionResult, SourceFile

from tl_extract.imagehdr import read_image_header
from tl_extract.kinds import file_kind
from tl_extract.reading import STUBBED_NOTE, metadata_for, read_exact, run_guarded


class OcrExtractor:
    name = "ocr"
    version = "1"

    def accepts(self, source: SourceFile) -> bool:
        return file_kind(source) == "image"

    def extract(
        self, source: SourceFile, data: BinaryIO, options: Mapping[str, Any]
    ) -> ExtractionResult:
        def body() -> ExtractionResult:
            info = read_image_header(read_exact(source, data))
            return ExtractionResult(
                extractor=self.name,
                extractor_version=self.version,
                status="metadata_only",
                metadata=metadata_for(
                    source,
                    title=info.title,
                    author=info.author,
                    created=info.created,
                    modified=info.modified,
                    producer=info.producer,
                ),
                notes=[
                    f"image: format={info.format} width={info.width} height={info.height}",
                    STUBBED_NOTE.format(what="no text in the image was read"),
                ],
            )

        return run_guarded(self.name, self.version, source, body)
