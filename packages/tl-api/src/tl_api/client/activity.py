"""The activity read over HTTP (P2-INS-S1). Same name, parameters and return type as
``tl_tui.client.ClientInterface.activity``; an unknown or hidden record answers an empty page."""

from __future__ import annotations

from tl_core.insights.types import ActivityPage
from tl_core.services.errors import RecordNotFoundError

from tl_api.client.base import ApiClientBase, quote


class ActivityApi(ApiClientBase):
    def activity(
        self,
        record_id: str,
        *,
        revisions_only: bool = False,
        related: bool = True,
        before_seq: int | None = None,
        limit: int = 120,
    ) -> ActivityPage:
        params: dict[str, str | int | bool] = {
            "revisions_only": revisions_only,
            "related": related,
            "limit": limit,
        }
        if before_seq is not None:
            params["before_seq"] = before_seq
        try:
            data = self._get_json(f"/records/{quote(record_id)}/activity", params)
        except RecordNotFoundError:
            return ActivityPage(rows=[], next_before_seq=None)
        return self._model(ActivityPage, data)
