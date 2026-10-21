"""The actions the engineering module offers on a tag (P1-UX2-S1): by state and by role.

Every command a tag offers is run for real inside a unit of work that is rolled back, so the offer
is held to what the handlers do; a tag that has left service is offered nothing.
"""

from __future__ import annotations

from typing import Any

import pytest
from engworld import seed_registry
from tl_adapters.db import DbTarget, open_uow
from tl_core import confidentiality as cf
from tl_core.actions import Level, allowed_actions
from tl_core.services.commands import CommandResult
from tl_core.services.errors import RecordNotFoundError
from tl_mod_engineering.actions import ENDED, RULES
from tl_mod_engineering.commands import API_COMMANDS
from tl_mod_engineering.errors import TagSupersededError
from tl_mod_engineering.handlers.tags import (
    CreateTag,
    MergeTags,
    ReclassifyTag,
    RenameTag,
    handle_create_tag,
    handle_merge_tags,
    handle_reclassify_tag,
    handle_rename_tag,
)

pytestmark = pytest.mark.usefixtures("fixture_schemas")

BASE: dict[str, Any] = {"actor": "user:u", "source": "test", "scope": "project:P123"}
RANK = {"user": 0, "controller": 1, "admin": 2}
ACCESS = {spec.model.__name__: spec.access for spec in API_COMMANDS}
VIEWERS: dict[str, tuple[cf.Viewer, Level]] = {
    "user": (cf.Viewer(actor="user:u", level=0, account="user:u"), "user"),
    "controller": (cf.Viewer(actor="user:ctl", level=1, account="user:ctl"), "controller"),
    "admin": (cf.Viewer(actor="user:boss", level=1, account="user:boss"), "admin"),
}


@pytest.fixture
def ledger(db: DbTarget) -> DbTarget:
    seed_registry(db)
    return db


def create(db: DbTarget, number: str = "47-FV-1001") -> CommandResult:
    fields: dict[str, Any] = {"number": number, "class_code": "ControlValve", "service": "Feed gas"}
    with open_uow(db) as uow:
        return handle_create_tag(uow, CreateTag(**{**BASE, **fields}))


def offered(db: DbTarget, tag_id: str, who: str) -> list[str]:
    viewer, level = VIEWERS[who]
    with cf.use_viewer(viewer), open_uow(db, readonly=True) as uow:
        found = allowed_actions(
            uow, tag_id, actor=viewer.actor, holds=lambda wanted: RANK[wanted] <= RANK[level]
        )
    return [a.command for a in found.actions]


def test_every_rule_names_a_command_of_the_module_with_the_same_access() -> None:
    assert [r.command for r in RULES] == ["ReclassifyTag", "RenameTag", "MergeTags"]
    for rule in RULES:
        assert ACCESS[rule.command] == rule.level, rule.command


@pytest.mark.parametrize("who", ["user", "controller", "admin"])
def test_a_tag_in_service_offers_what_any_signed_in_person_may_do(
    ledger: DbTarget, who: str
) -> None:
    made = create(ledger)
    assert offered(ledger, made.stream_id, who) == ["ReclassifyTag", "RenameTag", "MergeTags"]


def test_the_labels_are_plain_words(ledger: DbTarget) -> None:
    made = create(ledger)
    viewer, _ = VIEWERS["user"]
    with cf.use_viewer(viewer), open_uow(ledger, readonly=True) as uow:
        found = allowed_actions(uow, made.stream_id, actor=viewer.actor, holds=lambda _w: True)
    assert [a.label for a in found.actions] == ["Change class", "Rename", "Merge into another tag"]


class _Rollback(Exception):
    pass


def ended_refusal(db: DbTarget, tag_id: str, other_id: str) -> dict[str, bool]:
    """Per command, whether the handler refuses the tag as one that left service (rolled back)."""
    commands: dict[str, Any] = {
        "ReclassifyTag": (
            handle_reclassify_tag,
            ReclassifyTag(**BASE, stream_id=tag_id, class_code="ControlValve", reason="r"),
        ),
        "RenameTag": (
            handle_rename_tag,
            RenameTag(**BASE, stream_id=tag_id, new_number="47-FV-1009", reason="r"),
        ),
        "MergeTags": (
            handle_merge_tags,
            MergeTags(**BASE, stream_ids=[tag_id, other_id], new_number="47-FV-1010", reason="r"),
        ),
    }
    found: dict[str, bool] = {}
    for name, (handler, cmd) in commands.items():
        try:
            with open_uow(db) as uow:
                try:
                    handler(uow, cmd)
                except TagSupersededError:
                    found[name] = True
                    raise _Rollback from None
                except Exception:  # noqa: BLE001 - any other refusal is not about the state
                    pass
                raise _Rollback
        except _Rollback:
            found.setdefault(name, False)
    return found


def test_the_offer_is_what_the_handlers_do_not_refuse_as_a_tag_that_left_service(
    ledger: DbTarget,
) -> None:
    old = create(ledger)
    other = create(ledger, "47-FV-1002")
    with open_uow(ledger) as uow:
        handle_rename_tag(
            uow, RenameTag(**BASE, stream_id=old.stream_id, new_number="47-FV-1003", reason="r")
        )
    # a tag in service, and the one the rename left behind (Superseded)
    for tag_id, who in ((other.stream_id, "user"), (old.stream_id, "admin")):
        refused = ended_refusal(ledger, tag_id, other.stream_id)
        want = [name for name, no in refused.items() if not no]
        assert offered(ledger, tag_id, who) == want, tag_id


def test_a_tag_that_was_renamed_offers_nothing_and_its_successor_offers_everything(
    ledger: DbTarget,
) -> None:
    old = create(ledger)
    with open_uow(ledger) as uow:
        new = handle_rename_tag(
            uow, RenameTag(**BASE, stream_id=old.stream_id, new_number="47-FV-1002", reason="r")
        )
    for who in ("user", "controller", "admin"):
        assert offered(ledger, old.stream_id, who) == [], who
        assert offered(ledger, new.stream_id, who) == ["ReclassifyTag", "RenameTag", "MergeTags"]


def test_the_ended_states_are_the_ones_the_handlers_refuse() -> None:
    assert ENDED == ("Superseded", "Deleted")


def test_a_missing_tag_is_not_found(ledger: DbTarget) -> None:
    with pytest.raises(RecordNotFoundError, match="no record '01J000000000000000000000'"):
        offered(ledger, "01J000000000000000000000", "admin")


def test_an_agent_is_offered_nothing_on_a_tag(ledger: DbTarget) -> None:
    made = create(ledger)
    with open_uow(ledger, readonly=True) as uow:
        found = allowed_actions(uow, made.stream_id, actor="agent:bot", holds=lambda _w: True)
    assert found.actions == []
