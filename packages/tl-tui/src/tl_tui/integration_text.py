"""Plain text for the integration screens: table cells and the detail panel (P1-I7).

Pure functions of a row from ``ClientInterface.list_integration`` (a dict of a projection table
with its JSON columns parsed), so they are tested without a terminal. State is never colour alone:
`✓ on`, `✗ off`, `✗ retired`, `! failed`, `… waiting`. A time is `2026-10-11 12:15` (UTC). Nothing
here prints a secret or a payload: no row holds one.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from tl_tui.display import humanize

KINDS = (
    "endpoints",
    "rules",
    "actions",
    "enrichers",
    "apps",
    "invocations",
    "enrichments",
    "deliveries",
)
LABELS = {
    "endpoints": "Endpoints",
    "rules": "Rules",
    "actions": "Actions",
    "enrichers": "Enrichers",
    "apps": "Apps",
    "invocations": "Invocations",
    "enrichments": "Values",
    "deliveries": "Error queue",
}
COLUMNS: dict[str, tuple[str, ...]] = {
    "apps": ("Name", "State", "Owner", "Label"),
    "endpoints": ("Path", "State", "Mode", "Auth", "Access", "Ver"),
    "rules": ("Key", "State", "Mode", "Access", "Ver", "Title"),
    "actions": ("Name", "State", "Executor", "Access", "Approval", "Ver", "Label"),
    "enrichers": ("Name", "State", "Access", "Ver", "Code", "Properties"),
    "invocations": ("Id", "Status", "Action", "By", "Requested"),
    "deliveries": ("Id", "State", "Endpoint", "Received", "Error"),
    "enrichments": ("Id", "State", "Record", "Property", "Value", "Conf"),
}
PLAIN_ENRICHMENT_COLUMNS = ("State", "Record", "Property", "Value", "Confidence")
# Plain words for the stored states that do not humanize to the words people use (P1-UX-T07).
PLAIN_STATE_WORDS = {"proposed": "Waiting", "auto_accepted": "Accepted automatically"}
MAX_VALUE_CHARS = 30


def moment(stamp: object) -> str:
    """``2026-10-11T12:15:00.123456Z`` as ``2026-10-11 12:15``; ``-`` for nothing."""
    if not isinstance(stamp, str) or not stamp:
        return "-"
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")


def on_off(row: Mapping[str, Any]) -> str:
    """``✗ retired`` for a retired row, else ``✓ on`` or ``✗ off`` by ``enabled``."""
    if row.get("retired"):
        return "✗ retired"
    return "✓ on" if row.get("enabled") else "✗ off"


def run_state(state: object) -> str:
    """``✓ <state>`` for completed, applied and accepted ones; ``! <state>`` for failed and
    killed; ``… <state>`` for anything still waiting or running."""
    text = str(state)
    if text in ("completed", "applied", "accepted", "auto_accepted"):
        return f"✓ {text}"
    if text in ("failed", "killed", "rejected"):
        return f"! {text}"
    return f"… {text}"


def short_id(value: object) -> str:
    """The last eight characters of an id."""
    return str(value)[-8:]


def state_words(state: object, *, technical: bool) -> str:
    """Technical: ``run_state``. Plain: the same mark with words (``✓ Accepted``, ``… Waiting``)."""
    if technical:
        return run_state(state)
    symbol = run_state(state).split(" ", 1)[0]
    word = PLAIN_STATE_WORDS.get(str(state)) or humanize(str(state))
    return f"{symbol} {word}"


def property_words(path: str) -> str:
    """The property's last segment in words: ``enrich.doc_classifier.doc_type`` is ``Doc type``."""
    return humanize(path.rpartition(".")[2])


def shown_value(value: object) -> str:
    """The value as JSON (``ensure_ascii=False``), cut to ``MAX_VALUE_CHARS`` with ``…``."""
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= MAX_VALUE_CHARS else text[: MAX_VALUE_CHARS - 1] + "…"


