"""Details of a schema package version, read through ``get_schema_package`` (P1-UX-T09d).

The labelled rows show in both modes and name the version in words (``Engineering, version
3.2.0``). The key (``name@version``), the content hash show only in technical mode
(``Key``, ``Content hash``), as the envelope rows do (``technical_rows``).
"""

from __future__ import annotations

from typing import Any

from tl_tui.client import ClientInterface
from tl_tui.details import DetailRow, register
from tl_tui.details.generic import technical_rows
from tl_tui.display import Labels, actor_label, humanize, type_label
from tl_tui.schema_text import plain_ref
from tl_tui.text import EMPTY, timestamp


@register("schemareg.SchemaPackage")
def schema_package_rows(
    client: ClientInterface, project: str, record: dict[str, Any], labels: Labels
) -> list[DetailRow]:
    detail = client.get_schema_package(str(record["id"]))
    rows = [
        DetailRow("Type", type_label(labels, "schemareg.SchemaPackage")),
        DetailRow("Package", plain_ref(detail.key)),
    ]
    if detail.title:
        rows.append(DetailRow("Title", detail.title))
    rows += [
        DetailRow("Kind", humanize(detail.kind)),
        DetailRow("State", humanize(detail.state)),
    ]
    if detail.project:
        rows.append(DetailRow("Project", detail.project))
    rows.append(DetailRow("Worst change", detail.worst_class or EMPTY))
    rows.append(DetailRow("Drafted by", actor_label(labels, detail.drafted_by)))
    if detail.submitted_by:
        rows.append(DetailRow("Submitted by", actor_label(labels, detail.submitted_by)))
    if detail.approved_by:
        rows.append(DetailRow("Approved by", actor_label(labels, detail.approved_by)))
    if detail.published_at:
        rows.append(DetailRow("Published", timestamp(detail.published_at)))
    if detail.changelog:
        rows.append(DetailRow("Changelog", detail.changelog))
    rows += [
        DetailRow("Created", timestamp(record.get("created_at"))),
        DetailRow("Updated", timestamp(record.get("updated_at"))),
        DetailRow("Key", detail.key, technical=True),
        DetailRow("Content hash", detail.content_sha256, technical=True),
    ]
    return rows + technical_rows(record)
