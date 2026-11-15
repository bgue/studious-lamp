"""Forms engine rules (P2-FORMS S1): formats 1 and 2, visibility, answers, hash, intake."""

from __future__ import annotations

from typing import Any

import pytest
from tl_core.forms import rules as r

ULID = "01HZX3K9Q7M2N4P5R6S8T0V1WA"


def f(fid: str, kind: str = "text", *, required: bool = True, **kw: Any) -> dict[str, Any]:
    """A format 1 question (all nine keys); keyword arguments override or add keys."""
    base: dict[str, Any] = {
        "id": fid,
        "text": f"field {fid}",
        "kind": kind,
        "required": required,
        "unit": None,
        "min": None,
        "max": None,
        "choices": None,
        "fails_when": None,
    }
    base.update(kw)
    return base


def a(qid: str, value: Any, note: str | None = None) -> dict[str, Any]:
    return {"q": qid, "value": value, "note": note}


# ---- format 1 stays valid, format 2 is a superset -----------------------------------------------


def test_format_1_questions_are_valid_in_both_formats() -> None:
    fields = [
        f("q1", "yes_no_na", fails_when="no"),
        f("q2", "number", min=0, max=9, fails_when="out_of_range"),
    ]
    assert r.validate_questions(fields) == []
    assert r.validate_questions(fields, fmt=2) == []


@pytest.mark.parametrize(
    "bad",
    [
        f("q1", section="Isolation"),
        f("q1", help="Look at the gauge"),
        f("q1", visible_when={"q": "q0", "answered": True}),
        f("q1", "multi", choices=["a", "b"]),
        f("q1", "date"),
        f("q1", "photo"),
        f("claim_name"),
    ],
)
def test_format_1_refuses_every_format_2_addition(bad: dict[str, Any]) -> None:
    assert r.validate_questions([f("q0"), bad]) != []


def test_format_2_accepts_the_new_keys_and_kinds() -> None:
    fields = [
        f("q1", section="Isolation", help="Check the tag", required=False),
        f("q2", "multi", choices=["lock", "tag", "try"], section="Isolation"),
        f("q3", "date", required=False),
        f("q4", "photo", required=False),
        f("claim_name", required=False),
    ]
    assert r.validate_questions(fields, fmt=2) == []


def test_format_2_limits_and_ids() -> None:
    assert r.validate_questions([f("q1", section="s" * 64)], fmt=2) == []
    assert r.validate_questions([f("q1", section="s" * 65)], fmt=2) != []
    assert r.validate_questions([f("q1", help="h" * 300)], fmt=2) == []
    assert r.validate_questions([f("q1", help="h" * 301)], fmt=2) != []
    assert r.validate_questions([f("Bad-Id")], fmt=2) != []
    assert r.validate_questions([f("q1", "multi", choices=["a", "a"])], fmt=2) != []
    assert r.validate_questions([f("q1", "date", fails_when="no")], fmt=2) != []


def test_unknown_format_is_refused() -> None:
    with pytest.raises(ValueError):
        r.validate_questions([f("q1")], fmt=3)


# ---- visible_when -------------------------------------------------------------------------------

Q1 = f("q1", "number", min=0, max=100)


@pytest.mark.parametrize(
    "cond",
    [
        {"q": "q1", "is": 5},
        {"q": "q1", "in": [1, 2, 3]},
        {"q": "q1", "gte": 5},
        {"q": "q1", "lte": 5},
        {"q": "q1", "answered": True},
        {"all": [{"q": "q1", "gte": 1}, {"q": "q1", "lte": 9}]},
        {"any": [{"q": "q1", "is": 1}, {"q": "q1", "is": 2}]},
        {"not": {"q": "q1", "answered": False}},
        {"not": {"all": [{"any": [{"q": "q1", "is": 1}]}]}},  # three deep
    ],
)
def test_good_conditions(cond: dict[str, Any]) -> None:
    assert r.validate_questions([Q1, f("q2", required=False, visible_when=cond)], fmt=2) == []


@pytest.mark.parametrize(
    "cond",
    [
        {"q": "q3", "is": 1},  # a later field
        {"q": "q2", "is": 1},  # itself
        {"q": "q9", "is": 1},  # unknown
        {"q": "q1", "is": 1, "gte": 0},  # two operators
        {"q": "q1"},  # no operator
        {"q": "q1", "gte": "x"},  # not a number
        {"q": "q1", "in": []},
        {"q": "q1", "is": 1, "extra": 1},
        {"all": []},
        {"all": [{"q": "q1", "is": 1}], "any": [{"q": "q1", "is": 2}]},
        {"not": {"not": {"not": {"not": {"q": "q1", "is": 1}}}}},  # four deep
        "q1",
    ],
)
def test_bad_conditions(cond: Any) -> None:
    fields = [Q1, f("q2", required=False, visible_when=cond), f("q3", required=False)]
    problems = r.validate_questions(fields, fmt=2)
    assert problems != [] and all(p.startswith(("q2:", "question 2:")) for p in problems)


