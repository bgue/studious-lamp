"""Record-thread and dispatch contracts for P1-I7 (brief §21.5, §10.6 sketch 13, §19.2).

Frozen for the increment: change only by orchestrator decision (``docs/tickets/P1-I7/FANOUT.md``).

A **thread** is one stream per record (``thread:<record id>``, stream type ``core.Thread``),
created by its first message, so messages never bump the record's version. A **dispatch** is a
message whose first line is a slash command: :class:`DispatchParser` turns the line into a
:class:`ParsedDispatch` (pure, no database); a :class:`DispatchPlanner` resolves it into
:class:`~tl_core.integration.contract.PlannedCommand` items that run **existing** commands with the
caller's access and never more, and returns a :class:`DispatchPreview`; confirming runs exactly
what was previewed (the preview ``token``) in one unit of work and appends ``Thread.Dispatched``.

``/summarise`` is a deterministic stub (ADR-0008 decision 8: no model, no spend). Agents never
dispatch: the MCP tool ``propose_dispatch`` records a proposal a person accepts.

Grammar of the command line (the parser and the contract test hold to it):

* A message is a dispatch when its first non-blank character is ``/``. Only the first line is the
  command line (``line``, stripped); later lines, stripped, are the ``note`` (``None`` when
  empty). The verb follows the ``/`` directly and is matched without regard to case;
  ``/summarize`` is accepted for ``/summarise``.
* Tokens are separated by white space; ``"double quoted"`` text is one token and always a word
  (no escapes; an unclosed quote is the problem ``unterminated_quote``).
* ``@handle`` is a mention (``@jsmith``, ``@crew:P-07``, ``@party:acme-nde``, ``@agent:planner``);
  ``#KEY`` is a record key; a bare token is a word. Mentions and keys are kept as typed, without
  the sigil; the planner resolves them. ``text`` is the words left over, joined by one space
  (``None`` when there are none).
* Where a verb takes mentions (``assign``, ``notify``, ``remind``) every mention token is one,
  wherever it stands. ``raise`` takes every ``#KEY`` as a target. ``dispatch`` takes every unquoted
  ``name=value`` token (``name`` matching ``[a-z][a-z0-9_]*``) as a parameter; a repeated name or
  more than :data:`MAX_PARAMETERS` is ``bad_parameter``. ``link`` takes every token before ``as``
  as a key (``#`` removed); a mention there is ``unexpected_arguments``; ``as`` must be followed by
  exactly one relation token.
* ``+<n>`` counts are 1 or more; a ``due`` is at most :data:`DUE_MAX_DAYS` days ahead and a
  ``remind`` at most :data:`REMIND_MAX_DAYS`; past dates are the planner's to refuse (the parser
  has no clock).
* Per verb, after the verb:

  ======== ==========================================================================
  assign   one or more mentions, then item keys (``#KEY`` or bare words)
  dispatch the request type or action name, then ``name=value`` parameters, then text
  raise    the record type alias (``rfi``, ``record``), then ``#KEY`` targets, then text
  link     one or more keys (``#KEY`` or bare), optionally ``as <relation>`` at the end
  status   the target state (one token), then text (the reason)
  hold     text (the reason), optional
  release  text, optional
  due      one date token: ``YYYY-MM-DD`` or ``+<n>d`` / ``+<n>w``
  notify   one or more mentions, then text
  remind   one time token: ``+<n>m``, ``+<n>h``, ``+<n>d``, ``+<n>w``, ``YYYY-MM-DD`` or
           ``YYYY-MM-DDTHH:MM``; then optional mentions, then text
  summarise nothing (any argument is ``unexpected_arguments``)
  ======== ==========================================================================

* Problems (never exceptions): ``unknown_verb``, ``missing_argument``, ``unexpected_arguments``,
  ``bad_date``, ``bad_time``, ``bad_parameter``, ``unterminated_quote``, ``too_long``,
  ``too_many_keys``, ``too_many_mentions``, ``control_character``. ``too_long``: the line is over
  :data:`MAX_COMMAND_LINE_CHARS` or the whole text over :data:`MAX_MESSAGE_CHARS`.
  ``control_character``: U+007F, or a character below U+0020 other than tab in the line (other
  than tab, carriage return and newline in the note). A line of only ``/`` or ``/`` followed by a
  space is ``unknown_verb``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from tl_core.integration.contract import (
    Access,
    CommandRunner,
    PlannedCommand,
    Problem,
    RecordRef,
)
from tl_core.uow import UnitOfWork

# --------------------------------------------------------------------------------------------
# Streams, events, settings, tools
# --------------------------------------------------------------------------------------------

THREAD_STREAM_TYPE = "core.Thread"
THREAD_STREAM_PREFIX = "thread:"
THREAD_MESSAGE_POSTED = "Thread.MessagePosted"
THREAD_MESSAGE_EDITED = "Thread.MessageEdited"
THREAD_MESSAGE_RETRACTED = "Thread.MessageRetracted"
THREAD_DISPATCHED = "Thread.Dispatched"
THREAD_EVENT_TYPES = (
    THREAD_MESSAGE_POSTED,
    THREAD_MESSAGE_EDITED,
    THREAD_MESSAGE_RETRACTED,
    THREAD_DISPATCHED,
)
#: Delivered to webhook subscribers (§21.5); edits and retractions are not.
THREAD_WEBHOOK_EVENT_TYPES = (THREAD_MESSAGE_POSTED, THREAD_DISPATCHED)

#: about:config keys (§21.5) that Phase 1 has behaviour behind.
SETTING_ENABLED = "threads.enabled"
SETTING_ENABLED_TYPES = "threads.enabled_types"
SETTING_DISPATCH_ENABLED = "threads.dispatch.enabled"
SETTING_DISPATCH_ROLES = "threads.dispatch.roles"
SETTING_AGENTS_CAN_DISPATCH = "threads.agents.can_dispatch"

#: MCP tools (§21.5). ``propose_dispatch`` is a proposal; the other two are a read and a message.
MCP_READ_THREAD = "read_thread"
MCP_POST_THREAD_MESSAGE = "post_thread_message"
MCP_PROPOSE_DISPATCH = "propose_dispatch"

#: Entry-point group under which modules register :class:`DispatchTarget` objects (FANOUT D10).
DISPATCH_TARGET_ENTRY_POINT = "throughline.dispatch_targets"

# --------------------------------------------------------------------------------------------
# Bounds (FANOUT D9, D10)
# --------------------------------------------------------------------------------------------

MAX_MESSAGE_CHARS = 10_000
MAX_COMMAND_LINE_CHARS = 2_000
MAX_DISPATCH_KEYS = 20
MAX_MENTIONS = 20
MAX_PARAMETERS = 20
MAX_PLANNED_COMMANDS = 20
PREVIEW_TTL_S = 600
REMIND_MAX_DAYS = 366
DUE_MAX_DAYS = 3_660
SUMMARY_MAX_MESSAGES = 50
SUMMARY_MAX_CHARS = 2_000
READ_THREAD_MAX_PAGE = 200

DispatchVerb = Literal[
    "assign",
    "dispatch",
    "raise",
    "link",
    "status",
    "hold",
    "release",
    "due",
    "notify",
    "remind",
    "summarise",
]
DISPATCH_VERBS: tuple[DispatchVerb, ...] = (
    "assign",
    "dispatch",
    "raise",
    "link",
    "status",
    "hold",
    "release",
    "due",
    "notify",
    "remind",
    "summarise",
)
#: Verbs whose confirmed run changes something outside the thread; they always need a preview.
SIDE_EFFECTING_VERBS = frozenset(
    {"assign", "dispatch", "raise", "link", "status", "hold", "release", "due", "remind"}
)

# --------------------------------------------------------------------------------------------
# Parsed command line
# --------------------------------------------------------------------------------------------


class _Args(BaseModel):
    note: str | None = Field(default=None, max_length=MAX_MESSAGE_CHARS)


class AssignArgs(_Args):
    verb: Literal["assign"] = "assign"
    assignees: list[str] = Field(min_length=1, max_length=MAX_MENTIONS)
    items: list[str] = Field(default_factory=list[str], max_length=MAX_DISPATCH_KEYS)


class DispatchArgs(_Args):
    verb: Literal["dispatch"] = "dispatch"
    request_type: str
    parameters: dict[str, str] = Field(default_factory=dict[str, str])
    text: str | None = None


class RaiseArgs(_Args):
    verb: Literal["raise"] = "raise"
    record_type: str
    against: list[str] = Field(default_factory=list[str], max_length=MAX_DISPATCH_KEYS)
    text: str | None = None


class LinkArgs(_Args):
    verb: Literal["link"] = "link"
    keys: list[str] = Field(min_length=1, max_length=MAX_DISPATCH_KEYS)
    relation: str | None = None


class StatusArgs(_Args):
    verb: Literal["status"] = "status"
    target: str
    text: str | None = None


class HoldArgs(_Args):
    verb: Literal["hold"] = "hold"
    text: str | None = None


class ReleaseArgs(_Args):
    verb: Literal["release"] = "release"
    text: str | None = None


class DueArgs(_Args):
    verb: Literal["due"] = "due"
    #: As typed (``2026-11-02``, ``+3d``); the planner resolves it with the server date.
    when: str


class NotifyArgs(_Args):
    verb: Literal["notify"] = "notify"
    who: list[str] = Field(min_length=1, max_length=MAX_MENTIONS)
    text: str | None = None


class RemindArgs(_Args):
    verb: Literal["remind"] = "remind"
    #: As typed (``+2h``, ``2026-11-02T09:00``); the planner resolves it with the server clock.
    when: str
    who: list[str] = Field(default_factory=list[str], max_length=MAX_MENTIONS)
    text: str | None = None


class SummariseArgs(_Args):
    verb: Literal["summarise"] = "summarise"


DispatchArguments = Annotated[
    AssignArgs
    | DispatchArgs
    | RaiseArgs
    | LinkArgs
    | StatusArgs
    | HoldArgs
    | ReleaseArgs
    | DueArgs
    | NotifyArgs
    | RemindArgs
    | SummariseArgs,
    Field(discriminator="verb"),
]


class ParsedDispatch(BaseModel):
    """A command line the parser understood. ``line`` is the first line as typed (bounded)."""

    line: str = Field(max_length=MAX_COMMAND_LINE_CHARS)
    args: DispatchArguments

    @property
    def verb(self) -> DispatchVerb:
        return self.args.verb


class ParseProblem(BaseModel):
    """A command line the parser refused. ``column`` is 0-based in ``line`` when known."""

    code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    message: str = Field(max_length=500)
    column: int | None = None


@runtime_checkable
class DispatchParser(Protocol):
    """Pure and total: no database, no clock, never raises.

    ``None``: the text is a plain message (its first non-blank character is not ``/``).
    """

    def parse(self, text: str) -> ParsedDispatch | ParseProblem | None: ...


# --------------------------------------------------------------------------------------------
# Planning, preview, outcome
# --------------------------------------------------------------------------------------------


class DispatchContext(BaseModel):
    """What a dispatch target is told: the thread's record and who is dispatching."""

    record: RecordRef
    record_status: str | None = None
    scope: str
    actor: str
    #: ISO date and instant of the server, for ``/due`` and ``/remind``.
    today: str
    now: str


