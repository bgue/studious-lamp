"""The code functions of ``tl_core.qr.codes`` (P2-FORMS S7c, D15)."""

from __future__ import annotations

import hashlib
import re

import pytest
from tl_core.qr import codes
from tl_core.qr.codes import ALPHABET, CODE_LENGTH, code_hash, grouped, new_code, normalise_code

PLAIN = "7KQ2M9XA4TTCP9HV"


def test_the_alphabet_has_32_symbols_and_none_of_i_o_0_1() -> None:
    assert len(ALPHABET) == len(set(ALPHABET)) == 32
    assert not set("IO01") & set(ALPHABET)
    assert CODE_LENGTH == 16


def test_a_new_code_has_16_symbols_of_the_alphabet_and_1000_draws_differ() -> None:
    draws = [new_code() for _ in range(1000)]
    assert all(len(c) == 16 and set(c) <= set(ALPHABET) for c in draws)
    assert len(set(draws)) == 1000


@pytest.mark.parametrize(
    "text",
    [
        PLAIN,
        "7kq2-m9xa-4ttc-p9hv",
        " 7KQ2 M9XA 4TTC P9HV ",
        "7kq2m9xa4ttcp9hv",
        "7KQ2-M9XA 4ttc-P9HV",
    ],
)
def test_normalise_accepts_spaces_hyphens_and_lower_case(text: str) -> None:
    assert normalise_code(text) == PLAIN


@pytest.mark.parametrize(
    "text",
    [
        "",
        PLAIN[:15],
        PLAIN + "A",
        "7KQ2M9XA4TTCP9H0",
        "7KQ2M9XA4TTCP9HI",
        "7KQ2M9XA4TTCP9H!",
        "é" * 16,
    ],
)
def test_normalise_refuses_a_wrong_length_or_a_symbol_outside_the_alphabet(text: str) -> None:
    assert normalise_code(text) is None


@pytest.mark.parametrize("value", [None, 7, b"7KQ2M9XA4TTCP9HV", ["7KQ2M9XA4TTCP9HV"]])
def test_normalise_refuses_what_is_not_text(value: object) -> None:
    assert normalise_code(value) is None  # pyright: ignore[reportArgumentType]


def test_code_hash_is_sha256_of_the_normalised_code_whatever_the_spelling() -> None:
    expected = hashlib.sha256(PLAIN.encode()).hexdigest()
    assert code_hash(PLAIN) == code_hash("7kq2-m9xa-4ttc-p9hv") == expected
    assert re.fullmatch(r"[0-9a-f]{64}", expected)


def test_code_hash_refuses_a_non_code_without_repeating_it() -> None:
    with pytest.raises(ValueError) as caught:
        code_hash("secret-looking-text")
    assert "secret" not in str(caught.value)
    with pytest.raises(ValueError):
        grouped("short")


def test_grouped_is_four_groups_of_four_and_round_trips() -> None:
    assert grouped(PLAIN) == "7KQ2-M9XA-4TTC-P9HV"
    for _ in range(50):
        code = new_code()
        shown = grouped(code)
        assert re.fullmatch(r"([A-Z2-9]{4}-){3}[A-Z2-9]{4}", shown)
        assert normalise_code(shown) == code
        assert code_hash(shown) == code_hash(code)


def test_the_module_imports_only_the_standard_library() -> None:
    import ast
    import inspect

    names: set[str] = set()
    for node in ast.walk(ast.parse(inspect.getsource(codes))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    assert names == {"__future__", "hashlib", "re", "secrets"}
