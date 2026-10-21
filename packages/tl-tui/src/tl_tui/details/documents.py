"""Details of a controlled document, read through ``get_document`` (the key is the number).

Every other record type stays on the generic rows until its screen ticket adds a module here.
"""

from __future__ import annotations

from typing import Any

from tl_tui.client import ClientInterface
from tl_tui.details import DetailRow, register
from tl_tui.details.generic import technical_rows
from tl_tui.display import Labels, code_label, humanize, type_label
from tl_tui.text import EMPTY, conformance_mark, timestamp


def _or_empty(value: Any) -> str:
    return EMPTY if value is None or value == "" else str(value)


@register("documents.Document")
def document_rows(
    client: ClientInterface, project: str, record: dict[str, Any], labels: Labels
) -> list[DetailRow]:
    view = client.get_document(project, str(record["key"]))
    current = EMPTY
    if view.current_revision_code:
        status = f" ({view.current_revision_status})" if view.current_revision_status else ""
        current = f"{view.current_revision_code}{status}"
    rows = [
        DetailRow("Type", type_label(labels, "documents.Document")),
        DetailRow("Number", view.number),
        DetailRow("Title", view.title),
    ]
    if view.description:
        rows.append(DetailRow("Description", view.description))
    rows += [
        DetailRow("State", humanize(view.state)),
        DetailRow("Document type", code_label(labels, "doc_type", view.doc_type)),
        DetailRow("Discipline", code_label(labels, "discipline", view.discipline)),
        DetailRow("Originator", _or_empty(view.originator)),
        DetailRow("Confidentiality", code_label(labels, "confidentiality", view.confidentiality)),
        DetailRow("Current revision", current),
    ]
    if view.superseded_by:
        rows.append(DetailRow("Replaced by", view.superseded_by))
    rows += [
        DetailRow("Created", timestamp(record.get("created_at"))),
        DetailRow("Updated", timestamp(record.get("updated_at"))),
        DetailRow("Conformance", conformance_mark(view.conformance)),
    ]
    return rows + technical_rows(record)
