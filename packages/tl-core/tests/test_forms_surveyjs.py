"""SurveyJS model projection of form fields (P2-FORMS B1; ADR-0031).

No network and no database: the fixture templates are read from the repository.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from tl_core.forms.surveyjs import surveyjs_unsupported, to_surveyjs

REPO = Path(__file__).resolve().parents[3]
TEMPLATES = REPO / "schema" / "fixtures" / "forms" / "templates"
FIXTURES: list[Path] = sorted(TEMPLATES.glob("*.yaml"))  # top level only; intake/ is not projected
ALLOWED_KEYS = {
    "type",
    "name",
    "title",
    "description",
    "isRequired",
    "choices",
    "colCount",
    "inputType",
    "maxLength",
    "visibleIf",
    "elements",
}


def _load(path: Path) -> tuple[list[dict[str, Any]], int]:
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    fields: list[dict[str, Any]] = data["fields"]
    return fields, int(data["format_version"])


def _reversed(field: dict[str, Any]) -> dict[str, Any]:
    return dict(reversed(list(field.items())))


def _f(fid: str, kind: str, **kw: Any) -> dict[str, Any]:
    """A question with the nine format 1 keys; keyword arguments override or add keys."""
    base: dict[str, Any] = {
        "id": fid,
        "text": f"field {fid}",
        "kind": kind,
        "required": True,
        "unit": None,
        "min": None,
        "max": None,
        "choices": None,
        "fails_when": None,
    }
    base.update(kw)
    return base


def _elements_of(model: dict[str, Any]) -> list[dict[str, Any]]:
    page: dict[str, Any] = model["pages"][0]
    elements: list[dict[str, Any]] = page["elements"]
    return elements


def _walk(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every element, with the contents of panels, in order."""
    out: list[dict[str, Any]] = []
    for el in elements:
        out.append(el)
        if el["type"] == "panel":
            out.extend(_walk(el["elements"]))
    return out


