"""The fine access words (wave0.md section 2): 22 words, each naming a table word."""

from __future__ import annotations

from pathlib import Path

import pytest
from tl_core.auth.access_words import (
    DEFAULT_ACCESS_WORDS_FILE,
    TABLE_WORDS,
    AccessWordError,
    load_access_words,
    parse_access_words,
    table_word,
)

#: Every word of specs/m3-wbs-cwp.md section 3 (`awp.rollup` there is a job kind, not a word).
AWP = {
    "awp.view": "read",
    "awp.wbs.configure": "controller",
    "awp.path.configure": "controller",
    "awp.cwa.edit": "user",
    "awp.cwp.edit": "user",
    "awp.cwp.release": "controller",
    "awp.cwp.close": "controller",
    "awp.void": "controller",
    "awp.package.edit": "user",
}
#: The words of the IWP commands (P2-I2 S2, S3).
AWP_IWP = {
    "awp.iwp.edit": "user",
    # P2-I2 S3: sign-off, issue and hold
    "awp.iwp.signoff": "controller",
    "awp.iwp.issue": "controller",
    "awp.iwp.hold": "controller",
}
#: The two words of the core constraint (ADR-0024); `awp.constraint.edit` is gone.
CORE_CONSTRAINT = {"core.constraint.edit": "user", "core.constraint.view": "read"}
#: Every word of specs/m4-materials.md section 3.
MATERIALS = {
    "materials.view": "read",
    "materials.library.edit": "controller",
    "materials.item.adopt": "user",
    "materials.location.configure": "controller",
    "materials.po.edit": "user",
    "materials.receive": "user",
    "materials.receipt.decide": "user",
    "materials.void": "controller",
    "materials.move": "user",
    "materials.reserve": "user",
    "materials.adjust": "controller",
    "materials.mto.publish": "controller",
    "materials.mto.assign": "user",
}
#: The seven words of the punch list (P2-PUNCH S1); an assignment is an edit (no assign word).
QUALITY = {
    "quality.view": "read",
    "quality.punch.raise": "user",
    "quality.punch.edit": "user",
    "quality.punch.clear": "user",
    "quality.punch.verify": "controller",
    "quality.punch.reopen": "controller",
    "quality.punch.void": "controller",
}
GOOD = "version: 1\nwords:\n  awp.view: read\n  awp.cwp.edit: user\n"


def test_the_shipped_table_loads_35_words() -> None:
    words = load_access_words()
    assert (
        len(words)
        == 35
        == len(AWP) + len(AWP_IWP) + len(CORE_CONSTRAINT) + len(MATERIALS) + len(QUALITY)
    )
    assert "awp.constraint.edit" not in words


def test_every_word_of_the_two_module_specs_is_present_with_its_table_word() -> None:
    words = load_access_words()
    for word, table in {**AWP, **AWP_IWP, **CORE_CONSTRAINT, **MATERIALS, **QUALITY}.items():
        assert words.get(word) == table, word


def test_every_word_names_one_of_the_three_table_words() -> None:
    assert TABLE_WORDS == ("read", "user", "controller")
    assert set(load_access_words().values()) <= set(TABLE_WORDS)


def test_table_word_maps_fine_words_and_returns_a_table_word_unchanged() -> None:
    assert table_word("awp.cwp.release") == "controller"
    assert table_word("awp.view") == "read"
    assert table_word("materials.receive") == "user"
    for word in TABLE_WORDS:
        assert table_word(word) == word


def test_an_unknown_word_is_refused_fail_closed() -> None:
    for word in ("awp.cwp.teleport", "approve", ""):
        with pytest.raises(AccessWordError):
            table_word(word)


def test_the_loaded_table_is_read_only() -> None:
    with pytest.raises(TypeError):
        load_access_words()["awp.view"] = "controller"  # type: ignore[index]


def test_an_unknown_table_word_raises() -> None:
    with pytest.raises(AccessWordError, match="not one of"):
        parse_access_words("version: 1\nwords:\n  awp.view: approve\n")


def test_a_duplicate_word_raises() -> None:
    with pytest.raises(AccessWordError, match="twice"):
        parse_access_words("version: 1\nwords:\n  awp.view: read\n  awp.view: user\n")


@pytest.mark.parametrize(
    "text",
    [
        "version: 2\nwords:\n  awp.view: read\n",
        "version: 1\nwords: {}\n",
        "version: 1\nwords:\n  awp.view: read\nextra: 1\n",
        "version: 1\nwords:\n  AWP.View: read\n",
        "version: 1\nwords:\n  view: read\n",
        "version: 1\nwords:\n  user: user\n",
        "- a\n- list\n",
        "version: [unclosed",
    ],
)
def test_a_file_of_another_shape_raises(text: str) -> None:
    with pytest.raises(AccessWordError):
        parse_access_words(text)


def test_a_good_text_parses_and_a_file_path_loads(tmp_path: Path) -> None:
    assert dict(parse_access_words(GOOD)) == {"awp.view": "read", "awp.cwp.edit": "user"}
    path = tmp_path / "words.yaml"
    path.write_text(GOOD, encoding="utf-8")
    assert load_access_words(path) == parse_access_words(GOOD)


def test_a_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(AccessWordError, match="cannot read"):
        load_access_words(tmp_path / "missing.yaml")


def test_the_default_file_is_the_one_under_schema_settings() -> None:
    assert DEFAULT_ACCESS_WORDS_FILE.parts[-3:] == ("schema", "settings", "access-words.yaml")
