# pyright: basic
"""Pure forms rules over plain dicts (ADR-0031; P2-FORMS S1).

No database, clock or ``tl_core`` import except ``types``. Inputs are never mutated.
``failed_questions`` and ``result_of`` stay in ``tl_mod_quality.insp_rules``.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date
from typing import Any

from tl_core.forms.types import (
    FORMAT_1,
    FORMAT_2,
    INTAKE_MAX_ACCEPTS,
    INTAKE_MAX_FIELDS,
    INTAKE_PURPOSES,
    INTAKE_TEXT_MAX,
    KEYS_1,
    KEYS_2,
    KINDS_1,
    KINDS_2,
    MAX_ANSWER_TEXT,
    MAX_CHOICES,
    MAX_CONDITION_DEPTH,
    MAX_FIELD_TEXT,
    MAX_FIELDS,
    MAX_HELP,
    MAX_NOTE,
    MAX_PHOTOS,
    MAX_SECTION,
    RESERVED_CLAIM_IDS,
)

_ID_1 = re.compile(r"^q[0-9]+$")
_ID_2 = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_ULID = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_COMMAND = re.compile(r"^[A-Z][A-Za-z0-9]{2,63}$")
_YES_NO_NA = ("yes", "no", "na")
_SCALAR = (str, int, float, bool)


def _check_fmt(fmt: int) -> None:
    if fmt not in (FORMAT_1, FORMAT_2):
        raise ValueError(f"unknown form format {fmt!r}")


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _id_ok(fid: Any, fmt: int) -> bool:
    pattern = _ID_1 if fmt == FORMAT_1 else _ID_2
    return isinstance(fid, str) and pattern.fullmatch(fid) is not None


def _label(field: Any, i: int, fmt: int) -> str:
    fid = field.get("id") if isinstance(field, dict) else None
    if isinstance(fid, str) and _id_ok(fid, fmt):
        return fid
    return f"question {i}"


# ---- validate_questions ---------------------------------------------------------------------


def validate_questions(fields: list[dict[str, Any]], *, fmt: int = 1) -> list[str]:
    """Problems that stop a template being published; ``[]`` means publishable."""
    _check_fmt(fmt)
    if not isinstance(fields, list) or not fields:
        return ["question list: at least one question is required"]
    problems: list[str] = []
    if len(fields) > MAX_FIELDS:
        problems.append(f"question list: at most {MAX_FIELDS} questions")
    keys = KEYS_1 if fmt == FORMAT_1 else KEYS_2
    kinds = KINDS_1 if fmt == FORMAT_1 else KINDS_2
    seen: list[str] = []
    for i, field in enumerate(fields, start=1):
        label = _label(field, i, fmt)
        if not isinstance(field, dict):
            problems.append(f"{label}: must be an object")
            continue
        problems.extend(_question_problems(field, label, i, fmt, keys, kinds, seen))
        fid = field.get("id")
        if isinstance(fid, str):
            seen.append(fid)
    return problems


def _question_problems(
    field: dict[str, Any],
    label: str,
    i: int,
    fmt: int,
    keys: tuple[str, ...],
    kinds: tuple[str, ...],
    seen: list[str],
) -> list[str]:
    out: list[str] = []
    for key in field:
        if key not in keys:
            out.append(f"{label}: unknown key {key!r}")
    for key in KEYS_1:
        if key not in field:
            out.append(f"{label}: missing key {key!r}")
    fid = field.get("id")
    if not _id_ok(fid, fmt):
        out.append(f"{label}: bad id")
    elif fid in seen:
        out.append(f"{label}: duplicate id")
    text = field.get("text")
    if not isinstance(text, str) or not text.strip():
        out.append(f"{label}: text is required")
    elif len(text) > MAX_FIELD_TEXT:
        out.append(f"{label}: text is over {MAX_FIELD_TEXT} characters")
    kind = field.get("kind")
    if kind not in kinds:
        out.append(f"{label}: bad kind")
    if not isinstance(field.get("required"), bool):
        out.append(f"{label}: required must be true or false")
    unit = field.get("unit")
    if unit is not None and not isinstance(unit, str):
        out.append(f"{label}: unit must be text or null")
    lo, hi = field.get("min"), field.get("max")
    for name, bound in (("min", lo), ("max", hi)):
        if bound is not None and not _is_num(bound):
            out.append(f"{label}: {name} must be a number or null")
    if lo is not None and hi is not None and _is_num(lo) and _is_num(hi) and lo > hi:
        out.append(f"{label}: min is above max")
    out.extend(_choice_problems(field, label, kind))
    fails = field.get("fails_when")
    if fails is not None:
        if fails == "no":
            if kind != "yes_no_na":
                out.append(f"{label}: fails_when 'no' needs a yes_no_na question")
        elif fails == "out_of_range":
            if kind != "number":
                out.append(f"{label}: fails_when 'out_of_range' needs a number question")
            elif lo is None and hi is None:
                out.append(f"{label}: fails_when 'out_of_range' needs min or max")
        else:
            out.append(f"{label}: bad fails_when")
    if fmt == FORMAT_2:
        out.extend(_format2_problems(field, label, fields_before=seen))
    return out


def _choice_problems(field: dict[str, Any], label: str, kind: Any) -> list[str]:
    choices = field.get("choices")
    if kind not in ("choice", "multi"):
        return [] if choices is None else [f"{label}: choices only on choice or multi questions"]
    if not isinstance(choices, list) or not choices:
        return [f"{label}: choices are required"]
    out: list[str] = []
    if len(choices) > MAX_CHOICES:
        out.append(f"{label}: at most {MAX_CHOICES} choices")
    if not all(isinstance(c, str) and c for c in choices):
        out.append(f"{label}: each choice must be non-empty text")
    elif len(set(choices)) != len(choices):
        out.append(f"{label}: choices must be distinct")
    return out


def _format2_problems(field: dict[str, Any], label: str, fields_before: list[str]) -> list[str]:
    out: list[str] = []
    for key, cap in (("section", MAX_SECTION), ("help", MAX_HELP)):
        v = field.get(key)
        if v is None:
            continue
        if not isinstance(v, str):
            out.append(f"{label}: {key} must be text or null")
        elif len(v) > cap:
            out.append(f"{label}: {key} is over {cap} characters")
    cond = field.get("visible_when")
    if cond is not None:
        out.extend(_node_problems(cond, label, fields_before, 0)[0])
    return out


def _node_problems(node: Any, label: str, earlier: list[str], depth: int) -> tuple[list[str], int]:
    """Problems of one condition node, and its combinator depth (leaf 0)."""
    if not isinstance(node, dict):
        return [f"{label}: visible_when node must be an object"], 0
    ops = [k for k in node if k in ("is", "in", "gte", "lte", "answered", "all", "any", "not")]
    if "q" in node:
        allowed = {"q"} | set(ops)
        if set(node) - allowed or len(ops) != 1 or ops[0] in ("all", "any", "not"):
            return [f"{label}: visible_when leaf must be q plus exactly one operator"], 0
        out: list[str] = []
        if not isinstance(node["q"], str) or node["q"] not in earlier:
            out.append(f"{label}: visible_when must name an earlier question")
        op = ops[0]
        v = node[op]
        if op == "is" and not isinstance(v, _SCALAR):
            out.append(f"{label}: visible_when 'is' needs a plain value")
        elif op == "in":
            if not isinstance(v, list) or not 1 <= len(v) <= MAX_CHOICES:
                out.append(f"{label}: visible_when 'in' needs 1 to {MAX_CHOICES} values")
            elif not all(isinstance(x, _SCALAR) for x in v):
                out.append(f"{label}: visible_when 'in' needs plain values")
        elif op in ("gte", "lte") and not _is_num(v):
            out.append(f"{label}: visible_when '{op}' needs a number")
        elif op == "answered" and not isinstance(v, bool):
            out.append(f"{label}: visible_when 'answered' needs true or false")
        return out, 0
    if len(node) != 1 or len(ops) != 1 or ops[0] not in ("all", "any", "not"):
        return [f"{label}: visible_when node must be one operator"], 0
    op = ops[0]
    kids = node[op]
    if op == "not":
        children = [kids]
    else:
        if not isinstance(kids, list) or not 1 <= len(kids) <= MAX_CHOICES:
            return [f"{label}: visible_when '{op}' needs 1 to {MAX_CHOICES} nodes"], 0
        children = kids
    out = []
    deepest = 0
    for child in children:
        sub, d = _node_problems(child, label, earlier, depth + 1)
        out.extend(sub)
        deepest = max(deepest, d)
    mine = deepest + 1
    if mine > MAX_CONDITION_DEPTH and depth == 0:
        out.append(f"{label}: visible_when is nested deeper than {MAX_CONDITION_DEPTH}")
    return out, mine


# ---- visible_ids ----------------------------------------------------------------------------


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    return bool(a == b)


def _eval(node: Any, values: dict[str, Any]) -> bool:
    if not isinstance(node, dict):
        return False
    if "all" in node:
        return all(_eval(n, values) for n in node["all"])
    if "any" in node:
        return any(_eval(n, values) for n in node["any"])
    if "not" in node:
        return not _eval(node["not"], values)
    qid = str(node.get("q"))
    answered = qid in values
    value = values.get(qid)
    if "answered" in node:
        return answered is bool(node["answered"])
    if not answered:
        return False
    if "is" in node:
        return _same(value, node["is"])
    if "in" in node:
        return any(_same(value, x) for x in node["in"])
    if "gte" in node:
        return _is_num(value) and value >= node["gte"]
    if "lte" in node:
        return _is_num(value) and value <= node["lte"]
    return False


def _answer_values(answers: list[dict[str, Any]]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for ans in answers:
        if isinstance(ans, dict) and isinstance(ans.get("q"), str) and ans.get("q") not in values:
            if ans.get("value") is not None:
                values[ans["q"]] = ans["value"]
    return values


def visible_ids(fields: list[dict[str, Any]], answers: list[dict[str, Any]]) -> list[str]:
    """Ids of the fields shown for these answers, in field order."""
    values = _answer_values(answers)
    shown: list[str] = []
    live: dict[str, Any] = {}
    for field in fields:
        fid = field["id"]
        cond = field.get("visible_when")
        if cond is None or _eval(cond, live):
            shown.append(fid)
            if fid in values:
                live[fid] = values[fid]
    return shown


# ---- validate_answers -----------------------------------------------------------------------


def validate_answers(
    fields: list[dict[str, Any]],
    answers: list[dict[str, Any]],
    *,
    fmt: int = 1,
    partial: bool = False,
    intake: bool = False,
) -> list[str]:
    """Problems with a set of answers; ``[]`` means acceptable."""
    _check_fmt(fmt)
    by_id = {f["id"]: f for f in fields}
    shown = set(visible_ids(fields, answers))
    problems: list[str] = []
    seen: set[str] = set()
    for ans in answers:
        if not isinstance(ans, dict) or not isinstance(ans.get("q"), str):
            problems.append("answer: must be an object naming a question")
            continue
        qid = ans["q"]
        extra = set(ans) - {"q", "value", "note"}
        if extra:
            problems.append(f"{qid}: unknown key {sorted(extra)[0]!r} in answer")
        if qid not in by_id:
            problems.append(f"{qid}: no such question")
            continue
        if qid in seen:
            problems.append(f"{qid}: answered more than once")
            continue
        seen.add(qid)
        if qid not in shown:
            problems.append(f"{qid}: question is not shown for these answers")
            continue
        note = ans.get("note")
        if note is not None and (not isinstance(note, str) or len(note) > MAX_NOTE):
            problems.append(f"{qid}: note must be text of at most {MAX_NOTE} characters")
        problem = _value_problem(by_id[qid], ans.get("value"), intake)
        if problem:
            problems.append(f"{qid}: {problem}")
    if not partial:
        for field in fields:
            if field["id"] in shown and field.get("required") and field["id"] not in seen:
                problems.append(f"{field['id']}: answer required")
    return problems


def _value_problem(field: dict[str, Any], value: Any, intake: bool) -> str | None:
    kind = field.get("kind")
    if kind == "yes_no_na":
        return None if value in _YES_NO_NA and isinstance(value, str) else "must be yes, no or na"
    if kind == "number":
        return None if _is_num(value) else "must be a number"
    if kind == "text":
        cap = INTAKE_TEXT_MAX if intake else MAX_ANSWER_TEXT
        if not isinstance(value, str):
            return "must be text"
        return None if len(value) <= cap else f"text is over {cap} characters"
    if kind == "choice":
        ok = isinstance(value, str) and value in (field.get("choices") or [])
        return None if ok else "must be one of the choices"
    if kind == "multi":
        choices = field.get("choices") or []
        if not isinstance(value, list):
            return "must be a list of the choices"
        if not all(isinstance(v, str) and v in choices for v in value):
            return "must be a list of the choices"
        return None if len(set(value)) == len(value) else "choices must be distinct"
    if kind == "date":
        if not isinstance(value, str) or not _DATE.fullmatch(value):
            return "must be a date as YYYY-MM-DD"
        try:
            date.fromisoformat(value)
        except ValueError:
            return "must be a real date"
        return None
    if kind == "photo":
        if not isinstance(value, list) or not 1 <= len(value) <= MAX_PHOTOS:
            return f"must be 1 to {MAX_PHOTOS} photos"
        if not all(isinstance(v, str) and _ULID.fullmatch(v) for v in value):
            return "must be photo file ids"
        return None if len(set(value)) == len(value) else "photos must be distinct"
    return "unknown kind"


# ---- content_hash ---------------------------------------------------------------------------


def content_hash(fields: list[dict[str, Any]], *, fmt: int) -> str:
    """SHA-256 hex of the canonical JSON of the format and the fields."""
    _check_fmt(fmt)
    canon = json.dumps(
        {"format": fmt, "fields": fields},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


# ---- intake_problems ------------------------------------------------------------------------


def intake_problems(
    fields: list[dict[str, Any]], *, purpose: str, accepts_as: list[str]
) -> list[str]:
    """Extra problems for a template that is to be public intake (ADR-0032 decision 2)."""
    out: list[str] = []
    if len(fields) > INTAKE_MAX_FIELDS:
        out.append(f"intake: at most {INTAKE_MAX_FIELDS} fields")
    for i, field in enumerate(fields, start=1):
        label = _label(field, i, FORMAT_2)
        if field.get("kind") not in ("text", "choice", "number"):
            out.append(f"{label}: intake allows text, choice and number only")
        if field.get("visible_when") is not None:
            out.append(f"{label}: intake allows no visible_when")
        if field.get("kind") == "number" and (field.get("min") is None or field.get("max") is None):
            out.append(f"{label}: an intake number needs min and max")
        if field.get("id") in RESERVED_CLAIM_IDS and field.get("kind") != "text":
            out.append(f"{label}: a claim field must be text")
    if purpose not in INTAKE_PURPOSES:
        out.append(f"intake: purpose must be one of {', '.join(INTAKE_PURPOSES)}")
    if not isinstance(accepts_as, list) or not 1 <= len(accepts_as) <= INTAKE_MAX_ACCEPTS:
        out.append(f"intake: accepts_as needs 1 to {INTAKE_MAX_ACCEPTS} command names")
    else:
        if not all(isinstance(n, str) and _COMMAND.fullmatch(n) for n in accepts_as):
            out.append("intake: accepts_as names must look like SubmitForm")
        if len(set(map(str, accepts_as))) != len(accepts_as):
            out.append("intake: accepts_as names must be distinct")
    return out
