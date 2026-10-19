"""Record threads over HTTP: read, post, edit, retract, preview and confirm a dispatch (brief 21.5).

Same names, parameters and return types as the thread methods of
``tl_tui.client.ClientInterface``. Messages are the generated command routes; a message never
dispatches. Failures raise the embedded exception classes (``ThreadsDisabledError``,
``DispatchStaleError``, ``DispatchRefusedError`` and so on).
"""

from __future__ import annotations

from tl_core.services.commands import CommandResult
from tl_core.threads.dispatch import DispatchFromThread
from tl_core.threads.messages import EditThreadMessage, PostThreadMessage, RetractThreadMessage
from tl_core.threads.planner import PreviewResult
from tl_core.threads.queries import ThreadPage

from tl_api.client.base import ApiClientBase, quote


class ThreadsApi(ApiClientBase):
    def thread_page(
        self, record_id: str, *, limit: int = 50, before_seq: int | None = None
    ) -> ThreadPage:
        """The newest messages of a record's thread, oldest first (``GET /records/{id}/thread``)."""
        data = self._get_json(
            f"/records/{quote(record_id)}/thread", {"limit": limit, "before_seq": before_seq}
        )
        return self._model(ThreadPage, data)

    def thread_post(self, cmd: PostThreadMessage) -> CommandResult:
        return self._command("PostThreadMessage", cmd)

    def thread_edit(self, cmd: EditThreadMessage) -> CommandResult:
        return self._command("EditThreadMessage", cmd)

    def thread_retract(self, cmd: RetractThreadMessage) -> CommandResult:
        return self._command("RetractThreadMessage", cmd)

    def thread_preview(self, record_id: str, text: str) -> PreviewResult:
        """Plan a slash command as the token's actor (``POST /records/{id}/thread/preview``)."""
        data = self._post_json(f"/records/{quote(record_id)}/thread/preview", {"text": text})
        return self._model(PreviewResult, data)

    def thread_dispatch(self, cmd: DispatchFromThread) -> CommandResult:
        """Confirm a previewed command (``POST /records/{id}/thread/dispatch``).

        Only ``text``, ``token`` and ``expires_at`` are sent; the actor is the token's and the scope
        is the record's.
        """
        data = self._post_json(
            f"/records/{quote(cmd.record_id)}/thread/dispatch",
            {"text": cmd.text, "token": cmd.token, "expires_at": cmd.expires_at},
        )
        return self._model(CommandResult, data)
