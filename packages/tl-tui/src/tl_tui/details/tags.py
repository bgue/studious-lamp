"""Details of an engineering tag, read through ``get_tag`` (the key is the tag number) (P1-UX-T02).

Sections (P1-UX3; skill ``tui-layout``): the key facts (class, status, number check, conformance),
the number in its parts, and what the tag still lacks as a small table. The plain rows name the
class and the lacking properties in words; the technical rows (key, version, scope, schema hash)
come from the generic envelope and show only in technical mode. ``tag_content`` builds the rows
from a view already read; the Details tab and the tag register's panel both use it.
"""

from __future__ import annotations

from typing import Any

from tl_mod_engineering.views import TagView

from tl_tui.client import ClientInterface
from tl_tui.details import (
    TECHNICAL_SECTION,
    DetailRow,
    link_rows,
    record_rows,
    register,
    table_rows,
)
from tl_tui.details.generic import technical_rows
from tl_tui.display import Labels, code_label, humanize
from tl_tui.layout import Cell, state_style
from tl_tui.text import EMPTY, conformance_mark

FACTS = "Key facts"
NUMBER = "Number"
LACKS = "Lacks"
LACK_COLUMNS = ("Level", "Property", "Problem")


def number_fits(view: TagView) -> bool:
    """True when the number keeps the registry pattern."""
    return view.number_status == "ok"


def class_text(view: TagView) -> str:
    """The class in words (``Control valve``), ``—`` when the tag has none."""
    return humanize(view.class_code) if view.class_code else EMPTY


def label_path(path: str) -> str:
    """A property path as its labels: a leading ``psets`` is dropped, the rest humanized.

    ``psets.valve_data.body_material`` reads ``Valve data / Body material``.
    """
    parts = path.split(".")
    if parts and parts[0] == "psets":
        parts = parts[1:]
    return " / ".join(humanize(part) for part in parts)


def segment_word(labels: Labels | None, name: str, value: str) -> str:
    """A number part with its code-list label when the standards have one: ``47 (Unit 47, ...)``."""
    word = code_label(labels, name, value) if labels is not None else value
    return value if word == value else f"{value} ({word})"


def tag_content(
    view: TagView,
    labels: Labels,
    *,
    record: dict[str, Any] | None = None,
    client: ClientInterface | None = None,
) -> list[DetailRow]:
    """The sections of a tag. ``record`` (the envelope) adds the record dates and the technical
    envelope rows; ``client`` adds the links."""
    rows = [
        DetailRow("Class", class_text(view), section=FACTS),
        DetailRow("Status", humanize(view.status) if view.status else EMPTY, section=FACTS),
        DetailRow(
            "Number check",
            "ok" if number_fits(view) else "does not fit the pattern",
            section=FACTS,
        ),
        DetailRow("Conformance", conformance_mark(view.conformance), section=FACTS),
    ]
    for name, value in view.segments.items():
        rows.append(DetailRow(humanize(name), segment_word(labels, name, value), section=NUMBER))
    rows += [
        DetailRow(
            "",
            f"! {violation['segment'] or 'number'}: {violation['message']} ({violation['level']})",
            section=NUMBER,
        )
        for violation in view.violations
    ]
    if view.issues:
        lacks = [(issue.level, label_path(issue.path), issue.message) for issue in view.issues]
        rows += table_rows(
            f"{LACKS} ({len(lacks)})",
            LACK_COLUMNS,
            [(Cell(level, state_style(level)), path, message) for level, path, message in lacks],
        )
    elif view.conformance == "ok":
        rows.append(DetailRow("", "Nothing lacking", section=LACKS))
    else:
        rows.append(DetailRow("", "No detail loaded", section=LACKS))
    if client is not None:
        rows += link_rows(client, view.id)
    rows += record_rows(record) if record is not None else []
    rows += (
        technical_rows(record)
        if record is not None
        else [
            DetailRow("Number parts", _raw_segments(view), True, TECHNICAL_SECTION),
            DetailRow("Class code", view.class_code or EMPTY, True, TECHNICAL_SECTION),
        ]
    )
    return rows


def _raw_segments(view: TagView) -> str:
    return " ".join(f"{name}={value}" for name, value in view.segments.items()) or EMPTY


@register("engineering.Tag")
def tag_rows(
    client: ClientInterface, project: str, record: dict[str, Any], labels: Labels
) -> list[DetailRow]:
    view = client.get_tag(project, str(record["key"]))
    return tag_content(view, labels, record=record, client=client)
