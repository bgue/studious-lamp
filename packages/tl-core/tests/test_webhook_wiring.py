"""Environment wiring: the egress allow-list and the constructors."""

from __future__ import annotations

import pytest
from tl_core.webhooks.wiring import ALLOWLIST_ENV, allowlist_from

PORTS = " a.test , b.test:8080 ,10.0.0.0/8"
CASES = [
    ({}, (), ()),
    ({ALLOWLIST_ENV: ""}, (), ()),
    ({ALLOWLIST_ENV: " , ,"}, (), ()),
    ({ALLOWLIST_ENV: "localhost"}, (), ("localhost",)),
    ({ALLOWLIST_ENV: PORTS}, (), ("a.test", "b.test:8080", "10.0.0.0/8")),
    (
        {ALLOWLIST_ENV: "a.test,a.test, b.test"},
        ("b.test", "c.test"),
        ("b.test", "c.test", "a.test"),
    ),
    ({}, ("x.test",), ("x.test",)),
]


@pytest.mark.parametrize(("env", "extra", "expected"), CASES)
def test_allowlist_is_stripped_deduplicated_and_empty_means_empty(
    env: dict[str, str], extra: tuple[str, ...], expected: tuple[str, ...]
) -> None:
    assert allowlist_from(extra, env) == expected


def test_the_process_environment_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ALLOWLIST_ENV, "env.test")
    assert allowlist_from() == ("env.test",)
    monkeypatch.delenv(ALLOWLIST_ENV)
    assert allowlist_from() == ()
