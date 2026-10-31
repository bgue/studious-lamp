"""Details of a controlled document, read through ``get_document`` (the key is the number).

Sections (P1-UX3; skill ``tui-layout``): the description, the key facts (current revision first),
the revisions, the files of the current revision and the links, a stale one marked. The document
register's panel builds the same sections (``tl_tui.document_text``), with its own live file list.
Every other record type stays on the generic rows until its screen ticket adds a module here.
"""

from __future__ import annotations

from typing import Any

from tl_tui.client import ClientInterface
from tl_tui.details import DetailRow, file_rows, record_rows, register
from tl_tui.details.generic import technical_rows
from tl_tui.display import Labels
from tl_tui.document_text import (
    document_head_rows,
    document_link_rows,
    document_technical_rows,
    file_revision,
)


@register("documents.Document")
def document_rows(
    client: ClientInterface, project: str, record: dict[str, Any], labels: Labels
) -> list[DetailRow]:
    view = client.get_document(project, str(record["key"]))
    revision = file_revision(view)
    return [
        *document_head_rows(view, labels),
        *(
            file_rows(client, revision.id, {r.sha256: r.page_count for r in revision.renditions})
            if revision is not None
            else [DetailRow("", "No files", section="Files")]
        ),
        *document_link_rows(view, labels),
        *record_rows(record),
        *document_technical_rows(view, record),
        *technical_rows(record),
    ]
