"""``load_checks`` (W0-B1): the readiness-check registry and its refusals."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from sqlalchemy import Connection
from tl_core.readiness import (
    MAX_CHECKS,
    MAX_NAME_CHARS,
    CheckResult,
    IwpFacts,
    ReadinessCheck,
    ReadinessLoadError,
    load_checks,
)


class Check:
    version = "1"

    def __init__(self, name: str) -> None:
        self.name = name
        self.watches: frozenset[str] = frozenset()

    def evaluate(self, conn: Connection, iwp: IwpFacts, today: date) -> CheckResult:
        return CheckResult(name=self.name, version=self.version, state="n_a", detail="none")


class Entry:
    """The two members of an ``EntryPoint`` that ``load_checks`` uses."""

    def __init__(self, name: str, factory: Callable[[], Any]) -> None:
        self.name = name
        self._factory = factory

    def load(self) -> Callable[[], Any]:
        return self._factory


def entry(name: str, check_name: str | None = None) -> Entry:
    return Entry(name, lambda: Check(name if check_name is None else check_name))


def load(*entries: Entry) -> dict[str, ReadinessCheck]:
    return load_checks(entries)  # type: ignore[arg-type]


def test_only_the_materials_check_is_installed_by_default() -> None:
    assert set(load_checks()) == {
        "inspections_planned",
        "labour_requested",
        "materials_reserved",
        "model_slice_available",
        "permits_planned",
        "predecessors_handed_over",
        "rfis_answered",
        "documents_current",
    } | {"constraints_cleared"}  # P2-I2 S4
    assert load_checks([]) == {}


def test_a_check_is_found_by_name_and_the_result_is_sorted() -> None:
    found = load(entry("zeta_check"), entry("alpha_check"), entry("mid_check"))
    assert list(found) == ["alpha_check", "mid_check", "zeta_check"]
    assert all(isinstance(check, ReadinessCheck) for check in found.values())
    assert found["alpha_check"].name == "alpha_check"


def test_two_entries_with_one_check_name_are_refused() -> None:
    with pytest.raises(ReadinessLoadError, match="declared twice") as caught:
        load(entry("first", "same_name"), entry("second", "same_name"))
    assert "'same_name'" in str(caught.value)


def test_a_load_failure_is_refused_and_keeps_the_exception_type_only() -> None:
    def broken() -> Any:
        raise RuntimeError("secret internals /srv/private/path hunter2")

    with pytest.raises(ReadinessLoadError) as caught:
        load(Entry("bad_plugin", broken))
    text = str(caught.value)
    assert "'bad_plugin'" in text and "RuntimeError" in text
    assert "secret" not in text and "hunter2" not in text and "/srv" not in text


def test_a_load_failure_logs_the_full_text_for_the_server_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken() -> Any:
        raise ValueError("full detail for the log")

    with caplog.at_level(logging.WARNING), pytest.raises(ReadinessLoadError):
        load(Entry("bad_plugin", broken))
    assert "full detail for the log" in caplog.text


def test_an_entry_point_that_fails_while_loading_its_module_is_refused() -> None:
    class Unimportable(Entry):
        def load(self) -> Callable[[], Any]:
            raise ModuleNotFoundError("no module named secret_name")

    with pytest.raises(ReadinessLoadError, match="ModuleNotFoundError") as caught:
        load(Unimportable("gone", lambda: None))
    assert "secret_name" not in str(caught.value)


@pytest.mark.parametrize("produced", [None, "a string", 42, object(), {"name": "x"}])
def test_a_plugin_that_returns_something_that_is_not_a_check_is_refused(produced: Any) -> None:
    with pytest.raises(ReadinessLoadError, match="must return a ReadinessCheck"):
        load(Entry("not_a_check", lambda: produced))


def test_a_plugin_missing_a_member_of_the_protocol_is_refused() -> None:
    class NoEvaluate:
        name = "no_evaluate"
        version = "1"
        watches: frozenset[str] = frozenset()

    with pytest.raises(ReadinessLoadError, match="must return a ReadinessCheck"):
        load(Entry("no_evaluate", NoEvaluate))


@pytest.mark.parametrize(
    "bad", ["", "Upper", "1starts_with_digit", "has-dash", "has space", "_leading", "ünï"]
)
def test_a_name_that_is_not_snake_case_is_refused(bad: str) -> None:
    with pytest.raises(ReadinessLoadError, match="snake case"):
        load(entry("plugin", bad))


def test_a_name_over_the_length_bound_is_refused_and_one_at_the_bound_is_not() -> None:
    assert list(load(entry("p", "a" * MAX_NAME_CHARS))) == ["a" * MAX_NAME_CHARS]
    with pytest.raises(ReadinessLoadError, match=str(MAX_NAME_CHARS)):
        load(entry("p", "a" * (MAX_NAME_CHARS + 1)))


def test_exactly_max_checks_load_and_one_more_is_refused() -> None:
    names = [f"check_{i:03d}" for i in range(MAX_CHECKS)]
    assert list(load(*(entry(n) for n in names))) == names
    with pytest.raises(ReadinessLoadError, match=f"more than {MAX_CHECKS}"):
        load(*(entry(n) for n in [*names, "check_extra"]))


def test_the_first_failure_names_its_plugin_not_a_later_one() -> None:
    def broken() -> Any:
        raise RuntimeError("x")

    with pytest.raises(ReadinessLoadError) as caught:
        load(Entry("a_broken", broken), Entry("b_broken", broken))
    assert "'a_broken'" in str(caught.value) and "b_broken" not in str(caught.value)
