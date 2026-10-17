"""The extractor registry and the guarded call of a plugin (P1-I3 T03).

No database: entry points are replaced by real ``EntryPoint`` objects that name the callables of
``tl_core.derivation.testing``, and the plugins under test are small classes defined here.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Callable, Iterator, Mapping
from importlib.metadata import EntryPoint
from typing import Any, BinaryIO

import pytest
from tl_core.derivation import registry
from tl_core.derivation.registry import (
    AmbiguousExtractorError,
    ExtractorLoadError,
    NoExtractorError,
    choose,
    forget_loaded,
    load_extractors,
    run_extraction,
    use_extractors,
)
from tl_core.derivation.types import (
    EXTRACTOR_ENTRY_POINT,
    MAX_CELL_CHARS,
    MAX_COLUMNS,
    MAX_ROWS,
    MAX_SOURCE_BYTES,
    ExtractionResult,
    Extractor,
    FileMetadata,
    SourceFile,
)

TESTING = "tl_core.derivation.testing"


def entry(name: str, target: str) -> EntryPoint:
    return EntryPoint(name=name, value=f"{TESTING}:{target}", group=EXTRACTOR_ENTRY_POINT)


@pytest.fixture
def plugins(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., None]]:
    """``plugins(entry(...), ...)`` makes those the installed entry points of the group."""

    def install(*entries: EntryPoint) -> None:
        def fake_entry_points(*, group: str) -> list[EntryPoint]:
            assert group == EXTRACTOR_ENTRY_POINT
            return list(entries)

        monkeypatch.setattr(registry, "entry_points", fake_entry_points)
        forget_loaded()

    yield install
    forget_loaded()


def source(filename: str = "index.csv", data: bytes = b"tag\nA\n", **more: Any) -> SourceFile:
    fields: dict[str, Any] = {
        "file_id": "f1",
        "filename": filename,
        "content_type": "text/csv",
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "source_ref": "src.doc.ISD-001@A",
    }
    fields.update(more)
    return SourceFile(**fields)


class Plugin:
    """A configurable extractor: ``answer`` builds the result it returns (or raises)."""

    def __init__(
        self,
        name: str = "plug",
        *,
        accept: bool = True,
        answer: Callable[[SourceFile, Mapping[str, Any]], Any] | None = None,
    ) -> None:
        self.name = name
        self.version = "7"
        self._accept = accept
        self._answer = answer
        self.calls = 0
        self.seen_options: list[Mapping[str, Any]] = []

    def accepts(self, source: SourceFile) -> bool:
        return self._accept

    def extract(
        self, source: SourceFile, data: BinaryIO, options: Mapping[str, Any]
    ) -> ExtractionResult:
        self.calls += 1
        self.seen_options.append(options)
        if self._answer is not None:
            return self._answer(source, options)  # type: ignore[no-any-return]
        return self.ok(source)

    def ok(self, source: SourceFile, **more: Any) -> ExtractionResult:
        fields: dict[str, Any] = {
            "extractor": self.name,
            "extractor_version": self.version,
            "status": "ok",
            "metadata": FileMetadata(
                content_type=source.content_type, size=source.size, sha256=source.sha256
            ),
            "columns": ["tag"],
            "rows": [{"tag": "A"}],
        }
        fields.update(more)
        return ExtractionResult(**fields)


def registry_of(*plugs: Extractor) -> dict[str, Extractor]:
    return {p.name: p for p in plugs}


# --- load_extractors ----------------------------------------------------------------------------


def test_the_installed_extractors_are_loaded_by_name_in_name_order(
    plugins: Callable[..., None],
) -> None:
    plugins(entry("second", "make_second"), entry("fake", "make_fake"))
    found = load_extractors()
    assert list(found) == ["fake", "second"]
    assert found["fake"].name == "fake" and found["fake"].version == "1"
    assert found["second"].name == "second"


def test_with_no_entry_points_there_are_no_extractors(plugins: Callable[..., None]) -> None:
    plugins()
    assert load_extractors() == {}


def test_extractors_are_discovered_once_until_forgotten(
    plugins: Callable[..., None], monkeypatch: pytest.MonkeyPatch
) -> None:
    plugins(entry("fake", "make_fake"))
    first = load_extractors()
    calls: list[str] = []

    def spy(*, group: str) -> list[EntryPoint]:
        calls.append(group)
        return []

    monkeypatch.setattr(registry, "entry_points", spy)
    assert load_extractors()["fake"] is first["fake"]  # cached: the entry points are not read
    assert calls == []
    forget_loaded()
    assert load_extractors() == {} and calls == [EXTRACTOR_ENTRY_POINT]


def test_a_plugin_that_cannot_be_loaded_fails_loudly_and_every_time(
    plugins: Callable[..., None],
) -> None:
    plugins(entry("fake", "make_fake"), entry("broken", "make_that_raises"))
    for _ in range(2):  # the failure is not cached as an empty registry
        with pytest.raises(ExtractorLoadError, match="'broken' cannot be loaded.*RuntimeError"):
            load_extractors()


def test_a_missing_module_or_function_is_a_load_error(plugins: Callable[..., None]) -> None:
    plugins(EntryPoint(name="gone", value="no_such_package.mod:make", group=EXTRACTOR_ENTRY_POINT))
    with pytest.raises(ExtractorLoadError, match="'gone' cannot be loaded"):
        load_extractors()
    plugins(entry("gone", "no_such_function"))
    with pytest.raises(ExtractorLoadError, match="'gone' cannot be loaded"):
        load_extractors()


def test_an_entry_point_must_return_an_extractor(plugins: Callable[..., None]) -> None:
    plugins(entry("odd", "make_not_an_extractor"))
    with pytest.raises(ExtractorLoadError, match="'odd'.*must return an Extractor"):
        load_extractors()


def test_the_extractor_must_carry_the_name_of_its_entry_point(
    plugins: Callable[..., None],
) -> None:
    plugins(entry("fake", "make_wrong_name"))
    with pytest.raises(ExtractorLoadError, match="'fake'.*named 'not-the-entry-point-name'"):
        load_extractors()


def test_two_entry_points_with_one_name_are_an_error(plugins: Callable[..., None]) -> None:
    plugins(entry("fake", "make_fake"), entry("fake", "make_fake"))
    with pytest.raises(ExtractorLoadError, match="'fake' is declared twice"):
        load_extractors()


def test_use_extractors_replaces_the_installed_ones_for_the_block_only(
    plugins: Callable[..., None],
) -> None:
    plugins(entry("fake", "make_fake"))
    mine = Plugin("mine")
    with use_extractors({"mine": mine}):
        assert load_extractors() == {"mine": mine}
        with use_extractors({}):
            assert load_extractors() == {}
        assert load_extractors() == {"mine": mine}
    assert list(load_extractors()) == ["fake"]


# --- choose -------------------------------------------------------------------------------------


def test_the_single_extractor_that_accepts_the_source_is_chosen() -> None:
    yes, no = Plugin("yes"), Plugin("no", accept=False)
    assert choose(registry_of(no, yes), source()) is yes


def test_an_explicit_name_wins_even_when_the_extractor_would_not_accept() -> None:
    yes, no = Plugin("yes"), Plugin("no", accept=False)
    assert choose(registry_of(yes, no), source(), "no") is no


def test_an_unknown_name_says_which_extractors_exist() -> None:
    with pytest.raises(NoExtractorError, match="no extractor named 'x'.*known: a, b"):
        choose(registry_of(Plugin("b"), Plugin("a")), source(), "x")
    with pytest.raises(NoExtractorError, match="known: none installed"):
        choose({}, source(), "x")


def test_no_extractor_accepting_the_source_is_an_error_naming_the_file() -> None:
    with pytest.raises(NoExtractorError, match=r"no extractor accepts 'index\.csv' \(text/csv\)"):
        choose(registry_of(Plugin("a", accept=False)), source())
    with pytest.raises(NoExtractorError):
        choose({}, source())


def test_two_extractors_accepting_the_source_must_be_told_apart_by_name() -> None:
    with pytest.raises(AmbiguousExtractorError, match="several extractors accept.*a, b; name one"):
        choose(registry_of(Plugin("b"), Plugin("a")), source())
    assert choose(registry_of(Plugin("b"), Plugin("a")), source(), "b").name == "b"


def test_an_extractor_that_fails_in_accepts_is_a_load_error_not_a_skip() -> None:
    class Broken(Plugin):
        def accepts(self, source: SourceFile) -> bool:
            raise ValueError("oops")

    with pytest.raises(ExtractorLoadError, match="'plug' failed in accepts: ValueError"):
        choose(registry_of(Broken()), source())


# --- run_extraction -----------------------------------------------------------------------------


def test_a_good_result_is_returned_as_it_is() -> None:
    plug = Plugin()
    result = run_extraction(registry_of(plug), source(), io.BytesIO(b"x"))
    assert result.status == "ok" and result.rows == [{"tag": "A"}] and plug.calls == 1


def test_the_callers_options_are_copied_before_the_plugin_sees_them() -> None:
    def meddle(src: SourceFile, options: Mapping[str, Any]) -> ExtractionResult:
        options["header_row"] = 99  # type: ignore[index]
        return plug.ok(src)

    plug = Plugin(answer=meddle)
    mine = {"header_row": 1}
    run_extraction(registry_of(plug), source(), io.BytesIO(b""), options=mine)
    assert mine == {"header_row": 1} and plug.seen_options[0] == {"header_row": 99}
    run_extraction(registry_of(plug), source(), io.BytesIO(b""))
    assert plug.seen_options[1] == {"header_row": 99}  # no options: an empty copy, still a dict


def test_the_name_selects_the_extractor_and_choose_errors_propagate() -> None:
    a, b = Plugin("a"), Plugin("b")
    run_extraction(registry_of(a, b), source(), io.BytesIO(b""), name="b")
    assert (a.calls, b.calls) == (0, 1)
    with pytest.raises(AmbiguousExtractorError):
        run_extraction(registry_of(a, b), source(), io.BytesIO(b""))
    with pytest.raises(NoExtractorError):
        run_extraction({}, source(), io.BytesIO(b""))


def test_a_source_over_the_size_bound_is_refused_without_calling_the_plugin() -> None:
    plug = Plugin()
    big = source(size=MAX_SOURCE_BYTES + 1)
    result = run_extraction(registry_of(plug), big, io.BytesIO(b""))
    assert plug.calls == 0
    assert result.status == "failed" and result.extractor == "plug"
    assert result.extractor_version == "7"
    (problem,) = result.problems
    assert problem.code == "source_too_large" and str(MAX_SOURCE_BYTES) in problem.message
    exact = source(size=MAX_SOURCE_BYTES)
    assert run_extraction(registry_of(plug), exact, io.BytesIO(b"")).status == "ok"


def test_an_exception_in_a_plugin_is_a_failed_result_that_does_not_leak_its_text() -> None:
    def crash(src: SourceFile, options: Mapping[str, Any]) -> ExtractionResult:
        raise OSError("/home/user/private/secret.pdf: permission denied")

    result = run_extraction(registry_of(Plugin(answer=crash)), source(), io.BytesIO(b""))
    assert result.status == "failed"
    (problem,) = result.problems
    assert problem.code == "extractor_crashed"
    assert problem.message == "extractor plug failed: OSError"
    assert "secret" not in problem.message and "/home" not in problem.message


def test_a_failed_result_of_the_plugin_itself_passes_through() -> None:
    def refuse(src: SourceFile, options: Mapping[str, Any]) -> ExtractionResult:
        from tl_core.derivation.types import ExtractionProblem

        return ExtractionResult(
            extractor="plug",
            extractor_version="7",
            status="failed",
            problems=[ExtractionProblem(code="not_utf8", message="the file is not UTF-8")],
        )

    result = run_extraction(registry_of(Plugin(answer=refuse)), source(), io.BytesIO(b""))
    assert result.status == "failed" and result.problems[0].code == "not_utf8"


def violation(**changes: Any) -> Callable[[SourceFile, Mapping[str, Any]], ExtractionResult]:
    def build(src: SourceFile, options: Mapping[str, Any]) -> ExtractionResult:
        return Plugin().ok(src, **changes)

    return build


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"extractor": "other"}, "another extractor or version"),
        ({"extractor_version": "8"}, "another extractor or version"),
        ({"metadata": None}, "no file metadata"),
        (
            {"metadata": FileMetadata(content_type="text/csv", size=1, sha256="0" * 64)},
            "does not match the source",
        ),
        ({"status": "metadata_only", "rows": [{"tag": "A"}]}, "no rows"),
        ({"columns": [f"c{i}" for i in range(MAX_COLUMNS + 1)], "rows": []}, "columns"),
        ({"columns": ["tag", "tag"], "rows": []}, "not unique"),
        ({"rows": [{"tag": "A"}] * (MAX_ROWS + 1)}, "rows"),
        ({"rows": [{"other": "A"}]}, "exactly the columns"),
        ({"rows": [{"tag": "x" * (MAX_CELL_CHARS + 1)}]}, "longer than"),
    ],
)
def test_a_result_that_breaks_the_contract_is_replaced_by_a_failed_one(
    changes: dict[str, Any], fragment: str
) -> None:
    result = run_extraction(
        registry_of(Plugin(answer=violation(**changes))), source(), io.BytesIO(b"")
    )
    assert result.status == "failed" and result.rows == [] and result.columns == []
    (problem,) = result.problems
    assert problem.code == "contract_violation" and fragment in problem.message


def test_something_that_is_not_an_extraction_result_is_a_contract_violation() -> None:
    def junk(src: SourceFile, options: Mapping[str, Any]) -> Any:
        return {"status": "ok"}

    result = run_extraction(registry_of(Plugin(answer=junk)), source(), io.BytesIO(b""))
    assert result.status == "failed"
    assert result.problems[0].code == "contract_violation"
    assert "not an ExtractionResult" in result.problems[0].message


def test_the_bounds_are_inclusive() -> None:
    edge = violation(
        columns=[f"c{i}" for i in range(MAX_COLUMNS)],
        rows=[{f"c{i}": "x" * MAX_CELL_CHARS for i in range(MAX_COLUMNS)}],
    )
    result = run_extraction(registry_of(Plugin(answer=edge)), source(), io.BytesIO(b""))
    assert result.status == "ok" and len(result.columns) == MAX_COLUMNS
