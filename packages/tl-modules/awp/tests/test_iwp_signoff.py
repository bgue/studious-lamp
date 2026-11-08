"""S3: IWP sign-off, issue and hold (P2-I2-S3); readiness rows are written by hand."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

import pytest
from awp_world import SCOPE, World, refuses
from s3_checks import MINE, ROLES, build, hash_of, permit_registry, readiness
from tl_adapters.db import open_uow, rebuild_projections
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_roles import require_command_access
from tl_core.links.expected import missing_expected_links
from tl_core.settings.service import set_setting
from tl_mod_awp import actions, errors


@pytest.fixture
def w(tmp_path: Path) -> World:
    return build(tmp_path / "s3.db")


def make_iwp(w: World) -> str:
    i = w.iwp(title="Rack secret", planned_start="2026-12-01", foreman="user:uma")
    w.call("uma", "AddIwpScope", iwp=i, items=w.items(["10.0", "20.0"]))
    return i


def ready(w: World, signable: bool = True) -> str:
    i = make_iwp(w)
    w.set_status(i, "Ready")
    if signable:
        readiness(w, i, True)
    return i


def sign(w: World, who: str, i: str, rh: str | None = None) -> Any:
    return w.call(who, "SignOffIwp", iwp=i, record_hash=rh or hash_of(w, i))


def issue(w: World, who: str, i: str, rh: str | None = None, **more: Any) -> Any:
    return w.call(who, "IssueIwp", iwp=i, record_hash=rh or hash_of(w, i), **more)


def set_roles(w: World, roles: list[str]) -> None:
    with open_uow(w.db) as uow:
        set_setting(
            uow,
            key=ROLES,
            layer=f"project:{SCOPE[8:]}",
            value=roles,
            actor="user:ada",
            source="test",
            reason="t",
            accept_risk=True,
        )


@pytest.mark.parametrize("name", sorted(MINE))
def test_user_refused_every_signoff_command(w: World, name: str) -> None:
    cmd = MINE[name].model.model_construct(actor="user:uma", source="test", scope=SCOPE)
    with open_uow(w.db, readonly=True) as uow:
        refuses(ForbiddenError, partial(require_command_access, uow.conn(), cmd))


def test_signoff_needs_ready_state(w: World) -> None:
    refuses(errors.IwpStateError, partial(sign, w, "sue", make_iwp(w)))


@pytest.mark.parametrize("rows", ["none", "false", "unknown"])
def test_signoff_refused_when_not_ready(w: World, rows: str) -> None:
    i = ready(w, signable=False)
    if rows == "false":
        readiness(w, i, False)
    elif rows == "unknown":
        readiness(w, i, True, unknown=True)
    refuses(errors.IwpNotReadyError, partial(sign, w, "sue", i))
    readiness(w, i, True)
    assert sign(w, "sue", i)  # the same IWP signs once the rows say ready


def test_wrong_record_hash_refused_on_signoff_and_issue(w: World) -> None:
    i = ready(w)
    refuses(errors.IwpSignoffError, partial(sign, w, "sue", i, "0" * 64))
    sign(w, "sue", i)
    sign(w, "sam", i)
    refuses(errors.IwpSignoffError, partial(issue, w, "sue", i, "0" * 64))


def test_signer_without_the_role_refused(w: World) -> None:
    i = ready(w)
    set_roles(w, ["user"])
    refuses(errors.IwpSignoffError, partial(sign, w, "sue", i))
    set_roles(w, ["superuser"])
    assert sign(w, "sue", i)


def test_distinct_signers_needed(w: World) -> None:
    i = ready(w)
    set_roles(w, ["superuser"])
    sign(w, "sue", i)
    refuses(errors.IwpSignoffError, partial(sign, w, "sue", i))
    refuses(errors.IwpSignoffError, partial(issue, w, "sue", i))
    sign(w, "sam", i)
    rows = w.rows("SELECT signoffs_json FROM cur_awp_iwp WHERE id = :i", i=i)
    assert rows[0]["signoffs_json"].count('"by"') == 2


def signed_and_issued(w: World) -> tuple[str, Any]:
    i = ready(w)
    set_roles(w, ["superuser"])
    sign(w, "sue", i)
    sign(w, "sam", i)
    return i, issue(w, "sue", i, foreman="user:sam")


def test_issue_sets_foreman_and_permit_is_reported_missing_not_blocking(w: World) -> None:
    i, made = signed_and_issued(w)
    assert w.state(i) == "Issued" and w.column("cur_awp_iwp", "foreman", i) == "user:sam"
    with open_uow(w.db, readonly=True) as uow:
        gaps = missing_expected_links(uow, i, registry=permit_registry(), by_state="Issued")
    assert [g.expectation.display for g in gaps] == ["permit to work"]
    assert len(made.events) == 2  # issued, and nothing blocked it


def test_old_signatures_do_not_count_after_a_change(w: World) -> None:
    i = ready(w)
    set_roles(w, ["superuser"])
    sign(w, "sue", i)
    sign(w, "sam", i)
    w.set_status(i, "Constraint check")
    w.call("uma", "AddIwpScope", iwp=i, items=w.items(["5.0"]))
    w.set_status(i, "Ready")
    refuses(errors.IwpSignoffError, partial(issue, w, "sue", i))


def test_hold_and_release(w: World) -> None:
    i = ready(w)
    w.call("sue", "HoldIwp", iwp=i, reason="Waiting")
    assert w.state(i) == "On hold"
    w.call("sue", "ReleaseHold", iwp=i)
    assert w.state(i) == "Constraint check"
    for state in ("Issued", "In progress"):
        w.set_status(i, state)
        w.call("sue", "HoldIwp", iwp=i, reason="Wait")
        assert w.state(i) == "On hold"
        w.call("sue", "ReleaseHold", iwp=i, reason="ok")


def test_hold_refused_from_other_states(w: World) -> None:
    refuses(errors.IwpStateError, partial(w.call, "sue", "HoldIwp", iwp=make_iwp(w), reason="x"))


def test_refusal_texts_hold_no_cell_or_role_list(w: World) -> None:
    i = ready(w)
    set_roles(w, ["user"])
    calls: list[Callable[[], Any]] = [
        partial(sign, w, "sue", i, "0" * 64),
        partial(sign, w, "sue", i),
    ]
    said = [str(refuses(errors.IwpSignoffError, c)) for c in calls]
    assert not any("secret" in s or "superuser" in s for s in said)


def test_rules_words_equal_command_words() -> None:
    assert all(r.word == MINE[r.command].access for r in actions.RULES if r.command in MINE)


def test_rebuild_equals_incremental(w: World) -> None:
    signed_and_issued(w)
    tables = ("cur_awp_iwp", "cur_core_record", "cur_links")
    before = [w.rows(f"SELECT * FROM {t} ORDER BY 1") for t in tables]
    rebuild_projections(w.db)
    assert before == [w.rows(f"SELECT * FROM {t} ORDER BY 1") for t in tables]
