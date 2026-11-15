"""The forms contract and registry (P2-FORMS S1)."""

from __future__ import annotations

import ast
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import Connection
from tl_core.confidentiality import Viewer
from tl_core.forms import registry, rules, types
from tl_core.forms.registry import FormSourceLoadError, load_form_sources
from tl_core.forms.types import MAX_SOURCES, FormBinding, FormSource, TemplateRef

HASH = "a" * 64


def ref(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "source_type": "forms.Template",
        "source_id": "01HZX3K9Q7M2N4P5R6S8T0V1WA",
        "version": 1,
        "fmt": 2,
        "content_hash": HASH,
    }
    base.update(over)
    return base


def binding(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "record_type": "x.A",
        "key": "K-1",
        "template": ref(),
        "available": True,
        "reason": None,
        "command": "SubmitForm",
        "fixed_args": {"record": "K-1"},
        "answers_arg": "answers",
        "expected_version": 3,
        "prefill": [],
    }
    base.update(over)
    return base


def test_good_ref_and_binding_are_accepted() -> None:
    assert TemplateRef(**ref()).version == 1
    assert FormBinding(**binding()).available is True
    unavailable = binding(
        available=False, reason="closed", template=None, command=None, answers_arg=None
    )
    assert FormBinding(**unavailable).reason == "closed"


@pytest.mark.parametrize(
    "over",
    [
        {"extra": 1},
        {"content_hash": "A" * 64},
        {"content_hash": "a" * 63},
        {"content_hash": "g" * 64},
        {"version": 0},
        {"fmt": 3},
    ],
)
def test_template_ref_refuses(over: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        TemplateRef(**ref(**over))


def test_template_ref_is_frozen() -> None:
    with pytest.raises(ValidationError):
        TemplateRef(**ref()).version = 2  # type: ignore[misc]


@pytest.mark.parametrize(
    "over",
    [
        {"extra": 1},
        {"command": None},
        {"template": None},
        {"answers_arg": None},
        {"reason": "closed"},
        {"fixed_args": {"answers": []}},
        {"fixed_args": {"blob": "x" * 5000}},
        {"prefill": [{"q": "q1", "value": "x" * 70000, "note": None}]},
        {"prefill": [{"q": f"q{i}", "value": 1, "note": None} for i in range(61)]},
    ],
)
def test_binding_refuses(over: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        FormBinding(**binding(**over))


class Source:
    view_word = "forms.view"

    def __init__(self, record_type: str) -> None:
        self.record_type = record_type

    def binding(
        self, conn: Connection, record_id: str, viewer: Viewer, now: datetime
    ) -> FormBinding | None:
        return None


class Entry:
    def __init__(self, name: str, factory: Callable[[], Any]) -> None:
        self.name = name
        self._factory = factory

    def load(self) -> Callable[[], Any]:
        return self._factory


def entry(name: str, record_type: str) -> Entry:
    return Entry(name, lambda: Source(record_type))


def load(*entries: Entry) -> dict[str, FormSource]:
    return load_form_sources(entries)  # type: ignore[arg-type]


def test_an_empty_group_loads_as_empty() -> None:
    assert load() == {}


def test_sources_are_keyed_by_record_type() -> None:
    found = load(entry("b", "x.B"), entry("a", "x.A"))
    assert list(found) == ["x.A", "x.B"]


def test_two_sources_for_one_record_type_are_refused() -> None:
    with pytest.raises(FormSourceLoadError, match="twice"):
        load(entry("a", "x.A"), entry("b", "x.A"))


def test_a_source_that_does_not_satisfy_the_protocol_is_refused() -> None:
    with pytest.raises(FormSourceLoadError, match="FormSource"):
        load(Entry("a", lambda: object()))


def test_a_plugin_that_fails_to_load_names_the_type_only() -> None:
    def boom() -> Any:
        raise RuntimeError("secret detail")

    with pytest.raises(FormSourceLoadError) as info:
        load(Entry("a", boom))
    assert "RuntimeError" in str(info.value) and "secret" not in str(info.value)


def test_more_than_the_maximum_sources_is_refused() -> None:
    many = [entry(f"p{i:02}", f"x.T{i}") for i in range(MAX_SOURCES)]
    assert len(load(*many)) == MAX_SOURCES
    with pytest.raises(FormSourceLoadError, match="more than"):
        load(*many, entry("zz", "x.Extra"))


def test_the_default_group_is_read_from_the_entry_points() -> None:
    assert isinstance(load_form_sources(), dict)


def test_modules_import_no_web_cli_mcp_or_module_code() -> None:
    forbidden = ("tl_web", "tl_cli", "tl_mcp", "tl_api", "tl_tui", "tl_mod_")
    for mod in (types, rules, registry):
        tree = ast.parse(Path(str(mod.__file__)).read_text())
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                assert not name.startswith(forbidden), (mod.__name__, name)


def test_a_fresh_import_loads_no_forbidden_package() -> None:
    code = (
        "import sys, tl_core.forms, tl_core.forms.types, tl_core.forms.rules;"
        "import tl_core.forms.registry;"
        "bad=[m for m in sys.modules if m.split('.')[0] in "
        "('tl_api','tl_cli','tl_mcp','tl_tui','tl_web') or m.startswith('tl_mod_')];"
        "print(bad); sys.exit(1 if bad else 0)"
    )
    done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
