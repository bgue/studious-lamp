"""The one door from ``tl_web`` to the terminal's pure text modules (spec web-client-i1, section 6).

This is the only ``tl_web`` module that imports ``tl_tui``. It re-exports what the pages use, so
that the rows, panels, summaries, labels and action table of the web are the terminal's own
functions, and it never imports a Textual module (``widgets/*``, ``log_screen``, ``log_actions``):
importing any ``tl_web`` module leaves ``textual`` out of ``sys.modules``. If a pure function is
reachable only through a Textual import, a page stops and asks; it does not move terminal code.
"""

from __future__ import annotations

from typing import cast

from tl_tui import (
    action_ui,
    correspondence_text,
    details,
    display,
    document_text,
    labels_load,
    layout,
    log_text,
    rfi_text,
    text,
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
    "breadcrumb_text",
    "correspondence_text",
    "details",
    "display",
    "document_text",
    "find_technical",
    "key_label",
    "labels_load",
    "layout",
    "load_labels",
    "log_text",
    "plain_lines",
    "rfi_text",
    "stamp",
    "text",
    "visible_columns",
    "without_keys",
]


def as_client(reads: object) -> ClientInterface:
    """A ``WebReadClient`` as the ``ClientInterface`` the terminal's renderers take.

    The renderers call only the read methods ``WebReadClient`` mirrors (``reads.MIRRORS``); any
    other call raises ``UnsupportedRead`` there, so the narrow object is safe behind the wide type.
    """
    return cast(ClientInterface, reads)
