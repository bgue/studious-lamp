"""The link lifecycle: which event may happen in which status, and what status follows.

This is the single statement of the rules in brief 7.1. Command handlers call ``next_status`` to
refuse an impossible event before anything is appended; the projector calls it to compute the new
status while applying an event. Links are never deleted, so ``retracted`` is terminal.

======================  ==================================  ===============
Event                   Allowed in                          New status
======================  ==================================  ===============
``Link.Suggested``      (no link yet)                       ``suggested``
``Link.Added``          (no link yet)                       ``active``
``Link.Accepted``       ``suggested``                       ``active``
``Link.Declined``       ``suggested``                       ``retracted``
``Link.Repinned``       ``active``, ``stale``               ``active``
``Link.Verified``       ``active``                          ``active``
``Link.Flagged``        ``active``, ``stale``, ``broken``   the flagged status
``Link.Retracted``      any status except ``retracted``     ``retracted``
======================  ==================================  ===============

``Link.Flagged`` carries ``status`` (``stale`` or ``broken``) and must change the status.
"""

from __future__ import annotations

from typing import Literal, get_args

from tl_core.services.errors import InvalidLinkTransitionError

LinkStatus = Literal["suggested", "active", "stale", "broken", "retracted"]
LINK_STATUSES: tuple[LinkStatus, ...] = get_args(LinkStatus)
FlagStatus = Literal["stale", "broken"]
FLAG_STATUSES: tuple[FlagStatus, ...] = get_args(FlagStatus)

LINK_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "Link.Suggested",
        "Link.Added",
        "Link.Accepted",
        "Link.Declined",
        "Link.Repinned",
        "Link.Verified",
        "Link.Flagged",
        "Link.Retracted",
    }
)
#: Events that create the link (the first event of its stream).
CREATING_EVENTS: frozenset[str] = frozenset({"Link.Suggested", "Link.Added"})

_LIVE: tuple[LinkStatus, ...] = ("suggested", "active", "stale", "broken")


def next_status(
    current: LinkStatus | None, event_type: str, *, flag: str | None = None
) -> LinkStatus:
    """The status after ``event_type`` happens to a link in status ``current``.

    ``current`` is ``None`` for a link that does not exist yet. ``flag`` is the ``status`` field of
    a ``Link.Flagged`` payload and is required for that event. Raises ``InvalidLinkTransitionError``
    when the event is not allowed in ``current`` or the event type is unknown.
    """
    if event_type not in LINK_EVENT_TYPES:
        raise InvalidLinkTransitionError(f"{event_type} is not a link event")
    if event_type in CREATING_EVENTS:
        if current is not None:
            raise InvalidLinkTransitionError(f"{event_type} cannot happen to an existing link")
        return "suggested" if event_type == "Link.Suggested" else "active"
    if current is None:
        raise InvalidLinkTransitionError(f"{event_type} needs an existing link")

    if event_type == "Link.Accepted":
        _require(current, ("suggested",), event_type)
        return "active"
    if event_type == "Link.Declined":
        _require(current, ("suggested",), event_type)
        return "retracted"
    if event_type == "Link.Repinned":
        _require(current, ("active", "stale"), event_type)
        return "active"
    if event_type == "Link.Verified":
        _require(current, ("active",), event_type)
        return "active"
    if event_type == "Link.Flagged":
        _require(current, ("active", "stale", "broken"), event_type)
        if flag not in FLAG_STATUSES:
            raise InvalidLinkTransitionError(
                f"Link.Flagged needs status 'stale' or 'broken', got {flag!r}"
            )
        if flag == current:
            raise InvalidLinkTransitionError(f"the link is already {current}")
        return "stale" if flag == "stale" else "broken"
    _require(current, _LIVE, event_type)  # Link.Retracted
    return "retracted"


def _require(current: LinkStatus, allowed: tuple[LinkStatus, ...], event_type: str) -> None:
    if current not in allowed:
        raise InvalidLinkTransitionError(
            f"{event_type} is not allowed on a {current} link (allowed: {', '.join(allowed)})"
        )
