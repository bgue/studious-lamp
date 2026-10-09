"""Relation vocabulary of links (P0-I3-T01; brief 7.1)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from tl_core.links.vocabulary import (
    DEFAULT_RELATION,
    DEFAULT_RELATIONS,
    LINK_SOURCES,
    Relation,
    RelationVocabulary,
    default_relation,
    default_vocabulary,
)
from tl_core.services.errors import UnknownRelationError

LINKS_YAML = Path(__file__).resolve().parents[3] / "schema" / "core" / "links.yaml"


def test_the_default_vocabulary_has_the_thirteen_relations_of_the_brief() -> None:
    vocabulary = default_vocabulary()
    assert vocabulary.codes() == [
        "references",
        "derived_from",
        "supersedes",
        "responds_to",
        "raised_against",
        "resolves",
        "belongs_to",
        "requires",
        "blocks",
        "verifies",
        "dispatched_from",
        "attached_to",
        "same_as",
    ]


def test_default_vocabulary_returns_a_new_instance_each_time() -> None:
    first = default_vocabulary()
    first.add(Relation("custom", "custom", "custom_of", "custom of"))
    assert "custom" in first
    assert "custom" not in default_vocabulary()


def test_get_returns_the_relation_for_a_forward_code() -> None:
    relation = default_vocabulary().get("raised_against")
    assert relation == Relation("raised_against", "raised against", "has_raised", "has raised")
    assert relation.symmetric is False


def test_same_as_is_symmetric() -> None:
    assert default_vocabulary().get("same_as").symmetric is True


def test_contains_is_true_for_forward_codes_only() -> None:
    vocabulary = default_vocabulary()
    assert "requires" in vocabulary
    assert "required_by" not in vocabulary
    assert "nonsense" not in vocabulary
    assert 42 not in vocabulary


def test_get_unknown_code_raises() -> None:
    with pytest.raises(UnknownRelationError, match="unknown relation 'nonsense'"):
        default_vocabulary().get("nonsense")


def test_get_with_an_inverse_code_names_the_forward_relation() -> None:
    with pytest.raises(UnknownRelationError) as caught:
        default_vocabulary().get("has_raised")
    message = str(caught.value)
    assert "inverse of 'raised_against'" in message
    assert "swapped" in message


def test_resolve_accepts_forward_and_inverse_codes() -> None:
    vocabulary = default_vocabulary()
    forward, flipped = vocabulary.resolve("blocks")
    assert (forward.code, flipped) == ("blocks", False)
    inverse, flipped = vocabulary.resolve("blocked_by")
    assert (inverse.code, flipped) == ("blocks", True)


def test_resolve_of_a_symmetric_relation_is_never_flipped() -> None:
    relation, flipped = default_vocabulary().resolve("same_as")
    assert (relation.code, flipped) == ("same_as", False)


def test_resolve_unknown_code_raises() -> None:
    with pytest.raises(UnknownRelationError):
        default_vocabulary().resolve("nonsense")


def test_label_reads_out_and_in() -> None:
    vocabulary = default_vocabulary()
    assert vocabulary.label("raised_against", "out") == "raised against"
    assert vocabulary.label("raised_against", "in") == "has raised"
    assert vocabulary.label("same_as", "in") == "same as"


def test_label_of_an_inverse_code_is_refused() -> None:
    with pytest.raises(UnknownRelationError):
        default_vocabulary().label("has_raised", "out")


def test_add_extends_the_vocabulary() -> None:
    vocabulary = default_vocabulary()
    vocabulary.add(Relation("inspects", "inspects", "inspected_by", "inspected by"))
    assert vocabulary.codes()[-1] == "inspects"
    assert vocabulary.get("inspects").inverse_label == "inspected by"
    assert vocabulary.resolve("inspected_by")[1] is True


@pytest.mark.parametrize(
    "relation",
    [
        Relation("references", "x", "ref_by", "x"),  # forward code already taken
        Relation("new_one", "x", "referenced_by", "x"),  # inverse code already taken
    ],
)
def test_add_rejects_a_code_that_is_already_used(relation: Relation) -> None:
    with pytest.raises(ValueError, match="already in the vocabulary"):
        default_vocabulary().add(relation)


def test_add_rejects_a_malformed_code() -> None:
    with pytest.raises(ValueError, match="must match"):
        default_vocabulary().add(Relation("Bad Code", "x", "bad_inverse", "x"))
    with pytest.raises(ValueError, match="must match"):
        default_vocabulary().add(Relation("good_code", "x", "Bad-Inverse", "x"))


def test_a_new_symmetric_relation_can_be_added_once() -> None:
    vocabulary = default_vocabulary()
    vocabulary.add(Relation("twin_of", "twin of", "twin_of", "twin of"))
    assert vocabulary.get("twin_of").symmetric is True
    with pytest.raises(ValueError, match="already in the vocabulary"):
        vocabulary.add(Relation("twin_of", "twin of", "twin_of", "twin of"))


def test_the_constructor_registers_the_given_relations() -> None:
    vocabulary = RelationVocabulary(DEFAULT_RELATIONS[:2])
    assert vocabulary.codes() == ["references", "derived_from"]


def test_default_relation_for_the_weld_ncr_pair() -> None:
    assert default_relation("piping.Weld", "quality.NCR") == "raised_against"


def test_default_relation_falls_back_to_references() -> None:
    assert default_relation("core.Record", "core.Record") == DEFAULT_RELATION == "references"


def test_default_relation_lookup_order_is_exact_then_wildcards() -> None:
    pairs = {
        ("a.A", "b.B"): "requires",
        ("a.A", "*"): "blocks",
        ("*", "b.B"): "verifies",
    }
    assert default_relation("a.A", "b.B", pairs) == "requires"
    assert default_relation("a.A", "c.C", pairs) == "blocks"
    assert default_relation("z.Z", "b.B", pairs) == "verifies"
    assert default_relation("z.Z", "c.C", pairs) == "references"


def test_every_default_relation_has_distinct_codes() -> None:
    codes = [r.code for r in DEFAULT_RELATIONS] + [
        r.inverse_code for r in DEFAULT_RELATIONS if not r.symmetric
    ]
    assert len(codes) == len(set(codes))


def test_the_link_source_list_matches_the_linkml_enum() -> None:
    schema = yaml.safe_load(LINKS_YAML.read_text(encoding="utf-8"))
    assert list(schema["enums"]["LinkSource"]["permissible_values"]) == list(LINK_SOURCES)


def test_the_builtin_relation_list_matches_the_linkml_enum() -> None:
    schema = yaml.safe_load(LINKS_YAML.read_text(encoding="utf-8"))
    declared = list(schema["enums"]["LinkRelation"]["permissible_values"])
    assert declared == [r.code for r in DEFAULT_RELATIONS]
