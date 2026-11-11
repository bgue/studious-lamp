"""``TL_ENV`` classes (ADR-0009 section 9): dev tokens, the demo account and ``prod_like``."""

from __future__ import annotations

import pytest
from tl_core.auth.env import demo_allowed, dev_tokens_allowed, prod_like


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("prod", True),
        ("production", True),
        ("staging", True),
        (" PROD ", True),
        ("anything", True),
        ("dev", False),
        ("test", False),
        ("ci", False),
        ("demo", False),
        ("DEV", False),
        ("", False),
        ("   ", False),
    ],
)
def test_prod_like_is_true_for_a_set_name_that_is_not_a_dev_or_demo_name(
    value: str, expected: bool
) -> None:
    assert prod_like({"TL_ENV": value}) is expected
    assert prod_like(value) is expected


def test_prod_like_is_false_when_the_variable_is_unset() -> None:
    assert prod_like({}) is False


def test_prod_like_is_never_true_where_dev_tokens_or_the_demo_account_are_allowed() -> None:
    for name in ("dev", "test", "ci", "demo", "prod", "staging", ""):
        if dev_tokens_allowed(name) or demo_allowed(name):
            assert not prod_like(name)
