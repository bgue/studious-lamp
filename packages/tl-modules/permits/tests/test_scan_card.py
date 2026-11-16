"""The scan card of a permit (P2-PTW T09): the contract harness, banners and tones, bounded lines,
the answers ``None`` must give, the five readers, and the registry entry point."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from importlib.metadata import EntryPoint
from pathlib import Path

import pytest
from permit_world import World
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.qr.registry import load_scan_cards
from tl_core.qr.types import (
    MAX_LABEL_CHARS,
    MAX_LINES,
    MAX_VALUE_CHARS,
    SCAN_CARD_ENTRY_POINT,
    ScanCard,
)
from tl_mod_permits import views
from tl_mod_permits.names import PERMIT
from tl_mod_permits.scan_card import PermitScanCard, provider

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tests" / "contract"))

from scan_card_harness import check_scan_card_contract  # noqa: E402

READERS = {
    "bob": cf.Viewer(actor="user:bob", level=0, account="user:bob"),
    "ctl": cf.Viewer(actor="user:ctl", level=1, account="user:ctl"),
    "boss": cf.Viewer(actor="user:boss", level=1, account="user:boss"),
    "amy": cf.Viewer(actor="user:amy", level=0, account="user:amy"),
    "bot": cf.Viewer(actor="agent:bot", level=0, account=""),
}
#: What each reader may read of a restricted for-record: the cleared readers only.
READS_RESTRICTED = {"ctl", "boss"}
CLEARED = cf.Viewer(actor="user:dora", level=1, account="user:dora")
MADE_UP = "01HZZZZZZZZZZZZZZZZZZZZZZZ"


@pytest.fixture
def cards(world: World) -> World:
    return world


def card_of(
    world: World,
    record_id: str,
    viewer: cf.Viewer = READERS["bob"],
    now: datetime | None = None,
) -> ScanCard | None:
    with open_uow(world.db, readonly=True) as uow:
        return provider().card(uow.conn(), record_id, viewer, world.at if now is None else now)


def shown_state(world: World, permit: str, now: datetime) -> str:
    """The state ``views.permit_detail`` gives for the permit at ``now`` (the card must agree)."""
    with open_uow(world.db, readonly=True) as uow:
        conn = uow.conn()
        scope, key = conn.execute(
            text("SELECT scope, key FROM cur_core_record WHERE id = :i"), {"i": permit}
        ).one()
        detail = views.permit_detail(conn, str(scope), str(key), now=now, viewer=cf.LOWEST)
    assert detail is not None
    return detail.row.state


def test_the_provider_keeps_the_scan_card_contract(cards: World) -> None:
    visible = cards.request()
    hidden = cards.request("dora", for_record_id=cards.hidden_record())
    with open_uow(cards.db, readonly=True) as uow:
        card = check_scan_card_contract(
            provider(),
            uow.conn(),
            visible_id=visible,
            hidden_id=hidden,
            privileged=CLEARED,
            now=cards.at,
        )
    assert (card.record_type, card.banner, card.tone) == (
        PERMIT,
        "REQUESTED - not approved",
        "caution",
    )


def test_a_requested_and_an_approved_permit_are_caution(cards: World) -> None:
    requested = cards.request()
    approved = cards.approved()
    on_requested = card_of(cards, requested)
    on_approved = card_of(cards, approved)
    assert on_requested is not None and on_approved is not None
    assert (on_requested.banner, on_requested.tone) == ("REQUESTED - not approved", "caution")
    assert (on_approved.banner, on_approved.tone) == ("APPROVED - not issued", "caution")
    assert on_requested.valid_until is None and on_approved.valid_until is None


def test_an_active_permit_is_go_with_its_end_time(cards: World) -> None:
    permit = cards.active()
    card = card_of(cards, permit)
    assert card is not None
    assert (card.banner, card.tone) == ("ACTIVE until 18:00 UTC", "go")
    assert card.valid_until is not None
    assert card.valid_until.astimezone(UTC).strftime("%H:%M") == "18:00"
    assert card.open_path is None and card.as_of == cards.at


def test_an_active_permit_is_lapsed_once_now_is_past_its_end(cards: World) -> None:
    permit = cards.active()
    card = card_of(cards, permit)
    assert card is not None and card.valid_until is not None
    later = card.valid_until + timedelta(minutes=1)
    lapsed = card_of(cards, permit, now=later)
    assert lapsed is not None
    assert (lapsed.banner, lapsed.tone) == ("LAPSED - revalidate", "stop")
    assert lapsed.valid_until == card.valid_until
    assert shown_state(cards, permit, later) == "Lapsed"
    assert shown_state(cards, permit, cards.at) == "Active"


def test_a_suspended_permit_is_stop(cards: World) -> None:
    permit = cards.active()
    cards.call("uma", "SuspendPermit", permit=permit, reason="Gas alarm")
    card = card_of(cards, permit)
    assert card is not None
    assert (card.banner, card.tone) == ("SUSPENDED", "stop")
    assert card.valid_until is not None


def test_handed_back_is_neutral_and_closed_rejected_cancelled_show_their_name(cards: World) -> None:
    handed = cards.active()
    cards.call("rob", "HandBackPermit", permit=handed, handback_note="Site clear")
    closed = cards.active()
    cards.call("rob", "HandBackPermit", permit=closed, handback_note="Site clear")
    cards.call("pam", "ClosePermit", permit=closed)
    rejected = cards.request()
    cards.call("sue", "RejectPermit", permit=rejected, reason="Not this week")
    cancelled = cards.request()
    cards.call("pam", "CancelPermit", permit=cancelled, reason="Work moved")
    expected = {
        handed: ("HANDED BACK", "neutral"),
        closed: ("CLOSED", "neutral"),
        rejected: ("REJECTED", "neutral"),
        cancelled: ("CANCELLED", "neutral"),
    }
    for permit, (banner, tone) in expected.items():
        card = card_of(cards, permit)
        assert card is not None
        assert (card.banner, card.tone) == (banner, tone)
        assert card.valid_until is None


def test_lines_are_bounded_and_a_missing_value_is_left_out(cards: World) -> None:
    permit = cards.request(permit_type="hot_work", area="A1", holder="Rob")
    card = card_of(cards, permit)
    assert card is not None
    labels = {line.label: line.value for line in card.lines}
    assert labels == {
        "Type": "Hot work",
        "Area": "A1",
        "Holder": "Rob",
        "Location": "Pump room",
    }
    assert len(card.lines) <= MAX_LINES
    assert all(len(line.label) <= MAX_LABEL_CHARS for line in card.lines)
    assert all(len(line.value) <= MAX_VALUE_CHARS for line in card.lines)
    assert not any("None" in line.value for line in card.lines)
    assert permit not in card.model_dump_json()


def test_the_for_line_shows_the_key_of_the_record_the_work_is_for(cards: World) -> None:
    for_record = cards.record("awp.IWP", "P123-IWP-0001")
    permit = cards.request(for_record_id=for_record)
    card = card_of(cards, permit)
    assert card is not None
    assert {line.label: line.value for line in card.lines}["For"] == "P123-IWP-0001"
    bare = card_of(cards, cards.request())
    assert bare is not None
    assert "For" not in [line.label for line in bare.lines]


def test_revalidated_appears_only_after_a_revalidation(cards: World) -> None:
    permit = cards.active()
    before = card_of(cards, permit)
    assert before is not None
    assert "Revalidated" not in [line.label for line in before.lines]
    cards.call("rob", "RevalidatePermit", permit=permit)
    after = card_of(cards, permit)
    assert after is not None
    assert {line.label: line.value for line in after.lines}["Revalidated"] == "1 times"


def test_a_voided_permit_a_record_of_another_type_and_a_miss_answer_none(cards: World) -> None:
    voided = cards.request()
    with open_uow(cards.db) as uow:
        uow.conn().execute(
            text("UPDATE cur_core_record SET voided = :v WHERE id = :i"),
            {"v": True, "i": voided},
        )
    isolation = cards.isolation()
    gas_test = cards.gas_test(cards.request())
    assert card_of(cards, voided) is None
    assert card_of(cards, isolation) is None
    assert card_of(cards, gas_test) is None
    assert card_of(cards, MADE_UP) is None
    assert card_of(cards, "not an id") is None


@pytest.mark.parametrize("reader", sorted(READERS))
def test_each_reader_sees_the_card_or_none_as_the_class_says(cards: World, reader: str) -> None:
    visible = cards.request()
    hidden = cards.request("dora", for_record_id=cards.hidden_record())
    assert card_of(cards, visible, READERS[reader]) is not None
    assert (card_of(cards, hidden, READERS[reader]) is not None) == (reader in READS_RESTRICTED)


def test_a_permit_of_a_restricted_for_record_answers_none_to_the_lowest_viewer(
    cards: World,
) -> None:
    hidden = cards.request("dora", for_record_id=cards.hidden_record())
    assert card_of(cards, hidden, cf.LOWEST) is None
    assert card_of(cards, hidden, CLEARED) is not None


def test_the_registry_finds_the_provider_for_permits_permit() -> None:
    point = EntryPoint("permits_permit", "tl_mod_permits.scan_card:provider", SCAN_CARD_ENTRY_POINT)
    found = load_scan_cards([point])
    assert list(found) == [PERMIT]
    assert isinstance(found[PERMIT], PermitScanCard)
