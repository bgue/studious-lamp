"""The Checks read and the telemetry write over HTTP (P2-INS S2).

Same names and parameters as ``tl_tui.client.ClientInterface``. ``note_need`` never raises: a
refusal, a rate limit or a transport failure is dropped (a screen must not stumble on telemetry).
"""

from __future__ import annotations

from tl_core.insights.types import CheckFinding

from tl_api.client.base import ApiClientBase, quote


class InsightsApi(ApiClientBase):
    def checks(self, record_id: str) -> list[CheckFinding]:
        """What needs attention on the record (404 `RecordNotFoundError` when hidden or unknown)."""
        return self._models(CheckFinding, self._get_json(f"/records/{quote(record_id)}/checks"))

    def note_need(
        self, *, request_kind: str, trigger: str, record_type: str, record_id: str | None = None
    ) -> None:
        """Tell the server a need was shown. Every failure is dropped."""
        body = {
            "request_kind": request_kind,
            "trigger": trigger,
            "record_type": record_type,
            "record_id": record_id,
        }
        try:
            self._send("POST", "/insights/needs", json=body)
        except Exception:
            return
