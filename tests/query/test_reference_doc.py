"""The query-language reference page: examples must parse and errors must be real (P0-I4-T03)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from tl_core.query import QuerySyntaxError, parse
from tl_core.query.fields import ENVELOPE_FIELDS

DOC = Path(__file__).resolve().parents[2] / "docs" / "reference" / "query-language.md"
ERROR_MARK = re.compile(r"^(?P<query>.*?)\s+# position (?P<position>\d+)$")


def fenced(tag: str) -> list[str]:
    """Every non-blank line inside fenced blocks that open with ```<tag>."""
    lines: list[str] = []
    inside = False
    for line in DOC.read_text(encoding="utf-8").splitlines():
        if line.strip() == f"```{tag}":
            inside = True
        elif line.strip() == "```":
            inside = False
        elif inside and line.strip():
            lines.append(line.rstrip())
    return lines


def test_the_page_exists_and_opens_with_its_purpose() -> None:
    first = next(line for line in DOC.read_text(encoding="utf-8").splitlines() if line.strip())
    assert first.startswith("# ")
    assert "query" in first.lower()


def test_the_page_has_the_required_sections() -> None:
    headings = {
        line[3:].strip().lower()
        for line in DOC.read_text(encoding="utf-8").splitlines()
        if line.startswith("## ")
    }
    required = {"fields", "operators", "values", "boolean logic", "links", "dates", "errors"}
    assert required <= headings, f"missing sections: {sorted(required - headings)}"


def test_there_are_enough_runnable_examples() -> None:
    assert len(fenced("query")) >= 30
    assert len(fenced("query-error")) >= 8


@pytest.mark.parametrize("line", fenced("query"))
def test_every_query_example_parses(line: str) -> None:
    assert parse(line) is not None, line


@pytest.mark.parametrize("line", fenced("query-error"))
def test_every_error_example_fails_at_the_stated_position(line: str) -> None:
    match = ERROR_MARK.match(line)
    assert match is not None, f"write error examples as '<query>  # position <n>': {line!r}"
    with pytest.raises(QuerySyntaxError) as info:
        parse(match["query"])
    assert info.value.position == int(match["position"]), line


def test_every_envelope_field_is_in_the_fields_table() -> None:
    text = DOC.read_text(encoding="utf-8")
    missing = [name for name in ENVELOPE_FIELDS if f"`{name}`" not in text]
    assert not missing, f"fields not documented: {missing}"


@pytest.mark.parametrize("operator", [":", "=", "!=", "~", "<", "<=", ">", ">="])
def test_every_operator_is_documented(operator: str) -> None:
    assert f"`{operator}`" in DOC.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "term", ["linked", "count(", "missing(", "OR", "NOT", "today", "+7d", "psets."]
)
def test_the_main_terms_are_documented(term: str) -> None:
    assert term in DOC.read_text(encoding="utf-8")


def test_the_page_names_no_model_and_leaves_no_placeholders() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    for banned in ("claude", "sonnet", "haiku", "opus", "todo", "tbd", "<fill"):
        assert banned not in text, banned
