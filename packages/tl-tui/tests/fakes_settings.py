"""In-memory settings for `FakeClient` (P0-I8): the `ClientInterface` settings group, no database.

It keeps the real definitions (the platform file) and the real value checks, and a small model of
the layers: the user value beats the project value beats the company value beats the default; a
company lock hides project values; every change is one history row with a fixed clock.

The write rules are the service's: the same helpers (`require_layer`, `normalise`, `check_bounds`,
`check_bounds_shape`, `check_risk`, `clean_reason`), the same order of checks, no history row for a
change that changes nothing, and an undo that appends a row of its own. The messages that live
inside the service functions are copied here; `test_embedded_settings.py` runs the same script on
this fake and on the embedded client and compares the messages, so a drift fails there. Not
modelled: scheduled changes (`applies_at` is accepted and ignored) and pending effects.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from tl_core.services.errors import (
    ReasonRequiredError,
    SecretSettingUnavailableError,
    SettingChangeNotFoundError,
    SettingLockedError,
    SettingNotLockableError,
    SettingRevertNotLatestError,
)
from tl_core.settings import definitions, get_definition
from tl_core.settings.layers import LayerRef, parse_layer, require_layer
from tl_core.settings.service import check_risk, clean_reason
from tl_core.settings.types import EffectiveSetting, SettingChange, SettingDefinition
from tl_core.settings.values import check_bounds, check_bounds_shape, normalise, same_json
from tl_core.settings.views import SettingView

_SETTINGS_T0 = datetime(2026, 10, 9, 9, 0, 0, tzinfo=UTC)
_MISSING: Any = object()


class FakeSettingsSupport:
    """Mixin for `FakeClient`: call `_init_settings()` from its `__init__`."""

    def _init_settings(self) -> None:
        self._values: dict[tuple[str, str], Any] = {}  # (key, layer name) -> value
        self._locks: dict[str, dict[str, Any]] = {}  # key -> {"locked": bool, "bounds": ...}
        self._had_old: dict[int, bool] = {}  # change seq -> the layer held a value before it
        self._changes: dict[str, list[SettingChange]] = defaultdict(list)
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

    def _writable(self, key: str, layer: str) -> tuple[SettingDefinition, LayerRef]:
        defn = get_definition(key)
        if defn.sensitivity == "secret":
            raise SecretSettingUnavailableError(
                f"{key} is secret; secrets need a vault, which is not available yet (a human gate)"
            )
        ref = parse_layer(layer)
        require_layer(defn, ref)
        return defn, ref

    def _log_change(
        self, key: str, ref: LayerRef, new: Any, reset: bool, reason: str | None
    ) -> None:
        self._setting_seq += 1
        held = (key, ref.name) in self._values
        old = self._values.get((key, ref.name))
        self._had_old[self._setting_seq] = held
        if reset:
            self._values.pop((key, ref.name), None)
        else:
            self._values[(key, ref.name)] = deepcopy(new)
        at = (_SETTINGS_T0 + timedelta(minutes=self._setting_seq)).isoformat()
        self._changes[key].append(
            SettingChange(
                seq=self._setting_seq,
                key=key,
                layer=ref.name,
                old_value=deepcopy(old),
                new_value=None if reset else deepcopy(new),
                reset=reset,
                actor=self.setting_actor,
                reason=reason,
                recorded_at=at.replace("+00:00", "Z"),
                applies_at=None,
            )
        )

    def _change(
        self,
        key: str,
        layer: str,
        *,
        value: Any,
        reset: bool,
        reason: str | None,
        accept_risk: bool,
    ) -> SettingView:
        """``change_setting`` in miniature: the same checks in the same order."""
        defn, ref = self._writable(key, layer)
        clean = None if reset else normalise(defn, value)
        note = clean_reason(reason)
        if not reset and ref.kind != "company":
            lock = self._locks.get(key, {})
            if lock.get("locked"):
                raise SettingLockedError(
                    f"{key} is locked by the company; projects cannot change it"
                )
            check_bounds(defn, lock.get("bounds"), clean)
        check_risk(defn, note, accept_risk)
        holds = (key, ref.name) in self._values
        if reset:
            needed = holds
        else:
            needed = not (holds and same_json(self._values[(key, ref.name)], clean))
        if needed:
            self._log_change(key, ref, clean, reset, note)
        return self._view_at(key, layer)

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
        return self._change(
            key, layer, value=value, reset=False, reason=reason, accept_risk=accept_risk
        )

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
        return self._change(
            key, layer, value=None, reset=True, reason=reason, accept_risk=accept_risk
        )

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
            raise SettingNotLockableError(f"{key} cannot be locked or bounded by the company")
        if clean_reason(reason) is None:
            raise ReasonRequiredError(f"say why you are changing the lock on {key}")
        clean = check_bounds_shape(defn, bounds) if bounds else None
        self._locks[key] = {"locked": locked, "bounds": deepcopy(clean)}
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
        _, ref = self._writable(key, layer)
        here = [c for c in self._changes.get(key, []) if c.layer == ref.name]
        change = next((c for c in here if c.seq == seq), None)
        if change is None:
            raise SettingChangeNotFoundError(
                f"{key} has no change at seq {seq} on layer {ref.name}"
            )
        if here[-1].seq != seq:
            raise SettingRevertNotLatestError(
                f"change {seq} of {key} on {ref.name} is not the latest there; undoing it would "
                "also discard the later changes. Revert the latest first, or set the value you want"
            )
        if self._had_old[seq]:
            return self._change(
                key,
                layer,
                value=change.old_value,
                reset=False,
                reason=reason,
                accept_risk=accept_risk,
            )
        return self._change(
            key, layer, value=None, reset=True, reason=reason, accept_risk=accept_risk
        )
