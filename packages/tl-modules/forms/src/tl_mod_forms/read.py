"""What the routes and the embedded client share (V3-F1a): one template version as the detail, the
JSON Schema of its answers or the SurveyJS model, with its ETag.

Read as the given viewer through ``tl_mod_forms.views``; a template the viewer may not read and an
unknown key or version are one miss (``None``).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Final, Literal

from sqlalchemy import Connection
from tl_core import confidentiality
from tl_core.forms.jsonschema import to_json_schema
from tl_core.forms.surveyjs import surveyjs_unsupported, to_surveyjs

from tl_mod_forms import views

Projection = Literal["jsonschema", "surveyjs"]
PROJECTIONS: Final = ("jsonschema", "surveyjs")
MSG_TEMPLATE: Final = "no such template"


def version_body(
    conn: Connection,
    key: str,
    version: int,
    projection: Projection | None,
    viewer: confidentiality.Viewer,
) -> tuple[str, Any] | None:
    """``(etag, body)`` of template ``key`` at ``version``, or ``None`` when the viewer may read
    none. The ETag is the content hash (a draft: its version) and the projection."""
    page = views.template_list(conn, key=key, limit=views.MAX_LIMIT, viewer=viewer)
    found = next((r for r in page.rows if r.version == version), None)
    if found is None:
        return None
    detail = views.template_detail(conn, found.id, viewer=viewer)
    if detail is None:
        return None
    row = detail.row
    etag = f'"{row.content_hash or f"draft{row.version}"}-{projection or "detail"}"'
    fmt = row.format_version or 2
    body: Any
    if projection == "jsonschema":
        body = to_json_schema(detail.fields, fmt)
    elif projection == "surveyjs":
        body = {
            "model": to_surveyjs(detail.fields, fmt),
            "unsupported": surveyjs_unsupported(detail.fields),
        }
    else:
        body = {
            "row": json.loads(json.dumps(asdict(row))),
            "fields": detail.fields,
            "accepts_as": detail.accepts_as,
        }
    return etag, body
