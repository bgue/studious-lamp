"""Weekly plan commands, commitments, outcomes and the PPC (P2-I5 S4a)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pytest
from awp_world import SCOPE, World, refuses
from progress_world import WeekWorld, build_week_world, week_checks
from pydantic import ValidationError
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.services.errors import RecordNotFoundError
from tl_mod_awp import errors
from tl_mod_awp.commands import AWP_COMMANDS, CommitIwpToWeek
from tl_mod_awp.handlers.week import iso_week
from tl_mod_awp.module import spec
from tl_mod_awp.week_views import list_weeks, miss_reasons, week_detail


@pytest.fixture
def ww(world: World) -> WeekWorld:
    return build_week_world(world)


def _events(ww: WeekWorld, plan: str) -> list[str]:
    rows = ww.w.rows("SELECT event_type FROM events WHERE stream_id = :i ORDER BY seq", i=plan)
    return [str(r["event_type"]) for r in rows]


def test_the_acceptance_checks_pass(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    week_checks(build_week_world(world))
    assert capsys.readouterr().out.count("PASS ") == 19


@pytest.mark.parametrize(
    ("day", "monday", "week"),
    [
        ("2026-11-04", "2026-11-02", "2026-W45"),
        ("2026-11-02", "2026-11-02", "2026-W45"),
        ("2026-11-08", "2026-11-02", "2026-W45"),
        ("2027-01-01", "2026-12-28", "2026-W53"),
        ("2024-12-30", "2024-12-30", "2025-W01"),
    ],
)
def test_a_week_is_the_iso_week_of_its_monday(day: str, monday: str, week: str) -> None:
    got = iso_week(date.fromisoformat(day))
    assert (got[0].isoformat(), got[1]) == (monday, week)


def test_open_writes_one_quiet_event_and_a_draft_plan(ww: WeekWorld) -> None:
    plan = ww.open("2026-11-04")
    assert _events(ww, plan) == ["Record.Created", "WeeklyPlan.Opened"]
    opened = ww.w.rows(
        "SELECT payload FROM events WHERE stream_id = :i AND event_type = 'WeeklyPlan.Opened'",
        i=plan,
    )[0]["payload"]
    assert '"feed_policy": "none"' in opened.replace('":"', '": "') or "none" in opened
    row = ww.plan_row(plan)
    assert (row["week"], row["week_start"], row["ppc"]) == ("2026-W45", "2026-11-02", None)
    refuses(errors.WeekRuleError, lambda: ww.open("2026-11-06"))  # any day of the same week
    assert str(refuses(errors.WeekRuleError, lambda: ww.open("2026-11-02"))) == (
        "weekly plan: week already open"
    )


def test_open_needs_a_project_scope_and_its_word(ww: WeekWorld) -> None:
    from tl_core.auth.errors import ForbiddenError

    refuses(ForbiddenError, lambda: ww.open(who="vera"))


def test_commit_states_and_the_move(ww: WeekWorld) -> None:
    plan = ww.open()
    for state in ("Draft", "Ready", "Closed", "On hold"):
        iwp = ww.issued(state)
        refuses(errors.WeekStateError, lambda i=iwp: ww.commit(plan, i))  # type: ignore[misc]
    assert ww.w.state(plan) != "Committed"
    started = ww.issued("In progress")
    ww.commit(plan, started)
    assert ww.w.state(plan) == "Committed"
    assert _events(ww, plan)[-2:] == ["WeeklyPlan.IwpCommitted", "Workflow.Transitioned"]
    more = ww.issued()
    ww.commit(plan, more)  # a Committed plan takes more, with no second move
    assert _events(ww, plan).count("Workflow.Transitioned") == 1


def test_commit_foreman_default_and_hours_bounds(ww: WeekWorld) -> None:
    plan = ww.open()
    a = ww.issued(foreman="user:sue")
    b = ww.issued(foreman=None)
    ww.commit(plan, a)
    ww.commit(plan, b)
    foremen = {r["iwp_id"]: r["foreman"] for r in ww.commitments(plan)}
    assert foremen[a] == "user:sue" and foremen[b] == "user:uma"
    ww.commit(plan, a, "1", foreman="user:ada")
    row = [r for r in ww.commitments(plan) if r["iwp_id"] == a][0]
    assert (row["foreman"], row["committed_hours"]) == ("user:ada", "1.0")
    ww.commit(plan, a, "9999999999.9")
    assert [r for r in ww.commitments(plan) if r["iwp_id"] == a][0]["committed_hours"] == (
        "9999999999.9"
    )
    for bad in ("0", "0.0", "-1.0", "10000000000.0", "1.25", "abc", "", "1e3"):
        with pytest.raises(ValidationError):
            CommitIwpToWeek(
                actor="user:uma",
                source="t",
                scope=SCOPE,
                plan_id=plan,
                iwp_id=a,
                committed_hours=bad,
                expected_version=1,
            )


def test_commit_refuses_a_hidden_or_foreign_iwp_and_a_stale_plan(ww: WeekWorld) -> None:
    plan = ww.open()
    far = ww.other_project_iwp()
    refuses(RecordNotFoundError, lambda: ww.commit(plan, far))
    refuses(RecordNotFoundError, lambda: ww.commit(plan, "0" * 26))
    a = ww.issued()
    stale = ww.w.version(plan)
    ww.commit(plan, a)
    refuses(
        errors.StaleVersionError,
        lambda: ww.w.call(
            "uma",
            "CommitIwpToWeek",
            plan_id=plan,
            iwp_id=a,
            committed_hours="5.0",
            expected_version=stale,
        ),
    )


def test_outcomes_are_checked_and_correctable_until_closed(ww: WeekWorld) -> None:
    plan = ww.open()
    a, b = ww.issued(), ww.issued()
    refuses(errors.WeekStateError, lambda: ww.outcome(plan, a, "done"))  # Draft
    ww.commit(plan, a)
    refuses(errors.WeekRuleError, lambda: ww.outcome(plan, b, "done"))  # not committed in it
    reasons = miss_reasons_of(ww)
    assert "Weather" in reasons and "Other" in reasons
    refuses(errors.WeekRuleError, lambda: ww.outcome(plan, a, "missed", "weather"))
    ww.outcome(plan, a, "missed", "Weather")
    row = ww.commitments(plan)[0]
    assert (row["outcome"], row["miss_reason"]) == ("missed", "Weather")
    ww.outcome(plan, a, "done")  # a correction is a new event
    row = ww.commitments(plan)[0]
    assert (row["outcome"], row["miss_reason"]) == ("done", None)
    assert _events(ww, plan).count("WeeklyPlan.OutcomeRecorded") == 2
    ww.close(plan)
    refuses(errors.WeekStateError, lambda: ww.outcome(plan, a, "missed", "Weather"))
    with pytest.raises(ValidationError):
        ww.outcome(plan, a, "late")


def miss_reasons_of(ww: WeekWorld) -> list[str]:
    with open_uow(ww.w.db, readonly=True) as uow:
        return miss_reasons(uow.conn(), SCOPE)


def test_miss_reasons_are_the_keys_of_the_list(ww: WeekWorld) -> None:
    assert miss_reasons_of(ww) == sorted(miss_reasons_of(ww), key=miss_reasons_of(ww).index)
    assert set(miss_reasons_of(ww)) == {
        "Constraint", "Material", "Labour", "Weather", "Rework", "Access", "Equipment", "Other",
    }  # fmt: skip


def test_close_writes_the_ppc_and_the_card_on_closed_only(ww: WeekWorld) -> None:
    plan = ww.open()
    iwps = [ww.issued() for _ in range(3)]
    for i in iwps:
        ww.commit(plan, i)
    ww.outcome(plan, iwps[0], "done")
    ww.outcome(plan, iwps[1], "done")
    refuses(errors.WeekRuleError, lambda: ww.close(plan))
    assert str(refuses(errors.WeekRuleError, lambda: ww.close(plan))) == (
        "weekly plan: outcomes missing"
    )
    ww.outcome(plan, iwps[2], "missed", "Other")
    ww.close(plan)
    assert ww.plan_row(plan)["ppc"] == "66.7"  # 2 of 3, half-up
    assert ww.plan_row(plan)["closed_at"] is not None
    payloads = {
        str(r["event_type"]): str(r["payload"])
        for r in ww.w.rows(
            "SELECT event_type, payload FROM events WHERE stream_id = :i "
            "AND event_type LIKE 'WeeklyPlan.%'",
            i=plan,
        )
    }
    for quiet in ("Opened", "IwpCommitted", "OutcomeRecorded"):
        assert "feed_policy" in payloads[f"WeeklyPlan.{quiet}"]
    assert "feed_policy" not in payloads["WeeklyPlan.Closed"]
    assert _events(ww, plan)[-2:] == ["WeeklyPlan.Closed", "Workflow.Transitioned"]
    assert (
        str(refuses(errors.WeekStateError, lambda: ww.close(plan)))
        == "weekly plan: a closed week takes no more commands"
    )


def test_close_of_an_empty_plan_says_nothing_committed(ww: WeekWorld) -> None:
    plan = ww.open()
    assert str(refuses(errors.WeekRuleError, lambda: ww.close(plan))) == (
        "weekly plan: nothing committed"
    )


def test_a_hundred_percent_and_a_zero(ww: WeekWorld) -> None:
    for outcome, reason, want in (("done", None, "100.0"), ("missed", "Other", "0.0")):
        plan = ww.open("2026-11-02" if outcome == "done" else "2026-11-09")
        iwp = ww.issued()
        ww.commit(plan, iwp)
        ww.outcome(plan, iwp, outcome, reason)
        ww.close(plan)
        assert ww.plan_row(plan)["ppc"] == want


def test_views_list_detail_and_the_five_readers(ww: WeekWorld) -> None:
    p1, p2 = ww.open("2026-11-02"), ww.open("2026-11-09")
    a, b = ww.issued(), ww.issued()
    ww.commit(p1, a)
    ww.commit(p1, b)
    lowest = cf.Viewer()
    with open_uow(ww.w.db, readonly=True) as uow:
        conn = uow.conn()
        listed = list_weeks(conn, SCOPE, lowest)
        assert [w.week for w in listed] == ["2026-W46", "2026-W45"]
        assert [w.state for w in listed][1] == "Committed"
        assert len(list_weeks(conn, SCOPE, lowest, limit=1)) == 1
        assert list_weeks(conn, "project:P999", lowest) == []
        detail = week_detail(conn, p1, lowest)
        assert len(detail.commitments) == 2 and detail.ppc is None
        assert {c.iwp_state for c in detail.commitments} == {"Issued"}
        assert week_detail(conn, p2, lowest).notes == ["nothing committed"]
        refuses(RecordNotFoundError, lambda: week_detail(conn, a, lowest))  # an IWP is no plan
    with ww.hidden_plan(p1), open_uow(ww.w.db, readonly=True) as uow:
        assert [w.id for w in list_weeks(uow.conn(), SCOPE, lowest)] == [p2]
        refuses(RecordNotFoundError, lambda: week_detail(uow.conn(), p1, lowest))
        cleared = cf.Viewer(actor="user:uma", level=1, account="uma")
        assert week_detail(uow.conn(), p1, cleared).id == p1
    ww.pw.w.set_status(a, "Issued")


def test_the_module_wires_the_words_and_the_one_proposal() -> None:
    words = {c.model.__name__: c.access for c in AWP_COMMANDS}
    assert words["OpenWeeklyPlan"] == "awp.week.plan"
    assert words["CommitIwpToWeek"] == "awp.week.commit"
    assert words["RecordWeekOutcome"] == "awp.week.commit"
    assert words["CloseWeek"] == "awp.week.close"
    tools = {p.tool: p for p in spec().proposable}
    assert tools["propose_week_commitment"].model is CommitIwpToWeek
    assert tools["propose_week_commitment"].access == "user"
    assert not {"propose_open_week", "propose_week_outcome", "propose_close_week"} & set(tools)


def test_rebuild_equality_with_ppc(ww: WeekWorld) -> None:
    plan = ww.open()
    a, b = ww.issued(), ww.issued()
    ww.commit(plan, a, "10.0")
    ww.commit(plan, b, "20.0")
    ww.commit(plan, b, "25.5")
    ww.outcome(plan, a, "done")
    ww.outcome(plan, b, "missed", "Labour")
    ww.close(plan)
    open_plan = ww.open("2026-11-16")
    ww.commit(open_plan, ww.issued())
    before = ww.snapshot()
    assert before["cur_awp_weekly_plan"][0]["ppc"] is not None
    ww.pw.rebuild()
    assert ww.snapshot() == before


def test_the_handlers_do_not_read_intent() -> None:
    from pathlib import Path

    import tl_mod_awp.handlers.week as week

    assert "cmd.intent" not in Path(week.__file__).read_text()
    _ = Callable