def record_name(ref: object, *, technical: bool = True) -> str:
    """The key of a record reference (``RecordRef`` as a dict), else its id; ``?`` for nothing.

    Plain: the key, else ``(no number)``; the id never shows.
    """
    if not technical:
        key = ref.get("key") if isinstance(ref, Mapping) else None
        return str(key) if key else "(no number)"
    if not isinstance(ref, Mapping):
        return "?"
    return str(ref.get("key") or ref.get("id") or "?")


def columns(kind: str, *, technical: bool = True) -> tuple[str, ...]:
    """The table headings of a kind. Only the enrichments table has plain headings for now."""
    if technical or kind != "enrichments":
        return COLUMNS[kind]
    return PLAIN_ENRICHMENT_COLUMNS


def cells(
    kind: str,
    row: Mapping[str, Any],
    names: Mapping[str, str] | None = None,
    *,
    technical: bool = True,
) -> tuple[str, ...]:
    """The cells of a row, in the order of ``columns(kind, technical=...)``.

    ``names`` maps an endpoint id to its path for the error queue (a deliveries row holds only the
    id); an id it does not know shows as ``?``. ``technical=False`` gives plain words; only the
    enrichments kind reads it so far (the other kinds follow in P1-UX-T09a).
    """
    if kind == "apps":
        return (row["name"], on_off(row), str(row["owner"]), row["label"])
    if kind == "endpoints":
        mode = "dry-run" if row["dry_run"] else "live"
        path = f"{row['app']}/{row['name']}"
        return (path, on_off(row), mode, row["auth"], row["access"], f"v{row['version']}")
    if kind == "rules":
        return (
            row["key"],
            on_off(row),
            row["mode"],
            row["access"],
            f"v{row['version']}",
            row["title"],
        )
    if kind == "actions":
        approval = "yes" if row["requires_approval"] else "no"
        return (
            row["name"], on_off(row), row["executor"], row["access"], approval,
            f"v{row['version']}", row["label"],
        )  # fmt: skip
    if kind == "enrichers":
        properties = ",".join(p["name"] for p in row["properties"])
        return (
            row["name"], on_off(row), row["access"], f"v{row['version']}", row["code_version"],
            properties,
        )  # fmt: skip
    if kind == "invocations":
        return (
            short_id(row["invocation_id"]), run_state(row["status"]), row["action"],
            row["invoked_by"], moment(row["requested_at"]),
        )  # fmt: skip
    if kind == "deliveries":
        endpoint = (names or {}).get(row["endpoint_id"], "?")
        return (
            short_id(row["delivery_id"]), run_state(row["state"]), endpoint,
            moment(row["received_at"]), row["error_code"] or "-",
        )  # fmt: skip
    if kind == "enrichments":
        if not technical:
            return (
                state_words(row["acceptance_state"], technical=False),
                record_name(row["target"], technical=False), property_words(row["property_path"]),
                shown_value(row["value"]), f"{row['confidence']:.2f}",
            )  # fmt: skip
        return (
            short_id(row["value_id"]), run_state(row["acceptance_state"]),
            record_name(row["target"]), row["property_path"], shown_value(row["value"]),
            f"{row['confidence']:.2f}",
        )  # fmt: skip
    raise ValueError(f"no integration kind {kind}")


