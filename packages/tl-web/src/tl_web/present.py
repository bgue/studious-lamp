"""The one door from ``tl_web`` to the terminal's pure text modules (spec web-client-i1, section 6).

This is the only ``tl_web`` module that imports ``tl_tui``. It re-exports what the pages use, so
that the rows, panels, summaries, labels and action table of the web are the terminal's own
functions, and it never imports a Textual module (``widgets/*``, ``log_screen``, ``log_actions``):
importing any ``tl_web`` module leaves ``textual`` out of ``sys.modules``. If a pure function is
reachable only through a Textual import, a page stops and asks; it does not move terminal code.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from tl_tui import (
    action_ui,
    awp_text,
    correspondence_text,
    cwa_text,
    details,
    display,
    document_text,
    file_text,
    item_text,
    labels_load,
    layout,
    links_text,
    location_text,
    log_text,
    materials_text,
    mto_text,
    package_text,
    path_text,
    properties_text,
    receipt_text,
    record_text,
    rfi_text,
    text,
    thread_text,
    trace_text,
    wbs_text,
)
from tl_tui.action_ui import ACTION_UI, ActionUi, FormField, stamp, without_keys
from tl_tui.client import ClientInterface
from tl_tui.display import REFUSAL, Labels, find_technical
from tl_tui.labels_load import load_labels
from tl_tui.layout import Page, plain_lines
from tl_tui.log_text import breadcrumb_text, key_label, visible_columns

__all__ = [
    "ACTION_UI",
    "REFUSAL",
    "ActionUi",
    "FormField",
    "Labels",
    "Page",
    "action_ui",
    "as_client",
    "page_blocks",
    "state_tone",
    "web_summary",
    "awp_text",
    "breadcrumb_text",
    "correspondence_text",
    "cwa_text",
    "details",
    "display",
    "document_text",
    "file_text",
    "find_technical",
    "item_text",
    "key_label",
    "labels_load",
    "layout",
    "links_text",
    "load_labels",
    "location_text",
    "log_text",
    "materials_text",
    "mto_text",
    "package_text",
    "path_text",
    "plain_lines",
    "properties_text",
    "receipt_text",
    "record_text",
    "rfi_text",
    "stamp",
    "text",
    "tone",
    "thread_text",
    "trace_text",
    "visible_columns",
    "wbs_text",
    "without_keys",
]


_TONES = {"green": "done", "yellow": "waiting", "red": "bad"}


def tone(style: str) -> str:
    """The badge tone of a ``layout`` style word: green done, yellow waiting, red bad, else
    neutral."""
    return _TONES.get(style, "neutral")


def web_summary(text: str) -> str:
    """The web's status line: the terminal's `` | `` between facts shown as `` · ``."""
    return text.replace(" | ", " · ")


def state_tone(text: str) -> str:
    """The badge tone of a state's words (``layout.state_style``)."""
    return tone(layout.state_style(text))


def page_blocks(items: Sequence[object]) -> list[tuple[str, Any]]:
    """The items of a ``Section`` grouped for HTML: consecutive ``Prop`` items are one
    ``("props", [Prop, ...])``, consecutive ``TableRow`` items with the same columns one
    ``("table", [TableRow, ...])``, and a ``str`` is a ``("line", str)``."""
    blocks: list[tuple[str, Any]] = []
    for item in items:
        if isinstance(item, layout.Prop):
            if blocks and blocks[-1][0] == "props":
                blocks[-1][1].append(item)
            else:
                blocks.append(("props", [item]))
        elif isinstance(item, layout.TableRow):
            if blocks and blocks[-1][0] == "table" and blocks[-1][1][0].columns == item.columns:
                blocks[-1][1].append(item)
            else:
                blocks.append(("table", [item]))
        else:
            blocks.append(("line", item))
    return blocks


def as_client(reads: object) -> ClientInterface:
    """A ``WebReadClient`` as the ``ClientInterface`` the terminal's renderers take.

    The renderers call only the read methods ``WebReadClient`` mirrors (``reads.MIRRORS``); any
    other call raises ``UnsupportedRead`` there, so the narrow object is safe behind the wide type.
    """
    return cast(ClientInterface, reads)
