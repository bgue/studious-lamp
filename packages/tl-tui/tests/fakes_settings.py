"""In-memory settings for `FakeClient` (P0-I8): the `ClientInterface` settings group, no database.

It keeps the real definitions (the platform file) and the real value checks, and a small model of
the layers: the user value beats the project value beats the company value beats the default; a
company lock hides project values; every change is one history row with a fixed clock. Not
modelled: scheduled changes (`applies_at` is accepted and ignored) and pending effects.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from tl_core.services.errors import (
    ReasonRequiredError,
    RiskNotAcceptedError,
    SettingChangeNotFoundError,
    SettingLockedError,
    SettingNotLockableError,
    SettingRevertNotLatestError,
    SettingScopeError,
)
from tl_core.settings import definitions, get_definition
from tl_core.settings.layers import LayerRef, parse_layer
from tl_core.settings.types import EffectiveSetting, SettingChange, SettingDefinition
from tl_core.settings.values import normalise
from tl_core.settings.views import SettingView

_SETTINGS_T0 = datetime(2026, 10, 9, 9, 0, 0, tzinfo=UTC)
_MISSING: Any = object()


class FakeSettingsSupport:
    """Mixin for `FakeClient`: call `_init_settings()` from its `__init__`."""

    def _init_settings(self) -> None:
        self._values: dict[tuple[str, str], Any] = {}  # (key, layer name) -> value
        self._locks: dict[str, dict[str, Any]] = {}  # key -> {"locked": bool, "bounds": ...}
        self._changes: dict[str, list[SettingChange]] = defaultdict(list)
        self._undo: dict[tuple[str, str], list[Any]] = defaultdict(list)  # prior values
        self._setting_seq = 0
        self.setting_actor = "user:dev"
        self.setting_calls: list[tuple[str, dict[str, Any]]] = []  # (method, arguments)

    # --- seeding ----------------------------------------------------------------------------

    def seed_setting(self, key: str, layer: str, value: Any) -> None:
        """Put a value at a layer without validation or history (a starting state)."""
        get_definition(key)
        self._values[(key, parse_layer(layer).name)] = value

    # --- reads ------------------------------------------------------------------------------

    def _view(self, key: str, project: str | None, user: str | None) -> SettingView:
        defn = get_definition(key)
        lock = self._locks.get(key, {})
        locked = bool(lock.get("locked"))
        chain: list[LayerRef] = []
        if user is not None and "user" in defn.scopes:
            chain.append(LayerRef("user", user))
        if project is not None and "project" in defn.scopes and not locked:
            chain.append(LayerRef("project", project))
        if "company" in defn.scopes:
            chain.append(LayerRef("company", None))
        value, origin = deepcopy(defn.default), "default"
        for ref in chain:
            found = self._values.get((key, ref.name), _MISSING)
            if found is not _MISSING:
                value, origin = deepcopy(found), ref.kind
                break
        viewed = chain[0] if chain else None
        # a locked key still shows the project's viewed layer as unmodified
        modified = viewed is not None and (key, viewed.name) in self._values
        effective = EffectiveSetting(
            key=key,
            value=value,
            origin=origin,  # type: ignore[arg-type]
            modified_here=modified,
            locked=locked,
            bounds=deepcopy(lock.get("bounds")),
            scheduled=[],
            pending_effect=None,
        )
        return SettingView(definition=defn, effective=effective)

    def _view_at(self, key: str, layer: str) -> SettingView:
        ref = parse_layer(layer)
        return self._view(
            key,
            ref.ident if ref.kind == "project" else None,
            ref.ident if ref.kind == "user" else None,
        )

    def list_settings(
        self,
        *,
        project: str | None = None,
        user: str | None = None,
        prefix: str | None = None,
        modified_only: bool = False,
    ) -> list[SettingView]:
        self.setting_calls.append(("list_settings", {"project": project, "prefix": prefix}))
        views = [
            self._view(key, project, user)
            for key in sorted(definitions())
            if prefix is None or key.startswith(prefix)
        ]
        return [v for v in views if v.effective.modified_here or not modified_only]

    def get_setting(
        self, key: str, *, project: str | None = None, user: str | None = None
    ) -> SettingView:
        self.setting_calls.append(("get_setting", {"key": key, "project": project}))
        return self._view(key, project, user)

    def setting_history(self, key: str, *, layer: str | None = None) -> list[SettingChange]:
        get_definition(key)
        rows = self._changes.get(key, [])
        return [c for c in rows if layer is None or c.layer == layer]

    # --- writes -----------------------------------------------------------------------------

    def _log_change(self, key: str, layer: str, new: Any, reset: bool, reason: str | None) -> None:
        self._setting_seq += 1
        old = self._values.get((key, layer))
        self._undo[(key, layer)].append(old if (key, layer) in self._values else _MISSING)
        if reset:
            self._values.pop((key, layer), None)
        else:
            self._values[(key, layer)] = deepcopy(new)
        at = (_SETTINGS_T0 + timedelta(minutes=self._setting_seq)).isoformat()
        self._changes[key].append(
            SettingChange(
                seq=self._setting_seq,
                key=key,
                layer=layer,
                old_value=old,
                new_value=None if reset else deepcopy(new),
                reset=reset,
                actor=self.setting_actor,
                reason=reason,
                recorded_at=at.replace("+00:00", "Z"),
                applies_at=None,
            )
        )

    def _check_write(
        self, defn: SettingDefinition, layer: str, reason: str | None, accept_risk: bool
    ) -> LayerRef:
        ref = parse_layer(layer)
        if ref.kind not in defn.scopes:
            raise SettingScopeError(f"{defn.key} cannot be set at {layer}")
        if ref.kind == "project" and self._locks.get(defn.key, {}).get("locked"):
            raise SettingLockedError(f"{defn.key} is locked by the company")
        if defn.risk != "normal" and not (reason or "").strip():
            raise ReasonRequiredError(f"{defn.key} needs a reason")
        if defn.risk == "dangerous" and not accept_risk:
            raise RiskNotAcceptedError(f"{defn.key} is dangerous: accept the risk")
        return ref

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
        self.setting_calls.append(("set_setting", {"key": key, "layer": layer, "value": value}))
        defn = get_definition(key)
        ref = self._check_write(defn, layer, reason, accept_risk)
        checked = normalise(defn, value)
        self._log_change(key, ref.name, checked, False, reason)
        return self._view_at(key, layer)

    def reset_setting(
        self,
        key: str,
        *,
        layer: str,
        reason: str | None = None,
        accept_risk: bool = False,
        applies_at: datetime | None = None,
    ) -> SettingView:
        self.setting_calls.append(("reset_setting", {"key": key, "layer": layer}))
        defn = get_definition(key)
        ref = self._check_write(defn, layer, reason, accept_risk)
        self._log_change(key, ref.name, None, True, reason)
        return self._view_at(key, layer)

    def lock_setting(
        self,
        key: str,
        *,
        locked: bool,
        reason: str,
        bounds: dict[str, Any] | None = None,
    ) -> SettingView:
        self.setting_calls.append(("lock_setting", {"key": key, "locked": locked}))
        defn = get_definition(key)
        if not defn.lockable:
            raise SettingNotLockableError(f"{key} cannot be locked or bounded")
        self._locks[key] = {"locked": locked, "bounds": deepcopy(bounds)}
        return self._view_at(key, "company")

    def revert_setting(
        self,
        key: str,
        *,
        layer: str,
        seq: int,
        reason: str | None = None,
        accept_risk: bool = False,
    ) -> SettingView:
        self.setting_calls.append(("revert_setting", {"key": key, "layer": layer, "seq": seq}))
        get_definition(key)
        here = [c for c in self._changes.get(key, []) if c.layer == layer]
        if not any(c.seq == seq for c in here):
            raise SettingChangeNotFoundError(f"{key} has no change {seq} at {layer}")
        if here[-1].seq != seq:
            raise SettingRevertNotLatestError(f"change {seq} is not the latest at {layer}")
        prior = self._undo[(key, layer)].pop()
        if prior is _MISSING:
            self._values.pop((key, layer), None)
        else:
            self._values[(key, layer)] = prior
        self._changes[key] = [c for c in self._changes[key] if c.seq != seq]
        return self._view_at(key, layer)