def _leaves(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [el for el in _walk(elements) if el["type"] != "panel"]


def _by_name(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {el["name"]: el for el in _leaves(_elements_of(model))}


# ---- fixtures -------------------------------------------------------------------------------


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_fixture_projects_independent_of_key_order(path: Path) -> None:
    fields, fmt = _load(path)
    model = to_surveyjs(fields, fmt)
    reordered = to_surveyjs([_reversed(f) for f in fields], fmt)
    assert json.dumps(model, sort_keys=True) == json.dumps(reordered, sort_keys=True)
    json.dumps(model)  # JSON-serialisable


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_fixture_names_and_required_match_the_fields(path: Path) -> None:
    fields, fmt = _load(path)
    model = to_surveyjs(fields, fmt)
    leaves = _leaves(_elements_of(model))
    names = sorted(str(el["name"]) for el in leaves)
    expected = sorted(f["id"] for f in fields if f["id"] not in surveyjs_unsupported(fields))
    assert names == expected
    by_id = {f["id"]: f for f in fields}
    for el in leaves:
        assert el["isRequired"] is by_id[el["name"]]["required"]


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_fixture_elements_use_only_the_allowed_keys(path: Path) -> None:
    fields, fmt = _load(path)
    for el in _walk(_elements_of(to_surveyjs(fields, fmt))):
        assert set(el) <= ALLOWED_KEYS, el
        assert not {"min", "max", "html"} & set(el), el


def test_fixture_element_counts() -> None:
    counts: dict[str, int] = {}
    for path in FIXTURES:
        fields, fmt = _load(path)
        counts[path.name] = len(_leaves(_elements_of(to_surveyjs(fields, fmt))))
    assert counts == {
        "job-hazard-assessment.yaml": 9,
        "pre-use-check.yaml": 8,
        "toolbox-talk.yaml": 8,
    }


def test_pre_use_check_leaves_out_only_the_photo() -> None:
    fields, fmt = _load(TEMPLATES / "pre-use-check.yaml")
    assert surveyjs_unsupported(fields) == ["leak_photo"]
    assert "leak_photo" not in _by_name(to_surveyjs(fields, fmt))


# ---- visible_when ---------------------------------------------------------------------------


def _conditions() -> list[tuple[dict[str, Any], str]]:
    leaf_yes = {"q": "q1", "is": "yes"}
    leaf_gte = {"q": "q2", "gte": 0}
    return [
        ({"q": "q1", "is": "yes"}, "q1 = 'yes'"),
        ({"q": "q2", "is": 3}, "q2 = 3"),
        ({"q": "q3", "is": "it's a \\ test"}, "q3 = 'it\\'s a \\\\ test'"),
        ({"q": "q1", "is": True}, "q1 = true"),
        ({"q": "q2", "in": [1, 2.5]}, "(q2 = 1 or q2 = 2.5)"),
        ({"q": "q2", "gte": 0}, "q2 >= 0"),
        ({"q": "q2", "lte": 9.5}, "q2 <= 9.5"),
        ({"q": "q3", "answered": True}, "q3 notempty"),
        ({"q": "q3", "answered": False}, "q3 empty"),
        ({"all": [leaf_yes, leaf_gte]}, "(q1 = 'yes' and q2 >= 0)"),
        ({"any": [leaf_yes, leaf_gte]}, "(q1 = 'yes' or q2 >= 0)"),
        ({"not": leaf_yes}, "!(q1 = 'yes')"),
        (
            {
                "all": [
                    {"any": [{"not": {"q": "q1", "is": "no"}}, {"q": "q2", "gte": 1}]},
                    {"q": "q3", "answered": True},
                ]
            },
            "((!(q1 = 'no') or q2 >= 1) and q3 notempty)",
        ),
    ]


@pytest.mark.parametrize(("node", "expected"), _conditions())
def test_visible_when_grammar_is_pinned(node: dict[str, Any], expected: str) -> None:
    fields = [
        _f("q1", "yes_no_na"),
        _f("q2", "number", min=0, max=9),
        _f("q3", "text"),
        _f("t", "text", visible_when=node),
    ]
    model = to_surveyjs(fields, 2)
    assert _by_name(model)["t"]["visibleIf"] == expected


def test_no_visible_if_when_there_is_no_condition() -> None:
    model = to_surveyjs([_f("q1", "text")], 2)
    assert "visibleIf" not in _by_name(model)["q1"]


# ---- kinds ----------------------------------------------------------------------------------


def test_each_kind_has_its_pinned_element() -> None:
    fields = [
        _f("yn", "yes_no_na"),
        _f("num", "number"),
        _f("txt", "text"),
        _f("ch4", "choice", choices=["a", "b", "c", "d"]),
        _f("ch5", "choice", choices=["a", "b", "c", "d", "e"]),
        _f("multi", "multi", choices=["x", "y"]),
        _f("dt", "date"),
    ]
    by = _by_name(to_surveyjs(fields, 2))
    assert by["yn"]["type"] == "radiogroup"
    assert by["yn"]["colCount"] == 3
    assert by["yn"]["choices"] == [
        {"value": "yes", "text": "Yes"},
        {"value": "no", "text": "No"},
        {"value": "na", "text": "Not applicable"},
    ]
    assert by["num"] == {
        "name": "num",
        "title": "field num",
        "isRequired": True,
        "type": "text",
        "inputType": "number",
    }
    assert by["txt"]["type"] == "text"
    assert by["txt"]["maxLength"] == 1000
    assert by["ch4"]["type"] == "radiogroup"
    assert by["ch4"]["choices"] == ["a", "b", "c", "d"]
    assert by["ch5"]["type"] == "dropdown"
    assert by["multi"]["type"] == "checkbox"
    assert by["multi"]["choices"] == ["x", "y"]
    assert by["dt"]["type"] == "text"
    assert by["dt"]["inputType"] == "date"


def test_number_with_bounds_and_unit_shows_the_unit_and_no_bounds() -> None:
    field = _f("hours", "number", min=0, max=100, unit="h")
    el = _by_name(to_surveyjs([field], 2))["hours"]
    assert el["title"] == "field hours (h)"
    assert "min" not in el
    assert "max" not in el


def test_photo_is_not_in_the_model() -> None:
    fields = [_f("p", "photo"), _f("t", "text")]
    model = to_surveyjs(fields, 2)
    assert [el["name"] for el in _leaves(_elements_of(model))] == ["t"]
    assert surveyjs_unsupported(fields) == ["p"]


def test_description_is_help_and_left_out_when_none() -> None:
    fields = [
        _f("a", "text", section=None, help="Say more."),
        _f("b", "text", section=None, help=None),
    ]
    by = _by_name(to_surveyjs(fields, 2))
    assert by["a"]["description"] == "Say more."
    assert "description" not in by["b"]


# ---- sections -------------------------------------------------------------------------------


def test_consecutive_fields_in_a_section_share_one_panel() -> None:
    fields = [
        _f("a", "text", section="S"),
        _f("b", "text", section="S"),
        _f("c", "text", section=None),
    ]
    elements = _elements_of(to_surveyjs(fields, 2))
    assert len(elements) == 2
    panel = elements[0]
    assert panel["type"] == "panel"
    assert panel["name"] == "sec1"
    assert panel["title"] == "S"
    assert [el["name"] for el in panel["elements"]] == ["a", "b"]
    assert elements[1]["name"] == "c"
    assert "section" not in elements[1]


def test_a_section_with_only_a_photo_emits_no_panel() -> None:
    fields = [
        _f("p", "photo", section="Photos"),
        _f("t", "text", section="Text"),
    ]
    elements = _elements_of(to_surveyjs(fields, 2))
    assert [el["type"] for el in elements] == ["panel"]
    assert elements[0]["name"] == "sec1"
    assert elements[0]["title"] == "Text"
    assert [el["name"] for el in elements[0]["elements"]] == ["t"]


def test_format_1_fields_are_all_top_level() -> None:
    fields = [_f("q1", "yes_no_na", fails_when="no"), _f("q2", "text")]
    elements = _elements_of(to_surveyjs(fields, 1))
    assert [el["name"] for el in elements] == ["q1", "q2"]
    assert all(el["type"] != "panel" for el in elements)


# ---- texts ----------------------------------------------------------------------------------


def test_texts_pass_through_unchanged() -> None:
    text = "<img src=x onerror=1> {topic}"
    fields = [_f("topic", "choice", text=text, choices=["</script>", "plain"])]
    el = _by_name(to_surveyjs(fields, 2))["topic"]
    assert el["title"] == text
    assert el["choices"] == ["</script>", "plain"]


# ---- refusals -------------------------------------------------------------------------------


def test_unknown_format_is_refused() -> None:
    with pytest.raises(ValueError):
        to_surveyjs([_f("q1", "text")], 3)


def test_bad_kind_is_refused() -> None:
    with pytest.raises(ValueError):
        to_surveyjs([_f("q1", "signature")], 2)