# ---- visible_ids --------------------------------------------------------------------------------

CHAIN = [
    f("q1", "yes_no_na"),
    f("q2", visible_when={"q": "q1", "is": "yes"}),
    f("q3", required=False, visible_when={"q": "q2", "answered": True}),
]


def test_visibility_follows_the_answers_and_chains() -> None:
    assert r.visible_ids(CHAIN, []) == ["q1"]
    assert r.visible_ids(CHAIN, [a("q1", "no")]) == ["q1"]
    assert r.visible_ids(CHAIN, [a("q1", "yes")]) == ["q1", "q2"]
    assert r.visible_ids(CHAIN, [a("q1", "yes"), a("q2", "x")]) == ["q1", "q2", "q3"]


def test_a_hidden_field_counts_as_unanswered_for_later_conditions() -> None:
    # q2 is hidden, so even a stray answer to it must not open q3
    assert r.visible_ids(CHAIN, [a("q1", "no"), a("q2", "x")]) == ["q1"]


@pytest.mark.parametrize(
    ("cond", "value", "shown"),
    [
        ({"q": "q1", "is": 5}, 5, True),
        ({"q": "q1", "is": 5}, 6, False),
        ({"q": "q1", "in": [1, 5]}, 5, True),
        ({"q": "q1", "in": [1, 5]}, 2, False),
        ({"q": "q1", "gte": 5}, 5, True),
        ({"q": "q1", "gte": 5}, 4.9, False),
        ({"q": "q1", "lte": 5}, 5, True),
        ({"q": "q1", "lte": 5}, 5.1, False),
        ({"q": "q1", "answered": False}, None, True),
        ({"not": {"q": "q1", "is": 5}}, 6, True),
        ({"any": [{"q": "q1", "is": 1}, {"q": "q1", "gte": 9}]}, 9, True),
        ({"all": [{"q": "q1", "gte": 1}, {"q": "q1", "lte": 3}]}, 9, False),
    ],
)
def test_condition_evaluation(cond: dict[str, Any], value: Any, shown: bool) -> None:
    fields = [Q1, f("q2", required=False, visible_when=cond)]
    answers = [] if value is None else [a("q1", value)]
    assert ("q2" in r.visible_ids(fields, answers)) is shown


def test_visible_ids_does_not_modify_inputs() -> None:
    answers = [a("q1", "yes")]
    before = (repr(CHAIN), repr(answers))
    r.visible_ids(CHAIN, answers)
    assert (repr(CHAIN), repr(answers)) == before


# ---- validate_answers in format 2 ---------------------------------------------------------------


def test_answer_to_a_hidden_field_is_a_problem_and_hidden_required_is_not() -> None:
    assert r.validate_answers(CHAIN, [a("q1", "no")], fmt=2) == []
    problems = r.validate_answers(CHAIN, [a("q1", "no"), a("q2", "x")], fmt=2)
    assert problems != [] and problems[0].startswith("q2:")


def test_visible_required_unanswered_is_the_fixed_phrase() -> None:
    assert r.validate_answers(CHAIN, [a("q1", "yes")], fmt=2) == ["q2: answer required"]


def test_partial_skips_required_but_not_shape_or_hidden() -> None:
    assert r.validate_answers(CHAIN, [a("q1", "yes")], fmt=2, partial=True) == []
    assert r.validate_answers(CHAIN, [], fmt=2, partial=True) == []
    assert r.validate_answers(CHAIN, [a("q1", "maybe")], fmt=2, partial=True) != []
    assert r.validate_answers(CHAIN, [a("q1", "no"), a("q2", "x")], fmt=2, partial=True) != []
    assert r.validate_answers(CHAIN, [a("zz", "x")], fmt=2, partial=True) != []


