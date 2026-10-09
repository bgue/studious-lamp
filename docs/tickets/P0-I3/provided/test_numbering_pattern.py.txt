"""Numbering pattern parser (P0-I3-T05; brief 8)."""

from __future__ import annotations

import pytest
from tl_core.numbering.pattern import ParsedKey, PatternError, Segment, parse_pattern

STANDARD = "{project}-{type}-{seq:4}"


def test_parses_the_standard_pattern_into_segments() -> None:
    pattern = parse_pattern(STANDARD)
    assert pattern.template == STANDARD
    assert pattern.segments == (
        Segment("field", "project"),
        Segment("literal", "-"),
        Segment("field", "type"),
        Segment("literal", "-"),
        Segment("seq", "", 4),
    )
    assert pattern.fields == ("project", "type")
    assert pattern.seq_width == 4


def test_parses_the_brief_pattern_with_a_discipline() -> None:
    pattern = parse_pattern("{project}-{type}-{discipline}-{seq:4}")
    assert pattern.fields == ("project", "type", "discipline")


def test_literal_prefix_and_suffix_are_kept() -> None:
    pattern = parse_pattern("NCR/{project}/{seq:3}-X")
    assert [s.kind for s in pattern.segments] == ["literal", "field", "literal", "seq", "literal"]
    assert pattern.segments[0].text == "NCR/"
    assert pattern.segments[-1].text == "-X"


def test_seq_without_a_width_means_no_padding() -> None:
    pattern = parse_pattern("DOC-{seq}")
    assert pattern.seq_width == 0
    assert pattern.render({}, 7) == "DOC-7"


def test_render_pads_the_sequence() -> None:
    pattern = parse_pattern(STANDARD)
    assert pattern.render({"project": "P123", "type": "REC"}, 1) == "P123-REC-0001"
    assert pattern.render({"project": "P123", "type": "REC"}, 42) == "P123-REC-0042"


def test_render_writes_a_long_sequence_in_full() -> None:
    pattern = parse_pattern("{project}-{seq:2}")
    assert pattern.render({"project": "P1"}, 123) == "P1-123"


def test_render_ignores_extra_values() -> None:
    pattern = parse_pattern("{project}-{seq:2}")
    assert pattern.render({"project": "P1", "other": "zzz"}, 3) == "P1-03"


def test_render_rejects_a_missing_field() -> None:
    with pytest.raises(PatternError, match="no value for field 'type'"):
        parse_pattern(STANDARD).render({"project": "P123"}, 1)


@pytest.mark.parametrize("bad", ["", "P 1", "P-1", "P.1", "P/1", "é"])
def test_render_rejects_a_value_that_is_not_letters_and_digits(bad: str) -> None:
    with pytest.raises(PatternError, match="letters and digits"):
        parse_pattern(STANDARD).render({"project": bad, "type": "REC"}, 1)


@pytest.mark.parametrize("sequence", [0, -1])
def test_render_rejects_a_sequence_below_one(sequence: int) -> None:
    with pytest.raises(PatternError, match="at least 1"):
        parse_pattern(STANDARD).render({"project": "P123", "type": "REC"}, sequence)


def test_prefix_is_the_key_without_the_sequence() -> None:
    pattern = parse_pattern(STANDARD)
    assert pattern.prefix({"project": "P123", "type": "REC"}) == "P123-REC-"


def test_prefix_of_a_pattern_with_a_suffix() -> None:
    pattern = parse_pattern("{project}-{seq:3}-X")
    assert pattern.prefix({"project": "P1"}) == "P1--X"


def test_prefix_rejects_a_missing_field() -> None:
    with pytest.raises(PatternError, match="no value for field"):
        parse_pattern(STANDARD).prefix({"project": "P123"})


def test_parse_reads_a_key_back() -> None:
    parsed = parse_pattern(STANDARD).parse("P123-REC-0042")
    assert parsed == ParsedKey(fields={"project": "P123", "type": "REC"}, sequence=42)


