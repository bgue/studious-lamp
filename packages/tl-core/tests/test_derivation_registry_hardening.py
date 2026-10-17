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
    ColumnProfile,
    ExtractionProblem,
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


def run_with(**changes: Any) -> ExtractionResult:
    """A result that is fine except for ``changes``, run through the guard."""

    class Shaped:
        name = "shaped"
        version = "1"

        def accepts(self, source: SourceFile) -> bool:
            return True

        def extract(
            self, source: SourceFile, data: BinaryIO, options: Mapping[str, Any]
        ) -> ExtractionResult:
            base = ExtractionResult(
                extractor=self.name,
                extractor_version=self.version,
                status="ok",
                metadata=FileMetadata(
                    content_type=source.content_type, size=source.size, sha256=source.sha256
                ),
                columns=["a"],
                rows=[{"a": "1"}],
            )
            return base.model_copy(update=changes)

    return run_extraction({"shaped": Shaped()}, SOURCE, io.BytesIO(DATA))


def meta(**fields: Any) -> FileMetadata:
    return FileMetadata(
        content_type=SOURCE.content_type, size=SOURCE.size, sha256=SOURCE.sha256, **fields
    )


@pytest.mark.parametrize(
    ("changes", "words"),
    [
        ({"notes": ["x"] * 101}, "more than 100 notes"),
        ({"notes": ["x" * 1001]}, "a note is longer than 1000"),
        (
            {"problems": [ExtractionProblem(code="c", message="m")] * 1001},
            "more than 1000 problems",
        ),
        ({"problems": [ExtractionProblem(code="c", message="m" * 501)]}, "problem message"),
        ({"columns": ["c" * 256], "rows": [{"c" * 256: "1"}]}, "a column name is longer"),
        ({"sheet": "s" * 256}, "the sheet name is longer"),
        ({"metadata": meta(title="t" * 1001)}, "a metadata text is longer"),
        ({"metadata": meta(producer="p" * 1001)}, "a metadata text is longer"),
        ({"metadata": meta(sheet_names=["s"] * 257)}, "more than 256 sheet names"),
        ({"metadata": meta(sheet_names=["s" * 256])}, "a sheet name is longer"),
        (
            {"profiles": [ColumnProfile(name="a", non_empty=1, distinct=1, max_length=1)] * 2},
            "more column profiles than columns",
        ),
        (
            {
                "profiles": [
                    ColumnProfile(
                        name="a", non_empty=1, distinct=1, max_length=1, samples=["s" * 10_001]
                    )
                ]
            },
            "a profile sample",
        ),
    ],
)
def test_every_part_of_a_result_is_bounded_and_a_breach_fails_instead_of_truncating(
    changes: dict[str, Any], words: str
) -> None:
    result = run_with(**changes)
    assert result.status == "failed" and result.rows == []
    (problem,) = result.problems
    assert problem.code == "contract_violation" and words in problem.message


def test_a_result_inside_every_bound_passes() -> None:
    ok = run_with(
        notes=["x" * 1000] * 100,
        metadata=meta(title="t" * 1000, sheet_names=["s" * 255] * 256),
        profiles=[ColumnProfile(name="a", non_empty=1, distinct=1, max_length=1, samples=["s"])],
    )
    assert ok.status == "ok"
