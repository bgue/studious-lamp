"""Status and refusal lines of the schema review name a package in words (P1-UX-S4)."""

from __future__ import annotations

from tl_tui.schema_review_text import plain_message


def test_a_package_reference_in_a_message_reads_in_words() -> None:
    text = "co.acme.engineering@4.0.0 makes changes that are not allowed in place: size_in"
    assert plain_message(text) == (
        "Engineering, version 4.0.0 makes changes that are not allowed in place: size_in"
    )


def test_technical_mode_keeps_the_message_as_it_came() -> None:
    text = "co.acme.engineering@4.0.0 makes changes that are not allowed in place"
    assert plain_message(text, technical=True) == text


def test_every_reference_is_rewritten_and_other_text_is_left_alone() -> None:
    text = "Base x.P123@1.0.0 and co.acme.engineering@3.3.0; mail a@b.example, v2.0, 3.3.0"
    assert plain_message(text) == (
        "Base P123, version 1.0.0 and Engineering, version 3.3.0; mail a@b.example, v2.0, 3.3.0"
    )


def test_a_longer_version_or_a_suffix_is_not_a_package_reference() -> None:
    text = "see pkg@1.2.3.4 and pkg@1.2.3x"
    assert plain_message(text) == text
