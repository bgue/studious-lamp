"""The user layer takes ``ui.*`` and ``tui.*`` keys only (P2-I5-T12a, decision D31)."""

from __future__ import annotations

import pytest
from tl_core.services.errors import SettingScopeError
from tl_core.settings.layers import LayerRef, allows_layer, require_layer
from tl_core.settings.types import SettingDefinition


def defn(key: str, scopes: list[str]) -> SettingDefinition:
    return SettingDefinition.model_validate(
        {
            "key": key,
            "type": "string",
            "default": "x",
            "description": "d",
            "scopes": scopes,
            "since": "0.1.0",
        }
    )


@pytest.mark.parametrize("key", ["ui.density", "tui.landing"])
def test_a_ui_or_tui_key_is_settable_at_the_user_layer(key: str) -> None:
    d = defn(key, ["platform", "user"])
    assert allows_layer(d, "user")
    require_layer(d, LayerRef("user", "frank"))


def test_a_tui_key_not_scoped_to_user_is_still_refused() -> None:
    d = defn("tui.other", ["platform", "company"])
    assert not allows_layer(d, "user")
    with pytest.raises(SettingScopeError):
        require_layer(d, LayerRef("user", "frank"))


def test_a_non_ui_user_scoped_key_is_refused_naming_both_prefixes() -> None:
    d = defn("feed.reactions", ["platform", "user"])
    assert not allows_layer(d, "user")
    with pytest.raises(SettingScopeError, match=r"ui\.\* and tui\.\*"):
        require_layer(d, LayerRef("user", "frank"))