def test_parse_round_trips_render() -> None:
    pattern = parse_pattern("{project}-{type}-{discipline}-{seq:4}")
    values = {"project": "P123", "type": "NCR", "discipline": "PIP"}
    for sequence in (1, 9, 10, 9999, 10000, 123456):
        parsed = pattern.parse(pattern.render(values, sequence))
        assert parsed == ParsedKey(fields=values, sequence=sequence)


@pytest.mark.parametrize(
    "key",
    [
        "",
        "P123-REC",
        "P123-REC-",
        "P123-REC-12",
        "P123-REC-0000",
        "P123-REC-00a1",
        "x P123-REC-0001",
    ],
)
def test_parse_returns_none_for_a_key_that_does_not_fit(key: str) -> None:
    assert parse_pattern(STANDARD).parse(key) is None


def test_parse_requires_the_whole_key() -> None:
    pattern = parse_pattern(STANDARD)
    assert pattern.parse("P123-REC-0001 ") is None
    assert pattern.parse("P123-REC-0001x") is None


def test_regex_has_named_groups() -> None:
    match = parse_pattern(STANDARD).regex().fullmatch("P123-REC-0042")
    assert match is not None
    assert match.group("project") == "P123"
    assert match.group("type") == "REC"
    assert match.group("seq") == "0042"


def test_literal_text_is_escaped_in_the_regex() -> None:
    pattern = parse_pattern("A.B+{seq:2}")
    assert pattern.parse("A.B+07") is not None
    assert pattern.parse("AxB+07") is None


def test_search_regex_finds_keys_in_text() -> None:
    regex = parse_pattern(STANDARD).search_regex()
    text = "See P123-REC-0001, and (P123-REC-0002) but not x-P123-REC-0003 or P123-REC-00044x."
    found = [m.group(0) for m in regex.finditer(text)]
    assert found == ["P123-REC-0001", "P123-REC-0002"]


def test_search_regex_does_not_match_inside_a_longer_dashed_token() -> None:
    regex = parse_pattern(STANDARD).search_regex()
    assert regex.search("pre-P123-REC-0001") is None
    assert regex.search("P123-REC-0001.") is not None


@pytest.mark.parametrize(
    ("template", "message"),
    [
        ("", "empty"),
        ("{project}-{type}", "exactly one"),
        ("{seq:4}-{seq:4}", "exactly one"),
        ("{project}-{project}-{seq:4}", "only once"),
        ("{project}{type}-{seq:4}", "literal text"),
        ("{project}{seq:4}", "literal text"),
        ("{seq:4}{seq:2}", "exactly one"),
        ("{project}-{seq:0}", "invalid segment"),
        ("{project}-{seq:10}", "invalid segment"),
        ("{Project}-{seq:4}", "invalid segment"),
        ("{pro ject}-{seq:4}", "invalid segment"),
        ("{}-{seq:4}", "invalid segment"),
        ("{project-{seq:4}", "unbalanced"),
        ("{project}}-{seq:4}", "unbalanced"),
        ("{project}-{{seq:4}", "unbalanced"),
    ],
)
def test_parse_pattern_rejects_a_bad_template(template: str, message: str) -> None:
    with pytest.raises(PatternError, match=message):
        parse_pattern(template)


def test_patterns_are_value_objects() -> None:
    assert parse_pattern(STANDARD) == parse_pattern(STANDARD)
    assert parse_pattern(STANDARD) != parse_pattern("{project}-{seq:4}")


def test_parse_is_strict_about_the_spelling_of_the_sequence() -> None:
    pattern = parse_pattern(STANDARD)
    assert pattern.parse("P123-REC-0012") is not None
    assert pattern.parse("P123-REC-00012") is None
    overflow = pattern.parse("P123-REC-10000")
    assert overflow is not None and overflow.sequence == 10000


def test_parse_of_an_unpadded_sequence_rejects_leading_zeros() -> None:
    pattern = parse_pattern("DOC-{seq}")
    assert pattern.parse("DOC-7") is not None
    assert pattern.parse("DOC-07") is None