class PlannedLink(BaseModel):
    """A ``dispatched_from`` link the dispatch adds: from a record it creates (``from_record_id``
    ``None`` until it exists) to the thread's record; ``note`` names the message."""

    from_record_id: str | None = None
    to_record_id: str
    relation: Literal["dispatched_from"] = "dispatched_from"
    note: str


@runtime_checkable
class DispatchTarget(Protocol):
    """Maps one verb to existing commands for one record type or alias (FANOUT D10).

    ``name`` is the alias for ``raise`` (``rfi``, ``record``) or the action name space for
    ``dispatch`` (``*``), and the record type for the other verbs (``documents.Revision``), or
    ``*`` for the core default. The most specific name wins. A target only builds commands; the
    planner validates them with the runner's models, checks each one's access against ``holds``
    and dry-runs them in a unit of work that is rolled back.
    """

    verb: DispatchVerb
    name: str

    def plan(
        self, uow: UnitOfWork, context: DispatchContext, parsed: ParsedDispatch
    ) -> list[PlannedCommand] | Problem: ...


class DispatchPreview(BaseModel):
    """What the caller sees before a side-effecting dispatch runs.

    ``can_dispatch`` is true when every planned command is ``permitted`` and has no ``problem``.
    ``token`` is the SHA-256 of the canonical JSON of (record id, record version, ``line``,
    ``planned``); a confirmation names it, and the run is refused (``dispatch_stale``) when the
    plan made then differs or ``expires_at`` has passed.
    """

    record: RecordRef
    parsed: ParsedDispatch
    planned: list[PlannedCommand] = Field(
        default_factory=list[PlannedCommand], max_length=MAX_PLANNED_COMMANDS
    )
    links: list[PlannedLink] = Field(default_factory=list[PlannedLink])
    side_effecting: bool
    can_dispatch: bool
    token: str = Field(pattern=r"^[0-9a-f]{64}$")
    expires_at: str
    problems: list[Problem] = Field(default_factory=list[Problem])
    #: e.g. "summary is deterministic, no model (ADR-0008 decision 8)".
    notes: list[str] = Field(default_factory=list[str], max_length=20)


