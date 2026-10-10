"""What the about:config screens show, as pure functions (P0-I8-S19; brief 30.2, 30.3).

Everything here is a hint for the person: which layer a change is sent to, how to type a value,
that a key is risky. None of it decides anything. The service refuses what is not allowed, and the
screens show its message.

The rows, the detail lines and the hints are text built from a ``SettingView`` and nothing else, so
the tests check them without a terminal. The layer a change goes to follows one rule
(:func:`target_layer`): UI keys go to the person's own layer; every other key goes to the project
when the person prefers it and the key allows it, else to the company.
"""

from __future__ import annotations

import json
from typing import Literal

from tl_core.settings.types import SettingChange, SettingDefinition
from tl_core.settings.values import format_value
from tl_core.settings.views import SettingView

MARK = "●"  # set at the layer being viewed (about:config's "modified")
MAX_VALUE = 36
Preference = Literal["project", "company"]


def user_of(actor: str) -> str | None:
    """``kim`` for ``user:kim``; ``None`` for an agent or anything else."""
    kind, _, ident = actor.partition(":")
    return ident if kind == "user" and ident else None


def target_layer(
    defn: SettingDefinition, prefer: Preference, project: str | None, user: str | None
) -> str | None:
    """The layer a change from this screen is written to, or ``None`` when the key has none.

    A key that allows the user layer (the ``ui.`` keys) goes to ``user:<id>``. Otherwise the
    preferred layer when the key allows it (``project:<id>`` needs a project), else the company
    layer, else ``None`` (a platform default only).
    """
    scopes = defn.scopes
    if "user" in scopes and user is not None:
        return f"user:{user}"
    if prefer == "project" and "project" in scopes and project is not None:
        return f"project:{project}"
    if "company" in scopes:
        return "company"
    if "project" in scopes and project is not None:
        return f"project:{project}"
    return None


def _cut(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def origin_text(view: SettingView) -> str:
    e = view.effective
    return f"{e.origin} {MARK}" if e.modified_here else e.origin


def row_cells(view: SettingView) -> tuple[str, str, str, str, str]:
    """The cells of a list row: key, value, type, origin and ``locked`` or an empty text."""
    e = view.effective
    return (
        e.key,
        _cut(format_value(e.value, max_items=3), MAX_VALUE),
        view.definition.type,
        origin_text(view),
        "locked" if e.locked else "",
    )


def hint_for(defn: SettingDefinition) -> str:
    """How to type a value of this key, such as ``whole number, 10 to 86400`` or ``one of a, b``."""
    v = defn.validation
    kind = defn.type
    if kind == "bool":
        return "true or false"
    if kind == "enum" and v is not None and v.choices:
        return "one of " + ", ".join(format_value(c) for c in v.choices)
    if kind in ("int", "decimal", "duration", "size"):
        names = {
            "int": "whole number",
            "decimal": "number",
            "duration": "duration such as 90s, 5m, 24h",
            "size": "size such as 512KB, 50MB",
        }
        rng = ""
        if v is not None and (v.minimum is not None or v.maximum is not None):
            low = "" if v.minimum is None else f"{v.minimum:g}"
            high = "" if v.maximum is None else f"{v.maximum:g}"
            rng = f", {low} to {high}".replace(" to ,", " to")
        return names[kind] + rng
    if kind == "list":
        return "words separated by commas, or a JSON list"
    if kind == "json":
        return "JSON"
    return "text"


def detail_lines(view: SettingView, target: str | None) -> list[str]:
    """Everything about one setting, a line each (``name text``), the way ``tl config get --long``
    prints it, plus the hint for typing a value and the layer a change would go to."""
    defn = view.definition
    e = view.effective
    lines = [
        f"key {e.key}",
        f"description {defn.description}",
        f"value {format_value(e.value)}",
        f"default {format_value(defn.default)}",
        f"type {defn.type} ({hint_for(defn)})",
        f"origin {origin_text(view)}",
        f"change goes to {target if target is not None else 'nowhere: platform default only'}",
    ]
    if defn.docs:
        lines.append(f"docs {' '.join(defn.docs.split())}")
    if defn.risk != "normal":
        needs = "a reason is required"
        if defn.risk == "dangerous":
            needs += "; you must accept the risk"
        lines.append(f"risk {defn.risk}: {needs}")
    if defn.effect != "live":
        lines.append(f"effect needs a {defn.effect} to be fully in force")
    if e.locked:
        lines.append("locked yes: projects cannot override it")
    if e.bounds:
        lines.append(f"bounds {json.dumps(e.bounds, sort_keys=True, ensure_ascii=False)}")
    for change in e.scheduled:
        lines.append(
            f"scheduled {change.applies_at} {format_value(change.new_value)} (seq {change.seq})"
        )
    if e.pending_effect is not None:
        lines.append(f"pending {e.pending_effect}: the change is not fully in force yet")
    return lines


def history_cells(change: SettingChange) -> tuple[str, str, str, str, str, str]:
    """seq, layer, time, actor, ``old -> new`` (or ``reset``) and the reason."""
    if change.reset:
        moved = "reset"
    else:
        before = _cut(format_value(change.old_value), 18)
        moved = f"{before} -> {_cut(format_value(change.new_value), 18)}"
    return (
        str(change.seq),
        change.layer,
        change.recorded_at[:16].replace("T", " "),
        change.actor,
        moved,
        change.reason or "",
    )
