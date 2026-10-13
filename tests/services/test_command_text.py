"""A NUL in any text of a command is a validation error, not a crash in the database driver."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError
from tl_core.services.commands import CreateRecord, contains_nul

BASE: dict[str, Any] = {"actor": "user:u", "source": "test", "scope": "project:P123"}


@pytest.mark.parametrize(
    "fields",
    [
        {"title": "a\x00b"},
        {"title": "t", "description": "x\x00"},
        {"title": "t", "key": "K\x00"},
        {"title": "t", "psets": {"p": {"v": ["ok", "bad\x00"]}}},
        {"title": "t", "psets": {"p\x00": {"v": 1}}},
        {"title": "t", "numbering": {"discipline": "P\x00"}},
    ],
)
def test_a_nul_anywhere_in_a_command_is_refused(fields: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="NUL"):
        CreateRecord(**BASE, record_type="core.Record", **fields)


def test_text_without_a_nul_is_untouched() -> None:
    made = CreateRecord(
        **BASE, record_type="core.Record", title="Valve\ttag\nline", psets={"p": {"v": [1, "x"]}}
    )
    assert made.title == "Valve\ttag\nline"
    assert not contains_nul({"a": [1, 2.5, None, True, ("x", "y")]})
