"""Details of an engineering tag, read through ``get_tag`` (the key is the tag number) (P1-UX-T02).

The plain rows name the class and the lacking properties in words; the technical rows (key,
version, scope, schema hash) come from the generic envelope and show only in technical mode.
"""

from __future__ import annotations

from typing import Any

from tl_tui.client import ClientInterface
from tl_tui.details import DetailRow, register
from tl_tui.details.generic import technical_rows
from tl_tui.display import Labels, humanize, type_label
from tl_tui.tag_text import label_path, number_fits
from tl_tui.text import EMPTY, conformance_mark, timestamp


@register("engineering.Tag")
def tag_rows(
    client: ClientInterface, project: str, record: dict[str, Any], labels: Labels
) -> list[DetailRow]:
    view = client.get_tag(project, str(record["key"]))
    rows = [
        DetailRow("Type", type_label(labels, "engineering.Tag")),
        DetailRow("Number", view.number),
        DetailRow("Title", view.title),
        DetailRow("Class", humanize(view.class_code) if view.class_code else EMPTY),
        DetailRow("Status", humanize(view.status) if view.status else EMPTY),
        DetailRow("Number check", "ok" if number_fits(view) else "does not fit the pattern"),
        DetailRow("Conformance", conformance_mark(view.conformance)),
        DetailRow("Created", timestamp(record.get("created_at"))),
        DetailRow("Updated", timestamp(record.get("updated_at"))),
    ]
    rows += [
        DetailRow("Lacks", f"{label_path(issue.path)} {issue.message}") for issue in view.issues
    ]
    return rows + technical_rows(record)
