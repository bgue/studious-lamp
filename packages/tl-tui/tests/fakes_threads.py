"""Thread behaviour of `FakeClient` (P1-I7 WS-B), kept apart so `fakes.py` stays readable.

The fake keeps a thread per record as real `ThreadMessageView` objects and the real parser decides
what a command line is. It does not plan: a test scripts the answer to a line with
`script_preview(text, preview)`; a line nobody scripted gets an empty, dispatchable preview whose
token is `DEFAULT_TOKEN`. `thread_dispatch` refuses a token that is not the scripted preview's
(`DispatchStaleError`, as the server does) and posts the message with a scripted outcome. Mentions
and record keys in a message are not detected (`mentions` and `record_refs` stay empty).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from tl_core.integration.contract import RecordRef
from tl_core.services.commands import CommandResult
from tl_core.services.errors import NoChangesError, RecordNotFoundError
from tl_core.threads.contract import (
    DispatchOutcome,
    DispatchPreview,
    ParsedDispatch,
    ParseProblem,
    ThreadMessageView,
)
from tl_core.threads.dispatch import DispatchFromThread
from tl_core.threads.errors import (
    DispatchStaleError,
    MessageRetractedError,
    NotMessageAuthorError,
    ThreadMessageNotFoundError,
    ThreadsDisabledError,
)
from tl_core.threads.messages import EditThreadMessage, PostThreadMessage, RetractThreadMessage
from tl_core.threads.parser import CommandLineParser
from tl_core.threads.planner import PreviewResult
from tl_core.threads.queries import ThreadPage, ThreadParticipant

_T0 = datetime(2026, 10, 17, 7, 0, 0, tzinfo=UTC)
DEFAULT_TOKEN = "f" * 64


class _ThreadHost(Protocol):
    calls: list[str]
    _records: dict[str, dict[str, Any]]


class FakeThreadSupport:
    """Mixin for `FakeClient`: call `_init_threads()` from its `__init__`."""

    def _init_threads(self) -> None:
        self._thread: dict[str, list[tuple[ThreadMessageView, str, int]]] = {}
        self._thread_n = 0
        self.threads_enabled = True
        self.dispatch_enabled = True
        self.thread_commands: list[Any] = []
        self.dispatched: list[DispatchFromThread] = []
        self._scripted: dict[str, PreviewResult] = {}
        self._scripted_outcome: dict[str, DispatchOutcome] = {}

    def _thost(self) -> _ThreadHost:
        return self  # type: ignore[return-value]

    # --- seeding ----------------------------------------------------------------------------

    def seed_message(
        self,
        record_id: str,
        body: str,
        *,
        author: str = "user:rgarcia",
        kind: str = "message",
        dispatch: DispatchOutcome | None = None,
    ) -> ThreadMessageView:
        """Add a message to a record's thread without any checks."""
        self._thread_n += 1
        message = ThreadMessageView(
            message_id=f"MSG{self._thread_n:023d}",
            record_id=record_id,
            author=author,
            body=body,
            posted_at=(_T0 + timedelta(minutes=self._thread_n)).isoformat(),
            dispatch=dispatch,
        )
        self._thread.setdefault(record_id, []).append((message, kind, self._thread_n))
        return message

    def script_preview(
        self,
        text: str,
        preview: DispatchPreview | ParseProblem,
        *,
        outcome: DispatchOutcome | None = None,
    ) -> None:
        """Answer `thread_preview(_, text)` with this; `outcome` is what confirming posts."""
        self._scripted[text] = (
            PreviewResult(problem=preview)
            if isinstance(preview, ParseProblem)
            else PreviewResult(preview=preview)
        )
        if outcome is not None:
            self._scripted_outcome[text] = outcome

    def default_preview(self, record_id: str, parsed: ParsedDispatch) -> DispatchPreview:
        record = self._thost()._records[record_id]
        return DispatchPreview(
            record=RecordRef(
                id=record_id,
                key=record["key"],
                record_type=record["type"],
                version=record["version"],
            ),
            parsed=parsed,
            side_effecting=False,
            can_dispatch=True,
            token=DEFAULT_TOKEN,
            expires_at=(_T0 + timedelta(hours=1)).isoformat(),
        )

    # --- the client interface ---------------------------------------------------------------

    def _thread_record(self, record_id: str) -> dict[str, Any]:
        found = self._thost()._records.get(record_id)
        if found is None:
            raise RecordNotFoundError(f"no record {record_id!r}")
        return found

    def thread_page(
        self, record_id: str, *, limit: int = 50, before_seq: int | None = None
    ) -> ThreadPage:
        self._thost().calls.append("thread_page")
        record = self._thread_record(record_id)
        items = [
            t for t in self._thread.get(record_id, []) if before_seq is None or t[2] < before_seq
        ]
        shown = items[-limit:]
        people: dict[str, list[str]] = {}
        for message, kind, _ in self._thread.get(record_id, []):
            if kind == "message":
                people.setdefault(message.author, ["author"])
        return ThreadPage(
            record=RecordRef(
                id=record_id,
                key=record["key"],
                record_type=record["type"],
                version=record["version"],
            ),
            enabled=self.threads_enabled,
            dispatch_enabled=self.dispatch_enabled,
            message_count=len(self._thread.get(record_id, [])),
            participants=[ThreadParticipant(actor=a, reasons=r) for a, r in people.items()],
            messages=[m for m, _, _ in shown],
            seqs=[n for _, _, n in shown],
            kinds=[k for _, k, _ in shown],
            next_before=shown[0][2] if len(items) > len(shown) and shown else None,
        )

    def thread_post(self, cmd: PostThreadMessage) -> CommandResult:
        self._thost().calls.append("thread_post")
        self.thread_commands.append(cmd)
        self._thread_record(cmd.record_id)
        if not self.threads_enabled:
            raise ThreadsDisabledError("threads are not switched on here")
        message = self.seed_message(cmd.record_id, cmd.body, author=cmd.actor)
        return CommandResult(
            stream_id=f"thread:{cmd.record_id}", key=message.message_id, version=1, events=[]
        )

    def _own(self, cmd: EditThreadMessage | RetractThreadMessage) -> int:
        for index, (message, kind, _) in enumerate(self._thread.get(cmd.record_id, [])):
            if message.message_id == cmd.message_id:
                if message.author != cmd.actor:
                    raise NotMessageAuthorError("only the author can change this message")
                if message.retracted:
                    raise MessageRetractedError("the message was retracted")
                assert kind == "message"
                return index
        raise ThreadMessageNotFoundError(f"no message {cmd.message_id!r}")

    def thread_edit(self, cmd: EditThreadMessage) -> CommandResult:
        self._thost().calls.append("thread_edit")
        self.thread_commands.append(cmd)
        index = self._own(cmd)
        message, kind, n = self._thread[cmd.record_id][index]
        if message.body == cmd.body:
            raise NoChangesError("the body is already that text")
        self._thread[cmd.record_id][index] = (
            message.model_copy(update={"body": cmd.body, "edited": True}),
            kind,
            n,
        )
        return CommandResult(
            stream_id=f"thread:{cmd.record_id}", key=cmd.message_id, version=2, events=[]
        )

    def thread_retract(self, cmd: RetractThreadMessage) -> CommandResult:
        self._thost().calls.append("thread_retract")
        self.thread_commands.append(cmd)
        index = self._own(cmd)
        message, kind, n = self._thread[cmd.record_id][index]
        self._thread[cmd.record_id][index] = (
            message.model_copy(update={"body": "", "retracted": True}),
            kind,
            n,
        )
        return CommandResult(
            stream_id=f"thread:{cmd.record_id}", key=cmd.message_id, version=2, events=[]
        )

    def thread_preview(self, record_id: str, text: str) -> PreviewResult:
        self._thost().calls.append("thread_preview")
        self._thread_record(record_id)
        if text in self._scripted:
            return self._scripted[text]
        parsed = CommandLineParser().parse(text)
        if parsed is None:
            return PreviewResult(
                problem=ParseProblem(code="not_a_dispatch", message="plain message")
            )
        if isinstance(parsed, ParseProblem):
            return PreviewResult(problem=parsed)
        return PreviewResult(preview=self.default_preview(record_id, parsed))

    def thread_dispatch(self, cmd: DispatchFromThread) -> CommandResult:
        self._thost().calls.append("thread_dispatch")
        self.dispatched.append(cmd)
        scripted = self._scripted.get(cmd.text)
        expected = scripted.preview.token if scripted and scripted.preview else DEFAULT_TOKEN
        if cmd.token != expected:
            raise DispatchStaleError("the plan is not the one you previewed")
        parsed = CommandLineParser().parse(cmd.text)
        outcome = self._scripted_outcome.get(cmd.text)
        if outcome is None and isinstance(parsed, ParsedDispatch):
            outcome = DispatchOutcome(message_id="", verb=parsed.verb, summary=parsed.verb)
        message = self.seed_message(
            cmd.record_id, cmd.text, author=cmd.actor, kind="dispatch", dispatch=outcome
        )
        return CommandResult(
            stream_id=f"thread:{cmd.record_id}", key=message.message_id, version=2, events=[]
        )
