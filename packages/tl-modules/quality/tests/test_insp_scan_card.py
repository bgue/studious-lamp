"""The scan card of an inspection (P2-INSP T09): the contract harness, banners and tones, the lines
and their bounds, the answers ``None`` must give, the five readers, and the registry entry point."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from importlib.metadata import EntryPoint
from pathlib import Path

import pytest
from insp_world import IWP, InspWorld, answers
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.qr.registry import load_scan_cards
from tl_core.qr.types import MAX_LABEL_CHARS, MAX_LINES, MAX_VALUE_CHARS, SCAN_CARD_ENTRY_POINT
from tl_mod_quality.names import INSPECTION
from tl_mod_quality.scan_card import InspectionScanCard, provider

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tests" / "contract"))

from scan_card_harness import check_scan_card_contract  # noqa: E402

NOW = datetime(2026, 12, 10, 9, 0, tzinfo=UTC)
MADE_UP = "01HZZZZZZZZZZZZZZZZZZZZZZZ"
#: The five kinds of reader (ADR-0016) over the inspection card: a plain user, a document
#: controller, an admin (a controller too), a named person and an agent with no account.
READERS = {
    "uma": cf.Viewer(actor="user:uma", level=0, account="user:uma"),
    "dora": cf.Viewer(actor="user:dora", level=1, account="user:dora"),
    "ada": cf.Viewer(actor="user:ada", level=1, account="user:ada"),
    "rob": cf.Viewer(actor="user:rob", level=0, account="user:rob"),
    "bot": cf.Viewer(actor="agent:bot", level=0, account=""),
}
#: The readers that see a card of an inspection hidden through a restricted subject.
READS_RESTRICTED = {"dora", "ada"}


def card_of(world: InspWorld, record_id: str, viewer: cf.Viewer = READERS["uma"]):  # type: ignore[no-untyped-def]
    with open_uow(world.db, readonly=True) as uow:
        return InspectionScanCard().card(uow.conn(), record_id, viewer, NOW)


def void(world: InspWorld, record_id: str) -> None:
    with open_uow(world.db) as uow:
        uow.conn().execute(
            text("UPDATE cur_core_record SET voided = :v WHERE id = :i"),
            {"v": True, "i": record_id},
        )


def banner_of(world: InspWorld, record_id: str) -> tuple[str, str]:
    card = card_of(world, record_id)
    assert card is not None
    return card.banner, card.tone


def test_the_provider_keeps_the_scan_card_contract(insp: InspWorld) -> None:
    visible = insp.plan()
    hidden = insp.plan(insp.hidden_record(), who="dora")
    with open_uow(insp.db, readonly=True) as uow:
        card = check_scan_card_contract(
            provider(),
            uow.conn(),
            visible_id=visible,
            hidden_id=hidden,
            privileged=READERS["dora"],
            now=NOW,
        )
    assert (card.record_type, card.banner, card.tone) == (
        INSPECTION,
        "HOLD POINT - not released",
        "stop",
    )


def test_a_planned_witness_is_neutral_and_a_planned_hold_point_is_stop(insp: InspWorld) -> None:
    witness = insp.plan(point="witness")
    held = insp.plan()
    assert banner_of(insp, witness) == ("PLANNED", "neutral")
    assert banner_of(insp, held) == ("HOLD POINT - not released", "stop")


def test_a_scheduled_hold_point_is_stop_and_a_scheduled_witness_shows_its_day(
    insp: InspWorld,
) -> None:
    held = insp.scheduled()
    witness = insp.scheduled(point="witness")
    assert banner_of(insp, held) == ("HOLD POINT - not released", "stop")
    assert banner_of(insp, witness) == ("SCHEDULED 1 Dec", "neutral")


def test_the_scheduled_day_is_day_then_month_without_a_zero(insp: InspWorld) -> None:
    item = insp.plan(point="witness")
    insp.call(
        "uma",
        "ScheduleInspection",
        inspection=item,
        checklist=insp.checklist(),
        scheduled_for="2026-11-18",
        inspector="M. Okafor",
    )
    assert banner_of(insp, item) == ("SCHEDULED 18 Nov", "neutral")


def test_a_done_accept_is_to_verify_and_a_done_reject_is_stop(insp: InspWorld) -> None:
    accepted = insp.scheduled(point="witness")
    insp.recorded(accepted, answers=answers())
    rejected = insp.scheduled(point="witness")
    insp.recorded(rejected, answers=answers(q1="no"))
    assert banner_of(insp, accepted) == ("DONE - to verify", "caution")
    assert banner_of(insp, rejected) == ("REJECTED", "stop")


def test_a_done_conditional_is_caution(insp: InspWorld) -> None:
    item = insp.scheduled(point="hold")
    insp.recorded(item, answers=answers(q2="no"))
    assert banner_of(insp, item) == ("CONDITIONAL", "caution")


def test_a_verified_accept_is_go_and_a_verified_reject_is_stop(insp: InspWorld) -> None:
    accepted = insp.scheduled(point="witness")
    insp.recorded(accepted, answers=answers())
    insp.call("sue", "VerifyInspection", inspection=accepted)
    rejected = insp.scheduled(point="witness")
    insp.recorded(rejected, answers=answers(q1="no"))
    insp.call("sue", "VerifyInspection", inspection=rejected)
    assert banner_of(insp, accepted) == ("ACCEPTED", "go")
    assert banner_of(insp, rejected) == ("REJECTED", "stop")


def test_a_verified_conditional_is_caution(insp: InspWorld) -> None:
    item = insp.scheduled(point="hold")
    insp.recorded(item, answers=answers(q2="no"))
    insp.call("sue", "VerifyInspection", inspection=item)
    assert banner_of(insp, item) == ("CONDITIONAL", "caution")


def test_a_cancelled_inspection_is_neutral(insp: InspWorld) -> None:
    item = insp.plan()
    insp.call("sue", "CancelInspection", inspection=item, reason="Scope moved")
    assert banner_of(insp, item) == ("CANCELLED", "neutral")


def test_lines_stay_in_bounds_and_a_missing_value_is_left_out(insp: InspWorld) -> None:
    subject = insp.record(IWP, "IWP-7")
    planned = insp.plan(subject, point="witness")
    bare = card_of(insp, planned)
    assert bare is not None
    labels = [line.label for line in bare.lines]
    assert labels == ["Point", "For", "Subject"]
    assert not any("None" in line.value for line in bare.lines)

    item = insp.scheduled(subject, point="witness", area="A1")
    card = card_of(insp, item)
    assert card is not None
    values = {line.label: line.value for line in card.lines}
    assert values["Point"] == "witness"
    assert values["Checklist"] == "P123-CHK-0001 v1"
    assert values["Inspector"] == "M. Okafor"
    assert values["Area"] == "A1"
    assert values["For"] == "IWP-7" and values["Subject"] == "IWP-7"
    assert "Punch items" not in values
    assert len(card.lines) <= MAX_LINES
    assert all(len(line.label) <= MAX_LABEL_CHARS for line in card.lines)
    assert all(len(line.value) <= MAX_VALUE_CHARS for line in card.lines)
    assert not any("None" in line.value for line in card.lines)
    assert item not in card.model_dump_json()


def test_punch_items_show_only_after_a_failed_answer_raised_one(insp: InspWorld) -> None:
    item = insp.scheduled(point="witness")
    insp.recorded(item, answers=answers())
    passed = card_of(insp, item)
    assert passed is not None and "Punch items" not in [line.label for line in passed.lines]

    failed = insp.scheduled(point="witness")
    insp.recorded(failed, answers=answers(q1="no"))
    card = card_of(insp, failed)
    assert card is not None
    assert {line.label: line.value for line in card.lines}["Punch items"] == "1"


def test_a_voided_inspection_a_checklist_a_punch_item_and_a_miss_answer_none(
    insp: InspWorld,
) -> None:
    voided = insp.plan()
    void(insp, voided)
    checklist = insp.checklist()
    failed = insp.scheduled(point="witness")
    insp.recorded(failed, answers=answers(q1="no"))
    (punch,) = insp.raised_by(failed)
    assert card_of(insp, voided) is None
    assert card_of(insp, checklist) is None
    assert card_of(insp, punch["id"]) is None
    assert card_of(insp, MADE_UP) is None
    assert card_of(insp, "not an id") is None


@pytest.mark.parametrize("reader", sorted(READERS))
def test_each_reader_sees_the_card_or_none_as_the_class_says(insp: InspWorld, reader: str) -> None:
    visible = insp.plan(insp.record(IWP, "IWP-1"))
    hidden = insp.plan(insp.hidden_record(), who="dora")
    assert card_of(insp, visible, READERS[reader]) is not None
    assert (card_of(insp, hidden, READERS[reader]) is not None) == (reader in READS_RESTRICTED)


def test_the_registry_finds_the_provider_for_quality_inspection() -> None:
    point = EntryPoint(
        "quality_inspection", "tl_mod_quality.scan_card:provider", SCAN_CARD_ENTRY_POINT
    )
    found = load_scan_cards([point])
    assert list(found) == [INSPECTION]
    assert isinstance(found[INSPECTION], InspectionScanCard)
