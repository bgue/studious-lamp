"""The actions the correspondence module offers on an item (P1-UX2-S1).

The offer must equal what the handlers would allow: for every state of an item and every kind of
viewer, each command is driven for real (inside a unit of work that is rolled back) and the set of
commands the handlers do not refuse on state or access grounds is compared with the offered set.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.actions import ActionOffer, Level, RecordActions, allowed_actions
from tl_core.auth.errors import ForbiddenError
from tl_core.services.commands import Command
from tl_core.services.errors import RecordNotFoundError
from tl_mod_correspondence.actions import RULES, effective_level, states_for
from tl_mod_correspondence.commands import API_COMMANDS
from tl_mod_correspondence.errors import CorrespondenceError, ItemStateError
from tl_mod_correspondence.handlers.commercial import (
    ReturnCommercial,
    ReviewCommercial,
    SubmitCommercial,
)
from tl_mod_correspondence.handlers.commercial_flow import (
    AssessCommercial,
    CloseCommercial,
    IssueCommercial,
    ReferCommercialToLegal,
)
from tl_mod_correspondence.handlers.escalate import EscalateTechnical
from tl_mod_correspondence.handlers.issue import IssueCorrespondence
from tl_mod_correspondence.handlers.responses import (
    CloseCorrespondence,
    RecordResponse,
    VoidCorrespondence,
    VoidDraft,
)
from tl_mod_correspondence.handlers.technical import ReturnTechnical, SubmitTechnical
from tl_mod_correspondence.handlers.technical_flow import (
    AnswerTechnical,
    CloseTechnical,
    IssueTechnical,
    ReissueTechnical,
    ReviewTechnicalAnswer,
)
from tl_mod_correspondence.handlers.triage import ConfirmTriage
from tl_mod_correspondence.names import COMMERCIAL, CORRESPONDENCE, TECHNICAL
from tl_mod_correspondence.testing import BASE, CONTROLLER, CorrWorld, frozen_today

USER = cf.Viewer(actor="user:u", level=0, account="user:u")
ADMIN = cf.Viewer(actor="user:boss", level=1, account="user:boss")
VIEWERS: dict[str, tuple[cf.Viewer, Level]] = {
    "user": (USER, "user"),
    "controller": (CONTROLLER, "controller"),
    "admin": (ADMIN, "admin"),
}
RANK = {"user": 0, "controller": 1, "admin": 2}
ACCESS = {spec.model.__name__: spec.access for spec in API_COMMANDS}
HANDLER = {spec.model.__name__: spec.handler for spec in API_COMMANDS}
LABEL = {rule.command: rule.label for rule in RULES}


def holds_for(level: Level) -> Callable[[Level], bool]:
    return lambda wanted: RANK[wanted] <= RANK[level]


def offered(world: CorrWorld, item_id: str, viewer: cf.Viewer, level: Level) -> list[ActionOffer]:
    with cf.use_viewer(viewer), open_uow(world.db, readonly=True) as uow:
        found = allowed_actions(uow, item_id, actor=viewer.actor, holds=holds_for(level))
    return found.actions


class _Refused(Exception):
    pass


class _Rollback(Exception):
    pass


def unrefused(world: CorrWorld, name: str, cmd: Command, viewer: cf.Viewer, level: Level) -> bool:
    """True when running ``cmd`` is not refused on state or access grounds.

    The access word of the command is the API's gate (not the handler's), so it is checked here
    the way the gate does; the handler is then run for real inside a unit of work that is rolled
    back whatever happens. Any other refusal (a missing recipient, a reason) is a question of the
    data the person types, not of what the item is.
    """
    if RANK[level] < RANK[ACCESS[name]]:
        return False
    try:
        with cf.use_viewer(viewer), open_uow(world.db) as uow:
            try:
                HANDLER[name](uow, cmd)
            except (ItemStateError, ForbiddenError) as exc:
                raise _Refused from exc
            except RecordNotFoundError:
                raise
            except CorrespondenceError:
                pass
            raise _Rollback
    except _Refused:
        return False
    except _Rollback:
        return True
    return True  # pragma: no cover


def cmd_of(model: type[Command], item_id: str, **fields: Any) -> Command:
    return model(**{**BASE, "stream_id": item_id, **fields})


def technical_commands(item_id: str) -> dict[str, Command]:
    return {
        "SubmitTechnical": cmd_of(SubmitTechnical, item_id),
        "ReturnTechnical": cmd_of(ReturnTechnical, item_id, reason="needs the drawing"),
        "IssueTechnical": cmd_of(IssueTechnical, item_id),
        "AnswerTechnical": cmd_of(
            AnswerTechnical, item_id, answer="Re-route above the beam.", cost_impact="no"
        ),
        "ReviewTechnicalAnswer": cmd_of(ReviewTechnicalAnswer, item_id, decision="accepted"),
        "ReissueTechnical": cmd_of(ReissueTechnical, item_id, reason="names both beams"),
        "CloseTechnical": cmd_of(CloseTechnical, item_id, reason="no longer needed"),
        "EscalateTechnical": cmd_of(EscalateTechnical, item_id),
        "VoidDraft": cmd_of(VoidDraft, item_id, reason="made in error"),
        "VoidCorrespondence": cmd_of(VoidCorrespondence, item_id, reason="filed in error"),
    }


def commercial_commands(item_id: str) -> dict[str, Command]:
    return {
        "SubmitCommercial": cmd_of(SubmitCommercial, item_id),
        "ReviewCommercial": cmd_of(ReviewCommercial, item_id),
        "ReturnCommercial": cmd_of(ReturnCommercial, item_id, reason="figures missing"),
        "IssueCommercial": cmd_of(IssueCommercial, item_id),
        "AssessCommercial": cmd_of(
            AssessCommercial, item_id, status="agreed", assessed_value="12500.00"
        ),
        "CloseCommercial": cmd_of(CloseCommercial, item_id, reason="settled"),
        "ReferCommercialToLegal": cmd_of(ReferCommercialToLegal, item_id, reason="formal"),
        "VoidDraft": cmd_of(VoidDraft, item_id, reason="made in error"),
        "VoidCorrespondence": cmd_of(VoidCorrespondence, item_id, reason="filed in error"),
    }


def letter_commands(item_id: str, other_id: str) -> dict[str, Command]:
    return {
        "ConfirmTriage": cmd_of(ConfirmTriage, item_id, domain="general", subtype="letter"),
        "RecordResponse": cmd_of(RecordResponse, item_id, response_id=other_id),
        "CloseCorrespondence": cmd_of(CloseCorrespondence, item_id, reason="no answer needed"),
        "IssueCorrespondence": cmd_of(IssueCorrespondence, item_id),
        "VoidDraft": cmd_of(VoidDraft, item_id, reason="made in error"),
        "VoidCorrespondence": cmd_of(VoidCorrespondence, item_id, reason="filed in error"),
    }


def not_refused(
    world: CorrWorld,
    commands: dict[str, Command],
    viewer: cf.Viewer,
    level: Level,
) -> set[str]:
    """The labels of the commands the handlers let through, one label once."""
    clean = {name for name, cmd in commands.items() if unrefused(world, name, cmd, viewer, level)}
    if "VoidDraft" in clean:  # the person's own void and the controller's are one word
        clean.discard("VoidCorrespondence")
    return clean


def asked(world: CorrWorld, item_id: str, who: str) -> set[str]:
    viewer, level = VIEWERS[who]
    return {a.command for a in offered(world, item_id, viewer, level)}


# --- the table is the handlers' ------------------------------------------------------------


def test_every_rule_names_a_command_of_the_module_with_the_same_access() -> None:
    """The level is written once here and once in ``API_COMMANDS``: they cannot drift apart."""
    for rule in RULES:
        assert rule.command in ACCESS, rule.command
        assert ACCESS[rule.command] == rule.level, rule.command


def test_a_pair_the_table_does_not_hold_is_a_key_error() -> None:
    assert states_for("AnswerTechnical", TECHNICAL) == ("Awaiting response",)
    with pytest.raises(KeyError):
        states_for("AnswerTechnical", CORRESPONDENCE)


def test_a_commercial_item_asks_for_a_controller_whatever_the_command_says() -> None:
    void = next(rule for rule in RULES if rule.command == "VoidDraft")
    assert void.level == "user"
    assert effective_level(void, COMMERCIAL) == "controller"
    assert effective_level(void, TECHNICAL) == "user"


# --- an RFI in each state, for each viewer ------------------------------------------------

RFI_STATES = (
    "Draft",
    "Internal review",
    "Awaiting response",
    "Answered",
    "Rejected",
    "Accepted",
    "Closed",
    "Void",
)


@pytest.fixture
def rfis(world: CorrWorld) -> dict[str, str]:
    found: dict[str, str] = {}
    with frozen_today("2026-10-19"):
        for n, state in enumerate(RFI_STATES, start=1):
            number = f"P123-RFI-{n:04d}"
            if state == "Void":
                found[state] = world.forge_technical(number, state="Draft")
                world.void_draft(found[state])
            else:
                found[state] = world.forge_technical(number, state=state)
    return found


@pytest.mark.parametrize("who", ["user", "controller", "admin"])
@pytest.mark.parametrize("state", RFI_STATES)
def test_the_offered_set_is_what_the_handlers_do_not_refuse_for_an_rfi(
    world: CorrWorld, rfis: dict[str, str], state: str, who: str
) -> None:
    viewer, level = VIEWERS[who]
    item_id = rfis[state]
    with frozen_today("2026-10-19"):
        want = not_refused(world, technical_commands(item_id), viewer, level)
    assert asked(world, item_id, who) == want, (state, who)


def test_the_rfi_flow_offers_the_next_step_to_the_person_who_takes_it(
    world: CorrWorld, rfis: dict[str, str]
) -> None:
    assert asked(world, rfis["Draft"], "user") == {"SubmitTechnical", "VoidDraft"}
    assert asked(world, rfis["Internal review"], "user") == {
        "ReturnTechnical",
        "VoidDraft",
    }
    assert asked(world, rfis["Internal review"], "controller") >= {"IssueTechnical"}
    assert asked(world, rfis["Awaiting response"], "user") == {"AnswerTechnical", "CloseTechnical"}
    assert asked(world, rfis["Answered"], "user") == {"ReviewTechnicalAnswer"}
    assert asked(world, rfis["Rejected"], "user") == {"ReissueTechnical", "CloseTechnical"}
    assert asked(world, rfis["Accepted"], "controller") == {"CloseTechnical", "EscalateTechnical"}
    for state in ("Closed", "Void"):
        assert not [a for a in asked(world, rfis[state], "user")], state


def test_an_answer_is_offered_while_awaiting_a_response_and_not_in_draft(
    world: CorrWorld, rfis: dict[str, str]
) -> None:
    assert "AnswerTechnical" in asked(world, rfis["Awaiting response"], "user")
    assert "AnswerTechnical" not in asked(world, rfis["Draft"], "user")
    assert "AnswerTechnical" not in asked(world, rfis["Draft"], "admin")


def test_issuing_is_offered_to_a_controller_and_not_to_a_user(
    world: CorrWorld, rfis: dict[str, str]
) -> None:
    review = rfis["Internal review"]
    assert "IssueTechnical" not in asked(world, review, "user")
    assert "IssueTechnical" in asked(world, review, "controller")
    assert "IssueTechnical" in asked(world, review, "admin")


def test_the_labels_are_plain_words_and_the_void_is_one_word(
    world: CorrWorld, rfis: dict[str, str]
) -> None:
    ctl = offered(world, rfis["Draft"], CONTROLLER, "controller")
    assert [a.label for a in ctl] == ["Submit for review", "Void"]
    assert [a.command for a in ctl] == ["SubmitTechnical", "VoidDraft"]
    assert all(a.label == LABEL[a.command] for a in ctl)


def test_an_rfi_is_escalated_once_and_after_an_answer(
    world: CorrWorld, rfis: dict[str, str]
) -> None:
    answered = rfis["Answered"]
    assert "EscalateTechnical" in asked(world, answered, "controller")
    assert "EscalateTechnical" not in asked(world, answered, "user")
    assert "EscalateTechnical" not in asked(world, rfis["Awaiting response"], "controller")
    with frozen_today("2026-10-21"), cf.use_viewer(CONTROLLER):
        world.escalate(answered)
    assert "EscalateTechnical" not in asked(world, answered, "controller")


def test_a_privileged_item_not_named_to_the_viewer_answers_not_found(world: CorrWorld) -> None:
    secret = world.forge_technical(
        "P123-RFI-0042", state="Awaiting response", confidentiality="privileged"
    )
    for who in ("user", "controller", "admin"):
        with pytest.raises(RecordNotFoundError) as caught:
            asked(world, secret, who)
        assert str(caught.value) == f"no record {secret!r}"
    missing = "01J000000000000000000000"
    with pytest.raises(RecordNotFoundError) as unknown:
        asked(world, missing, "controller")
    assert str(unknown.value).replace(missing, "X") == str(caught.value).replace(secret, "X")
    named = cf.Viewer(actor="user:amy", level=0, account="user:amy")
    world.forge_item_event(
        secret,
        "Correspondence.ClearanceGranted",
        {"account": "user:amy", "granted_on": "2026-10-19", "reason": "counsel"},
    )
    assert [a.command for a in offered(world, secret, named, "user")] == [
        "AnswerTechnical",
        "CloseTechnical",
    ]


# --- commercial items -----------------------------------------------------------------------

COMMERCIAL_STATES = (
    "Draft",
    "Commercial review",
    "PM approval",
    "Issued",
    "Awaiting assessment",
    "Agreed",
    "Disputed",
    "Partially agreed",
    "Closed",
    "Escalated",
)


@pytest.fixture
def notices(world: CorrWorld) -> dict[str, str]:
    """One notice per state, of class ``internal`` so that a plain user can read it: the offers
    are then judged on the access alone (a restricted one is not found by a plain user)."""
    found: dict[str, str] = {}
    with frozen_today("2026-10-19"):
        for n, state in enumerate(COMMERCIAL_STATES, start=1):
            found[state] = world.forge_commercial(
                f"P123-EW-{n:04d}", state=state, confidentiality="internal"
            )
    return found


@pytest.mark.parametrize("who", ["user", "controller", "admin"])
@pytest.mark.parametrize("state", COMMERCIAL_STATES)
def test_the_offered_set_is_what_the_handlers_do_not_refuse_for_a_commercial_item(
    world: CorrWorld, notices: dict[str, str], state: str, who: str
) -> None:
    viewer, level = VIEWERS[who]
    with frozen_today("2026-10-19"):
        want = not_refused(world, commercial_commands(notices[state]), viewer, level)
    assert asked(world, notices[state], who) == want, (state, who)


def test_commercial_items_offer_nothing_to_a_plain_user_and_the_controller_set_to_a_controller(
    world: CorrWorld, notices: dict[str, str]
) -> None:
    for state, item_id in notices.items():
        assert asked(world, item_id, "user") == set(), state
    assert asked(world, notices["Draft"], "controller") == {"SubmitCommercial", "VoidDraft"}
    assert asked(world, notices["PM approval"], "controller") == {
        "ReturnCommercial",
        "IssueCommercial",
        "VoidDraft",
    }
    assert asked(world, notices["Disputed"], "admin") == {
        "CloseCommercial",
        "ReferCommercialToLegal",
    }
    assert asked(world, notices["Awaiting assessment"], "controller") == {"AssessCommercial"}
    assert asked(world, notices["Closed"], "controller") == set()


def test_a_restricted_commercial_item_is_not_found_by_a_plain_user(world: CorrWorld) -> None:
    restricted = world.forge_commercial("P123-EW-0099", state="Draft")  # restricted by default
    with pytest.raises(RecordNotFoundError):
        asked(world, restricted, "user")
    assert asked(world, restricted, "controller") == {"SubmitCommercial", "VoidDraft"}


# --- letters and minutes ----------------------------------------------------------------------


@pytest.fixture
def letters(world: CorrWorld) -> dict[str, str]:
    found = {
        "Draft out": world.forge_item("P123-COR-0001", direction="out", state="Draft"),
        "Draft in": world.forge_item("P123-COR-0002", direction="in", state="Draft"),
        "Received": world.forge_item("P123-COR-0003", state="Received"),
        "Triaged": world.forge_item("P123-COR-0004", state="Triaged"),
        "Issued": world.forge_item("P123-COR-0005", direction="out", state="Issued"),
        "Responded": world.forge_item("P123-COR-0006", state="Responded"),
    }
    closed = world.forge_item("P123-COR-0007", state="Triaged")
    world.close(closed, reason="no answer needed")
    found["Closed"] = closed
    gone = world.forge_item("P123-COR-0008", direction="out", state="Draft")
    world.void_draft(gone)
    found["Void"] = gone
    return found


@pytest.mark.parametrize("who", ["user", "controller", "admin"])
@pytest.mark.parametrize(
    "state",
    ["Draft out", "Draft in", "Received", "Triaged", "Issued", "Responded", "Closed", "Void"],
)
def test_the_offered_set_is_what_the_handlers_do_not_refuse_for_a_letter(
    world: CorrWorld, letters: dict[str, str], state: str, who: str
) -> None:
    viewer, level = VIEWERS[who]
    other = letters["Received"] if state != "Received" else letters["Triaged"]
    want = not_refused(world, letter_commands(letters[state], other), viewer, level)
    assert asked(world, letters[state], who) == want, (state, who)


def test_a_letter_we_received_is_never_offered_for_issue(
    world: CorrWorld, letters: dict[str, str]
) -> None:
    assert "IssueCorrespondence" in asked(world, letters["Draft out"], "controller")
    assert "IssueCorrespondence" not in asked(world, letters["Draft in"], "controller")


def test_a_received_letter_is_voided_by_a_controller_only(
    world: CorrWorld, letters: dict[str, str]
) -> None:
    assert asked(world, letters["Received"], "user") == {"ConfirmTriage", "RecordResponse"}
    assert asked(world, letters["Received"], "controller") == {
        "ConfirmTriage",
        "RecordResponse",
        "VoidCorrespondence",
    }


def test_the_state_is_reported_with_the_offers(world: CorrWorld, rfis: dict[str, str]) -> None:
    with cf.use_viewer(USER), open_uow(world.db, readonly=True) as uow:
        found: RecordActions = allowed_actions(
            uow, rfis["Awaiting response"], actor="user:u", holds=holds_for("user")
        )
    assert found.state == "Awaiting response" and found.record_id == rfis["Awaiting response"]
