"""The project feed over HTTP: pages, posting, editing, reactions and composer completion.

Same names, parameters and return types as the feed methods of ``tl_tui.client.ClientInterface``.
Writes are the generated command routes, so ``source`` is sent as given and the token's actor is
recorded. Failures raise the embedded exception classes (``PostNotFoundError`` and so on).
"""

from __future__ import annotations

from typing import Literal

from pydantic import TypeAdapter
from tl_core.services.commands import CommandResult
from tl_core.services.feed import EditPost, PostToFeed
from tl_core.services.feed_actions import ReactToPost, RetractPost
from tl_core.services.feed_queries import Completion, FeedPage

from tl_api.client.base import ApiClientBase

_PAGE: TypeAdapter[FeedPage] = TypeAdapter(FeedPage)
_COMPLETIONS: TypeAdapter[list[Completion]] = TypeAdapter(list[Completion])


class FeedApi(ApiClientBase):
    def feed_page(
        self,
        scope: str,
        *,
        record_id: str | None = None,
        include_linked: bool = False,
        tag: str | None = None,
        item_type: Literal["post", "card"] | None = None,
        limit: int = 50,
        before_seq: int | None = None,
    ) -> FeedPage:
        """Posts and cards of a project, newest first (``GET /feed``)."""
        data = self._get_json(
            "/feed",
            {
                "scope": scope,
                "record_id": record_id,
                "include_linked": include_linked,
                "tag": tag,
                "item_type": item_type,
                "limit": limit,
                "before_seq": before_seq,
            },
        )
        return _PAGE.validate_python(data)

    def feed_post(self, cmd: PostToFeed) -> CommandResult:
        return self._command("PostToFeed", cmd)

    def feed_edit(self, cmd: EditPost) -> CommandResult:
        return self._command("EditPost", cmd)

    def feed_retract(self, cmd: RetractPost) -> CommandResult:
        return self._command("RetractPost", cmd)

    def feed_react(self, cmd: ReactToPost) -> CommandResult:
        return self._command("ReactToPost", cmd)

    def feed_complete(
        self, scope: str, sigil: Literal["#", "@"], prefix: str, *, limit: int = 8
    ) -> list[Completion]:
        """Composer candidates after ``#`` or ``@`` (``GET /feed/complete``)."""
        data = self._get_json(
            "/feed/complete", {"scope": scope, "sigil": sigil, "prefix": prefix, "limit": limit}
        )
        return _COMPLETIONS.validate_python(data)
