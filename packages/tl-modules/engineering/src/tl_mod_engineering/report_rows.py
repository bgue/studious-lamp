"""The engineering module's line-level report (``tl report tags``; V3-P0b): the tag register.

Pages through ``registry.list_tags`` (the read ``tl tag ls`` makes; it has no view word) with its
own ``offset``, so a tag in service is a row and a superseded or deleted tag is not (the list's
default). A tag has no record id column: the tag number names the row.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Final

from sqlalchemy import Connection
from tl_core import confidentiality
from tl_core.modules import Report

from tl_mod_engineering import registry

#: The page size the report reads the list with (a monkeypatched value in the tests).
_PAGE: Final = 500
# TagRow has no description, system or ended_on field and the list read (registry.list_tags) does
# not select them, so the columns are the ones the row carries: title stands for the description.
TAG_COLUMNS: Final = ("tag", "class", "state", "title", "area")


def tag_rows(
    conn: Connection, scope: str, viewer: confidentiality.Viewer
) -> Iterator[Mapping[str, Any]]:
    offset = 0
    while True:
        page = registry.list_tags(conn, scope, limit=_PAGE, offset=offset)
        for tag in page:
            yield {
                "tag": tag.number,
                "class": tag.class_code,
                "state": tag.status,
                "title": tag.title,
                "area": tag.area,
            }
        offset += len(page)
        if len(page) < _PAGE:
            return


REPORTS: Final = (Report("tags", "Tag register", TAG_COLUMNS, tag_rows),)
