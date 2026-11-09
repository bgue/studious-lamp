"""The rules-of-credit engine and the progress commands (P2-I5 S2)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from awp_world import SCOPE, World, refuses
from progress_world import ProgressWorld, checks
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.auth.errors import ForbiddenError
from tl_core.services.errors import RecordNotFoundError, ServiceError
from tl_mod_awp import errors
from tl_mod_awp.commands import AWP_COMMANDS
from tl_mod_awp.module import spec
from tl_mod_awp.progress import engine


@pytest.fixture
def pw(world: World) -> ProgressWorld:
    return ProgressWorld(world)


def test_the_acceptance_checks_pass(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    checks(ProgressWorld(world))
    assert capsys.readouterr().out.count("PASS ") == 22


def test_the_rounding_is_half_up_and_exact() -> None:
    for value, want in [("0.05", "0.1"), ("0.04", "0.0"), ("99.95", "100.0"), ("2.25", "2.3")]:
        assert str(engine.round_half_up(Decimal(value))) == want
    assert str(engine.round_half_up(Decimal("0.049999999999999999999999999999"))) == "0.0"


@pytest.mark.parametrize(
    ("total", "percents", "want"),
    [
        ("10.0", ["33", "33", "34"], ["3.3", "3.3", "3.4"]),
        ("10.0", ["1", "1", "1"], ["3.4", "3.3", "3.3"]),
        ("0.1", ["50", "50"], ["0.1", "0.0"]),
        ("7.0", ["100"], ["7.0"]),
        ("0.9", ["15", "35", "50"], ["0.1", "0.3", "0.5"]),
    ],
)
def test_largest_remainder_sums_to_the_rounded_total(
    total: str, percents: list[str], want: list[str]
) -> None:
    parts = engine.largest_remainder(Decimal(total), [Decimal(p) for p in percents])
    assert [str(p) for p in parts] == want
    assert sum(parts) == engine.round_half_up(Decimal(total))


def test_ppc_is_a_count_not_hours() -> None:
    assert engine.ppc(1, 3) == (Decimal("33.3"), [])
    assert engine.ppc(2, 3) == (Decimal("66.7"), [])
    assert engine.ppc(0, 4) == (Decimal("0.0"), [])
    assert engine.ppc(0, 0) == (None, ["nothing committed"])


def test_the_figure_is_capped_and_a_void_item_drops_out(pw: ProgressWorld) -> None:
    iwp, (a, b) = pw.package(["10.0", "10.0"])
    for item in (a, b):
        pw.move("InstallScopeItem", item)
        pw.move("VerifyScopeItem", item)
        pw.manual(iwp, item)
    assert pw.pct(iwp) == "100.0"
    iwp2, (c, d) = pw.package(["10.0", "30.0"])
    pw.move("InstallScopeItem", c)
    assert pw.pct(iwp2) == "15.0"
    pw.w.set_status(d, "Void")
    assert str(pw.earned(iwp2).pct) == "60.0"


def test_a_recorded_figure_keeps_its_edition(pw: ProgressWorld) -> None:
    iwp, (a, b) = pw.package(["10.0", "10.0"])
    pw.move("InstallScopeItem", a)
    assert pw.row(iwp)["edition"] == "co.acme.awp@1.1.0"  # type: ignore[index]
    pw.set_edition("co.acme.nope@9.9.9")
    with open_uow(pw.w.db, readonly=True) as uow:
        refuses(errors.RulesOfCreditError, lambda: engine.edition_for(uow.conn(), SCOPE))
    assert str(pw.earned(iwp).pct) == "30.0"  # the stored edition is still used
    pw.move("InstallScopeItem", b)
    assert pw.pct(iwp) == "60.0" and pw.row(iwp)["edition"] == "co.acme.awp@1.1.0"  # type: ignore[index]


def test_the_stored_figure_does_not_depend_on_the_writer(pw: ProgressWorld) -> None:
    iwp, (a, b) = pw.package(["10.0", "10.0"])
    with pw.hidden(a):
        pw.move(
            "InstallScopeItem", b
        )  # the writer (a person) can open both; the figure covers both
    assert pw.pct(iwp) == "30.0"
    pw.move("InstallScopeItem", a)
    with pw.hidden(a):
        seen = pw.earned(iwp, cf.Viewer())
    assert str(seen.pct) == pw.pct(iwp) == "60.0"
    assert [i.item_id for i in seen.items] == [b]
    assert "some items not shown" in seen.notes
    assert not any("1" in n for n in seen.notes if "shown" in n)  # no count of hidden


def test_a_viewer_who_cannot_open_the_iwp_gets_not_found(pw: ProgressWorld) -> None:
    refuses(RecordNotFoundError, lambda: pw.earned("0" * 26, cf.Viewer()))


def test_manual_entries_are_checked(pw: ProgressWorld) -> None:
    iwp, (a,) = pw.package(["10.0"])
    other, (b,) = pw.package(["10.0"])

    def call(item: str, step: str, target: str = iwp) -> object:
        return pw.w.call(
            "uma",
            "RecordManualProgress",
            iwp_id=target,
            steps=[{"scope_item_id": item, "step": step, "done": True}],
            expected_version=pw.w.version(target),
        )

    refuses(errors.ProgressRuleError, lambda: call(a, "Installed"))
    refuses(errors.ProgressRuleError, lambda: call(a, "No such step"))
    refuses(errors.ProgressRuleError, lambda: call(b, "Material received"))
    refuses(
        errors.StaleVersionError,
        lambda: pw.w.call(
            "uma",
            "RecordManualProgress",
            iwp_id=iwp,
            steps=[{"scope_item_id": a, "step": "Material received", "done": True}],
            expected_version=pw.w.version(iwp) + 1,
        ),
    )
    assert pw.row(iwp) is None
    call(a, "Material received")
    assert pw.row(iwp)["manual_json"] is not None  # type: ignore[index]
    pw.w.set_status(iwp, "Closed")
    refuses(errors.IwpStateError, lambda: call(a, "Material received"))


def test_start_and_complete_need_their_states_and_write_the_events(pw: ProgressWorld) -> None:
    iwp, (a,) = pw.package(["10.0"])
    refuses(errors.IwpStateError, lambda: pw.field("StartIwpWork", iwp))
    pw.w.set_status(iwp, "Issued")
    refuses(errors.IwpStateError, lambda: pw.field("CompleteIwpField", iwp))
    refuses(
        errors.StaleVersionError,
        lambda: pw.w.call("uma", "StartIwpWork", iwp_id=iwp, expected_version=99),
    )
    pw.field("StartIwpWork", iwp, at="2026-11-02")
    assert pw.count(iwp, "IWP.Started") == 1
    before = pw.count(iwp)
    pw.field("CompleteIwpField", iwp)
    assert pw.count(iwp, "IWP.FieldCompleted") == 1
    assert pw.count(iwp) == before + 1  # a last figure even when nothing changed
    last = pw.w.rows(
        "SELECT event_type FROM events WHERE stream_id = :i ORDER BY seq DESC LIMIT 1", i=iwp
    )
    assert last[0]["event_type"] == "IWP.ProgressRecorded"


def test_a_blocking_constraint_refuses_start(pw: ProgressWorld) -> None:
    iwp, _ = pw.package(["10.0"])
    pw.w.set_status(iwp, "Issued")
    pw.raise_blocking(iwp, "start")
    refuses(ServiceError, lambda: pw.field("StartIwpWork", iwp))
    assert pw.w.state(iwp) == "Issued" and pw.count(iwp, "IWP.Started") == 0


def test_the_words_and_the_proposals(world: World) -> None:
    table = {c.model.__name__: c.access for c in AWP_COMMANDS}
    for name in ("InstallScopeItem", "ReturnScopeItem", "VerifyScopeItem", "RecordManualProgress"):
        assert table[name] == "awp.progress.record"
    assert table["StartIwpWork"] == table["CompleteIwpField"] == "awp.iwp.edit"
    tools = {p.tool: p.model.__name__ for p in spec().proposable}
    assert tools["propose_progress"] == "RecordManualProgress"
    assert tools["propose_scope_installed"] == "InstallScopeItem"
    assert "VerifyScopeItem" not in tools.values() and "StartIwpWork" not in tools.values()
    refuses(
        ForbiddenError,
        lambda: world.call("vera", "VerifyScopeItem", record_id="0" * 26, expected_version=1),
    )


def test_rebuild_equals_the_progress_and_week_tables(pw: ProgressWorld) -> None:
    iwp, (a, b) = pw.package(["10.0", "30.0"])
    pw.move("InstallScopeItem", a)
    pw.manual(iwp, b)
    pw.w.set_status(iwp, "Issued")
    pw.field("StartIwpWork", iwp)
    pw.field("CompleteIwpField", iwp)
    before = pw.snapshot()
    assert before["cur_awp_iwp_progress"][0]["manual_json"] is not None
    pw.rebuild()
    assert pw.snapshot() == before


def test_the_database_holds_one_row_per_iwp(pw: ProgressWorld) -> None:
    iwp, (a, b) = pw.package(["10.0", "10.0"])
    pw.move("InstallScopeItem", a)
    pw.move("InstallScopeItem", b)
    assert pw.count(iwp) == 2
    rows = pw.w.rows("SELECT earned_pct FROM cur_awp_iwp_progress WHERE iwp_id = :i", i=iwp)
    assert [r["earned_pct"] for r in rows] == ["60.0"]


def test_an_edition_whose_weights_pass_100_is_capped(pw: ProgressWorld) -> None:
    from tl_schema.packages import CreditStep

    steps = (
        CreditStep(name="Installed", weight=60, evidence="scope_state:Installed"),
        CreditStep(name="Verified", weight=60, evidence="scope_state:Verified"),
    )
    rules = engine.Rules(edition="x.over@1.0.0", by_commodity={"piping": steps})
    iwp, (a,) = pw.package(["10.0"])
    pw.move("InstallScopeItem", a)
    pw.move("VerifyScopeItem", a)
    with open_uow(pw.w.db, readonly=True) as uow:
        figure = engine.compute_figure(uow.conn(), iwp, rules)
    assert str(figure.pct) == "100.0" and str(figure.items[0].pct) == "100.0"
