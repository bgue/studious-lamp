# P0-I6-T06 — Composer with `#` and `@` completion

Status: ready
Tier: haiku
Labels: tui
Depends on: — (the `ClientInterface` feed methods and the fake are on the base)
Branch: `p0/i6a-t06-composer`

## Goal
`tl_tui/widgets/composer.py` is the modal in which a person writes a post: a one-line input with a list under it that offers records,
signal tags, codes, topics and people while a `#` or `@` token is being typed. Tab puts the highlighted candidate into the text; Enter posts
through `client.feed_post`. The module has the layout, bindings and constructor; two pure functions and the methods raise
`NotImplementedError`. A provided test file (10 tests) must pass. Opening the composer from the app (`p`) is not part of this ticket.

## Brief references (pasted)
> **21.4** Feed pane: `p` new post. "The composer autocompletes keys, codes, topics, and people on `#` and `@`."
> **21.2** `#NCR-P123-0042` record reference; `#area:A12` namespaced code; `#safety #hold #decision #urgent #fyi` signal tags; `#bevel-damage` topic; `@jsmith @crew:P-07 @party:acme-nde` mentions.
> Tab accepts an inline suggestion (brief 7.2: "Tab accepts it inline").

Learnings that apply:
- pyright is `standard` for `packages/tl-tui`; ruff limits lines to 100 columns (docstrings and comments too). Run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Provided tests live under `docs/tickets/P0-I6/provided/*.py.txt`; copy them into the test tree byte for byte. Do not edit the copy.
- Commit your report at `docs/reports/P0-I6/P0-I6-T06.md` (it is inside your Allowed paths).
- A fresh worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages.
- No new dependencies. Remove the `STUB` paragraph from every docstring you fill in.
- An `Input` built with a non-empty value outside a running app raises; create it in `compose()` (it is, in the stub) and set its cursor in `on_mount` (L-P0-I2-B6). `Input.Changed` fires once at mount with the initial value: that is fine here.
- `Static(..., markup=False)` and `rich.text.Text` for anything that holds user data (L-P0-I3-7). Do not name attributes after Textual DOM properties (L-P0-I2-B4).
- A priority `Binding("tab", ...)` on the screen beats focus movement; the action must do nothing when the list is not visible.
- Tests set `input.value` and `input.cursor_position` directly, then `await pilot.pause()`, because `Input.Changed` is delivered asynchronously (L-P0-I3-9).
- Drive tests with `helpers.run_pilot(app, scenario)`; there is no async pytest plugin (L-P0-I2-B2).

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-tui/src/tl_tui/widgets/composer.py (existing stub; layout, bindings and constructor are final)
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
```
```python
# packages/tl-tui/src/tl_tui/client.py (final): the two ClientInterface methods used
    def feed_post(self, cmd: PostToFeed) -> CommandResult: ...
    def feed_complete(self, scope: str, sigil: Literal["#", "@"], prefix: str, *, limit: int = 8) -> list[Completion]: ...
# tl_core.services.feed.PostToFeed(Command): actor, source, scope, body, importance="normal", post_id=None
# tl_core.services.feed_queries.Completion(text, kind, detail)   (text has no sigil)
# tl_core.services.commands.CommandResult: stream_id (the post id), key, version, events
# tl_tui.errors: CLIENT_ERRORS (tuple of exception types), describe_error(exc) -> str
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-tui/src/tl_tui/widgets/composer.py`
- `packages/tl-tui/src/tl_tui/widgets/prompt.py` (a modal with an `Input`)
- `packages/tl-tui/tests/fakes_feed.py` (`feed_complete` and `feed_post` of the fake)
- `docs/tickets/P0-I6/provided/a-test_composer.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/composer.py` (edit)
- `packages/tl-tui/tests/test_composer.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I6/P0-I6-T06.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I6/provided/a-test_composer.py.txt packages/tl-tui/tests/test_composer.py`
2. Implement `completion_token` and `apply_completion` first, then the screen's methods; delete the STUB paragraphs; add the imports you use.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-tui/tests/test_composer.py -q
just check
just test-tui
```
Expected: 10 tests pass; `just check` clean; `just test-tui` green.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report.

## Escalation triggers
- Stop and report *Blocked* if a test cannot pass without editing a file outside Allowed paths.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
