"""Marks and decisions of the six isolation and gas test commands (safety acts, like D10)."""

from __future__ import annotations

import tomllib
from pathlib import Path

from tl_mod_permits.module import COMMANDS, PROPOSABLE, spec

EXCLUSIONS = Path(__file__).resolve().parents[4] / "tests" / "tools" / "proposable_exclusions.toml"
SIX = {
    "ApplyIsolation": "permits.isolation.apply",
    "VerifyIsolation": "permits.isolation.verify",
    "RemoveIsolation": "permits.isolation.apply",
    "LinkIsolation": "permits.isolation.apply",
    "UnlinkIsolation": "permits.isolation.apply",
    "RecordGasTest": "permits.gastest.record",
}


def test_the_six_rows_are_excluded_reserved_in_their_meta() -> None:
    rows = {c.model.__name__: c for c in COMMANDS}
    assert set(SIX) <= set(rows) and len(COMMANDS) == 16
    for name in SIX:
        assert rows[name].meta == {"delegation": "excluded:reserved"}, name


def test_each_row_carries_its_table_word_and_the_spec_follows() -> None:
    assert {c.model.__name__: c.access for c in COMMANDS if c.model.__name__ in SIX} == SIX
    words = dict(spec().command_words)
    assert {name: words[name] for name in SIX} == SIX


def test_the_six_are_in_the_exclusions_file_with_a_reason_and_have_no_agent_row() -> None:
    listed = tomllib.loads(EXCLUSIONS.read_text(encoding="utf-8"))["commands"]
    for name in SIX:
        assert name in listed and listed[name].strip(), name
    assert [p.model.__name__ for p in PROPOSABLE] == ["RequestPermit"]
    assert not {p.model.__name__ for p in PROPOSABLE} & set(SIX)


def test_the_six_are_hooked_from_the_modules_own_package() -> None:
    for command in COMMANDS:
        assert command.handler.__module__.startswith("tl_mod_permits.handlers.")
        assert command.model.__module__.startswith("tl_mod_permits.")
    assert {c.model.__module__ for c in COMMANDS if c.model.__name__ in SIX} == {
        "tl_mod_permits.iso_commands"
    }


def test_an_agent_token_is_refused_every_one_of_the_six_by_the_common_path() -> None:
    import pytest
    from tl_api.auth import AGENT_DIRECT_COMMANDS, AGENT_MUST_PROPOSE, refuse_agent_writes
    from tl_api.errors import ApiError

    assert not set(SIX) & AGENT_DIRECT_COMMANDS
    with pytest.raises(ApiError) as caught:
        refuse_agent_writes("agent:bot")
    assert caught.value.status == 403 and caught.value.error == AGENT_MUST_PROPOSE
    refuse_agent_writes("user:uma")
