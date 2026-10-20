"""The read shapes: summaries, detail with the diff, adoptions, waivers, drift, test on sample."""

from __future__ import annotations

from datetime import timedelta

import pytest
from tl_adapters.db import open_uow
from tl_core.util import utcnow
from tl_mod_schemareg import views
from tl_mod_schemareg.errors import SchemaPackageNotFoundError
from tl_mod_schemareg.handlers.adoption import AdoptSchemaPackage
from tl_mod_schemareg.handlers.packages import AnalyseSchemaPackage, DraftSchemaPackage
from tl_mod_schemareg.handlers.waivers import ApproveWaiver, RequestWaiver
from tl_mod_schemareg.testing import (
    ADMIN,
    AUTHOR,
    RegistryWorld,
    add_optional_property,
    add_required_property,
    make_record,
    next_version,
    publish_version,
)

PKG = "co.acme.engineering"


def draft(world: RegistryWorld, version: str = "3.3.0", edit=add_optional_property) -> str:  # type: ignore[no-untyped-def]
    return world.do(DraftSchemaPackage, content=next_version(PKG, version, edit)).stream_id


def test_summaries_filter_by_state_and_package_and_list_the_highest_first(
    world: RegistryWorld,
) -> None:
    publish_version(world, "3.3.0")
    draft(world, "3.4.0")
    with open_uow(world.db, readonly=True) as uow:
        everything = views.package_summaries(uow.conn())
        drafts = views.package_summaries(uow.conn(), state="Draft")
        published = views.package_summaries(uow.conn(), state="Published", package=PKG)
        other = views.package_summaries(uow.conn(), package="nope")
        paged = views.package_summaries(uow.conn(), limit=1, offset=1)
    assert [p.version for p in everything] == ["3.4.0", "3.3.0"]
    assert [p.key for p in drafts] == [f"{PKG}@3.4.0"] and [p.state for p in published] == [
        "Published"
    ]
    assert other == [] and [p.version for p in paged] == ["3.3.0"]
    assert not drafts[0].analysed and published[0].analysed


def test_detail_has_the_reports_the_lint_and_a_diff_against_the_base(world: RegistryWorld) -> None:
    package_id = draft(world)
    world.do(AnalyseSchemaPackage, package_id=package_id)
    with open_uow(world.db, readonly=True) as uow:
        by_id = views.package_detail(uow.conn(), package_id)
        by_key = views.package_detail(uow.conn(), f"{PKG}@3.3.0")
    assert by_id == by_key
    assert by_id.base_ref == f"{PKG}@3.2.0" and by_id.classification is not None
    assert by_id.classification.worst == "additive" and by_id.impact is not None
    assert by_id.impact.new_hash and by_id.analysed
    assert "+      seat_leak_class:" in by_id.diff and by_id.diff.startswith(f"--- {PKG}@3.2.0")
    assert not by_id.diff_truncated


def test_a_package_that_is_not_there_is_not_found(world: RegistryWorld) -> None:
    with open_uow(world.db, readonly=True) as uow:
        with pytest.raises(SchemaPackageNotFoundError):
            views.package_detail(uow.conn(), "nope")
        with pytest.raises(SchemaPackageNotFoundError):
            views.package_detail(uow.conn(), f"{PKG}@9.9.9")


def test_a_first_version_has_no_diff(world: RegistryWorld) -> None:
    from tl_mod_schemareg.testing import fixture_text

    text = fixture_text("co.acme.engineering").replace("co.acme.engineering", "co.beta.engineering")
    package_id = world.do(DraftSchemaPackage, content=text).stream_id
    with open_uow(world.db, readonly=True) as uow:
        detail = views.package_detail(uow.conn(), package_id)
    assert detail.diff == "" and detail.base_ref is None


def test_adoptions_waivers_and_drift(world: RegistryWorld) -> None:
    publish_version(world, "3.3.0")
    world.do(AdoptSchemaPackage, ADMIN, project="P999", package=PKG, version="3.3.0")
    expires = (utcnow().date() + timedelta(days=10)).isoformat()
    waiver = world.do(
        RequestWaiver,
        AUTHOR,
        project="P998",
        path="psets.valve_data.size_in",
        reason="Legacy.",
        expires=expires,
    )
    with open_uow(world.db, readonly=True) as uow:
        adoptions = views.adoption_views(uow.conn(), "P999")
        none = views.adoption_views(uow.conn(), "P998")
        waivers = views.waiver_views(uow.conn(), "P998")
    assert [(a.package, a.version) for a in adoptions] == [(PKG, "3.3.0")] and none == []
    assert [(w.state, w.expired) for w in waivers] == [("Requested", False)]
    world.do(ApproveWaiver, ADMIN, waiver_id=waiver.stream_id)
    drift = {d.package: d for d in views.drift_views("P998")}
    assert drift[PKG].behind and not drift[PKG].pinned and drift[PKG].company_version == "3.3.0"
    pinned = {d.package: d for d in views.drift_views("P999")}
    assert not pinned[PKG].behind and pinned[PKG].pinned


def test_the_sample_test_counts_records_that_would_newly_fail(world: RegistryWorld) -> None:
    make_record(world, "R-1", {"valve_data": {"manufacturer": "Acme"}})
    make_record(world, "R-2", {"valve_data": {"manufacturer": "Borealis"}})
    make_record(world, "R-3", {})
    package_id = draft(world, "3.3.0", _required_everywhere)
    with open_uow(world.db, readonly=True) as uow:
        result = views.sample_test(uow.conn(), package_id)
        small = views.sample_test(uow.conn(), package_id, 1)
    assert result.checked == 4 and result.newly_nonconformant == 2  # the draft is a record too
    assert {e.path for e in result.examples} == {"psets.valve_data.seat_leak_class"}
    assert result.examples[0].rule == "required_in_state"
    assert small.checked == 1 and small.sample == 1


def _required_everywhere(data: dict) -> None:  # type: ignore[type-arg]
    add_required_property(data)
    data["psets"]["valve_data"]["properties"]["seat_leak_class"]["required_in_states"] = ["*"]


def test_an_additive_draft_changes_no_record(world: RegistryWorld) -> None:
    make_record(world, "R-1", {"valve_data": {"manufacturer": "Acme"}})
    package_id = draft(world)
    with open_uow(world.db, readonly=True) as uow:
        result = views.sample_test(uow.conn(), package_id)
    assert (result.checked, result.newly_nonconformant, result.newly_warning, result.fixed) == (
        2,
        0,
        0,
        0,
    )
