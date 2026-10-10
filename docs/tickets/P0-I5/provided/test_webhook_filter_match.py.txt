"""WebhookFilter.matches_row: every part of the subscription filter (P0-I5-T22)."""

from __future__ import annotations

import pytest
from tl_core.webhooks.filters import WebhookFilter
from tl_core.webhooks.rows import OutboxRow

RID = "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5"
OTHER = "01J9Z6Q4W3X2Y1V0T9S8R7Q6P6"
THIRD = "01J9Z6Q4W3X2Y1V0T9S8R7Q6P7"


def row(**kw: object) -> OutboxRow:
    base: dict[str, object] = {
        "seq": 10,
        "event_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6P9",
        "scope": "project:P123",
        "event_type": "Record.Updated",
        "stream_id": RID,
        "stream_type": "core.Record",
        "stream_version": 2,
        "subject_id": RID,
        "actor": "user:a",
        "recorded_at": "2026-10-09T03:14:07.000000+00:00",
        "correlation_id": "c",
    }
    base.update(kw)
    return OutboxRow(**base)  # type: ignore[arg-type]


def test_an_empty_filter_matches_every_row() -> None:
    assert WebhookFilter().matches_row(row())
    assert WebhookFilter().matches_row(row(event_type="Anything.Else", scope="company"))


@pytest.mark.parametrize(
    ("patterns", "event_type", "expected"),
    [
        (("Record.Updated",), "Record.Updated", True),
        (("Record.Updated",), "Record.Created", False),
        (("Record.*",), "Record.Voided", True),
        (("*.Created",), "File.Created", True),
        (("*.Created",), "Record.Updated", False),
        (("Link.Added", "Record.*"), "Record.Updated", True),
        (("Link.Added", "Record.*"), "Pset.ValuesSet", False),
        (("record.*",), "Record.Updated", False),  # case-sensitive
        (("Record.Updat?d",), "Record.Updated", True),
    ],
)
def test_event_types_are_exact_names_or_globs(
    patterns: tuple[str, ...], event_type: str, expected: bool
) -> None:
    assert WebhookFilter(event_types=patterns).matches_row(row(event_type=event_type)) is expected


@pytest.mark.parametrize(
    ("selector", "scope", "expected"),
    [
        ("project:P123", "project:P123", True),
        ("project:P123", "project:P999", False),
        ("project:*", "project:P999", True),
        ("project:*", "company", False),
        ("company", "company", True),
    ],
)
def test_scope_selector_is_an_id_or_a_glob(selector: str, scope: str, expected: bool) -> None:
    assert WebhookFilter(scope_selector=selector).matches_row(row(scope=scope)) is expected


def test_record_ids_match_the_subject_or_the_far_end_of_a_link() -> None:
    wanted = WebhookFilter(record_ids=frozenset({RID}))
    assert wanted.matches_row(row(subject_id=RID))
    assert wanted.matches_row(row(subject_id=OTHER, related_ids=(THIRD, RID)))
    assert not wanted.matches_row(row(subject_id=OTHER, related_ids=(THIRD,)))
    assert not wanted.matches_row(row(subject_id=OTHER))


def test_changed_fields_match_by_name_glob_or_parent_path() -> None:
    changed = row(changed_fields=("psets.vt.result", "status"))
    assert WebhookFilter(changed_fields=("status",)).matches_row(changed)
    assert WebhookFilter(changed_fields=("psets.vt.*",)).matches_row(changed)
    assert WebhookFilter(changed_fields=("psets.vt",)).matches_row(changed)  # a parent matches
    assert WebhookFilter(changed_fields=("psets",)).matches_row(changed)
    assert not WebhookFilter(changed_fields=("psets.valve",)).matches_row(changed)
    assert not WebhookFilter(changed_fields=("stat",)).matches_row(changed)  # no bare prefix
    assert not WebhookFilter(changed_fields=("status",)).matches_row(row())  # nothing changed


@pytest.mark.parametrize(
    ("entry", "src", "dst", "expected"),
    [
        ("InReview -> Issued", "InReview", "Issued", True),
        ("InReview -> Issued", "Draft", "Issued", False),
        ("InReview->Issued", "InReview", "Issued", True),
        ("InReview → Issued", "InReview", "Issued", True),
        ("* -> Passed", "Anything", "Passed", True),
        ("* -> Passed", "Anything", "Failed", False),
        ("Draft -> *", "Draft", "Whatever", True),
        ("* -> *", "A", "B", True),
        ("In* -> Is*", "InReview", "Issued", True),
    ],
)
def test_transitions_match_from_and_to_with_wildcards(
    entry: str, src: str, dst: str, expected: bool
) -> None:
    flt = WebhookFilter(transitions=(entry,))
    assert flt.matches_row(row(from_state=src, to_state=dst)) is expected


def test_transitions_need_a_transition_and_any_listed_one_is_enough() -> None:
    flt = WebhookFilter(transitions=("A -> B", "C -> D"))
    assert flt.matches_row(row(from_state="C", to_state="D"))
    assert not flt.matches_row(row())  # not a transition event
    assert not flt.matches_row(row(from_state="C", to_state=None))


def test_link_relations_and_file_slots_match_by_glob() -> None:
    assert WebhookFilter(link_relations=("raised_against",)).matches_row(
        row(link_relations=("raised_against",))
    )
    assert WebhookFilter(link_relations=("raised_*",)).matches_row(
        row(link_relations=("belongs_to", "raised_against"))
    )
    assert not WebhookFilter(link_relations=("belongs_to",)).matches_row(
        row(link_relations=("raised_against",))
    )
    assert not WebhookFilter(link_relations=("belongs_to",)).matches_row(row())
    assert WebhookFilter(file_slots=("mtr",)).matches_row(row(file_slot="mtr"))
    assert WebhookFilter(file_slots=("m*", "other")).matches_row(row(file_slot="mtr"))
    assert not WebhookFilter(file_slots=("mtr",)).matches_row(row(file_slot="photo"))
    assert not WebhookFilter(file_slots=("mtr",)).matches_row(row())


def test_hashtags_ignore_case_and_the_hash_sign() -> None:
    posted = row(hashtags=("Safety", "qa"))
    assert WebhookFilter(hashtags=("safety",)).matches_row(posted)
    assert WebhookFilter(hashtags=("#SAFETY",)).matches_row(posted)
    assert WebhookFilter(hashtags=("x", "QA")).matches_row(posted)
    assert not WebhookFilter(hashtags=("hold",)).matches_row(posted)
    assert not WebhookFilter(hashtags=("hold",)).matches_row(row())


def test_every_part_that_is_set_must_match() -> None:
    flt = WebhookFilter(
        scope_selector="project:*",
        event_types=("Workflow.Transitioned",),
        record_ids=frozenset({RID}),
        transitions=("* -> Issued",),
    )
    good = row(event_type="Workflow.Transitioned", from_state="InReview", to_state="Issued")
    assert flt.matches_row(good)
    assert not flt.matches_row(row(event_type="Record.Updated", from_state="a", to_state="Issued"))
    assert not flt.matches_row(
        row(event_type="Workflow.Transitioned", from_state="a", to_state="Issued", subject_id=OTHER)
    )
    assert not flt.matches_row(
        row(event_type="Workflow.Transitioned", from_state="a", to_state="Done")
    )
    assert not flt.matches_row(
        row(event_type="Workflow.Transitioned", from_state="a", to_state="Issued", scope="company")
    )


def test_the_record_selector_is_not_judged_by_matches_row() -> None:
    assert WebhookFilter(record_selector="status:open").matches_row(row())
