# pyright: basic
"""ADR-0026 F5: the `tl:valid_time` tag on module event payloads and its untagged baseline.

Run `uv run python packages/tl-schema/tests/test_valid_time_tag.py --write-baseline` once to write
`tests/tools/valid_time_baseline.toml` from the current schema. The baseline only shrinks: a class
that gains a tag or disappears must leave the baseline in the same change.
"""

from __future__ import annotations

import json
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from linkml_runtime.utils.schemaview import SchemaView

REPO = Path(__file__).resolve().parents[3]
MODULES = REPO / "schema" / "modules"
BASELINE = REPO / "tests" / "tools" / "valid_time_baseline.toml"
TAG = "tl:valid_time"
EVENT_TAG = "tl:event_type"
VALUES = ("at", "from", "to")
DATE_RANGES = ("date", "datetime")
UNTAGGED_REASON = "pre-wave-3, untagged"
HEADER = (
    "# class = reason; generated from schema/modules/** at P2-INT; new classes must tag a slot\n"
    "# or be added with a reason\n"
    "# Only shrinks: a class that gains a tag or is removed leaves this file in the same change.\n"
)


@dataclass
class Inventory:
    """What the module schemas say about valid time, keyed by ``<schema name>.<class name>``."""

    events: set[str] = field(default_factory=set)
    tagged: dict[str, list[tuple[str, str, str]]] = field(default_factory=dict)
    bad_values: list[str] = field(default_factory=list)
    shape: list[str] = field(default_factory=list)


def _annotation(obj: Any, tag: str) -> str | None:
    annotations: Any = getattr(obj, "annotations", None)
    if annotations is None or tag not in annotations:
        return None
    return str(annotations[tag].value)


def module_files() -> list[Path]:
    return sorted(MODULES.rglob("*.yaml"))


def inventory(paths: list[Path]) -> Inventory:
    inv = Inventory()
    for path in paths:
        view: Any = SchemaView(str(path))
        schema = view.schema
        for class_name in sorted(schema.classes):
            cls = view.get_class(class_name)
            key = f"{schema.name}.{class_name}"
            if _annotation(cls, EVENT_TAG) is not None:
                inv.events.add(key)
            for slot in view.class_induced_slots(class_name):
                value = _annotation(slot, TAG)
                if value is None:
                    continue
                range_name = slot.range or schema.default_range or "string"
                if value not in VALUES:
                    inv.bad_values.append(
                        f"{key}.{slot.name}: {TAG} is {value!r}, not at, from or to"
                    )
                inv.tagged.setdefault(key, []).append((slot.name, value, range_name))
    for key, tags in sorted(inv.tagged.items()):
        values = [value for _, value, _ in tags]
        ats, froms, tos = values.count("at"), values.count("from"), values.count("to")
        if ats > 1 or froms > 1 or tos > 1 or (ats and (froms or tos)):
            inv.shape.append(
                f"{key}: {TAG} must be one at, or at most one from and one to; got {values}"
            )
        for slot_name, _, range_name in tags:
            if range_name not in DATE_RANGES:
                inv.shape.append(
                    f"{key}.{slot_name}: tagged slot has range {range_name!r}, not date or datetime"
                )
    return inv


