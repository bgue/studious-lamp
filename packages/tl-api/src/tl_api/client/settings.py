"""about:config over HTTP: the client side of the `/settings` routes (P0-I8-T08).

STUB (P0-I8-T08): remove this paragraph when every method has a body.

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

from tl_api.client.base import ApiClientBase


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

        STUB (P0-I8-T08): remove this paragraph when you implement the body.

        Query parameters: ``project``, ``user``, ``prefix`` and ``modified`` (``True`` only when
        ``modified_only``; leave it out otherwise).
        """
        raise NotImplementedError("STUB: P0-I8-T08")

    def get_setting(
        self, key: str, *, project: str | None = None, user: str | None = None
    ) -> SettingView:
        """One setting (``GET /settings/{key}``); the key goes through ``quote``.

        STUB (P0-I8-T08): remove this paragraph when you implement the body.
        """
        raise NotImplementedError("STUB: P0-I8-T08")

    def setting_history(self, key: str, *, layer: str | None = None) -> list[SettingChange]:
        """Every change of the key, oldest first (``GET /settings/{key}/history``).

        STUB (P0-I8-T08): remove this paragraph when you implement the body.
        """
        raise NotImplementedError("STUB: P0-I8-T08")

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

        STUB (P0-I8-T08): remove this paragraph when you implement the body.

        The body has ``layer``, ``value``, ``reason``, ``accept_risk`` and ``applies_at`` (an ISO
        text, or left out when None; build it with ``applies_at.isoformat()``).
        """
        raise NotImplementedError("STUB: P0-I8-T08")

    def reset_setting(
        self,
        key: str,
        *,
        layer: str,
        reason: str | None = None,
        accept_risk: bool = False,
        applies_at: datetime | None = None,
    ) -> SettingView:
        """Take the layer's own value away (``POST /settings/{key}/reset``).

        STUB (P0-I8-T08): remove this paragraph when you implement the body.
        """
        raise NotImplementedError("STUB: P0-I8-T08")

    def lock_setting(
        self,
        key: str,
        *,
        locked: bool,
        reason: str,
        bounds: dict[str, Any] | None = None,
    ) -> SettingView:
        """Lock a key for projects, or bound their values (``POST /settings/{key}/lock``).

        STUB (P0-I8-T08): remove this paragraph when you implement the body.
        """
        raise NotImplementedError("STUB: P0-I8-T08")

    def revert_setting(
        self,
        key: str,
        *,
        layer: str,
        seq: int,
        reason: str | None = None,
        accept_risk: bool = False,
    ) -> SettingView:
        """Undo the latest change at a layer (``POST /settings/{key}/revert``).

        STUB (P0-I8-T08): remove this paragraph when you implement the body.
        """
        raise NotImplementedError("STUB: P0-I8-T08")

    def diff_settings(self, left: str, right: str) -> list[SettingDiff]:
        """The keys whose effective value differs between two layers (``GET /settings/diff``).

        STUB (P0-I8-T08): remove this paragraph when you implement the body.
        """
        raise NotImplementedError("STUB: P0-I8-T08")

    def export_settings(self, layer: str) -> str:
        """What a layer holds as a YAML document (``GET /settings/export``): the response text.

        STUB (P0-I8-T08): remove this paragraph when you implement the body.
        """
        raise NotImplementedError("STUB: P0-I8-T08")

    def import_settings(
        self,
        document: str,
        *,
        layer: str,
        reason: str | None = None,
        accept_risk: bool = False,
    ) -> list[str]:
        """Apply a YAML document to a layer, all or nothing (``POST /settings/import``).

        STUB (P0-I8-T08): remove this paragraph when you implement the body.

        The answer is ``{"layer": ..., "keys": [...]}``; return the keys.
        """
        raise NotImplementedError("STUB: P0-I8-T08")
