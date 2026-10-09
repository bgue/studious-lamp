"""Feed pane: the activity feed of a project, a record or a hashtag (P0-I6-T04; brief 21.4).

Sketch 6 is the layout. One option per feed item, newest first. A post shows ``author · time``, its
body with `#tags` and `@mentions` highlighted, and a line of reactions and suggestions; an event
card is one line (``▤ jsmith created 14 records (P1-REC-0001, ...) · 09:15``). A tab strip filters
(All, Posts, Events, #hold). The pane reads and writes only through `ClientInterface` and posts
messages for what it cannot do itself: `PostRequested` (the app opens the composer) and
`OpenRecord`.

STUB (P0-I6-T04): the pure functions and the methods marked STUB raise NotImplementedError.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import OptionList
from tl_core.feed.types import FeedItem, Reaction
from tl_core.services.feed_queries import FeedSuggestion

from tl_tui.client import ClientInterface

Filter = Literal["all", "posts", "events", "hold"]
FILTERS: tuple[Filter, ...] = ("all", "posts", "events", "hold")
FILTER_LABELS: dict[Filter, str] = {
    "all": "All",
    "posts": "Posts",
    "events": "Events",
    "hold": "#hold",
}
PAGE_SIZE = 50
MAX_LABELS = 3
TAG_STYLES: dict[str, str] = {
    "record": "bold underline",
    "signal": "bold red",
    "code": "bold cyan",
    "topic": "cyan",
    "mention": "magenta",
}


def author_text(actor: str) -> str:
    """``mlee`` for ``user:mlee``; agents read ``agent:triage ⚙``; other actors as they are.

    STUB: replace this paragraph and the body (P0-I6-T04).
    """
    raise NotImplementedError


def clock(item: FeedItem) -> str:
    """``09:42`` (UTC, ``%H:%M``) from the item's time.

    STUB: replace this paragraph and the body (P0-I6-T04).
    """
    raise NotImplementedError


def tabs_text(active: Filter) -> str:
    """``[All] Posts Events #hold``: the labels of ``FILTERS`` joined by a space, the active one in
    brackets.

    STUB: replace this paragraph and the body (P0-I6-T04).
    """
    raise NotImplementedError


def labels_suffix(item: FeedItem, labels: dict[str, str]) -> str:
    """`` (K1, K2, K3 +2)`` for the item's records that have a label: the first ``MAX_LABELS``
    joined by ``, ``, then `` +N`` for the rest; ``""`` when no record has a label.

    STUB: replace this paragraph and the body (P0-I6-T04).
    """
    raise NotImplementedError


def reactions_line(item: FeedItem, suggestions: list[FeedSuggestion]) -> str:
    """``+1 1 · ack 3 · proposal: constraint on FV-1001 [a]``.

    Parts joined by `` · ``: ``<reaction> <count>`` for each reaction, sorted by reaction name, then
    ``proposal: constraint on <record_key or record_id> [a]`` for each suggestion. ``""`` when
    there are none.

    STUB: replace this paragraph and the body (P0-I6-T04).
    """
    raise NotImplementedError


def item_text(item: FeedItem, labels: dict[str, str], suggestions: list[FeedSuggestion]) -> Text:
    """The option text of one item (a `rich.text.Text`, so brackets are never markup).

    A card is one line, dim: ``▤ <summary><labels_suffix> · <clock>``.

    A post is ``<author_text> · <clock>`` (bold; with `` !`` appended for high importance unless
    retracted), a newline, then the body. A retracted post shows its summary (``[retracted]``) dim
    and italic. Otherwise each tag of the item is styled in the body with ``TAG_STYLES[tag.kind]``
    over ``tag.start`` to ``tag.end``. When ``reactions_line`` is not empty add a newline, two
    spaces and the line, dim.

    STUB: replace this paragraph and the body (P0-I6-T04).
    """
    raise NotImplementedError


class PostRequested(Message):
    """The user pressed `p`: the app should open the composer."""

    def __init__(self, record_key: str | None) -> None:
        super().__init__()
        self.record_key = record_key


class FeedPane(Vertical):
    """The feed of ``scope``; with ``record_id`` the feed of that record, with ``tag`` a hashtag."""

    KEY_HINTS: ClassVar[str] = (
        "j/k move  Enter/o open record  p post  . ack  + like  x resolved  "
        "1-4 filter  L linked  t thread  f follow  r reload"
    )
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("j", "move(1)", "Down", show=False),
        Binding("k", "move(-1)", "Up", show=False),
        Binding("o", "open", "Open", show=False),
        Binding("p", "post", "Post", show=False),
        Binding("full_stop", "react('ack')", "Ack", show=False),
        Binding("plus", "react('+1')", "Like", show=False),
        Binding("x", "react('resolved')", "Resolved", show=False),
        Binding("1", "filter('all')", "All", show=False),
        Binding("2", "filter('posts')", "Posts", show=False),
        Binding("3", "filter('events')", "Events", show=False),
        Binding("4", "filter('hold')", "#hold", show=False),
        Binding("L", "toggle_linked", "Linked", show=False),
        Binding("t", "thread", "Thread", show=False),
        Binding("f", "follow", "Follow", show=False),
        Binding("a", "accept", "Accept", show=False),
        Binding("r", "reload", "Reload", show=False),
    ]

    def __init__(
        self,
        client: ClientInterface,
        scope: str,
        *,
        record_id: str | None = None,
        record_key: str | None = None,
        tag: str | None = None,
        actor: str = "user:dev",
        page_size: int = PAGE_SIZE,
        id: str | None = None,  # noqa: A002
    ) -> None:
        super().__init__(id=id)
        self.client = client
        self.scope = scope
        self.record_id = record_id
        self.record_key = record_key
        self.tag = tag
        self.actor = actor
        self.page_size = page_size
        self.active: Filter = "all"
        self.include_linked = False
        self.items: list[FeedItem] = []
        self.labels: dict[str, str] = {}
        self.suggestions: dict[str, list[FeedSuggestion]] = {}
        self.next_before: int | None = None

    def compose(self) -> ComposeResult:
        """Three children: a `Static` ``#feed-title`` and a `Static` ``#feed-tabs`` (both with
        ``markup=False``), then an `OptionList` ``#feed-list``.

        STUB: replace this paragraph and the body (P0-I6-T04).
        """
        raise NotImplementedError

    def on_mount(self) -> None:
        """``reload``.

        STUB: replace this paragraph and the body (P0-I6-T04).
        """
        raise NotImplementedError

    def focus(self, scroll_visible: bool = True) -> FeedPane:
        """Focus the option list (the pane itself takes no focus) and return the pane.

        STUB: replace this paragraph and the body (P0-I6-T04).
        """
        raise NotImplementedError

    @property
    def highlighted_item(self) -> FeedItem | None:
        """The item under the option list's highlight, ``None`` when nothing is highlighted.

        STUB: replace this paragraph and the body (P0-I6-T04).
        """
        raise NotImplementedError

    def reload(self) -> None:
        """Fetch the first page again and show it, keeping the highlight on the same item id when
        it is still listed, else on the first.

        The fetch is ``client.feed_page(scope, record_id=..., include_linked=..., tag=...,
        item_type=..., limit=page_size, before_seq=...)``. The filter decides: ``posts`` is
        ``item_type="post"``, ``events`` is ``"card"``, ``hold`` sets ``tag="hold"`` (otherwise the
        pane's own ``tag``). Store ``items``, ``labels``, ``suggestions`` and ``next_before`` from
        the page. A client error (``CLIENT_ERRORS``) posts ``StatusMessage(describe_error(exc),
        "error")`` and keeps what is shown. Update ``#feed-title`` and ``#feed-tabs``: the title is
        ``Feed · <scope without "project:">``, then `` · record <key or id>`` for a record feed
        (with `` · + linked`` when ``include_linked``), then `` · #tag`` (or the ``@mention``) for a
        tag feed. The list has one `Option(item_text(...), id=item.id)` per item; with no items it
        holds one dim option ``Nothing here yet. Press p to post.`` and no highlight.

        STUB: replace this paragraph and the body (P0-I6-T04).
        """
        raise NotImplementedError

    def load_more(self) -> bool:
        """Append the page that follows (``before_seq=next_before``) to ``items``, ``labels`` and
        ``suggestions``, keep the highlight, redraw, and return True; False when ``next_before`` is
        None or the fetch failed.

        STUB: replace this paragraph and the body (P0-I6-T04).
        """
        raise NotImplementedError

    def action_move(self, delta: int) -> None:
        """Move the highlight by ``delta`` (j: +1, k: -1), clamped to the items. Moving down from
        the last item calls ``load_more`` and, when a page came, moves onto its first item. No
        items: do nothing.

        STUB: replace this paragraph and the body (P0-I6-T04).
        """
        raise NotImplementedError

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Enter on an option: stop the event and do what ``o`` does.

        STUB: replace this paragraph and the body (P0-I6-T04).
        """
        raise NotImplementedError

    def action_open(self) -> None:
        """Post ``OpenRecord(record["scope"], record["key"], follow=True)`` for the first record of
        the highlighted item; the record comes from ``client.get_record_by_id``. Nothing
        highlighted: do nothing. The item has no record: say "This item references no record"
        (info). The client finds no record or it has no key: say "The referenced record is not
        available" (warning). "Say" means post a ``StatusMessage``.

        STUB: replace this paragraph and the body (P0-I6-T04).
        """
        raise NotImplementedError

    def action_post(self) -> None:
        """Post ``PostRequested(self.record_key)``.

        STUB: replace this paragraph and the body (P0-I6-T04).
        """
        raise NotImplementedError

    def action_react(self, reaction: Reaction) -> None:
        """Toggle ``reaction`` on the highlighted post for ``self.actor``.

        Send ``client.feed_react(ReactToPost(actor=self.actor, source="tui", scope=self.scope,
        post_id=..., reaction=reaction, on=True))``. If it raises ``NoChangesError`` the actor
        already has the reaction, so send the same command with ``on=False``. Any other
        ``CLIENT_ERRORS`` error: say ``describe_error`` (error) and stop. After success ``reload``.
        On a card, or with nothing highlighted, say "Reactions go on posts" (info).

        STUB: replace this paragraph and the body (P0-I6-T04).
        """
        raise NotImplementedError

    def action_filter(self, name: Filter) -> None:
        """Make ``name`` the active filter and ``reload``.

        STUB: replace this paragraph and the body (P0-I6-T04).
        """
        raise NotImplementedError

    def action_toggle_linked(self) -> None:
        """Flip ``include_linked`` and ``reload``. Outside a record feed (no ``record_id``) say
        "Linked records apply to a record's feed" (info) and change nothing.

        STUB: replace this paragraph and the body (P0-I6-T04).
        """
        raise NotImplementedError

    def action_thread(self) -> None:
        """Say "Threads are switched off for this project" (info).

        STUB: replace this paragraph and the body (P0-I6-T04).
        """
        raise NotImplementedError

    def action_follow(self) -> None:
        """Say "Following arrives with the settings screen" (info).

        STUB: replace this paragraph and the body (P0-I6-T04).
        """
        raise NotImplementedError

    def action_accept(self) -> None:
        """On an item that has a suggestion say "Constraint proposals arrive with the review queue"
        (info); otherwise say "No suggestion on this item" (info). Nothing is created in Phase 0.

        STUB: replace this paragraph and the body (P0-I6-T04).
        """
        raise NotImplementedError

    def action_reload(self) -> None:
        """``reload``.

        STUB: replace this paragraph and the body (P0-I6-T04).
        """
        raise NotImplementedError
