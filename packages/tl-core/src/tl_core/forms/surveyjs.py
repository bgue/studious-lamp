"""SurveyJS model projection of a form's fields (P2-FORMS B1; ADR-0031).

A pure projection: no I/O, and it imports only ``tl_core.forms.rules`` and ``tl_core.forms.types``.
The model is what the vendored SurveyJS renderer builds a page from. The browser only helps the
person; the server stays the validator (``validate_answers``). Photo fields are not in the model;
``surveyjs_unsupported`` names them.
"""

from __future__ import annotations

from typing import Any

from tl_core.forms.rules import validate_questions
from tl_core.forms.types import FORMAT_1, FORMAT_2, MAX_ANSWER_TEXT

_RADIO_MAX = 4  # a choice with more choices than this is a dropdown
_YES_NO_NA = (("yes", "Yes"), ("no", "No"), ("na", "Not applicable"))


def to_surveyjs(fields: list[dict[str, Any]], fmt: int = FORMAT_2) -> dict[str, Any]:
    """SurveyJS model (a JSON-serialisable dict) for a template with these fields.

    Raises ``ValueError`` for an unknown format, or for fields that ``validate_questions`` refuses
    (the first problem is the message).
    """
    if fmt not in (FORMAT_1, FORMAT_2):
        raise ValueError(f"unknown form format {fmt!r}")
    problems = validate_questions(fields, fmt=fmt)
    if problems:
        raise ValueError(problems[0])
    return {
        "showQuestionNumbers": "off",
        "clearInvisibleValues": "onHidden",
        "checkErrorsMode": "onComplete",
        "pages": [{"name": "page1", "elements": _elements(fields)}],
    }


def surveyjs_unsupported(fields: list[dict[str, Any]]) -> list[str]:
    """Ids of the fields left out of the model, in field order (today: photo fields)."""
    return [str(f["id"]) for f in fields if f.get("kind") == "photo"]


# ---- elements -------------------------------------------------------------------------------


def _elements(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Top-level elements: runs of one non-null section become a panel; other fields stand alone."""
    out: list[dict[str, Any]] = []
    panels = 0
    run: list[dict[str, Any]] = []
    run_section: str | None = None
    for field in fields:
        section = field.get("section")
        if section is not None and section == run_section:
            run.append(field)
            continue
        panel = _panel(run, run_section, panels)
        if panel is not None:
            out.append(panel)
            panels += 1
        run, run_section = [], section
        if section is None:
            element = _element_of(field)
            if element is not None:
                out.append(element)
        else:
            run.append(field)
    panel = _panel(run, run_section, panels)
    if panel is not None:
        out.append(panel)
    return out


def _panel(run: list[dict[str, Any]], section: str | None, panels: int) -> dict[str, Any] | None:
    """The panel for a finished run of fields in one section; ``None`` if it holds no element."""
    if section is None or not run:
        return None
    elements = [e for e in (_element_of(f) for f in run) if e is not None]
    if not elements:
        return None
    return {"type": "panel", "name": f"sec{panels + 1}", "title": section, "elements": elements}


def _element_of(field: dict[str, Any]) -> dict[str, Any] | None:
    kind = field["kind"]
    if kind == "photo":
        return None
    title = field["text"]
    if kind == "number" and field.get("unit") is not None:
        title = f"{title} ({field['unit']})"
    element: dict[str, Any] = {"name": field["id"], "title": title, "isRequired": field["required"]}
    if field.get("help") is not None:
        element["description"] = field["help"]
    element.update(_kind_part(field))
    if field.get("visible_when") is not None:
        element["visibleIf"] = _expr(field["visible_when"])
    return element


def _kind_part(field: dict[str, Any]) -> dict[str, Any]:
    kind = field["kind"]
    if kind == "yes_no_na":
        choices = [{"value": value, "text": text} for value, text in _YES_NO_NA]
        return {"type": "radiogroup", "choices": choices, "colCount": 3}
    if kind == "number":
        return {"type": "text", "inputType": "number"}
    if kind == "text":
        return {"type": "text", "maxLength": MAX_ANSWER_TEXT}
    if kind == "choice":
        kind_type = "radiogroup" if len(field["choices"]) <= _RADIO_MAX else "dropdown"
        return {"type": kind_type, "choices": list(field["choices"])}
    if kind == "multi":
        return {"type": "checkbox", "choices": list(field["choices"])}
    if kind == "date":
        return {"type": "text", "inputType": "date"}
    # validate_questions has already refused any other kind
    raise ValueError(f"unknown kind {kind!r}")


# ---- visible_when ---------------------------------------------------------------------------


def _expr(node: dict[str, Any]) -> str:
    """The SurveyJS expression for one condition node (S1 grammar; one rule per node)."""
    if "q" in node:
        return _leaf(node)
    if "all" in node:
        return "(" + " and ".join(_expr(n) for n in node["all"]) + ")"
    if "any" in node:
        return "(" + " or ".join(_expr(n) for n in node["any"]) + ")"
    return f"!({_expr(node['not'])})"


def _leaf(node: dict[str, Any]) -> str:
    q = node["q"]
    if "is" in node:
        return f"{q} = {_literal(node['is'])}"
    if "in" in node:
        return "(" + " or ".join(f"{q} = {_literal(v)}" for v in node["in"]) + ")"
    if "gte" in node:
        return f"{q} >= {_literal(node['gte'])}"
    if "lte" in node:
        return f"{q} <= {_literal(node['lte'])}"
    return f"{q} notempty" if node["answered"] else f"{q} empty"


def _literal(value: Any) -> str:
    if isinstance(value, bool):  # before int: a bool is an int in Python
        return "true" if value else "false"
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
    return repr(value)
