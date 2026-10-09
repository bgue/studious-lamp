"""The hashtag and mention parser (P0-I6-S2; brief 21.2)."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from tl_core.feed.tags import (
    effective_importance,
    parse_tags,
    record_ids_of,
    tag_key,
    tags_from_payload,
    tags_to_payload,
)
from tl_core.feed.types import ParsedTag
from tl_core.numbering.config import NumberingPattern
from tl_core.numbering.detect import KeyMatch

REC = NumberingPattern(
    id="core.Record",
    record_type="core.Record",
    template="{project}-{type}-{seq:4}",
    type_code="REC",
    scope="project:*",
)
FV = NumberingPattern(
    id="fake.fv", record_type="core.Record", template="FV-{seq:4}", type_code="FV", scope="*"
)
KNOWN = {"P123-REC-0003": "01REC3", "FV-1001": "01FV1001"}


def resolve(match: KeyMatch) -> str | None:
    return KNOWN.get(match.key)


def parse(text: str) -> list[ParsedTag]:
    return parse_tags(text, patterns=[REC, FV], resolve=resolve)


def kinds(text: str) -> list[tuple[str, str]]:
    return [(t.kind, t.text) for t in parse(text)]


def test_the_brief_example_has_a_record_a_signal_and_a_mention() -> None:
    text = "Spool S03 arrived with damaged bevels #P123-REC-0003 #hold @party:fab-a"
    tags = parse(text)
    assert [(t.kind, t.text) for t in tags] == [
        ("record", "P123-REC-0003"),
        ("signal", "hold"),
        ("mention", "party:fab-a"),
    ]
    assert tags[0].record_id == "01REC3"
    assert tags[2].namespace == "party"
    for tag in tags:
        assert text[tag.start] in "#@"
        assert text[tag.start + 1 : tag.end] == tag.text


def test_a_record_like_tag_that_matches_no_record_stays_a_topic() -> None:
    tags = parse("see #P123-REC-0099")
    assert [(t.kind, t.text, t.record_id) for t in tags] == [("topic", "P123-REC-0099", None)]


def test_a_second_pattern_resolves_too() -> None:
    assert kinds("check #FV-1001 today") == [("record", "FV-1001")]


def test_a_key_must_be_spelled_the_way_the_pattern_writes_it() -> None:
    assert kinds("#FV-10010") == [("topic", "FV-10010")]
    assert kinds("#FV-1001x") == [("topic", "FV-1001x")]


def test_a_bare_key_without_a_hash_is_not_a_tag() -> None:
    assert parse("see FV-1001 and P123-REC-0003") == []


def test_namespaced_codes_keep_their_namespace_and_are_not_resolved() -> None:
    tags = parse("#area:A12 #disc:PIP #sys:47-01 #cc:4210")
    assert [(t.kind, t.namespace, t.text) for t in tags] == [
        ("code", "area", "area:A12"),
        ("code", "disc", "disc:PIP"),
        ("code", "sys", "sys:47-01"),
        ("code", "cc", "cc:4210"),
    ]
    assert all(t.record_id is None for t in tags)


def test_signal_tags_match_without_regard_to_case_and_keep_the_text_as_written() -> None:
    tags = parse("#HOLD #Safety #decision #urgent #fyi")
    assert [(t.kind, t.text) for t in tags] == [
        ("signal", "HOLD"),
        ("signal", "Safety"),
        ("signal", "decision"),
        ("signal", "urgent"),
        ("signal", "fyi"),
    ]
    assert [tag_key(t) for t in tags] == ["hold", "safety", "decision", "urgent", "fyi"]


def test_a_custom_signal_set_is_honoured() -> None:
    tags = parse_tags("#hold #stop", patterns=[], resolve=resolve, signal_tags=("stop",))
    assert [(t.kind, t.text) for t in tags] == [("topic", "hold"), ("signal", "stop")]


def test_topics_need_a_letter() -> None:
    assert kinds("item #3 and #2026 and #bevel-damage and #A12") == [
        ("topic", "bevel-damage"),
        ("topic", "A12"),
    ]


def test_trailing_punctuation_is_not_part_of_a_tag() -> None:
    text = "Done #hold. Next #bevel-damage, then (#safety) and #area:A12: ok"
    tags = parse(text)
    assert [(t.kind, t.text) for t in tags] == [
        ("signal", "hold"),
        ("topic", "bevel-damage"),
        ("signal", "safety"),
        ("code", "area:A12"),
    ]
    first = tags[0]
    assert text[first.start : first.end] == "#hold"


def test_a_sigil_glued_to_a_word_is_not_a_tag() -> None:
    assert parse("c#sharp me@site.org a#b ##x @@y") == []


def test_mentions() -> None:
    tags = parse("@jsmith @crew:P-07 @party:acme-nde @agent:sim-doc @42")
    assert [(t.kind, t.text, t.namespace) for t in tags] == [
        ("mention", "jsmith", None),
        ("mention", "crew:P-07", "crew"),
        ("mention", "party:acme-nde", "party"),
        ("mention", "agent:sim-doc", "agent"),
    ]


def test_the_same_tag_twice_gives_two_entries() -> None:
    tags = parse("#hold and again #hold")
    assert [t.start for t in tags] == [0, 16]


def test_offsets_of_a_record_tag_cover_the_whole_key() -> None:
    text = "x #FV-1001, y"
    (tag,) = parse(text)
    assert text[tag.start : tag.end] == "#FV-1001"


def test_the_resolver_is_called_once_per_record_like_tag_in_text_order() -> None:
    seen: list[str] = []

    def spy(match: KeyMatch) -> str | None:
        seen.append(match.key)
        return None

    parse_tags("#FV-1001 #P123-REC-0003 #hold", patterns=[REC, FV], resolve=spy)
    assert seen == ["FV-1001", "P123-REC-0003"]


def test_record_ids_are_unique_and_in_text_order() -> None:
    tags = parse("#FV-1001 #P123-REC-0003 #FV-1001 #nope")
    assert record_ids_of(tags) == ["01FV1001", "01REC3"]


def test_a_signal_tag_makes_a_post_high_importance() -> None:
    assert effective_importance("normal", parse("plain #bevel")) == "normal"
    assert effective_importance("low", parse("plain #bevel")) == "low"
    assert effective_importance("low", parse("look #hold")) == "high"


def test_tags_round_trip_through_a_payload() -> None:
    tags = parse("#P123-REC-0003 #hold @party:fab-a #area:A12 #bevel")
    payload = tags_to_payload(tags)
    assert payload[0] == {
        "text": "P123-REC-0003",
        "kind": "record",
        "start": 0,
        "end": 14,
        "namespace": None,
        "record_id": "01REC3",
    }
    assert tags_from_payload(payload) == tuple(tags)


_ALPHABET = st.sampled_from(list("ab1 #@:.-/,_\n") + ["FV-1001", "hold", "P123-REC-0003"])


@settings(max_examples=200, deadline=None)
@given(parts=st.lists(_ALPHABET, max_size=30))
def test_any_text_gives_ordered_non_overlapping_tags_whose_offsets_match_their_text(
    parts: list[str],
) -> None:
    text = "".join(parts)
    tags = parse(text)
    end_of_previous = 0
    for tag in tags:
        assert tag.start >= end_of_previous
        assert tag.end > tag.start + 1
        assert text[tag.start] == ("@" if tag.kind == "mention" else "#")
        assert text[tag.start + 1 : tag.end] == tag.text
        assert (tag.kind == "record") == (tag.record_id is not None)
        end_of_previous = tag.end
