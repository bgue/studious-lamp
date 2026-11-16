"""The scan card of an IWP (P2-QR T04): the contract harness, banners and tones, readiness counts,
bounded lines, the answers ``None`` must give, the five readers, and the registry entry point."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from importlib.metadata import EntryPoint
from pathlib import Path

import pytest
from awp_world import SCOPE
from s3_checks import build, readiness
from sqlalchemy import text
from test_five_readers import READERS, READS_RESTRICTED
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.modules import ConfidentialSource, confidential_sources
from tl_core.qr.registry import load_scan_cards
from tl_core.qr.types import MAX_LABEL_CHARS, MAX_LINES, MAX_VALUE_CHARS, SCAN_CARD_ENTRY_POINT
from tl_core.services.commands import Command
from tl_mod_awp.common import move
from tl_mod_awp.names import IWP
from tl_mod_awp.scan_card import IwpScanCard, provider

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tests" / "contract"))

from scan_card_harness import check_scan_card_contract  # noqa: E402

NOW = datetime(2026, 12, 10, 9, 0, tzinfo=UTC)
CLASS_TABLE = "t_card_class"
MADE_UP = "01HZZZZZZZZZZZZZZZZZZZZZZZ"


@pytest.fixture
def cards(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator:
    """A ledger where every IWP carries a class: a test-only source, as the five readers walk."""
    w = build(tmp_path / "card.db")
    with open_uow(w.db) as uow:
        uow.conn().execute(
            text(f"CREATE TABLE {CLASS_TABLE} (id TEXT PRIMARY KEY, cls TEXT NOT NULL)")
        )
    source = ConfidentialSource(
        record_types=frozenset({IWP}),
        table=CLASS_TABLE,
        id_column="id",
        class_column="cls",
    )

    def sources() -> list[ConfidentialSource]:
        return [*confidential_sources(), source]

    monkeypatch.setattr(cf, "confidential_sources", sources)
    yield w


def new_iwp(w, cls: str = "internal", **more) -> str:  # type: ignore[no-untyped-def]
    """An IWP made by ``uma`` with the given class (the id)."""
    record = w.iwp(**more)
    with open_uow(w.db) as uow:
        uow.conn().execute(
            text(f"INSERT INTO {CLASS_TABLE} (id, cls) VALUES (:i, :c)"), {"i": record, "c": cls}
        )
    return record


def card_of(w, record_id: str, viewer: cf.Viewer = READERS["bob"]):  # type: ignore[no-untyped-def]
    with open_uow(w.db, readonly=True) as uow:
        return IwpScanCard().card(uow.conn(), record_id, viewer, NOW)


def evaluate(w, iwp: str, states: tuple[str, ...]) -> None:  # type: ignore[no-untyped-def]
    """A readiness evaluation with one check per state, as the projector holds it."""
    readiness(w, iwp, True)
    with open_uow(w.db) as uow:
        conn = uow.conn()
        for n, state in enumerate(states):
            conn.execute(
                text(
                    "INSERT INTO cur_awp_readiness_check (row_id, scope, iwp_id, name, version, "
                    "state, detail, count_ok, count_total, resolve_via_json, as_of_seq) "
                    "VALUES (:row, 'project:P123', :i, :n, '1', :st, '', 0, 0, '[]', 0)"
                ),
                {"row": f"{iwp}-{n}", "i": iwp, "n": f"check{n}", "st": state},
            )


def void(w, record_id: str) -> None:  # type: ignore[no-untyped-def]
    with open_uow(w.db) as uow:
        uow.conn().execute(
            text("UPDATE cur_core_record SET voided = :v WHERE id = :i"),
            {"v": True, "i": record_id},
        )


#: The workflow path from Draft to each state the card reads (``schema/fixtures/workflows/
#: awp-iwp.yaml``), walked along the real transitions so ``cur_workflow_state`` agrees with the
#: record status, as the awp tests do.
IWP_STEPS: dict[str, tuple[str, ...]] = {
    "Draft": (),
    "Ready": ("develop", "check_constraints", "ready"),
    "Issued": ("develop", "check_constraints", "ready", "issue"),
    "In progress": ("develop", "check_constraints", "ready", "issue", "start"),
    "On hold": ("develop", "check_constraints", "ready", "hold"),
    "Field complete": ("develop", "check_constraints", "ready", "issue", "start", "complete"),
    "Closed": ("develop", "check_constraints", "ready", "issue", "start", "complete", "close"),
    "Cancelled": ("cancel",),
    "Split": ("split",),
}


def walk(w, iwp: str, state: str) -> None:  # type: ignore[no-untyped-def]
    """Move ``iwp`` along the real workflow to ``state``."""
    for step in IWP_STEPS[state]:
        if step == "develop":
            w.call("uma", "StartIwpDevelopment", iwp=iwp)
        elif step == "check_constraints":
            w.call("uma", "SendIwpToConstraintCheck", iwp=iwp)
        else:
            with open_uow(w.db) as uow:
                move(uow, Command(actor="user:uma", source="test", scope=SCOPE), iwp, step)


def test_the_provider_keeps_the_scan_card_contract(cards) -> None:  # type: ignore[no-untyped-def]
    visible = new_iwp(cards, title="Rack north")
    hidden = new_iwp(cards, cls="restricted", title="Rack secret")
    with open_uow(cards.db, readonly=True) as uow:
        card = check_scan_card_contract(
            provider(),
            uow.conn(),
            visible_id=visible,
            hidden_id=hidden,
            privileged=READERS["boss"],
            now=NOW,
        )
    assert (card.record_type, card.banner, card.tone) == (IWP, "DRAFT", "neutral")


def test_a_draft_without_an_evaluation_is_neutral_draft(cards) -> None:  # type: ignore[no-untyped-def]
    card = card_of(cards, new_iwp(cards, title="Rack north"))
    assert card is not None
    assert (card.banner, card.tone, card.open_path, card.valid_until) == (
        "DRAFT",
        "neutral",
        None,
        None,
    )


def test_issued_is_go_and_on_hold_is_stop(cards) -> None:  # type: ignore[no-untyped-def]
    issued = new_iwp(cards, title="Rack north")
    walk(cards, issued, "Issued")
    held = new_iwp(cards, title="Rack south")
    walk(cards, held, "On hold")
    on_issued = card_of(cards, issued)
    on_held = card_of(cards, held)
    assert on_issued is not None and on_held is not None
    assert (on_issued.banner, on_issued.tone) == ("ISSUED", "go")
    assert (on_held.banner, on_held.tone) == ("ON HOLD", "stop")


@pytest.mark.parametrize(
    ("state", "banner"),
    [
        ("Closed", "CLOSED"),
        ("Field complete", "FIELD COMPLETE"),
        ("Cancelled", "CANCELLED"),
        ("Split", "SPLIT"),
    ],
)
def test_a_closed_like_state_shows_its_name_neutral(cards, state: str, banner: str) -> None:  # type: ignore[no-untyped-def]
    i = new_iwp(cards, title="Rack north")
    walk(cards, i, state)
    card = card_of(cards, i)
    assert card is not None
    assert (card.banner, card.tone) == (banner, "neutral")


@pytest.mark.parametrize(
    ("states", "banner", "tone"),
    [
        (("ok", "blocked", "n_a"), "READY 1/2", "caution"),
        (("ok", "pending", "unknown"), "READY 1/3", "caution"),
        (("ok", "ok", "n_a"), "READY 2/2", "go"),
    ],
)
def test_a_ready_state_with_an_evaluation_counts_its_checks(
    cards, states: tuple[str, ...], banner: str, tone: str
) -> None:  # type: ignore[no-untyped-def]
    i = new_iwp(cards, title="Rack north")
    walk(cards, i, "Ready")
    evaluate(cards, i, states)
    card = card_of(cards, i)
    assert card is not None
    assert (card.banner, card.tone) == (banner, tone)
    readiness_line = [line.value for line in card.lines if line.label == "Readiness"]
    assert readiness_line == [banner.removeprefix("READY ") + " checks ok"]


def test_a_ready_state_without_an_evaluation_shows_its_name(cards) -> None:  # type: ignore[no-untyped-def]
    i = new_iwp(cards, title="Rack north")
    walk(cards, i, "Ready")
    card = card_of(cards, i)
    assert card is not None
    assert (card.banner, card.tone) == ("READY", "neutral")
    assert "Readiness" not in [line.label for line in card.lines]


def test_lines_stay_in_bounds_and_a_missing_foreman_is_left_out(cards) -> None:  # type: ignore[no-untyped-def]
    i = new_iwp(
        cards,
        title="Rack north",
        planned_start="2026-12-01",
        planned_finish="2026-12-09",
        foreman="user:uma",
    )
    cards.call("uma", "AddIwpScope", iwp=i, items=cards.items(["10.0", "20.0"]))
    card = card_of(cards, i)
    assert card is not None
    labels = {line.label: line.value for line in card.lines}
    assert labels["Foreman"] == "user:uma"
    assert labels["Window"] == "2026-12-01 to 2026-12-09"
    assert labels["Scope"] == "2 items"
    assert labels["Open constraints"] == "0"
    assert len(card.lines) <= MAX_LINES
    assert all(len(line.label) <= MAX_LABEL_CHARS for line in card.lines)
    assert all(len(line.value) <= MAX_VALUE_CHARS for line in card.lines)
    assert i not in card.model_dump_json()

    bare = card_of(cards, new_iwp(cards, title="Rack bare"))
    assert bare is not None
    assert "Foreman" not in [line.label for line in bare.lines]
    assert not any("None" in line.value for line in bare.lines)


def test_a_voided_iwp_a_record_of_another_type_and_a_miss_answer_none(cards) -> None:  # type: ignore[no-untyped-def]
    voided = new_iwp(cards, title="Rack north")
    void(cards, voided)
    item = cards.items(["5.0"])[0]
    assert card_of(cards, voided) is None
    assert card_of(cards, item) is None
    assert card_of(cards, MADE_UP) is None
    assert card_of(cards, "not an id") is None


@pytest.mark.parametrize("reader", sorted(READERS))
def test_each_reader_sees_the_card_or_none_as_the_class_says(cards, reader: str) -> None:  # type: ignore[no-untyped-def]
    visible = new_iwp(cards, title="Rack north")
    hidden = new_iwp(cards, cls="restricted", title="Rack secret")
    assert card_of(cards, visible, READERS[reader]) is not None
    assert (card_of(cards, hidden, READERS[reader]) is not None) == (reader in READS_RESTRICTED)


def test_an_agent_with_no_account_sees_none_of_the_hidden_iwp(cards) -> None:  # type: ignore[no-untyped-def]
    hidden = new_iwp(cards, cls="restricted", title="Rack secret")
    assert card_of(cards, hidden, READERS["bot"]) is None


def test_the_registry_finds_the_provider_for_awp_iwp() -> None:
    point = EntryPoint("awp_iwp", "tl_mod_awp.scan_card:provider", SCAN_CARD_ENTRY_POINT)
    found = load_scan_cards([point])
    assert list(found) == [IWP]
    assert isinstance(found[IWP], IwpScanCard)
