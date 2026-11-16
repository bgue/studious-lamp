"""Scan codes: the module takes its code functions from ``tl_core.qr.codes`` and defines none."""

from __future__ import annotations

import hashlib

import pytest
from tl_core.qr import codes as core
from tl_mod_qr import codes


def test_the_module_defines_no_code_function_of_its_own() -> None:
    assert codes.new_code is core.new_code
    assert codes.normalise_code is core.normalise_code
    assert codes.code_hash is core.code_hash
    assert codes.grouped is core.grouped


def test_a_code_is_sixteen_symbols_of_the_alphabet() -> None:
    code = codes.new_code()
    assert len(code) == 16
    assert set(code) <= set(core.ALPHABET)
    assert len(set(core.ALPHABET)) == 32


def test_ten_thousand_codes_are_distinct() -> None:
    assert len({codes.new_code() for _ in range(10_000)}) == 10_000


def test_normalise_round_trips_the_printed_form() -> None:
    code = codes.new_code()
    printed = codes.grouped(code)
    assert printed.count("-") == 3 and all(len(g) == 4 for g in printed.split("-"))
    assert codes.normalise_code(printed) == code
    assert codes.normalise_code(printed.lower().replace("-", " ")) == code


@pytest.mark.parametrize(
    "text",
    [
        "",
        "ABC",
        "A" * 15,
        "A" * 17,
        "ABCDEFGHJKLMNPQ0",
        "ABCDEFGHJKLMNPQI",
        "ABCDEFGHJKLMNPQ!",
        "é" * 16,
    ],
)
def test_normalise_refuses_what_is_not_a_code(text: str) -> None:
    assert codes.normalise_code(text) is None


def test_the_hash_is_sha256_of_the_normalised_code() -> None:
    code = codes.new_code()
    expected = hashlib.sha256(code.encode()).hexdigest()
    assert codes.code_hash(code) == codes.code_hash(codes.grouped(code).lower()) == expected


def test_the_hash_of_a_non_code_is_refused_without_its_text() -> None:
    with pytest.raises(ValueError) as caught:
        codes.code_hash("SECRETTEXT")
    assert "SECRETTEXT" not in str(caught.value)
