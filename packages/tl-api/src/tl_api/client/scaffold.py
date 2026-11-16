"""The scaffold module's read methods over HTTP (P2-I4B-T09b2), one per read route.

The same models the embedded client returns (``tl_mod_scaffold.views``: dataclasses, so they are
decoded with a ``TypeAdapter``). A missing or hidden scaffold is the service's
``RecordNotFoundError``, rebuilt from the 404 body. ``export_scaffolds`` returns the response text;
a format other than ``csv`` or ``jsonl`` is a ``ValueError`` raised before anything is sent.
"""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter
from tl_mod_scaffold import views as scaffold_views

from tl_api.client.base import ApiClientBase, quote

_PAGE: TypeAdapter[scaffold_views.ScaffoldPage] = TypeAdapter(scaffold_views.ScaffoldPage)
_DETAIL: TypeAdapter[scaffold_views.ScaffoldDetail] = TypeAdapter(scaffold_views.ScaffoldDetail)
_ROWS: TypeAdapter[list[scaffold_views.ScaffoldRow]] = TypeAdapter(list[scaffold_views.ScaffoldRow])


class ScaffoldApi(ApiClientBase):
    def list_scaffolds(
        self,
        project: str,
        *,
        state: str | None = None,
        tag: str | None = None,
        overdue: bool = False,
        limit: int = 200,
    ) -> scaffold_views.ScaffoldPage:
        """A project's scaffolds by key (``GET .../scaffolds``); ``total`` counts the matches."""
        data: Any = self._get_json(
            f"/projects/{quote(project)}/scaffolds",
            {"state": state, "tag": tag, "overdue": overdue, "limit": limit},
        )
        return _PAGE.validate_python(data)

    def get_scaffold(self, project: str, key: str) -> scaffold_views.ScaffoldDetail:
        """One scaffold with its inspections (``GET .../scaffolds/{key}``); 404 when missing."""
        data: Any = self._get_json(f"/projects/{quote(project)}/scaffolds/{quote(key)}")
        return _DETAIL.validate_python(data)

    def list_scaffolds_due(
        self, project: str, *, limit: int = 200
    ) -> list[scaffold_views.ScaffoldRow]:
        """Standing scaffolds due for inspection today or earlier (``GET .../scaffold-due``)."""
        data: Any = self._get_json(f"/projects/{quote(project)}/scaffold-due", {"limit": limit})
        return _ROWS.validate_python(data)

    def export_scaffolds(
        self,
        project: str,
        *,
        fmt: str = "csv",
        state: str | None = None,
        tag: str | None = None,
        overdue: bool = False,
    ) -> str:
        """The visible scaffolds as CSV or JSON lines (``GET .../scaffold-export``): the text."""
        if fmt not in scaffold_views.EXPORT_FORMATS:
            raise ValueError(scaffold_views.MSG_FORMAT)
        return self._send(
            "GET",
            f"/projects/{quote(project)}/scaffold-export",
            params={"format": fmt, "state": state, "tag": tag, "overdue": overdue},
        ).text
