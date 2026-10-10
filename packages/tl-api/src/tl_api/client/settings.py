"""about:config over HTTP: the client side of the `/settings` routes (P0-I8-T08).

One method per route, with the names of the `tl_core.settings` service where there is one. A read
returns the models of ``tl_core.settings`` (``SettingView``, ``SettingChange``, ``SettingDiff``).
A write answers with the key as seen at the layer it changed. The token's actor is recorded and
the source is ``api``. Failures raise the embedded exception classes (``UnknownSettingError``,
``SettingLockedError``, ``InvalidSettingValueError``, ``ReasonRequiredError``,
``RiskNotAcceptedError``, ``SettingRevertNotLatestError`` and so on); an agent token gets
``ApiError`` 403 ``agent_must_propose`` for every write.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from tl_core.settings.types import SettingChange, SettingDiff
from tl_core.settings.views import SettingView

from tl_api.client.base import ApiClientBase, quote


class SettingsApi(ApiClientBase):
    def list_settings(
        self,
        *,
        project: str | None = None,
        user: str | None = None,
        prefix: str | None = None,
        modified_only: bool = False,
    ) -> list[SettingView]:
        """Every setting with its definition and state, sorted by key (``GET /settings``).

        ``modified_only`` keeps the settings set at the layer being viewed.
        """
        data = self._get_json(
            "/settings",
            {
                "project": project,
                "user": user,
                "prefix": prefix,
                "modified": True if modified_only else None,
            },
        )
        return self._models(SettingView, data)

    def get_setting(
        self, key: str, *, project: str | None = None, user: str | None = None
    ) -> SettingView:
        """One setting (``GET /settings/{key}``); the key goes through ``quote``."""
        data = self._get_json(f"/settings/{quote(key)}", {"project": project, "user": user})
        return self._model(SettingView, data)

    def setting_history(self, key: str, *, layer: str | None = None) -> list[SettingChange]:
        """Every change of the key, oldest first (``GET /settings/{key}/history``)."""
        data = self._get_json(f"/settings/{quote(key)}/history", {"layer": layer})
        return self._models(SettingChange, data)

    def set_setting(
        self,
        key: str,
        *,
        layer: str,
        value: Any,
        reason: str | None = None,
        accept_risk: bool = False,
        applies_at: datetime | None = None,
    ) -> SettingView:
        """Set a key at a layer (``PUT /settings/{key}``).

        ``applies_at`` (a time with a zone, in the future) schedules the change.
        """
        body: dict[str, Any] = {
            "layer": layer,
            "value": value,
            "reason": reason,
            "accept_risk": accept_risk,
        }
        if applies_at is not None:
            body["applies_at"] = applies_at.isoformat()
        data = self._send("PUT", f"/settings/{quote(key)}", json=body).json()
        return self._model(SettingView, data)

    def reset_setting(
        self,
        key: str,
        *,
        layer: str,
        reason: str | None = None,
        accept_risk: bool = False,
        applies_at: datetime | None = None,
    ) -> SettingView:
        """Take the layer's own value away (``POST /settings/{key}/reset``)."""
        body: dict[str, Any] = {"layer": layer, "reason": reason, "accept_risk": accept_risk}
        if applies_at is not None:
            body["applies_at"] = applies_at.isoformat()
        data = self._post_json(f"/settings/{quote(key)}/reset", body)
        return self._model(SettingView, data)

    def lock_setting(
        self,
        key: str,
        *,
        locked: bool,
        reason: str,
        bounds: dict[str, Any] | None = None,
    ) -> SettingView:
        """Lock a key for projects, or bound their values (``POST /settings/{key}/lock``)."""
        body: dict[str, Any] = {"locked": locked, "bounds": bounds, "reason": reason}
        data = self._post_json(f"/settings/{quote(key)}/lock", body)
        return self._model(SettingView, data)

    def revert_setting(
        self,
        key: str,
        *,
        layer: str,
        seq: int,
        reason: str | None = None,
        accept_risk: bool = False,
    ) -> SettingView:
        """Undo the latest change at a layer (``POST /settings/{key}/revert``)."""
        body: dict[str, Any] = {
            "layer": layer,
            "seq": seq,
            "reason": reason,
            "accept_risk": accept_risk,
        }
        data = self._post_json(f"/settings/{quote(key)}/revert", body)
        return self._model(SettingView, data)

    def diff_settings(self, left: str, right: str) -> list[SettingDiff]:
        """The keys whose effective value differs between two layers (``GET /settings/diff``)."""
        data = self._get_json("/settings/diff", {"left": left, "right": right})
        return self._models(SettingDiff, data)

    def export_settings(self, layer: str) -> str:
        """What a layer holds as a YAML document (``GET /settings/export``): the response text."""
        return self._send("GET", "/settings/export", params={"layer": layer}).text

    def import_settings(
        self,
        document: str,
        *,
        layer: str,
        reason: str | None = None,
        accept_risk: bool = False,
    ) -> list[str]:
        """Apply a YAML document to a layer, all or nothing (``POST /settings/import``).

        The answer is ``{"layer": ..., "keys": [...]}``; return the keys.
        """
        body: dict[str, Any] = {
            "layer": layer,
            "document": document,
            "reason": reason,
            "accept_risk": accept_risk,
        }
        data = self._post_json("/settings/import", body)
        return [str(k) for k in data["keys"]]
