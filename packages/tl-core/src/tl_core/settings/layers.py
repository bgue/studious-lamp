"""Setting layers: ``company``, ``project:<id>`` and ``user:<id>`` (brief 30.2).

A layer names where a value is set. It maps to the ledger like this: the stream of a key at a layer
is ``setting:<layer>:<key>`` (stream type ``core.Setting``) and the event scope is ``project:<id>``
for a project layer, else ``company``. Only UI keys (``ui.*``) have a user layer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from tl_core.services.errors import SettingScopeError
from tl_core.settings.display import shown
from tl_core.settings.types import SettingDefinition

SETTING_STREAM_TYPE = "core.Setting"
USER_KEY_PREFIX = "ui."

LayerKind = Literal["company", "project", "user"]
_PROJECT_ID = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_USER_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}")


@dataclass(frozen=True)
class LayerRef:
    """A parsed layer. ``ident`` is the project or user id, None for the company."""

    kind: LayerKind
    ident: str | None = None

    @property
    def name(self) -> str:
        """``company``, ``project:P123`` or ``user:alice``."""
        return "company" if self.ident is None else f"{self.kind}:{self.ident}"

    @property
    def scope(self) -> str:
        """The ledger scope of an event at this layer."""
        return f"project:{self.ident}" if self.kind == "project" else "company"


COMPANY = LayerRef("company")


def parse_layer(text: str) -> LayerRef:
    """``company``, ``project:<id>`` or ``user:<id>`` as a :class:`LayerRef`.

    Raises ``SettingScopeError`` for anything else, including the default layer: nobody sets the
    platform default at run time.
    """
    if text == "company":
        return COMPANY
    kind, _, ident = text.partition(":")
    if kind == "project" and _PROJECT_ID.fullmatch(ident):
        return LayerRef("project", ident)
    if kind == "user" and _USER_ID.fullmatch(ident):
        return LayerRef("user", ident)
    raise SettingScopeError(f"{shown(text)} is not a layer: use company, project:<id> or user:<id>")


def project_of_scope(scope: str) -> str | None:
    """``P123`` for the scope ``project:P123``; None for ``company``.

    What code that knows a ledger scope passes as ``project=`` to the settings reads.
    """
    kind, _, ident = scope.partition(":")
    return ident if kind == "project" and ident else None


def stream_id(layer: LayerRef, key: str) -> str:
    """The ledger stream of ``key`` at ``layer``."""
    return f"setting:{layer.name}:{key}"


def allows_layer(defn: SettingDefinition, kind: LayerKind) -> bool:
    """Whether a value of ``defn`` may be set at a layer of this kind.

    The definition's ``scopes`` must list it; the user layer also needs a ``ui.`` key.
    """
    if kind == "user":
        return "user" in defn.scopes and defn.key.startswith(USER_KEY_PREFIX)
    return kind in defn.scopes


def require_layer(defn: SettingDefinition, layer: LayerRef) -> None:
    """Raise ``SettingScopeError`` unless ``defn`` may be set at ``layer``."""
    if allows_layer(defn, layer.kind):
        return
    if layer.kind == "user" and "user" in defn.scopes:
        raise SettingScopeError(f"{defn.key} is not a UI key; only ui.* keys have a user layer")
    allowed = [k for k in ("company", "project", "user") if allows_layer(defn, k)]  # pyright: ignore[reportArgumentType]
    where = ", ".join(allowed) if allowed else "nowhere (it is a platform default only)"
    raise SettingScopeError(
        f"{defn.key} cannot be set at the {layer.kind} layer; it is set at: {where}"
    )
