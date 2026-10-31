"""Offline classes: may a node capture this command while offline? (offline-classes spec, 5).

Pure and unwired in Phase 2: nothing writes through it yet. Phase 3's local unit of work calls
``require_capture_allowed(type, command, node=node_kind())`` before it records a pending command.

The class of a record type is generated from the schema (``tl_schema.generated.offline_classes``);
an extension type declares it in ``type.yaml`` (``tl:offline``) and is read from the attached
extension source without touching the ledger. The rule of ``capture_allowed``, in order:

1. node ``authority``: allowed (``authority``);
2. type unknown: refused (``unknown_type``);
3. the command's word is ``controller``, ``admin`` or ``company``: refused (``central_act``);
4. class ``none``: refused (``online_only``); ``full``: allowed (``full``); ``draft_only``: allowed
   for a command in the module's ``offline_drafts`` for that type (``draft``), else refused
   (``not_drafting``).

A command with no declared word (a core command, or one of the four generic commands) is not a
central act: it follows the class of the record's type.
"""

from __future__ import annotations

import os
from typing import Final, Literal, cast, get_args

from pydantic import BaseModel
from tl_schema.generated.offline_classes import OFFLINE_CLASSES, OFFLINE_STREAMS, OfflineClass
from tl_schema.generated.type_labels import TYPE_LABELS

from tl_core.services.errors import ServiceError

NodeKind = Literal["authority", "site", "device"]
Reason = Literal[
    "authority", "full", "draft", "online_only", "central_act", "not_drafting", "unknown_type"
]

NODE_KIND_VARIABLE: Final = "TL_NODE_KIND"
#: The access words of an act that is always central (design section 4): never captured offline.
CENTRAL_WORDS: Final = frozenset({"controller", "admin", "company"})
#: The generic commands on a record; they follow the record's type class and are not central.
GENERIC_CAPTURE_COMMANDS: Final = ("AddLink", "AttachFile", "SetPsetValues", "TransitionWorkflow")


class OnlineOnlyError(ServiceError):
    """The command cannot be captured offline on this node (409 ``online_only``)."""


class NodeKindNotBuiltError(ServiceError):
    """This process was asked to run as a node kind whose replica layer is not built yet."""


class OfflineDecision(BaseModel):
    allowed: bool
    reason: Reason


def node_kind() -> NodeKind:
    """``TL_NODE_KIND``: ``authority`` (also when unset or empty), ``site`` or ``device``."""
    value = os.environ.get(NODE_KIND_VARIABLE, "").strip()
    if not value:
        return "authority"
    if value not in get_args(NodeKind):
        raise ValueError(f"{NODE_KIND_VARIABLE} must be one of authority, site, device")
    return cast("NodeKind", value)


def require_node_built() -> None:
    """Refuse to start as a node kind whose replica layer does not exist yet (fails closed)."""
    if node_kind() != "authority":
        raise NodeKindNotBuiltError("offline replicas arrive in Phase 3")


def is_authority(scope: str) -> bool:
    """Whether this node is the authority of ``scope``.

    Today every node is the authority of every scope it holds, so no scope data is read; Phase 3
    replaces the body with the scope's ledgered authority without changing callers.
    """
    return node_kind() == "authority"


def _known_class(record_type: str) -> OfflineClass | None:
    """The class of a record type, or ``None`` when the type is not known to this process."""
    declared = OFFLINE_CLASSES.get(record_type)
    if declared is not None:
        return declared
    from tl_core.extypes.provider import attached_offline_class  # avoid an import cycle

    extension = attached_offline_class(record_type)
    return cast("OfflineClass", extension) if extension is not None else None


def offline_class(record_type: str) -> OfflineClass:
    """The offline class of a record type; a type nobody declared is ``none`` (fail closed)."""
    return _known_class(record_type) or "none"


def stream_class(stream_type: str) -> OfflineClass:
    """The offline class of a core stream that is not a record; unknown is ``none``."""
    return OFFLINE_STREAMS.get(stream_type, "none")


def _command_word(command: str) -> str | None:
    """The table or platform word a module declared for ``command``, or ``None``."""
    from tl_core.auth.module_roles import normalise_word  # avoid an import cycle
    from tl_core.modules import load_modules

    for spec in load_modules():
        word = spec.command_words.get(command)
        if word is not None:
            return normalise_word(word)
    return None


def _drafting_commands(record_type: str) -> frozenset[str]:
    from tl_core.modules import load_modules

    for spec in load_modules():
        if record_type in spec.record_types:
            return spec.offline_drafts.get(record_type, frozenset())
    return frozenset()


def capture_allowed(record_type: str, command: str, *, node: NodeKind) -> OfflineDecision:
    """Whether a node of kind ``node`` may capture ``command`` on ``record_type`` while offline."""
    if node == "authority":
        return OfflineDecision(allowed=True, reason="authority")
    declared = _known_class(record_type)
    if declared is None:
        return OfflineDecision(allowed=False, reason="unknown_type")
    if _command_word(command) in CENTRAL_WORDS:
        return OfflineDecision(allowed=False, reason="central_act")
    if declared == "none":
        return OfflineDecision(allowed=False, reason="online_only")
    if declared == "full":
        return OfflineDecision(allowed=True, reason="full")
    if command in _drafting_commands(record_type):
        return OfflineDecision(allowed=True, reason="draft")
    return OfflineDecision(allowed=False, reason="not_drafting")


def require_capture_allowed(record_type: str, command: str, *, node: NodeKind) -> None:
    """``capture_allowed``, raising ``OnlineOnlyError`` (409 ``online_only``) when refused."""
    decision = capture_allowed(record_type, command, node=node)
    if not decision.allowed:
        raise OnlineOnlyError(
            f"{command} on a {record_type} record cannot be captured offline on a {node} node "
            f"({decision.reason})"
        )


class RecordTypeRow(BaseModel):
    """One record type as the record-types route and client answer it (no record data)."""

    record_type: str  # "engineering.Tag"
    label: str  # TYPE_LABELS, else the record type itself
    module: str  # the part before the first "."
    offline: OfflineClass
    drafting_commands: list[str]  # sorted; [] unless the class is draft_only


def record_type_rows() -> list[RecordTypeRow]:
    """One row per record type of the offline table, sorted by record type.

    Reads only generated data and the module table: no record, no ledger.
    """
    rows: list[RecordTypeRow] = []
    for record_type in sorted(OFFLINE_CLASSES):
        offline = OFFLINE_CLASSES[record_type]
        commands = sorted(_drafting_commands(record_type)) if offline == "draft_only" else []
        rows.append(
            RecordTypeRow(
                record_type=record_type,
                label=TYPE_LABELS.get(record_type, record_type),
                module=record_type.split(".", 1)[0],
                offline=offline,
                drafting_commands=commands,
            )
        )
    return rows
