"""Two rules added after the T03 review: plugin error text stays out of messages, and the
metadata's content type must be the source's (coordinator decisions of 2026-10-17)."""

from __future__ import annotations

import hashlib
import io
import logging
from collections.abc import Iterator, Mapping
from importlib.metadata import EntryPoint
from typing import Any, BinaryIO

import pytest
from tl_core.derivation import registry
from tl_core.derivation.registry import (
    ExtractorLoadError,
    forget_loaded,
    load_extractors,
    run_extraction,
)
from tl_core.derivation.types import (
    EXTRACTOR_ENTRY_POINT,
    ExtractionResult,
    Extractor,
    FileMetadata,
    SourceFile,
)

DATA = b"tag\nA\n"
SOURCE = SourceFile(
    file_id="f1",
    filename="index.csv",
    content_type="text/csv",
    size=len(DATA),
    sha256=hashlib.sha256(DATA).hexdigest(),
    source_ref="src.doc.ISD-001@A",
)


class Typed:
    """Returns metadata with the content type it was told to."""

    name = "typed"
    version = "1"

    def __init__(self, content_type: str) -> None:
        self.content_type = content_type

    def accepts(self, source: SourceFile) -> bool:
        return True

    def extract(
        self, source: SourceFile, data: BinaryIO, options: Mapping[str, Any]
    ) -> ExtractionResult:
        return ExtractionResult(
            extractor=self.name,
            extractor_version=self.version,
            status="ok",
            metadata=FileMetadata(
                content_type=self.content_type, size=source.size, sha256=source.sha256
            ),
            columns=["tag"],
            rows=[{"tag": "A"}],
        )


def run(content_type: str) -> ExtractionResult:
    plug: Extractor = Typed(content_type)
    return run_extraction({"typed": plug}, SOURCE, io.BytesIO(DATA))


@pytest.fixture
def installed(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    def install(*entries: EntryPoint) -> None:
        monkeypatch.setattr(registry, "entry_points", lambda *, group: list(entries))
        forget_loaded()

    yield install
    forget_loaded()


def test_a_load_error_names_the_entry_point_and_the_exception_type_only(
    installed: Any, caplog: pytest.LogCaptureFixture
) -> None:
    installed(
        EntryPoint(
            name="broken",
            value="tl_core.derivation.testing:make_that_raises",
            group=EXTRACTOR_ENTRY_POINT,
        )
    )
    with caplog.at_level(logging.WARNING), pytest.raises(ExtractorLoadError) as caught:
        load_extractors()
    assert str(caught.value) == "extractor 'broken' cannot be loaded: RuntimeError"
    assert "this plugin is broken" in caplog.text  # the full text is for the server log


def test_a_missing_module_message_does_not_carry_the_import_error_text(installed: Any) -> None:
    installed(
        EntryPoint(name="gone", value="no_such_package.mod:make", group=EXTRACTOR_ENTRY_POINT)
    )
    with pytest.raises(ExtractorLoadError) as caught:
        load_extractors()
    assert str(caught.value) == "extractor 'gone' cannot be loaded: ModuleNotFoundError"


def test_metadata_with_another_content_type_is_a_contract_violation() -> None:
    result = run("application/pdf")
    assert result.status == "failed" and result.rows == []
    assert result.problems[0].code == "contract_violation"
    assert "does not match the source" in result.problems[0].message


def test_metadata_with_the_sources_content_type_passes() -> None:
    assert run("text/csv").status == "ok"


class Hoarder:
    name = "hoarder"
    version = "1"

    def accepts(self, source: SourceFile) -> bool:
        return True

    def extract(
        self, source: SourceFile, data: BinaryIO, options: Mapping[str, Any]
    ) -> ExtractionResult:
        raise MemoryError("secret path /home/x/file.pdf")


class Wide:
    name = "wide"
    version = "1"

    def accepts(self, source: SourceFile) -> bool:
        return True

    def extract(
        self, source: SourceFile, data: BinaryIO, options: Mapping[str, Any]
    ) -> ExtractionResult:
        columns = [f"c{n}" for n in range(200)]
        return ExtractionResult(
            extractor=self.name,
            extractor_version=self.version,
            status="ok",
            metadata=FileMetadata(
                content_type=source.content_type, size=source.size, sha256=source.sha256
            ),
            columns=columns,
            rows=[dict.fromkeys(columns, "x") for _ in range(5001)],
        )


def test_a_memory_error_in_a_plugin_is_the_fixed_limit_problem() -> None:
    result = run_extraction({"hoarder": Hoarder()}, SOURCE, io.BytesIO(DATA))
    (problem,) = result.problems
    assert (result.status, problem.code) == ("failed", "extraction_limit")
    assert problem.message == registry.LIMIT_MESSAGE and "secret" not in problem.message


def test_a_result_over_the_cell_bound_is_a_contract_violation() -> None:
    result = run_extraction({"wide": Wide()}, SOURCE, io.BytesIO(DATA))
    assert result.status == "failed" and result.problems[0].code == "contract_violation"
    assert "more than 1000000 cells" in result.problems[0].message
