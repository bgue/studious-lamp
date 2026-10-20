"""Package text from a person: no aliases, no anchors, bounded, single-value defaults."""

from __future__ import annotations

import time

import pytest
import yaml
from tl_schema.plain_yaml import MAX_NODES, PlainYamlError, load_plain
from tl_schema.registry import PackageError, parse_package

PACKAGE = """
package: co.acme.x
version: 1.0.0
kind: company
description: A package.
psets:
  p:
    label: P
    description: A pset.
    applies_to: [core.Record]
    properties:
      q:
        label: Q
        description: A property.
        range: string
        default: %s
"""


def bomb(levels: int = 9, width: int = 9) -> str:
    """About 700 bytes that stand for width ** levels nodes once the aliases are followed."""
    lines = ["l0: &l0 [x, x, x, x, x, x, x, x, x]"]
    for n in range(1, levels):
        refs = ", ".join(f"*l{n - 1}" for _ in range(width))
        lines.append(f"l{n}: &l{n} [{refs}]")
    return "\n".join(lines)


def test_an_alias_bomb_is_refused_at_once_and_does_not_hang() -> None:
    text = bomb()
    assert len(text.encode()) < 1000
    started = time.perf_counter()
    with pytest.raises(PlainYamlError, match="aliases|anchors"):
        load_plain(text)
    assert time.perf_counter() - started < 1.0


def test_a_package_that_is_a_bomb_is_a_package_error_in_under_a_second() -> None:
    text = PACKAGE % "&d [x]" + "\nextra: " + bomb().replace("\n", "\n  ")
    started = time.perf_counter()
    with pytest.raises(PackageError, match="invalid YAML"):
        parse_package(text, source="package")
    assert time.perf_counter() - started < 1.0


def test_an_anchor_alone_and_an_alias_alone_are_refused() -> None:
    with pytest.raises(PlainYamlError, match="anchors"):
        load_plain("a: &x 1\n")
    with pytest.raises(PlainYamlError, match="aliases"):
        load_plain("a: *x\n")
    with pytest.raises(PlainYamlError, match="aliases"):
        load_plain("a: {<<: *x}\n")


def test_ordinary_yaml_is_read_as_safe_load_reads_it() -> None:
    text = "a: 1\nb: [x, 'y', 2.5, true, null]\nc:\n  d: text\n"
    assert load_plain(text) == yaml.safe_load(text)


def test_a_document_with_too_many_nodes_is_refused() -> None:
    text = "[" + ",".join("1" for _ in range(MAX_NODES + 1)) + "]"
    with pytest.raises(PlainYamlError, match="more than"):
        load_plain(text)


def test_very_deep_nesting_is_refused_not_a_crash() -> None:
    with pytest.raises(yaml.YAMLError):
        load_plain("[" * 5000 + "]" * 5000)


def test_a_syntax_error_names_the_line_and_not_the_text() -> None:
    with pytest.raises(PackageError) as raised:
        parse_package("a: [unclosed secret-value\nb: 1\n", source="package")
    message = str(raised.value)
    assert "line" in message and "secret-value" not in message


def test_a_default_is_one_value() -> None:
    parse_package(PACKAGE % "plain", source="package")
    for bad in ("[a, b]", "{k: v}"):
        with pytest.raises(PackageError, match="single value"):
            parse_package(PACKAGE % bad, source="package")


def test_the_message_for_a_default_that_does_not_fit_has_no_value() -> None:
    from tl_schema.compile import SchemaCompileError
    from tl_schema.compose import compose

    doc = parse_package(
        (PACKAGE % "topsecret").replace("range: string", "range: integer"), source="package"
    )
    with pytest.raises(SchemaCompileError) as raised:
        compose([doc], "company")
    assert "topsecret" not in str(raised.value)
