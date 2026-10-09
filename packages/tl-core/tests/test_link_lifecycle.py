"""Link lifecycle rules (P0-I3; brief 7.1)."""

from __future__ import annotations

import pytest
from tl_core.links.lifecycle import (
    LINK_EVENT_TYPES,
    LINK_STATUSES,
    LinkStatus,
    next_status,
)
from tl_core.services.errors import InvalidLinkTransitionError

#: (event, flag) -> {status it is allowed in: status that follows}
ALLOWED: dict[tuple[str, str | None], dict[LinkStatus, LinkStatus]] = {
    ("Link.Accepted", None): {"suggested": "active"},
    ("Link.Declined", None): {"suggested": "retracted"},
    ("Link.Repinned", None): {"active": "active", "stale": "active"},
    ("Link.Verified", None): {"active": "active"},
    ("Link.Flagged", "stale"): {"active": "stale", "broken": "stale"},
    ("Link.Flagged", "broken"): {"active": "broken", "stale": "broken"},
    ("Link.Retracted", None): {
        "suggested": "retracted",
        "active": "retracted",
        "stale": "retracted",
        "broken": "retracted",
    },
}


@pytest.mark.parametrize("event_type", ["Link.Suggested", "Link.Added"])
def test_creating_events_start_a_link(event_type: str) -> None:
    expected = "suggested" if event_type == "Link.Suggested" else "active"
    assert next_status(None, event_type) == expected


@pytest.mark.parametrize("event_type", ["Link.Suggested", "Link.Added"])
@pytest.mark.parametrize("status", LINK_STATUSES)
def test_creating_events_refuse_an_existing_link(event_type: str, status: LinkStatus) -> None:
    with pytest.raises(InvalidLinkTransitionError):
        next_status(status, event_type)


@pytest.mark.parametrize(("event_type", "flag"), list(ALLOWED))
def test_every_other_event_needs_an_existing_link(event_type: str, flag: str | None) -> None:
    with pytest.raises(InvalidLinkTransitionError, match="existing link"):
        next_status(None, event_type, flag=flag)


@pytest.mark.parametrize(("event_type", "flag"), list(ALLOWED))
@pytest.mark.parametrize("status", LINK_STATUSES)
def test_the_full_transition_table(event_type: str, flag: str | None, status: LinkStatus) -> None:
    allowed = ALLOWED[(event_type, flag)]
    if status in allowed:
        assert next_status(status, event_type, flag=flag) == allowed[status]
    else:
        with pytest.raises(InvalidLinkTransitionError):
            next_status(status, event_type, flag=flag)


def test_retracted_is_terminal() -> None:
    for event_type, flag in ALLOWED:
        with pytest.raises(InvalidLinkTransitionError):
            next_status("retracted", event_type, flag=flag)


@pytest.mark.parametrize("flag", [None, "active", "retracted", "nonsense"])
def test_flagged_needs_a_stale_or_broken_status(flag: str | None) -> None:
    with pytest.raises(InvalidLinkTransitionError, match="stale' or 'broken"):
        next_status("active", "Link.Flagged", flag=flag)


def test_flagging_to_the_same_status_is_refused() -> None:
    with pytest.raises(InvalidLinkTransitionError, match="already stale"):
        next_status("stale", "Link.Flagged", flag="stale")


def test_an_unknown_event_type_is_refused() -> None:
    with pytest.raises(InvalidLinkTransitionError, match="not a link event"):
        next_status("active", "Link.Deleted")


def test_the_event_list_covers_the_eight_events_of_the_brief() -> None:
    assert sorted(LINK_EVENT_TYPES) == [
        "Link.Accepted",
        "Link.Added",
        "Link.Declined",
        "Link.Flagged",
        "Link.Repinned",
        "Link.Retracted",
        "Link.Suggested",
        "Link.Verified",
    ]