class DispatchResult(BaseModel):
    """One command a confirmed dispatch ran."""

    command_type: str
    stream_id: str
    key: str | None = None
    version: int


class DispatchOutcome(BaseModel):
    """The payload of ``Thread.Dispatched`` and the result card in the thread."""

    message_id: str
    verb: DispatchVerb
    results: list[DispatchResult] = Field(default_factory=list[DispatchResult])
    link_ids: list[str] = Field(default_factory=list[str])
    summary: str = Field(default="", max_length=500)


class ThreadMessageView(BaseModel):
    """A message as the thread tab, the API and ``read_thread`` show it."""

    message_id: str
    record_id: str
    author: str
    body: str = Field(max_length=MAX_MESSAGE_CHARS)
    posted_at: str
    edited: bool = False
    retracted: bool = False
    mentions: list[str] = Field(default_factory=list[str])
    record_refs: list[str] = Field(default_factory=list[str])
    dispatch: DispatchOutcome | None = None


@runtime_checkable
class DispatchPlanner(Protocol):
    """Resolves a dispatch for one record as one actor (WS-B, supervisor-built).

    ``holds`` and ``runner`` come from the client layer (Python arguments, never a request field).
    ``preview`` writes nothing. It returns the parse problem as is, and a preview whose planned
    commands carry their own problems otherwise.
    """

    def preview(
        self,
        uow: UnitOfWork,
        *,
        record_id: str,
        text: str,
        actor: str,
        holds: Callable[[Access], bool],
        runner: CommandRunner,
    ) -> DispatchPreview | ParseProblem: ...
