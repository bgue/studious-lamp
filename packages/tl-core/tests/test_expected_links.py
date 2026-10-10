"""Expected links: declarations and the missing list (P0-I3-T04; brief 7.1)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core.links.expected import (
    ExpectedLink,
    ExpectedLinkError,
    ExpectedLinkRegistry,
    default_expected_links,
    load_expected_links,
    missing_expected_links,
    parse_expected_links,
    unmet_expectations,
)
from tl_core.services.commands import CreateRecord
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.records import handle_create_record
from tl_core.uow import UnitOfWork

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "schema" / "fixtures" / "links"

SCHEMA = """
id: https://example.org/test
name: test
annotations:
  tl:module: piping
classes:
  Weld:
    annotations:
      tl:expects_link:
        - relation: requires
          target_type: piping.WPS
          by_state: Welded
          label: WPS
        - relation: raised_against
          direction: in
          min_count: 2
  Spool:
    annotations:
      tl:expects_link:
        relation: belongs_to
        direction: out
  Plain:
    description: no expectations
"""


# --- parsing --------------------------------------------------------------------------------


def test_expected_link_defaults() -> None:
    link = ExpectedLink(relation="requires")
    assert (link.direction, link.target_type, link.by_state) == ("out", None, None)
    assert (link.label, link.min_count) == (None, 1)
    assert link.display == "requires"
    assert ExpectedLink(relation="requires", label="WPS").display == "WPS"


def test_expected_link_rejects_bad_values() -> None:
    with pytest.raises(ValueError):
        ExpectedLink(relation="requires", min_count=0)
    with pytest.raises(ValueError):
        ExpectedLink.model_validate({"relation": "requires", "direction": "sideways"})
    with pytest.raises(ValueError):
        ExpectedLink.model_validate({"relation": "requires", "colour": "red"})


def test_parse_reads_every_class_of_the_schema() -> None:
    registry = parse_expected_links(SCHEMA, source="s.yaml")
    assert registry.record_types() == ["piping.Spool", "piping.Weld"]
    weld = registry.for_type("piping.Weld")
    assert weld == [
        ExpectedLink(relation="requires", target_type="piping.WPS", by_state="Welded", label="WPS"),
        ExpectedLink(relation="raised_against", direction="in", min_count=2),
    ]
    assert registry.for_type("piping.Spool") == [ExpectedLink(relation="belongs_to")]
    assert registry.for_type("piping.Plain") == []
    assert registry.for_type("nothing.Here") == []


def test_for_type_returns_a_copy() -> None:
    registry = parse_expected_links(SCHEMA)
    registry.for_type("piping.Weld").clear()
    assert len(registry.for_type("piping.Weld")) == 2


def test_a_schema_without_expectations_gives_an_empty_registry() -> None:
    assert parse_expected_links("id: x\nname: x\nclasses:\n  A: {}\n").record_types() == []
    assert parse_expected_links("id: x\nname: x\n").record_types() == []


@pytest.mark.parametrize(
    ("text_", "message"),
    [
        ("id: [", r"^s\.yaml: invalid YAML"),
        ("- a", r"^s\.yaml: a schema file must be a YAML mapping"),
        (
            "classes:\n  A:\n    annotations:\n      tl:expects_link:\n        - relation: r\n",
            r"^s\.yaml: class A has tl:expects_link but the schema has no tl:module",
        ),
        (
            "annotations:\n  tl:module: m\nclasses:\n  A:\n    annotations:\n"
            "      tl:expects_link:\n        - direction: out\n",
            r"^s\.yaml: A\.tl:expects_link\[0\]: relation",
        ),
    ],
)
def test_parse_errors_name_the_source(text_: str, message: str) -> None:
    with pytest.raises(ExpectedLinkError, match=message):
        parse_expected_links(text_, source="s.yaml")


def test_registry_add_and_merge() -> None:
    first = ExpectedLinkRegistry()
    first.add("a.A", ExpectedLink(relation="requires"))
    second = ExpectedLinkRegistry({"a.A": [ExpectedLink(relation="blocks")]})
    second.add("b.B", ExpectedLink(relation="verifies"))
    first.merge(second)
    assert [e.relation for e in first.for_type("a.A")] == ["requires", "blocks"]
    assert first.record_types() == ["a.A", "b.B"]


def test_load_reads_a_file_or_a_directory(tmp_path: Path) -> None:
    (tmp_path / "b.yaml").write_text(SCHEMA.replace("piping", "second"), encoding="utf-8")
    (tmp_path / "a.yaml").write_text(SCHEMA, encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("nope", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.yaml").write_text(SCHEMA.replace("piping", "third"), encoding="utf-8")
    assert load_expected_links(tmp_path).record_types() == [
        "piping.Spool",
        "piping.Weld",
        "second.Spool",
        "second.Weld",
    ]
    assert load_expected_links(tmp_path / "a.yaml").record_types() == [
        "piping.Spool",
        "piping.Weld",
    ]


def test_load_of_a_missing_path_is_empty(tmp_path: Path) -> None:
    assert load_expected_links(tmp_path / "missing").record_types() == []


def test_load_names_the_bad_file(tmp_path: Path) -> None:
    (tmp_path / "bad.yaml").write_text("id: [", encoding="utf-8")
    with pytest.raises(ExpectedLinkError, match=r"^bad\.yaml: invalid YAML"):
        load_expected_links(tmp_path)


def test_the_shipped_sample_declares_one_expectation_for_core_record() -> None:
    registry = load_expected_links(FIXTURE_DIR)
    assert registry.record_types() == ["core.Record"]
    assert registry.for_type("core.Record") == [
        ExpectedLink(
            relation="references", direction="out", by_state="Approved", label="supporting record"
        )
    ]


def test_default_expected_links_follows_the_schema_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    assert default_expected_links().record_types() == ["core.Record"]
    (tmp_path / "links").mkdir()
    (tmp_path / "links" / "x.yaml").write_text(SCHEMA, encoding="utf-8")
    monkeypatch.setenv("TL_SCHEMA_DIR", str(tmp_path))
    assert default_expected_links().record_types() == ["piping.Spool", "piping.Weld"]


# --- evaluation against cur_links -----------------------------------------------------------


@pytest.fixture
def uow(new_db: Callable[[], DbTarget]) -> Iterator[UnitOfWork]:
    db = new_db()
    create_schema(db)
    with open_uow(db) as handle:
        yield handle


def record(uow: UnitOfWork, key: str, **kw: Any) -> str:
    result = handle_create_record(
        uow,
        CreateRecord(
            actor="u", source="t", scope="project:P1", record_type="core.Record", title=key, key=key
        ),
    )
    if kw.get("voided"):
        uow.conn().execute(
            text("UPDATE cur_core_record SET voided = TRUE WHERE id = :id"),
            {"id": result.stream_id},
        )
    if "type" in kw:
        uow.conn().execute(
            text("UPDATE cur_core_record SET type = :t WHERE id = :id"),
            {"t": kw["type"], "id": result.stream_id},
        )
    return result.stream_id


_n = 0


def add_link(
    uow: UnitOfWork, from_id: str, to_id: str, relation: str = "requires", status: str = "active"
) -> None:
    global _n
    _n += 1
    uow.conn().execute(
        text(
            "INSERT INTO cur_links (link_id, scope, from_id, to_id, relation, status, source, "
            "declined, created_by, created_at, updated_at, version, last_seq) VALUES "
            "(:id, 'project:P1', :f, :t, :r, :s, 'manual', FALSE, 'u', "
            "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', 1, 1)"
        ),
        {"id": f"L{_n}", "f": from_id, "t": to_id, "r": relation, "s": status},
    )


def test_no_links_means_everything_is_missing(uow: UnitOfWork) -> None:
    a = record(uow, "A")
    expectation = ExpectedLink(relation="requires", label="permit")
    missing = unmet_expectations(uow, a, [expectation])
    assert len(missing) == 1
    assert (missing[0].expectation, missing[0].found, missing[0].needed) == (expectation, 0, 1)


def test_an_active_outbound_link_satisfies_an_out_expectation(uow: UnitOfWork) -> None:
    a, b = record(uow, "A"), record(uow, "B")
    add_link(uow, a, b)
    assert unmet_expectations(uow, a, [ExpectedLink(relation="requires")]) == []
    # the other end sees it as inbound, not outbound
    assert len(unmet_expectations(uow, b, [ExpectedLink(relation="requires")])) == 1
    assert unmet_expectations(uow, b, [ExpectedLink(relation="requires", direction="in")]) == []
    assert unmet_expectations(uow, b, [ExpectedLink(relation="requires", direction="either")]) == []


@pytest.mark.parametrize("status", ["suggested", "stale", "broken", "retracted"])
def test_only_an_active_link_counts(uow: UnitOfWork, status: str) -> None:
    a, b = record(uow, "A"), record(uow, "B")
    add_link(uow, a, b, status=status)
    assert len(unmet_expectations(uow, a, [ExpectedLink(relation="requires")])) == 1


def test_the_relation_must_match(uow: UnitOfWork) -> None:
    a, b = record(uow, "A"), record(uow, "B")
    add_link(uow, a, b, relation="references")
    assert len(unmet_expectations(uow, a, [ExpectedLink(relation="requires")])) == 1


def test_target_type_must_match_the_other_end(uow: UnitOfWork) -> None:
    a = record(uow, "A")
    b = record(uow, "B", type="piping.WPS")
    c = record(uow, "C")
    add_link(uow, a, c)
    want = ExpectedLink(relation="requires", target_type="piping.WPS")
    assert len(unmet_expectations(uow, a, [want])) == 1
    add_link(uow, a, b)
    assert unmet_expectations(uow, a, [want]) == []


def test_a_voided_other_end_does_not_count(uow: UnitOfWork) -> None:
    a = record(uow, "A")
    b = record(uow, "B", voided=True)
    add_link(uow, a, b)
    assert len(unmet_expectations(uow, a, [ExpectedLink(relation="requires")])) == 1


def test_min_count_reports_found_and_needed(uow: UnitOfWork) -> None:
    a, b, c = record(uow, "A"), record(uow, "B"), record(uow, "C")
    add_link(uow, a, b)
    want = ExpectedLink(relation="requires", min_count=2)
    (missing,) = unmet_expectations(uow, a, [want])
    assert (missing.found, missing.needed) == (1, 2)
    add_link(uow, a, c)
    assert unmet_expectations(uow, a, [want]) == []


def test_either_counts_both_directions_once_each(uow: UnitOfWork) -> None:
    a, b, c = record(uow, "A"), record(uow, "B"), record(uow, "C")
    add_link(uow, a, b)
    add_link(uow, c, a)
    want = ExpectedLink(relation="requires", direction="either", min_count=2)
    assert unmet_expectations(uow, a, [want]) == []
    (missing,) = unmet_expectations(
        uow, b, [ExpectedLink(relation="requires", direction="either", min_count=2)]
    )
    assert missing.found == 1


def test_unmet_expectations_keeps_the_order_given(uow: UnitOfWork) -> None:
    a = record(uow, "A")
    wants = [ExpectedLink(relation="blocks"), ExpectedLink(relation="verifies")]
    assert [m.expectation.relation for m in unmet_expectations(uow, a, wants)] == [
        "blocks",
        "verifies",
    ]


def test_missing_expected_links_uses_the_record_type(uow: UnitOfWork) -> None:
    a, b = record(uow, "A"), record(uow, "B")
    registry = ExpectedLinkRegistry(
        {
            "core.Record": [ExpectedLink(relation="references", by_state="Approved")],
            "other.Type": [ExpectedLink(relation="blocks")],
        }
    )
    assert [m.expectation.relation for m in missing_expected_links(uow, a, registry=registry)] == [
        "references"
    ]
    add_link(uow, a, b, relation="references")
    assert missing_expected_links(uow, a, registry=registry) == []


def test_by_state_narrows_the_expectations_checked(uow: UnitOfWork) -> None:
    a = record(uow, "A")
    registry = ExpectedLinkRegistry(
        {
            "core.Record": [
                ExpectedLink(relation="references", by_state="Approved"),
                ExpectedLink(relation="requires", by_state="Issued"),
                ExpectedLink(relation="blocks"),
            ]
        }
    )
    assert len(missing_expected_links(uow, a, registry=registry)) == 3
    only = missing_expected_links(uow, a, registry=registry, by_state="Issued")
    assert [m.expectation.relation for m in only] == ["requires"]
    assert missing_expected_links(uow, a, registry=registry, by_state="Nowhere") == []


def test_missing_expected_links_defaults_to_the_shipped_declarations(
    uow: UnitOfWork, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    a, b = record(uow, "A"), record(uow, "B")
    missing = missing_expected_links(uow, a, by_state="Approved")
    assert [m.expectation.label for m in missing] == ["supporting record"]
    add_link(uow, a, b, relation="references")
    assert missing_expected_links(uow, a, by_state="Approved") == []


def test_an_unknown_record_is_refused(uow: UnitOfWork) -> None:
    with pytest.raises(RecordNotFoundError):
        missing_expected_links(uow, "NOPE", registry=ExpectedLinkRegistry())


# --- supervisor additions (review of T04) ----------------------------------------------------


def test_an_empty_file_declares_nothing() -> None:
    assert parse_expected_links("", source="e.yaml").record_types() == []
    assert parse_expected_links("# only a comment\n", source="e.yaml").record_types() == []


def test_a_non_list_annotation_value_is_refused() -> None:
    text_ = (
        "annotations:\n  tl:module: m\nclasses:\n  A:\n    annotations:\n"
        "      tl:expects_link: just-a-string\n"
    )
    with pytest.raises(ExpectedLinkError, match=r"^s\.yaml: A\.tl:expects_link must be a mapping"):
        parse_expected_links(text_, source="s.yaml")


def test_a_self_link_counts_once_under_either(uow: UnitOfWork) -> None:
    a = record(uow, "A")
    add_link(uow, a, a)  # the commands refuse self-links; the projection could still hold one
    want = ExpectedLink(relation="requires", direction="either", min_count=2)
    (missing,) = unmet_expectations(uow, a, [want])
    assert missing.found == 1
