"""Fake extractors for tests of the pipeline (P1-I3): never registered, never run in production.

``FakeExtractor`` reads a small CSV (comma, first line is the header) deterministically, which is
enough to drive the job runner, validation and publication before the real extractors exist and
beside them afterwards. ``make_fake`` and ``make_wrong_name`` are the zero-argument callables an
entry point names; tests build real ``EntryPoint`` objects that point at them.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping
from typing import Any, BinaryIO

from tl_core.derivation.types import (
    ColumnProfile,
    ExtractionProblem,
    ExtractionResult,
    FileMetadata,
    SourceFile,
)


class FakeExtractor:
    """Reads ``.csv`` and ``.txt`` files as a table; anything else it does not accept."""

    name = "fake"
    version = "1"

    def accepts(self, source: SourceFile) -> bool:
        return source.filename.lower().endswith((".csv", ".txt"))

    def extract(
        self, source: SourceFile, data: BinaryIO, options: Mapping[str, Any]
    ) -> ExtractionResult:
        raw = data.read()
        meta = FileMetadata(
            content_type=source.content_type, size=source.size, sha256=source.sha256
        )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return ExtractionResult(
                extractor=self.name,
                extractor_version=self.version,
                status="failed",
                problems=[ExtractionProblem(code="not_utf8", message="the file is not UTF-8 text")],
            )
        records = list(csv.reader(io.StringIO(text), strict=False))
        if not records:
            return ExtractionResult(
                extractor=self.name,
                extractor_version=self.version,
                status="failed",
                problems=[ExtractionProblem(code="empty_file", message="the file has no rows")],
            )
        columns = [c.strip() for c in records[0]]
        rows: list[dict[str, str | None]] = []
        problems: list[ExtractionProblem] = []
        for number, record in enumerate(records[1:], start=1):
            if len(record) != len(columns):
                problems.append(
                    ExtractionProblem(
                        code="ragged_row",
                        message=f"row has {len(record)} cells, the header has {len(columns)}",
                        row=number,
                    )
                )
                continue
            rows.append(dict(zip(columns, (c if c != "" else None for c in record), strict=True)))
        profiles: list[ColumnProfile] = []
        for column in columns:
            values = [v for v in (r[column] for r in rows) if v is not None]
            profiles.append(
                ColumnProfile(
                    name=column,
                    non_empty=len(values),
                    distinct=len(set(values)),
                    max_length=max((len(v) for v in values), default=0),
                    samples=values[:5],
                )
            )
        return ExtractionResult(
            extractor=self.name,
            extractor_version=self.version,
            status="ok",
            metadata=meta,
            columns=columns,
            rows=rows,
            profiles=profiles,
            problems=problems,
        )


def make_fake() -> FakeExtractor:
    return FakeExtractor()


class _Second(FakeExtractor):
    name = "second"


def make_second() -> FakeExtractor:
    """A second, differently named extractor, for tests of choosing between two."""
    return _Second()


class _Misnamed(FakeExtractor):
    name = "not-the-entry-point-name"


def make_wrong_name() -> FakeExtractor:
    """An extractor whose ``name`` differs from the entry point that names it."""
    return _Misnamed()


def make_not_an_extractor() -> object:
    return object()


def make_that_raises() -> FakeExtractor:
    raise RuntimeError("this plugin is broken")


class SlowExtractor(FakeExtractor):
    """Sleeps ``options["seconds"]`` (default 0) before reading; for the wall-clock limit test."""

    name = "slow"

    def accepts(self, source: SourceFile) -> bool:
        return source.filename.endswith(".slow")

    def extract(
        self, source: SourceFile, data: BinaryIO, options: Mapping[str, Any]
    ) -> ExtractionResult:
        import time

        time.sleep(float(options.get("seconds", 0)))
        result = super().extract(source, data, options)
        return result.model_copy(update={"extractor": self.name})


class DyingExtractor(FakeExtractor):
    """Ends the whole process without answering, as a native library crash would."""

    name = "dying"

    def accepts(self, source: SourceFile) -> bool:
        return source.filename.endswith(".die")

    def extract(
        self, source: SourceFile, data: BinaryIO, options: Mapping[str, Any]
    ) -> ExtractionResult:
        import os

        os._exit(3)


class GreedyExtractor(FakeExtractor):
    """Asks for far more memory than any limit allows."""

    name = "greedy"

    def accepts(self, source: SourceFile) -> bool:
        return source.filename.endswith(".greedy")

    def extract(
        self, source: SourceFile, data: BinaryIO, options: Mapping[str, Any]
    ) -> ExtractionResult:
        hoard = bytearray(8 * 1024**3)
        return ExtractionResult(
            extractor=self.name,
            extractor_version=self.version,
            status="failed",
            problems=[ExtractionProblem(code="never", message=str(len(hoard)))],
        )


class PdfStubExtractor:
    """Reads no content from a PDF, as ADR-0008 decision 8 says: metadata only, rows empty."""

    name = "pdfstub"
    version = "1"

    def accepts(self, source: SourceFile) -> bool:
        return source.filename.lower().endswith(".pdf")

    def extract(
        self, source: SourceFile, data: BinaryIO, options: Mapping[str, Any]
    ) -> ExtractionResult:
        data.read()
        return ExtractionResult(
            extractor=self.name,
            extractor_version=self.version,
            status="metadata_only",
            metadata=FileMetadata(
                content_type=source.content_type, size=source.size, sha256=source.sha256
            ),
            notes=["content extraction stubbed (ADR-0008 decision 8)"],
        )


def make_extractors() -> dict[str, Any]:
    """The extractors of the pipeline tests, by name (an ``isolated`` factory)."""
    return {
        e.name: e
        for e in (
            FakeExtractor(),
            SlowExtractor(),
            DyingExtractor(),
            GreedyExtractor(),
            PdfStubExtractor(),
        )
    }
