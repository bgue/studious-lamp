"""The module role table (roles-mvp.md section 2): loaded whole, checked whole, fail closed."""

from __future__ import annotations

from pathlib import Path

import pytest
from tl_core.auth.errors import RoleTableError
from tl_core.auth.module_roles import (
    DEFAULT_ROLE_TABLE_FILE,
    PLATFORM_WORDS,
    RoleTable,
    load_role_table,
    parse_role_table,
)

TEXT = DEFAULT_ROLE_TABLE_FILE.read_text(encoding="utf-8")


def bad_copy(tmp_path: Path, old: str, new: str) -> Path:
    assert old in TEXT, old
    path = tmp_path / "module-roles.yaml"
    path.write_text(TEXT.replace(old, new, 1), encoding="utf-8")
    return path


def test_the_shipped_table_has_three_roles_three_words_and_two_agent_roles() -> None:
    table = load_role_table()
    assert isinstance(table, RoleTable)
    assert list(table.roles) == ["viewer", "user", "superuser"]
    assert set(table.words) == {"read", "user", "controller"}
    assert table.roles["viewer"] == ("read",)
    assert table.roles["user"] == ("read", "user")
    assert table.roles["superuser"] == ("read", "user", "controller")
    assert table.agent_roles == ("viewer", "user")


def test_the_platform_words_are_not_in_the_table() -> None:
    assert PLATFORM_WORDS == {"admin", "company"}
    assert not set(load_role_table().words) & PLATFORM_WORDS


def test_the_table_is_read_once_per_process() -> None:
    assert load_role_table() is load_role_table()


def test_a_path_reads_that_file_and_is_not_cached(tmp_path: Path) -> None:
    path = tmp_path / "copy.yaml"
    path.write_text(TEXT, encoding="utf-8")
    first, second = load_role_table(path), load_role_table(path)
    assert first == load_role_table() and first is not second


def test_the_words_of_a_set_of_roles_are_their_union() -> None:
    table = load_role_table()
    assert table.words_of(frozenset({"viewer"})) == {"read"}
    assert table.words_of(frozenset({"viewer", "superuser"})) == {"read", "user", "controller"}
    assert table.words_of(frozenset({"no_such_role"})) == frozenset()


def test_the_derive_block_gives_a_document_controller_the_three_controlled_modules() -> None:
    derive = load_role_table().derive
    assert ("*", "user") in derive["user"]
    superuser = {m for m, r in derive["document_controller"] if r == "superuser"}
    assert superuser == {"documents", "correspondence", "schedule"}


@pytest.mark.parametrize(
    ("old", "new", "why"),
    [
        ("superuser: [read, user, controller]", "superuser: [read, user, approve]", "unknown word"),
        ("- {module: documents, role: superuser}", "- {module: documents, role: boss}", "role"),
        ("  document_controller:\n", "  site_manager:\n", "account role"),
        ("agent_roles: [viewer, user]", "agent_roles: [viewer, boss]", "agent role"),
        ("  read: Read", "  admin: Read", "platform word admin"),
        ("  read: Read", "  company: Read", "platform word company"),
        ("version: 1", "version: 2", "version"),
        ("version: 1", "version: 1\nextra: 1", "unknown top-level key"),
        ("- {module: documents, role", "- {module: Documents, role", "unusable module name"),
        ("- {module: documents, role", "- {modul: documents, role", "entry shape"),
    ],
)
def test_a_bad_table_is_a_role_table_error(tmp_path: Path, old: str, new: str, why: str) -> None:
    with pytest.raises(RoleTableError):
        load_role_table(bad_copy(tmp_path, old, new))


def test_an_unknown_word_in_a_role_fails_closed_in_parse() -> None:
    data = {
        "version": 1,
        "words": {"read": "r"},
        "roles": {"viewer": ["read", "write"]},
        "agent_roles": ["viewer"],
        "derive": {},
    }
    with pytest.raises(RoleTableError, match="unknown word write"):
        parse_role_table(data)
    data["roles"] = {"viewer": ["read"]}
    assert parse_role_table(data).roles == {"viewer": ("read",)}


def test_a_file_that_is_not_there_or_not_yaml_is_a_role_table_error(tmp_path: Path) -> None:
    with pytest.raises(RoleTableError):
        load_role_table(tmp_path / "missing.yaml")
    broken = tmp_path / "broken.yaml"
    broken.write_text("a: [unclosed", encoding="utf-8")
    with pytest.raises(RoleTableError):
        load_role_table(broken)


def test_an_empty_roles_block_and_a_non_mapping_file_are_refused() -> None:
    with pytest.raises(RoleTableError):
        parse_role_table(["not", "a", "mapping"])
    with pytest.raises(RoleTableError, match="roles is empty"):
        parse_role_table(
            {"version": 1, "words": {"read": "r"}, "roles": {}, "agent_roles": [], "derive": {}}
        )
