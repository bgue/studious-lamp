"""Post composer: a one-line modal with completion after `#` and `@` (P0-I6-T06; brief 21.4).

"The composer autocompletes keys, codes, topics, and people on `#` and `@`." While the cursor is at
the end of a `#tag` or `@mention` being typed, a list under the input offers the candidates that
``client.feed_complete`` returns. Down and Up move in the list, Tab puts the highlighted candidate
into the text, Esc closes the list (a second Esc cancels), Enter or Ctrl+S posts. The composer
parses nothing: the service reads the tags when the post is made.

STUB (P0-I6-T06): the functions and methods marked STUB raise NotImplementedError.
"""

from __future__ import annotations

import re
from typing import ClassVar, Literal

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from tl_core.services.feed_queries import Completion

from tl_tui.client import ClientInterface

PLACEHOLDER = "Say something. # for records and tags, @ for people"
_TOKEN = re.compile(r"(?<![\w@#])([#@])([\w.:/-]*)$")


def completion_token(text: str, cursor: int) -> tuple[Literal["#", "@"], str, int] | None:
    """The `#` or `@` token the cursor is at the end of: ``(sigil, typed prefix, start offset)``.

    ``"see #FV-1"`` with the cursor at 9 gives ``("#", "FV-1", 4)``. A sigil starts a token only at
    the start of the text or after a character that is not a word character, `#` or `@` (``a#b`` and
    ``me@site.org`` are not tokens). The prefix is the word characters, ``.``, ``:``, ``/`` and
    ``-`` after the sigil, up to the cursor. ``None`` when the cursor is not at the end of such a
    token (for example after a space). Hint: ``_TOKEN`` matches the end of ``text[:cursor]``.

    STUB: replace this paragraph and the body (P0-I6-T06).
    """
    raise NotImplementedError


def apply_completion(
    text: str, cursor: int, start: int, sigil: str, candidate: str
) -> tuple[str, int]:
    """``text`` with the token from ``start`` to ``cursor`` replaced by ``sigil + candidate``.

    A space is added after it unless the text after the cursor already begins with one. Returns the
    new text and the new cursor offset: just after the inserted text and that space (when a space
    was already there, just after it).

    STUB: replace this paragraph and the body (P0-I6-T06).
    """
    raise NotImplementedError


class ComposerScreen(ModalScreen[str | None]):
    """Dismisses with the id of the new post, or ``None`` when cancelled."""

    KEY_HINTS: ClassVar[str] = "Enter post  Tab complete  Up/Down choose  Esc close/cancel"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("down", "choose(1)", "Next", show=False),
        Binding("up", "choose(-1)", "Previous", show=False),
        Binding("tab", "accept", "Complete", show=False, priority=True),
        Binding("ctrl+s", "submit", "Post", show=False),
    ]

    DEFAULT_CSS = """
    ComposerScreen { align: center middle; }
    ComposerScreen > Vertical {
        width: 70%;
        height: auto;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    ComposerScreen #composer-title { text-style: bold; }
    ComposerScreen #composer-popup { height: auto; max-height: 8; display: none; }
    ComposerScreen #composer-error { color: $error; height: auto; }
    """

    def __init__(
        self,
        client: ClientInterface,
        scope: str,
        *,
        actor: str = "user:dev",
        prefill: str = "",
        limit: int = 8,
    ) -> None:
        super().__init__()
        self.client = client
        self.scope = scope
        self.actor = actor
        self.prefill = prefill
        self.limit = limit
        self.candidates: list[Completion] = []
        self.token: tuple[Literal["#", "@"], str, int] | None = None
        self.popup_closed = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"New post · {self.scope.removeprefix('project:')}", id="composer-title")
            yield Input(
                value=self.prefill,
                placeholder="Say something. # for records and tags, @ for people",
                id="composer-input",
            )
            yield OptionList(id="composer-popup")
            yield Static("", id="composer-error", markup=False)

    def on_mount(self) -> None:
        """Focus ``#composer-input`` and put its cursor at the end of the prefill.


        STUB: replace this paragraph and the body (P0-I6-T06).
        """
        raise NotImplementedError

    @property
    def popup_visible(self) -> bool:
        """True when there are candidates and the list was not closed with Esc.


        STUB: replace this paragraph and the body (P0-I6-T06).
        """
        raise NotImplementedError

    def on_input_changed(self, event: Input.Changed) -> None:
        """Stop the event, clear ``#composer-error``, reopen the list (``popup_closed = False``) and
        ``_refresh_popup``.

        STUB: replace this paragraph and the body (P0-I6-T06).
        """
        raise NotImplementedError

    def _refresh_popup(self) -> None:
        """Recompute ``token`` from the input's value and cursor with ``completion_token``. With a
        token, ``candidates = client.feed_complete(scope, sigil, prefix, limit=self.limit)``; a
        ``CLIENT_ERRORS`` error is shown in ``#composer-error`` and leaves no candidates. Rebuild
        ``#composer-popup``: one `Option(Text(f"{c.text}   {c.detail}"), id=str(n))` per candidate,
        highlight the first (``None`` when there are none), and show the list (``styles.display =
        "block"``) only when ``popup_visible``, else hide it (``"none"``).

        STUB: replace this paragraph and the body (P0-I6-T06).
        """
        raise NotImplementedError

    def action_choose(self, delta: int) -> None:
        """Down (+1) or Up (-1): move the list's highlight, clamped. Does nothing when the list
        is not visible.

        STUB: replace this paragraph and the body (P0-I6-T06).
        """
        raise NotImplementedError

    def action_accept(self) -> None:
        """Tab: put the highlighted candidate into the input with ``apply_completion`` (using the
        token's sigil and start and the input's cursor), set the input's value and cursor. Does
        nothing when the list is not visible.

        STUB: replace this paragraph and the body (P0-I6-T06).
        """
        raise NotImplementedError

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Stop the event and ``action_submit``.


        STUB: replace this paragraph and the body (P0-I6-T06).
        """
        raise NotImplementedError

    def action_submit(self) -> None:
        """Enter or Ctrl+S: a blank body shows "Write something first" in ``#composer-error`` and
        posts nothing. Otherwise ``client.feed_post(PostToFeed(actor=self.actor, source="tui",
        scope=self.scope, body=<the input's value, unstripped>))`` and
        ``dismiss(result.stream_id)``. A ``CLIENT_ERRORS`` error shows ``describe_error`` in
        ``#composer-error``, keeps the text, and the screen stays open.

        STUB: replace this paragraph and the body (P0-I6-T06).
        """
        raise NotImplementedError

    def action_cancel(self) -> None:
        """Esc: when the list is visible, close it (``popup_closed = True``, hide it) and stay;
        otherwise ``dismiss(None)``.

        STUB: replace this paragraph and the body (P0-I6-T06).
        """
        raise NotImplementedError
