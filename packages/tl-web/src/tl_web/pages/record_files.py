"""The Files tab of the record screen: ``?tab=files`` on the record page (P2-WEB1-T04).

A table of the record's current files the viewer may read (a hidden file is not listed, ADR-0016):
name, type and size, with a View link (the full viewer page) and a Download link per file. Page 1
of the first PDF is drawn as a picture; only that one, since at most two renders run at once. A
read the service does not offer, or one ``body_for`` maps, shows its reason in place of the rows;
any other exception propagates.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from tl_api.errors import body_for

from tl_web import present
from tl_web.pages.record import RecordCtx, Tab, tab
from tl_web.pages.viewer import is_pdf


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "headers": list(present.details.FILE_COLUMNS_NO_PAGES),
        "rows": [],
        "picture": "",
        "empty": f"Files unavailable: {reason}",
    }


def _files(ctx: RecordCtx) -> dict[str, Any]:
    try:
        files = ctx.client.list_record_files(ctx.record["id"])
    except NotImplementedError:
        return _unavailable("the file services are not installed yet")
    except Exception as exc:
        mapped = body_for(exc)
        if mapped is None:
            raise
        return _unavailable(mapped[1].message)
    rows = [
        {
            "cells": (
                f.filename,
                present.file_text.file_kind(f.content_type, f.filename),
                present.file_text.human_size(f.size),
            ),
            "view": f"/web/p/{ctx.project}/files/{f.file_id}/view",
            "download": f"/web/files/{f.file_id}/content?scope={quote(f.scope, safe='')}",
        }
        for f in files
    ]
    picture = ""
    for f in files:
        if is_pdf(f.content_type, f.filename):
            picture = f"/web/files/{f.file_id}/page1.png?scope={quote(f.scope, safe='')}"
            break
    return {
        "headers": list(present.details.FILE_COLUMNS_NO_PAGES),
        "rows": rows,
        "picture": picture,
        "empty": "" if files else "No files.",
    }


tab(Tab("files", "Files", "files.html", _files))
