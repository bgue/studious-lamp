"""Schema-evolution guard: event payload schemas may only grow (owner rule: additive only).

The baseline ``packages/tl-schema/compat/event-schemas.json`` holds, per event type and
``schema_version``, the generated JSON Schema of the payload (descriptions and titles dropped).
``diff(baseline, current)`` returns one line per non-additive change, each naming the event and the
property. Allowed: new event types, new versions, new optional properties, a looser rule.
Refused: a removed event type, version or property, a changed type or format, a property that
became required, a tightened enum, pattern, const or bound.

``python -m tl_schema.compat --check`` fails on any such line (a stale baseline is fine);
``--update`` refuses to write when there is one (``just compat-update``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

PACKAGE_DIR = Path(__file__).resolve().parent
CATALOG_DIR = PACKAGE_DIR / "generated" / "catalog"
BASELINE_PATH = PACKAGE_DIR.parents[1] / "compat" / "event-schemas.json"

Baseline = dict[str, dict[str, Any]]

_DROP = {"description", "title"}
_MIN = ("minimum", "exclusiveMinimum", "minLength", "minItems", "minProperties")
_MAX = ("maximum", "exclusiveMaximum", "maxLength", "maxItems", "maxProperties")


def _clean(node: Any, in_properties: bool = False) -> Any:
    """Drop description and title, except where they are property names."""
    if isinstance(node, dict):
        items = cast("dict[str, Any]", node)
        return {
            k: _clean(v, k == "properties" and not in_properties)
            for k, v in items.items()
            if in_properties or k not in _DROP
        }
    if isinstance(node, list):
        return [_clean(v) for v in cast("list[Any]", node)]
    return node


def current_schemas(catalog_dir: Path = CATALOG_DIR) -> Baseline:
    """``{event_type: {str(schema_version): payload schema}}`` from the generated catalog."""
    index = json.loads((catalog_dir / "index.json").read_text(encoding="utf-8"))
    out: Baseline = {}
    for entry in index["events"]:
        doc = json.loads((catalog_dir / entry["schema"]).read_text(encoding="utf-8"))
        detail = doc["properties"]["data"]["properties"]["detail"]
        out.setdefault(entry["event_type"], {})[str(entry["version"])] = _clean(detail)
    return {k: dict(sorted(v.items())) for k, v in sorted(out.items())}


def load_baseline(path: Path | None = None) -> Baseline:
    path = path or BASELINE_PATH
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def dumps(schemas: Baseline) -> str:
    return json.dumps(schemas, indent=1, sort_keys=True) + "\n"


def _types(node: dict[str, Any]) -> set[str] | None:
    t = node.get("type")
    if t is None:
        return None
    return set(cast("list[str]", t)) if isinstance(t, list) else {cast(str, t)}


def _node(old: dict[str, Any], new: dict[str, Any], where: str, out: list[str]) -> None:
    ot, nt = _types(old), _types(new)
    if ot is not None and (nt is None or not ot <= nt):
        if nt is not None:
            out.append(f"{where}: type changed {sorted(ot)} -> {sorted(nt)}")
        # a type constraint removed entirely is a loosening
    elif ot is None and nt is not None:
        out.append(f"{where}: type {sorted(nt)} added to an untyped property")
    if old.get("format") != new.get("format") and new.get("format") is not None:
        out.append(f"{where}: format changed {old.get('format')!r} -> {new['format']!r}")
    if new.get("pattern") is not None and new["pattern"] != old.get("pattern"):
        out.append(f"{where}: pattern tightened or changed")
    if "const" in new and new["const"] != old.get("const", object()):
        out.append(f"{where}: const tightened or changed")
    if "enum" in new and (
        "enum" not in old
        or not set(map(json.dumps, old["enum"])) <= set(map(json.dumps, new["enum"]))
    ):
        out.append(f"{where}: enum tightened (a value removed or a new enum)")
    for key in _MIN:
        if key in new and (key not in old or new[key] > old[key]):
            out.append(f"{where}: {key} tightened")
    for key in _MAX:
        if key in new and (key not in old or new[key] < old[key]):
            out.append(f"{where}: {key} tightened")
    if "anyOf" in old or "anyOf" in new:
        before = {json.dumps(x, sort_keys=True) for x in old.get("anyOf", [])}
        after = {json.dumps(x, sort_keys=True) for x in new.get("anyOf", [])}
        if not before <= after:
            out.append(f"{where}: anyOf alternative removed or changed")
    if isinstance(old.get("items"), dict) and isinstance(new.get("items"), dict):
        _node(old["items"], new["items"], f"{where}[]", out)
    elif "items" in new and "items" not in old:
        out.append(f"{where}: items constraint added")
    if old.get("properties") is not None or new.get("properties") is not None:
        _object(old, new, where, out)


def _object(old: dict[str, Any], new: dict[str, Any], where: str, out: list[str]) -> None:
    oprops: dict[str, Any] = old.get("properties", {})
    nprops: dict[str, Any] = new.get("properties", {})
    for name, schema in oprops.items():
        if name not in nprops:
            out.append(f"{where}: property '{name}' removed")
        else:
            _node(schema, nprops[name], f"{where}.{name}", out)
    for name in sorted(set(new.get("required", [])) - set(old.get("required", []))):
        verb = "became required" if name in oprops else "added as required"
        out.append(f"{where}: property '{name}' {verb}")
    if old.get("additionalProperties") is not False and new.get("additionalProperties") is False:
        out.append(f"{where}: additional properties now forbidden")


def diff(baseline: Baseline, current: Baseline) -> list[str]:
    """One line per non-additive change from ``baseline`` to ``current``; empty means additive."""
    out: list[str] = []
    for event, versions in sorted(baseline.items()):
        if event not in current:
            out.append(f"{event}: event type removed")
            continue
        for version, schema in sorted(versions.items()):
            where = f"{event} v{version}"
            if version not in current[event]:
                out.append(f"{where}: schema version removed")
            else:
                lines: list[str] = []
                _node(schema, current[event][version], "payload", lines)
                out.extend(f"{where}: {line}" for line in lines)
    return out


_METHODS = ("get", "put", "post", "delete", "patch", "head", "options")


def _params(op: dict[str, Any]) -> dict[tuple[Any, Any], dict[str, Any]]:
    """Operation parameters keyed by ``(name, in)``."""
    return {(p.get("name"), p.get("in")): p for p in op.get("parameters", [])}


def diff_openapi(baseline: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """One line per breaking change between two OpenAPI documents (P2-X1-T04)."""
    out: list[str] = []
    bpaths: dict[str, Any] = baseline.get("paths", {})
    cpaths: dict[str, Any] = current.get("paths", {})
    for path in sorted(bpaths):
        bitem: dict[str, Any] = bpaths[path]
        citem: dict[str, Any] = cpaths.get(path, {})
        for method in _METHODS:
            if method not in bitem:
                continue
            label = f"{method.upper()} {path}"
            if method not in citem:
                out.append(f"{label}: operation removed")
                continue
            bop: dict[str, Any] = bitem[method]
            cop: dict[str, Any] = citem[method]
            bcodes = {str(code) for code in bop.get("responses", {})}
            ccodes = {str(code) for code in cop.get("responses", {})}
            for code in sorted(bcodes - ccodes):
                out.append(f"{label}: response {code} removed")
            bparams = _params(bop)
            cparams = _params(cop)
            for key in sorted(set(cparams) - set(bparams), key=repr):
                if cparams[key].get("required") is True:
                    out.append(f"{label}: parameter {key[0]!r} added as required")
            for key in sorted(set(bparams) & set(cparams), key=repr):
                if not bparams[key].get("required") and cparams[key].get("required") is True:
                    out.append(f"{label}: parameter {key[0]!r} became required")
    bschemas: dict[str, Any] = baseline.get("components", {}).get("schemas", {})
    cschemas: dict[str, Any] = current.get("components", {}).get("schemas", {})
    for name in sorted(bschemas):
        where = f"schema {name}"
        if name not in cschemas:
            out.append(f"{where}: removed")
        else:
            _node(bschemas[name], cschemas[name], where, out)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tl_schema.compat")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--update", action="store_true")
    args = parser.parse_args(argv)
    current = current_schemas()
    problems = diff(load_baseline(), current) if BASELINE_PATH.exists() else []
    if problems:
        for line in problems:
            print(line, file=sys.stderr)
        print(
            "non-additive schema change: events are never changed, only added to", file=sys.stderr
        )
        return 1
    if args.check:
        stale = not BASELINE_PATH.exists() or load_baseline() != current
        print(
            "event schemas are additive over the baseline"
            + (" (baseline stale: `just compat-update`)" if stale else "")
        )
        return 0
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(dumps(current), encoding="utf-8")
    print(f"wrote {BASELINE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