@pytest.mark.parametrize(
    ("kind", "extra", "value", "ok"),
    [
        ("multi", {"choices": ["a", "b", "c"]}, ["a", "c"], True),
        ("multi", {"choices": ["a", "b", "c"]}, [], True),
        ("multi", {"choices": ["a", "b", "c"]}, ["a", "a"], False),
        ("multi", {"choices": ["a", "b", "c"]}, ["z"], False),
        ("multi", {"choices": ["a", "b", "c"]}, "a", False),
        ("date", {}, "2026-11-15", True),
        ("date", {}, "2026-02-30", False),
        ("date", {}, "15/11/2026", False),
        ("date", {}, 20261115, False),
        ("photo", {}, [ULID], True),
        ("photo", {}, [ULID] * 10, True),
        ("photo", {}, [ULID] * 11, False),
        ("photo", {}, [], False),
        ("photo", {}, ["not-a-file-id"], False),
        ("photo", {}, ULID, False),
    ],
)
def test_new_kinds_in_answers(kind: str, extra: dict[str, Any], value: Any, ok: bool) -> None:
    fields = [f("q1", kind, **extra)]
    assert (r.validate_answers(fields, [a("q1", value)], fmt=2) == []) is ok


def test_format_1_validate_answers_default_is_unchanged() -> None:
    fields = [f("q1", "yes_no_na"), f("q2", "number", min=0, max=1, required=False)]
    assert r.validate_answers(fields, [a("q1", "yes"), a("q2", 7)]) == []
    assert r.validate_answers(fields, []) == ["q1: answer required"]


def test_intake_caps_text_answers_at_280() -> None:
    fields = [f("q1")]
    assert r.validate_answers(fields, [a("q1", "x" * 281)]) == []
    assert r.validate_answers(fields, [a("q1", "x" * 280)], fmt=2, intake=True) == []
    assert r.validate_answers(fields, [a("q1", "x" * 281)], fmt=2, intake=True) != []


# ---- content hash -------------------------------------------------------------------------------


def test_content_hash_is_stable_and_sensitive() -> None:
    one = [f("q1"), f("q2", "yes_no_na")]
    reordered_keys = [dict(reversed(list(x.items()))) for x in one]
    h = r.content_hash(one, fmt=1)
    assert len(h) == 64 and h == h.lower() and int(h, 16) >= 0
    assert r.content_hash(reordered_keys, fmt=1) == h
    assert r.content_hash([f("q1", text="other"), f("q2", "yes_no_na")], fmt=1) != h
    assert r.content_hash(list(reversed(one)), fmt=1) != h
    assert r.content_hash(one, fmt=2) != h


# ---- intake profile (ADR-0032 decision 2) -------------------------------------------------------

GOOD_INTAKE = [
    f("q1", "choice", choices=["scaffold", "ladder"]),
    f("q2", "number", min=1, max=20),
    f("claim_name", required=False),
    f("claim_phone", required=False),
]


def test_good_intake_profile() -> None:
    assert r.intake_problems(GOOD_INTAKE, purpose="request", accepts_as=["RaiseRequisition"]) == []
    assert r.intake_problems(GOOD_INTAKE, purpose="sign_on", accepts_as=["SubmitForm"]) == []


@pytest.mark.parametrize(
    "fields",
    [
        [f(f"q{i}") for i in range(1, 10)],  # nine fields
        [f("q1", "photo")],
        [f("q1", "date")],
        [f("q1", "multi", choices=["a", "b"])],
        [f("q1"), f("q2", visible_when={"q": "q1", "answered": True})],
        [f("q1", "number")],  # a quantity needs bounds
        [f("q1", "yes_no_na")],
        [f("claim_name", "choice", choices=["a", "b"])],  # claim ids are text
    ],
)
def test_intake_profile_refusals(fields: list[dict[str, Any]]) -> None:
    assert r.intake_problems(fields, purpose="request", accepts_as=["SubmitForm"]) != []


def test_intake_purpose_and_accepts_as() -> None:
    ok = GOOD_INTAKE
    assert r.intake_problems(ok, purpose="complaint", accepts_as=["SubmitForm"]) != []
    assert r.intake_problems(ok, purpose="request", accepts_as=[]) != []
    assert r.intake_problems(ok, purpose="request", accepts_as=["submit form"]) != []
    assert r.intake_problems(ok, purpose="request", accepts_as=[f"Cmd{i}" for i in range(6)]) != []
    assert r.intake_problems(ok, purpose="request", accepts_as=["SubmitForm", "SubmitForm"]) != []


def test_bounds_are_the_documented_ones() -> None:
    from tl_core.forms import types as t

    assert (t.MAX_FIELDS, t.MAX_FIELD_TEXT, t.MAX_CHOICES, t.MAX_SECTION, t.MAX_HELP) == (
        60,
        200,
        8,
        64,
        300,
    )
    assert (t.MAX_CONDITION_DEPTH, t.INTAKE_MAX_FIELDS, t.INTAKE_TEXT_MAX) == (3, 8, 280)
    assert t.FORM_SOURCE_ENTRY_POINT == "throughline.form_sources"
    assert set(t.RESERVED_CLAIM_IDS) == {"claim_name", "claim_company", "claim_phone"}
