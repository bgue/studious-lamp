"""The shared check for text with control or text-direction characters."""

from __future__ import annotations

import pytest
from tl_core.text import (
    FORBIDDEN_TEXT,
    MESSAGE,
    clean_optional_text,
    clean_text,
    has_forbidden_text,
)

FORBIDDEN = [
    *(chr(c) for c in range(0x00, 0x20)),  # C0, tab and newline included
    *(chr(c) for c in range(0x7F, 0xA0)),  # DEL and C1 (U+0085 NEL among them)
    chr(0x061C),
    chr(0x200E),
    chr(0x200F),
    chr(0x2028),
    chr(0x2029),
    *(chr(c) for c in range(0x202A, 0x202F)),
    *(chr(c) for c in range(0x2066, 0x206A)),
    chr(0xFEFF),
]


@pytest.mark.parametrize("char", FORBIDDEN, ids=[f"U+{ord(c):04X}" for c in FORBIDDEN])
def test_every_forbidden_character_is_refused_anywhere_in_the_text(char: str) -> None:
    for text in (char, f"a{char}", f"{char}a", f"ab{char}cd"):
        with pytest.raises(ValueError, match="control"):
            clean_text(text)
        assert has_forbidden_text(text)


def test_the_message_does_not_repeat_the_value() -> None:
    with pytest.raises(ValueError) as caught:
        clean_text("secret" + chr(0x202E) + "text")
    assert str(caught.value) == MESSAGE and "secret" not in str(caught.value)


@pytest.mark.parametrize(
    "text",
    ["", "4210-PIP", "Pipe installation (revised)", "café", "€ 100", "مرحبا", "a b", " ", "​", "‐"],
)
def test_ordinary_text_and_other_scripts_pass_unchanged(text: str) -> None:
    assert clean_text(text) == text and not has_forbidden_text(text)


def test_the_optional_form_lets_none_through() -> None:
    assert clean_optional_text(None) is None
    assert clean_optional_text("ok") == "ok"
    with pytest.raises(ValueError):
        clean_optional_text("a\nb")


def test_the_pattern_covers_exactly_the_listed_characters() -> None:
    found = [c for c in map(chr, range(0x3000)) if FORBIDDEN_TEXT.search(c)]
    assert sorted(found) == sorted(set(c for c in FORBIDDEN if ord(c) < 0x3000))