def detail_lines(
    kind: str,
    row: Mapping[str, Any],
    names: Mapping[str, str] | None = None,
    *,
    technical: bool = True,
) -> list[str]:
    """The panel under the table: one ``Label       value`` line per fact (label padded to 12).

    Plain (``technical=False``) is only given for the enrichments kind so far: no value id, no
    enricher version, no property path.
    """
    pairs: list[tuple[str, str]]
    if kind == "apps":
        pairs = [("App", row["name"]), ("State", on_off(row)), ("Owner", str(row["owner"])),
                 ("Label", row["label"]), ("About", row["description"] or "-")]  # fmt: skip
    elif kind == "endpoints":
        pairs = [
            ("Path", f"/in/{row['app']}/{row['name']}"), ("State", on_off(row)),
            ("Mode", "dry-run (nothing is applied)" if row["dry_run"] else "live"),
            ("Auth", row["auth"]), ("Access", row["access"]),
            ("Acts as", row["service_actor"]), ("Owner", row["owner"]),
            ("Allowed", ", ".join(row["allowed_commands"])),
            ("Body cap", f"{row['max_body_bytes']} bytes"),
            ("Rate", f"{row['rate_per_minute']} per minute"),
        ]  # fmt: skip
    elif kind == "rules":
        pairs = [
            ("Rule", row["key"]), ("Title", row["title"]), ("State", on_off(row)),
            ("Mode", row["mode"]), ("Access", row["access"]), ("Acts as", row["service_actor"]),
            ("Owner", row["owner"]),
            ("Steps", ", ".join(step["command"] for step in row["then"])),
        ]  # fmt: skip
        if row.get("condition"):
            pairs.append(("If", row["condition"]))
    elif kind == "actions":
        pairs = [
            ("Action", row["name"]), ("Label", row["label"]), ("State", on_off(row)),
            ("Executor", row["executor"]), ("Access", row["access"]),
            ("Approval", "needs another person" if row["requires_approval"] else "none"),
            ("Effect", row["side_effect_class"]), ("Owner", row["owner"]),
            ("Parameters", ", ".join(p["name"] for p in row["parameters"]) or "-"),
        ]  # fmt: skip
    elif kind == "enrichers":
        pairs = [
            ("Enricher", row["name"]), ("State", on_off(row)), ("Access", row["access"]),
            ("Code", row["code_version"]), ("Owner", row["owner"]),
        ]  # fmt: skip
        pairs += [
            (f"  {p['name']}", f"{p['kind']}, {p['policy']} (threshold {p['threshold']})")
            for p in row["properties"]
        ]
    elif kind == "invocations":
        pairs = [
            ("Invocation", row["invocation_id"]),
            ("Action", f"{row['action']} v{row['action_version']}"),
            ("Status", run_state(row["status"])), ("By", row["invoked_by"]),
            ("Requested", moment(row["requested_at"])), ("Finished", moment(row["finished_at"])),
            ("Targets", str(len(row["targets"]))),
        ]  # fmt: skip
    elif kind == "deliveries":
        endpoint_name = (names or {}).get(row["endpoint_id"], "?")
        pairs = [
            ("Delivery", row["delivery_id"]),
            ("Endpoint", f"{endpoint_name} v{row['endpoint_version']}"),
            ("State", run_state(row["state"])), ("Received", moment(row["received_at"])),
            ("Size", f"{row['payload_size']} bytes"), ("Attempts", str(row["attempts"])),
            ("Error", f"{row['error_code']}: {row['error_message']}" if row["error_code"] else "-"),
        ]  # fmt: skip
    elif kind == "enrichments" and not technical:
        pairs = [
            ("State", state_words(row["acceptance_state"], technical=False)),
            ("Record", record_name(row["target"], technical=False)),
            ("Property", property_words(row["property_path"])),
            ("Proposed", shown_value(row["value"])),
            ("Confidence", f"{row['confidence']:.2f}"),
            ("Enricher", humanize(row["enricher"])),
            ("Produced", moment(row["produced_at"])),
        ]  # fmt: skip
        if row.get("reason"):
            pairs.append(("Reason", row["reason"]))
    elif kind == "enrichments":
        pairs = [
            ("Value", row["value_id"]), ("State", run_state(row["acceptance_state"])),
            ("Record", record_name(row["target"])), ("Property", row["property_path"]),
            ("Proposed", shown_value(row["value"])),
            ("Confidence", f"{row['confidence']:.2f}"),
            ("Enricher", f"{row['enricher']}@{row['enricher_version']}"),
            ("Produced", moment(row["produced_at"])),
        ]  # fmt: skip
        if row.get("reason"):
            pairs.append(("Reason", row["reason"]))
    else:
        raise ValueError(f"no integration kind {kind}")
    return [f"{label:<12}{value}" for label, value in pairs]
