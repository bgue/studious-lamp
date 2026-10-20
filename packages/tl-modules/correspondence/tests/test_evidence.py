"""The evidence trail: the chain around an item as the ledger left it on a day (P1-I6-S4).

One story, replayed to different days. 19 Oct: a client letter is logged and an RFI that refers to
it is raised and submitted. 20 Oct: the RFI is retitled. 21 Oct: it is issued. 22 Oct: the answer
says cost impact yes and the RFI is escalated to an early warning. 25 Oct: a second letter is
linked to the warning. 26 Oct: the first letter is made restricted. 27 Oct: the link to the second
letter is retracted. The same questions
are asked of each day, as a plain person, a controller and an agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_mod_correspondence import evidence as ev
from tl_mod_correspondence.errors import EvidenceDateError, ItemNotFoundError
from tl_mod_correspondence.testing import CONTROLLER, PROJECT, CorrWorld, at, frozen_today

PLAIN = cf.Viewer(actor="user:bob", level=0, account="user:bob")
AGENT = cf.Viewer(actor="agent:bot", level=0, account="")


@dataclass
class Story:
    world: CorrWorld
    letter: str
    rfi: str
    warning: str
    later_letter: str
    later_link: str


@pytest.fixture
def story(world: CorrWorld) -> Story:
    with at("2026-10-19"):
        letter = world.forge_item("P123-COR-0001", subject="Client letter", state="Received")
        raised = world.raise_technical(
            required_by="2026-11-02", references=[{"record_id": letter, "note": "the letter"}]
        )
        world.submit_technical(raised.stream_id)
    with at("2026-10-20"):
        world.update_technical(raised.stream_id, subject="Beam B12 clash")
    with at("2026-10-21"), cf.use_viewer(CONTROLLER):
        world.issue_technical(raised.stream_id)
    with at("2026-10-22"):
        world.answer_technical(raised.stream_id, cost_impact="yes", schedule_impact="no")
        with cf.use_viewer(CONTROLLER):
            warning = world.escalate(raised.stream_id)
    with at("2026-10-25"):
        later = world.forge_item("P123-COR-0002", subject="Second letter", state="Received")
        with cf.use_viewer(CONTROLLER):
            link = world.link(warning.stream_id, later)
    with at("2026-10-26"), cf.use_viewer(CONTROLLER):
        world.set_class(letter, "restricted")
    with at("2026-10-27"), cf.use_viewer(CONTROLLER):
        world.retract_link(link.stream_id)
    return Story(world, letter, raised.stream_id, warning.stream_id, later, link.stream_id)


def trail(
    story: Story, number: str, as_of: str | None, viewer: cf.Viewer = CONTROLLER, **more: Any
) -> ev.EvidenceTrail:
    with (
        frozen_today("2026-10-30"),
        cf.use_viewer(viewer),
        open_uow(story.world.db, readonly=True) as uow,
    ):
        return ev.evidence_trail(uow.conn(), PROJECT, number, as_of, **more)


def keys(found: ev.EvidenceTrail) -> list[str | None]:
    return [n.key for n in found.nodes]


def node(found: ev.EvidenceTrail, key: str) -> ev.EvidenceNode:
    [one] = [n for n in found.nodes if n.key == key]
    return one


def test_on_the_day_of_the_answer_the_warning_leads_to_the_rfi_and_the_letter(story: Story) -> None:
    found = trail(story, "P123-EW-0001", "2026-10-22")
    assert found.as_of == "2026-10-22" and found.root_id == story.warning and not found.truncated
    assert keys(found) == ["P123-EW-0001", "P123-RFI-0001", "P123-COR-0001"]
    warning, rfi, letter = found.nodes
    assert (warning.depth, warning.parent_id, warning.via, warning.state) == (
        0,
        None,
        None,
        "Draft",
    )
    assert (rfi.depth, rfi.parent_id) == (1, story.warning)
    assert rfi.via is not None
    assert (rfi.via.relation, rfi.via.label, rfi.via.direction, rfi.via.status) == (
        "derived_from",
        "derived from",
        "out",
        "active",
    )
    assert rfi.via.since == "2026-10-22"
    assert rfi.state == "Answered" and rfi.facts["cost_impact"] == "yes"
    assert rfi.facts["answered_on"] == "2026-10-22" and "answer" in rfi.facts
    assert (letter.depth, letter.parent_id, letter.state) == (2, story.rfi, "Received")
    assert letter.via is not None and letter.via.label == "references"  # RFI -> letter


def test_the_link_from_the_rfi_to_the_letter_reads_as_references_from_the_rfi(story: Story) -> None:
    found = trail(story, "P123-RFI-0001", "2026-10-22", depth=1)
    letter = node(found, "P123-COR-0001")
    assert letter.via is not None
    assert (letter.via.relation, letter.via.direction, letter.via.note) == (
        "references",
        "out",
        "the letter",
    )


def test_the_trail_leaves_out_what_did_not_exist_yet(story: Story) -> None:
    before = trail(story, "P123-RFI-0001", "2026-10-21")
    assert keys(before) == ["P123-RFI-0001", "P123-COR-0001"]  # no warning: made on the 22nd
    rfi = node(before, "P123-RFI-0001")
    assert rfi.state == "Awaiting response" and "answered_on" not in rfi.facts
    assert rfi.facts["required_by"] == "2026-11-02" and rfi.created_on == "2026-10-19"
    assert rfi.facts["issued_on"] == "2026-10-21"
    with pytest.raises(EvidenceDateError, match="did not exist on 2026-10-21"):
        trail(story, "P123-EW-0001", "2026-10-21")


def test_the_state_and_the_title_are_the_ones_of_the_day(story: Story) -> None:
    def rfi(day: str) -> ev.EvidenceNode:
        return node(trail(story, "P123-RFI-0001", day, depth=0), "P123-RFI-0001")

    assert (rfi("2026-10-19").title, rfi("2026-10-19").state) == (
        "Beam B12 clashes with line 47",
        "Internal review",
    )
    assert (rfi("2026-10-20").title, rfi("2026-10-20").state) == (
        "Beam B12 clash",
        "Internal review",
    )
    assert rfi("2026-10-21").state == "Awaiting response"
    assert rfi("2026-10-22").state == "Answered"
    assert rfi("2026-10-30").title == "Beam B12 clash"


def test_a_link_made_later_is_absent_and_one_retracted_later_is_there_with_its_status(
    story: Story,
) -> None:
    assert "P123-COR-0002" not in keys(trail(story, "P123-EW-0001", "2026-10-24"))
    on_the_26th = trail(story, "P123-EW-0001", "2026-10-26")
    later = node(on_the_26th, "P123-COR-0002")
    assert (
        later.via is not None and later.via.status == "active" and later.via.since == "2026-10-25"
    )
    assert (later.via.relation, later.via.direction, later.parent_id) == (
        "references",
        "out",
        story.warning,
    )
    assert "P123-COR-0002" not in keys(trail(story, "P123-EW-0001", "2026-10-27"))
    assert "P123-COR-0002" not in keys(trail(story, "P123-EW-0001", None))  # today: retracted


def test_a_record_the_viewer_cannot_read_today_is_left_out_whatever_its_class_was(
    story: Story,
) -> None:
    on_the_22nd = trail(story, "P123-RFI-0001", "2026-10-22", viewer=PLAIN)
    # the letter was internal on the 22nd, restricted since the 26th: the class of today decides
    assert keys(on_the_22nd) == ["P123-RFI-0001"]  # and the warning is restricted all along
    with_boss = trail(story, "P123-RFI-0001", "2026-10-22")
    assert keys(with_boss) == ["P123-RFI-0001", "P123-COR-0001", "P123-EW-0001"]
    assert keys(trail(story, "P123-RFI-0001", "2026-10-22", viewer=AGENT)) == ["P123-RFI-0001"]


def test_nothing_says_how_many_records_were_left_out(story: Story) -> None:
    plain = trail(story, "P123-RFI-0001", "2026-10-22", viewer=PLAIN)
    assert plain.truncated is False
    dumped = plain.model_dump_json()
    for secret in ("P123-EW-0001", "P123-COR-0001", story.warning, story.letter):
        assert secret not in dumped
    assert "derived" not in dumped and "Client letter" not in dumped


def test_a_hidden_or_unknown_item_is_not_found_with_the_same_words(story: Story) -> None:
    with pytest.raises(ItemNotFoundError) as hidden:
        trail(story, "P123-EW-0001", "2026-10-22", viewer=PLAIN)
    with pytest.raises(ItemNotFoundError) as unknown:
        trail(story, "P123-EW-0099", "2026-10-22", viewer=PLAIN)
    assert str(hidden.value).replace("0001", "0099") == str(unknown.value)


def test_a_privileged_letter_linked_to_the_rfi_is_seen_only_by_the_named(story: Story) -> None:
    with at("2026-10-23"), cf.system_view():
        secret = story.world.forge_item(
            "P123-COR-0003",
            subject="Counsel advice",
            state="Received",
            confidentiality="privileged",
        )
        story.world.link(story.rfi, secret)
    found = trail(story, "P123-RFI-0001", "2026-10-30", viewer=CONTROLLER, depth=1)
    assert "P123-COR-0003" not in keys(found)  # a controller who is not named does not see it
    assert "Counsel advice" not in found.model_dump_json()


def test_the_depth_and_the_node_bounds(story: Story) -> None:
    assert keys(trail(story, "P123-EW-0001", "2026-10-22", depth=0)) == ["P123-EW-0001"]
    assert keys(trail(story, "P123-EW-0001", "2026-10-22", depth=1)) == [
        "P123-EW-0001",
        "P123-RFI-0001",
    ]
    capped = trail(story, "P123-EW-0001", "2026-10-22", max_nodes=2)
    assert len(capped.nodes) == 2 and capped.truncated is True
    assert trail(story, "P123-EW-0001", "2026-10-22", depth=99).nodes  # clamped, not refused


@pytest.mark.parametrize(
    "bad",
    [
        "2026-13-01",
        "20261020",
        "2026-10-1",
        "tomorrow",
        "2026-10-31",
        "1999-12-31",
        "２０２６-10-20",
    ],
)
def test_a_date_that_is_not_a_day_or_is_to_come_is_refused(story: Story, bad: str) -> None:
    with pytest.raises(EvidenceDateError):
        trail(story, "P123-RFI-0001", bad)


def test_today_is_the_default_and_the_whole_day_counts(story: Story) -> None:
    default = trail(story, "P123-EW-0001", None)
    assert default.as_of == "2026-10-30"
    on_the_day = trail(story, "P123-EW-0001", "2026-10-22")
    assert "P123-RFI-0001" in keys(on_the_day)  # recorded at noon, asked for the whole day


def test_the_facts_of_a_commercial_item_are_folded_from_its_events(story: Story) -> None:
    with at("2026-10-28"), cf.use_viewer(CONTROLLER):
        story.world.update_commercial(story.warning, estimated_value="1000", currency="USD")
    earlier = node(trail(story, "P123-EW-0001", "2026-10-27"), "P123-EW-0001")
    later = node(trail(story, "P123-EW-0001", "2026-10-28"), "P123-EW-0001")
    assert "estimated_value" not in earlier.facts
    assert later.facts["estimated_value"] == "1000.00" and later.facts["currency"] == "USD"
    assert later.facts["aware_on"] == "2026-10-22"