def read_baseline(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    classes: dict[str, str] = data.get("classes", {})
    return classes


def untagged_events(inv: Inventory, baseline: dict[str, str]) -> list[str]:
    """Event classes with no tagged slot that the baseline does not list."""
    return sorted(k for k in inv.events if k not in inv.tagged and k not in baseline)


def stale_entries(inv: Inventory, baseline: dict[str, str]) -> list[str]:
    """Baseline keys naming a class that no longer exists as an event, or that now has a tag."""
    return sorted(k for k in baseline if k not in inv.events or k in inv.tagged)


def write_baseline(path: Path, inv: Inventory) -> int:
    keys = sorted(k for k in inv.events if k not in inv.tagged)
    lines = [HEADER, "[classes]\n"]
    lines += [f"{json.dumps(k)} = {json.dumps(UNTAGGED_REASON)}\n" for k in keys]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")
    return len(keys)


def test_every_tag_value_is_at_from_or_to() -> None:
    inv = inventory(module_files())
    assert inv.bad_values == []


def test_shape_per_class_and_date_range() -> None:
    inv = inventory(module_files())
    assert inv.shape == []


def test_every_event_class_is_tagged_or_baselined() -> None:
    inv = inventory(module_files())
    assert inv.events, "no module event classes found; the scan is broken"
    assert untagged_events(inv, read_baseline(BASELINE)) == []


def test_baseline_only_shrinks() -> None:
    inv = inventory(module_files())
    assert stale_entries(inv, read_baseline(BASELINE)) == []


# Synthetic schemas: each failure case from the ticket, in tmp_path.


def _schema_file(tmp_path: Path, name: str, classes: dict[str, Any]) -> Path:
    doc = {
        "id": f"https://example.org/throughline/test/{name}",
        "name": name,
        "prefixes": {
            "linkml": "https://w3id.org/linkml/",
            "throughline": "https://example.org/throughline/",
        },
        "default_prefix": "throughline",
        "imports": ["linkml:types"],
        "default_range": "string",
        "classes": classes,
    }
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return path


def _event(slots: dict[str, Any]) -> dict[str, Any]:
    return {
        "annotations": {EVENT_TAG: "X.Happened"},
        "attributes": slots,
    }


def _when(value: str | None, range_name: str = "datetime") -> dict[str, Any]:
    slot: dict[str, Any] = {"range": range_name}
    if value is not None:
        slot["annotations"] = {TAG: value}
    return slot


def test_good_schema_passes(tmp_path: Path) -> None:
    path = _schema_file(
        tmp_path,
        "tl_mod_x_good",
        {
            "SpanPayload": _event({"start": _when("from", "date"), "end": _when("to", "date")}),
            "MomentPayload": _event({"when": _when("at"), "due_date": _when(None, "date")}),
        },
    )
    inv = inventory([path])
    assert inv.bad_values == [] and inv.shape == []
    assert untagged_events(inv, {}) == []
    assert sorted(inv.tagged) == ["tl_mod_x_good.MomentPayload", "tl_mod_x_good.SpanPayload"]


def test_bad_value_fails(tmp_path: Path) -> None:
    path = _schema_file(tmp_path, "tl_mod_x_bad", {"DuePayload": _event({"when": _when("due")})})
    inv = inventory([path])
    assert any("tl_mod_x_bad.DuePayload.when" in p and "'due'" in p for p in inv.bad_values)


def test_mixed_or_repeated_fails(tmp_path: Path) -> None:
    path = _schema_file(
        tmp_path,
        "tl_mod_x_mixed",
        {
            "MixedPayload": _event({"a": _when("at"), "b": _when("from", "date")}),
            "TwoAtPayload": _event({"a": _when("at"), "b": _when("at")}),
        },
    )
    shape = inventory([path]).shape
    assert any("MixedPayload" in p and "must be one at" in p for p in shape)
    assert any("TwoAtPayload" in p and "must be one at" in p for p in shape)


def test_tagged_slot_must_be_a_date(tmp_path: Path) -> None:
    path = _schema_file(
        tmp_path, "tl_mod_x_str", {"NamePayload": _event({"when": _when("at", "string")})}
    )
    assert any(
        "tl_mod_x_str.NamePayload.when" in p and "'string'" in p for p in inventory([path]).shape
    )


def test_untagged_event_class_fails(tmp_path: Path) -> None:
    path = _schema_file(
        tmp_path, "tl_mod_x_untagged", {"BarePayload": _event({"name": _when(None, "string")})}
    )
    inv = inventory([path])
    assert untagged_events(inv, {}) == ["tl_mod_x_untagged.BarePayload"]
    assert untagged_events(inv, {"tl_mod_x_untagged.BarePayload": UNTAGGED_REASON}) == []


def test_stale_baseline_entry_fails(tmp_path: Path) -> None:
    path = _schema_file(
        tmp_path,
        "tl_mod_x_stale",
        {
            "GonePayload": _event({"when": _when(None)}),
            "NowTagged": _event({"when": _when("at")}),
        },
    )
    inv = inventory([path])
    baseline = {
        "tl_mod_x_stale.NowTagged": UNTAGGED_REASON,
        "tl_mod_x_stale.Removed": UNTAGGED_REASON,
    }
    assert stale_entries(inv, baseline) == ["tl_mod_x_stale.NowTagged", "tl_mod_x_stale.Removed"]
    assert stale_entries(inv, {"tl_mod_x_stale.GonePayload": UNTAGGED_REASON}) == []


def test_write_baseline_round_trips(tmp_path: Path) -> None:
    path = _schema_file(
        tmp_path,
        "tl_mod_x_rt",
        {
            "AlphaPayload": _event({"name": _when(None, "string")}),
            "CTagged": _event({"when": _when("at")}),
        },
    )
    inv = inventory([path])
    target = tmp_path / "baseline.toml"
    assert write_baseline(target, inv) == 1
    assert read_baseline(target) == {"tl_mod_x_rt.AlphaPayload": UNTAGGED_REASON}
    assert untagged_events(inv, read_baseline(target)) == []


if __name__ == "__main__":
    if "--write-baseline" in sys.argv:
        count = write_baseline(BASELINE, inventory(module_files()))
        print(f"wrote {BASELINE} with {count} entries")
    else:
        print("usage: test_valid_time_tag.py --write-baseline", file=sys.stderr)
        raise SystemExit(2)
