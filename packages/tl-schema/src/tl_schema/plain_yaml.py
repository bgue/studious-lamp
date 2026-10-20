"""Reading YAML that comes from a person: no anchors, no aliases, a bounded number of nodes.

A package is text a signed-in person sends. YAML aliases let a few hundred bytes stand for
billions of nodes (the "billion laughs" document), so they are refused outright, and the number of
nodes is capped as well. ``PlainYamlError`` says what was refused and never quotes the text.
"""

from __future__ import annotations

from typing import Any, cast

import yaml
from yaml.nodes import Node

MAX_NODES = 100_000


class PlainYamlError(yaml.YAMLError):
    """The text uses a YAML feature this reader does not take, or is too large."""


class _PlainLoader(yaml.SafeLoader):
    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self._nodes = 0

    def compose_node(self, parent: Node | None, index: Any) -> Node | None:
        me: Any = self  # PyYAML ships no type information for the event methods
        if me.check_event(yaml.AliasEvent):
            raise PlainYamlError("YAML aliases are not allowed in a package")
        event: Any = me.peek_event()
        if getattr(event, "anchor", None) is not None:
            raise PlainYamlError("YAML anchors are not allowed in a package")
        self._nodes += 1
        if self._nodes > MAX_NODES:
            raise PlainYamlError(f"the document has more than {MAX_NODES} nodes")
        return super().compose_node(parent, index)


def load_plain(text: str) -> Any:
    """Like ``yaml.safe_load`` for text without anchors, aliases or more than ``MAX_NODES`` nodes.

    Raises ``PlainYamlError`` (a ``yaml.YAMLError``) when the text uses one; very deep nesting is
    refused the same way.
    """
    loader = _PlainLoader(text)
    try:
        return loader.get_single_data()
    except RecursionError as exc:
        raise PlainYamlError("the document is nested too deeply") from exc
    finally:
        cast(Any, loader).dispose()
