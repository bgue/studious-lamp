"""Issue, revoke and rotate: rules, fixed messages, and a code that is never written anywhere."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import pytest
from pydantic import ValidationError
from qr_world import BASE, CARDED, CARDLESS, NOW, SCOPE, FakeProvider, World
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.auth.errors import ForbiddenError
from tl_core.services.errors import RecordNotFoundError
from tl_core.util import new_ulid, utcnow
from tl_mod_qr import service
from tl_mod_qr.codes import code_hash, grouped
from tl_mod_qr.errors import (
    MSG_BASE,
    MSG_CAP,
    MSG_EXPIRY,
    MSG_REVOKED,
    MSG_UNKNOWN,
    QrRuleError,
    QrStateError,
)
from tl_mod_qr.resolve import resolve

ISSUE = "IssueScanCode"
REVOKE = "RevokeScanCode"
ROTATE = "RotateScanCode"
CODES = "SELECT * FROM cur_qr_scan_code ORDER BY issued_at, id"
EVENTS = "SELECT * FROM events WHERE stream_type = 'qr.ScanCode'"


def issued(world: World, target: str, who: str = "uma", **more: Any) -> service.IssuedCode:
    return world.serve(service.issue, who, ISSUE, target_id=target, **more)


def lookup(world: World, code: str) -> object:
    viewer = cf.Viewer(actor="user:uma", level=0, account="user:uma")
    with open_uow(world.db, readonly=True) as uow:
        return resolve(uow.conn(), code, viewer, NOW)


def written(world: World) -> int:
    return len(world.rows(EVENTS))


# --- issue ------------------------------------------------------------------------------------


def test_issue_is_refused_while_the_public_address_is_empty(
    bare: World, provider: FakeProvider
) -> None:
    del provider
    target = bare.record()
    with pytest.raises(QrRuleError) as caught:
        issued(bare, target)
    assert str(caught.value) == MSG_BASE == "set api.public_base_url first"
    assert written(bare) == 0


def test_issue_with_the_address_set_gives_the_code_once_and_stores_the_hash(world: World) -> None:
    target = world.record()
    made = issued(world, target, label_text="Pump P-101", size="card")
    (row,) = world.rows(CODES)
    assert row["code_hash"] == code_hash(made.code)
    assert (row["target_id"], row["target_type"], row["issued_by"]) == (target, CARDED, "user:uma")
    assert (row["label_text"], row["size"], row["scope"]) == ("Pump P-101", "card", SCOPE)
    assert row["id"] == made.result.stream_id and made.result.key is None
    assert lookup(world, made.code) is not None
    assert made.code not in repr(made)


def test_the_handler_is_the_service_minus_the_code(world: World) -> None:
    target = world.record()
    result = world.call("uma", ISSUE, target_id=target)
    (row,) = world.rows(CODES)
    assert row["id"] == result.stream_id
    assert world.rows("SELECT 1 FROM events WHERE event_type = 'ScanCode.Issued'")


def test_an_expiry_in_the_past_is_refused_and_today_is_not(world: World) -> None:
    target = world.record()
    today = utcnow().date()
    with pytest.raises(QrRuleError) as caught:
        issued(world, target, expires_on=today - timedelta(days=1))
    assert str(caught.value) == MSG_EXPIRY
    issued(world, target, expires_on=today)
    assert len(world.rows(CODES)) == 1


@pytest.mark.parametrize("kind", ["hidden", "cardless", "missing", "project", "not_record"])
def test_a_target_that_cannot_be_used_answers_one_text_and_writes_nothing(
    world: World, kind: str
) -> None:
    target = {
        "hidden": lambda: world.hidden_record(),
        "cardless": lambda: world.record(CARDLESS, "W-1"),
        "missing": new_ulid,
        "project": lambda: world.record(CARDED, "O-1", "project:OTHER"),
        "not_record": lambda: "not an id",
    }[kind]()
    before = written(world)
    with pytest.raises(RecordNotFoundError) as caught:
        issued(world, target)
    assert str(caught.value) == MSG_UNKNOWN
    assert written(world) == before


def test_the_cap_refuses_the_next_live_code_and_a_revoke_frees_a_place(world: World) -> None:
    world.cap(2)
    target = world.record()
    first, _second = issued(world, target), issued(world, target)
    with pytest.raises(QrRuleError) as caught:
        issued(world, target)
    assert str(caught.value) == MSG_CAP
    assert not any(ch.isdigit() for ch in MSG_CAP)
    world.call("ada", REVOKE, code_id=first.result.stream_id, reason="lost")
    issued(world, target)
    assert len(world.rows(CODES)) == 3


def test_an_expired_code_does_not_count_against_the_cap(world: World) -> None:
    world.cap(1)
    target = world.record()
    old = issued(world, target)
    with open_uow(world.db) as uow:  # age the code: it ended yesterday
        uow.conn().execute(
            text("UPDATE cur_qr_scan_code SET expires_on = :d WHERE id = :i"),
            {"d": (utcnow().date() - timedelta(days=1)).isoformat(), "i": old.result.stream_id},
        )
    issued(world, target)


def test_the_models_refuse_an_unknown_field_a_long_label_and_a_control_character(
    world: World,
) -> None:
    target = world.record()
    for bad in (
        {"code": "AAAA"},
        {"label_text": "x" * 41},
        {"label_text": "a\nb"},
        {"label_text": "  "},
        {"size": "poster"},
    ):
        with pytest.raises(ValidationError):
            world.command("uma", ISSUE, target_id=target, **bad)
    with pytest.raises(ValidationError):
        world.command("uma", REVOKE, code_id="x", reason="")
    with pytest.raises(ValidationError):
        world.command("uma", ROTATE, code_id="x", reason="r" * 301)


# --- revoke -----------------------------------------------------------------------------------


def test_revoke_needs_the_controller_word_and_fixes_the_state(world: World) -> None:
    target = world.record()
    made = issued(world, target)
    code_id = made.result.stream_id
    with pytest.raises(ForbiddenError):
        world.call("uma", REVOKE, code_id=code_id, reason="lost")
    world.call("ada", REVOKE, code_id=code_id, reason="lost")
    (row,) = world.rows(CODES)
    assert (row["revoked_by"], row["revoke_reason"], row["replaced_by_id"]) == (
        "user:ada",
        "lost",
        None,
    )
    assert lookup(world, made.code) is None
    with pytest.raises(QrStateError) as caught:
        world.call("ada", REVOKE, code_id=code_id, reason="again")
    assert str(caught.value) == MSG_REVOKED


def test_revoke_of_an_unknown_id_and_of_a_hidden_codes_id_answer_alike(world: World) -> None:
    secret = world.hidden_record()
    with pytest.raises(RecordNotFoundError) as unknown:
        world.call("ada", REVOKE, code_id=new_ulid(), reason="x")
    assert str(unknown.value) == MSG_UNKNOWN
    # a code of a record that became hidden: issued by the cleared reader, read by a low one
    made = world.serve(service.issue, "dora", ISSUE, target_id=secret)
    with pytest.raises(RecordNotFoundError) as hidden:
        world.serve(
            service.revoke, "uma", REVOKE, check=False, code_id=made.result.stream_id, reason="x"
        )
    assert str(hidden.value) == MSG_UNKNOWN


# --- rotate -----------------------------------------------------------------------------------


def test_rotate_revokes_the_old_code_and_issues_a_new_one_like_it(world: World) -> None:
    world.cap(1)  # the old code leaves its place to the new one
    target = world.record()
    made = issued(world, target, label_text="Pump", size="card")
    fresh = world.serve(service.rotate, "uma", ROTATE, code_id=made.result.stream_id, reason="worn")
    assert lookup(world, made.code) is None
    assert lookup(world, fresh.code) is not None
    old, new = world.rows(CODES)
    assert old["id"] == made.result.stream_id and new["id"] == fresh.result.stream_id
    assert old["revoked_at"] is not None and old["replaced_by_id"] == new["id"]
    assert (old["revoke_reason"], old["revoked_by"]) == ("worn", "user:uma")
    assert (new["target_id"], new["label_text"], new["size"]) == (target, "Pump", "card")
    assert new["revoked_at"] is None and new["code_hash"] != old["code_hash"]


def test_rotate_of_a_revoked_code_is_refused(world: World) -> None:
    target = world.record()
    made = issued(world, target)
    world.call("ada", REVOKE, code_id=made.result.stream_id, reason="lost")
    with pytest.raises(QrStateError) as caught:
        world.serve(service.rotate, "uma", ROTATE, code_id=made.result.stream_id, reason="x")
    assert str(caught.value) == MSG_REVOKED


def test_rotate_is_refused_when_the_address_was_emptied_and_changes_nothing(world: World) -> None:
    target = world.record()
    made = issued(world, target)
    world.base("")
    before = written(world)
    with pytest.raises(QrRuleError):
        world.serve(service.rotate, "uma", ROTATE, code_id=made.result.stream_id, reason="x")
    assert written(world) == before
    world.base(BASE)
    assert lookup(world, made.code) is not None


def test_a_reader_who_cannot_see_the_target_cannot_rotate_its_code(world: World) -> None:
    secret = world.hidden_record()
    made = world.serve(service.issue, "dora", ISSUE, target_id=secret)
    with pytest.raises(RecordNotFoundError) as caught:
        world.serve(service.rotate, "uma", ROTATE, code_id=made.result.stream_id, reason="x")
    assert str(caught.value) == MSG_UNKNOWN


def test_the_cleared_reader_issues_for_a_restricted_record_and_the_low_one_cannot(
    world: World,
) -> None:
    secret = world.hidden_record()
    with pytest.raises(RecordNotFoundError):
        issued(world, secret, who="uma")
    assert issued(world, secret, who="dora").code


# --- the code is written nowhere --------------------------------------------------------------


def test_no_event_error_text_or_log_line_holds_the_code(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    target = world.record()
    texts: list[str] = []
    made = issued(world, target, label_text="Pump")
    again = world.serve(service.rotate, "uma", ROTATE, code_id=made.result.stream_id, reason="r")
    for attempt in (
        lambda: issued(world, new_ulid()),
        lambda: world.call("ada", REVOKE, code_id=made.result.stream_id, reason="r"),
        lambda: world.serve(
            service.rotate, "uma", ROTATE, code_id=made.result.stream_id, reason="r"
        ),
    ):
        with pytest.raises(Exception) as caught:
            attempt()
        texts += [str(caught.value), repr(caught.value)]
    for code in (made.code, again.code):
        needles = {code, grouped(code), grouped(code).lower(), code.lower()}
        everything = "\n".join(
            str(v) for row in world.rows("SELECT * FROM events") for v in row.values()
        )
        everything += "\n".join(
            str(v) for row in world.rows("SELECT * FROM cur_qr_scan_code") for v in row.values()
        )
        everything += "\n".join(texts) + caplog.text + repr(made) + repr(again)
        assert not any(n in everything for n in needles)
