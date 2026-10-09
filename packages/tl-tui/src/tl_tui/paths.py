"""Pset value lookup in a record envelope (brief 6.3 layer-aware paths).

A record's ``psets`` is addressed by the dotted paths of the brief, for example
``psets.valve_data.x.fat_witness_by`` or ``psets.prj.shutdown_tie_in.window``. Pset names may
themselves contain dots (``prj.shutdown_tie_in``) and the custom section is ``x``, so a path is
resolved by trying every dotted prefix of the remaining parts as a key. That also accepts a store
that keeps ``"x.fat_witness_by"`` as one flat key.
"""

from __future__ import annotations

from typing import Any

_PREFIX = "psets."


def pset_value(psets: dict[str, Any], path: str) -> Any:
    """The value at ``path`` (with or without the leading ``psets.``), or ``None`` when absent."""
    dotted = path.removeprefix(_PREFIX)
    return _lookup(psets, dotted.split("."))


def _lookup(node: Any, parts: list[str]) -> Any:
    if not parts:
        return node
    if not isinstance(node, dict):
        return None
    mapping: dict[str, Any] = node  # pyright: ignore[reportUnknownVariableType]
    for i in range(1, len(parts) + 1):
        key = ".".join(parts[:i])
        if key in mapping:
            found = _lookup(mapping[key], parts[i:])
            if found is not None:
                return found
    return None


def relative_key(field_path: str, group: str) -> str:
    """The key of ``field_path`` relative to its pset, for ``SetPsetValues.values``.

    ``relative_key("psets.valve_data.x.fat_witness_by", "valve_data")`` is ``"x.fat_witness_by"``.
    """
    prefix = f"{_PREFIX}{group}."
    if not field_path.startswith(prefix):
        raise ValueError(f"{field_path!r} is not under pset {group!r}")
    return field_path[len(prefix) :]
