"""The conformance dashboard: counts by type and status, stale, waivers, drift, the viewer."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.modules import ConfidentialSource
from tl_core.util import utcnow
from tl_mod_schemareg import dashboard
from tl_mod_schemareg.dashboard import ConformanceView, TypeConformance
from tl_mod_schemareg.handlers.adoption import AdoptSchemaPackage
from tl_mod_schemareg.handlers.waivers import ApproveWaiver, RequestWaiver, RevokeWaiver
from tl_mod_schemareg.testing import ADMIN, AUTHOR, RegistryWorld, make_record, publish_version

PKG = "co.acme.engineering"
PATH = "psets.valve_data.size_in"
PROJECT = "P999"
SCOPE = "project:P999"
THING, OTHER, VAULT = "core.Record", "core.Other", "core.Vault"
OLD = "0" * 64
READER = cf.Viewer(actor="user:ann", level=0, account="user:ann")
CONTROLLER = cf.Viewer(actor="user:ctl", level=1, account="user:ctl")


def hash_in_force(world: RegistryWorld, project: str = PROJECT) -> str:
    return world.provider.effective(f"project:{project}").hash


def place(
    world: RegistryWorld,
    key: str,
    *,
    type: str = THING,
    status: str = "ok",
    hash: str | None = None,
    scope: str = SCOPE,
    voided: bool = False,
) -> str:
    """A record whose projected row says what a test needs (type, stored status, hash, voided)."""
    record = make_record(world, key, {}, scope)
    with open_uow(world.db) as uow:
        uow.conn().execute(
            text(
                "UPDATE cur_core_record SET type = :t, conformance = :c, "
                "effective_schema_hash = :h, voided = :v WHERE id = :id"
            ),
            {"t": type, "c": status, "h": hash, "v": voided, "id": record},
        )
    return record


def view(world: RegistryWorld, project: str = PROJECT) -> ConformanceView:
    with open_uow(world.db, readonly=True) as uow:
        return dashboard.conformance_dashboard(uow.conn(), project)


def types(found: ConformanceView) -> dict[str, TypeConformance]:
    return {t.type: t for t in found.by_type}


def days(n: int) -> str:
    return (utcnow().date() + timedelta(days=n)).isoformat()


def waiver(world: RegistryWorld, path: str = PATH, n: int = 10, approve: bool = True) -> str:
    made = world.do(
        RequestWaiver, AUTHOR, project=PROJECT, path=path, reason="Legacy.", expires=days(n)
    )
    if approve:
        world.do(ApproveWaiver, ADMIN, waiver_id=made.stream_id)
    return made.stream_id


def set_expiry(world: RegistryWorld, waiver_id: str, expires: str) -> None:
    with open_uow(world.db) as uow:
        uow.conn().execute(
            text("UPDATE cur_schemareg_waiver SET expires = :e WHERE id = :id"),
            {"e": expires, "id": waiver_id},
        )
    world.provider.reload()


def test_an_empty_project_has_a_hash_and_nothing_else(world: RegistryWorld) -> None:
    found = view(world)
    assert found.project == PROJECT and found.schema_hash == hash_in_force(world)
    assert (found.total, found.by_type, found.waivers, found.expired_waivers) == (0, [], [], 0)


def test_counts_by_type_and_status_with_the_total_their_sum_and_types_sorted(
    world: RegistryWorld,
) -> None:
    current = hash_in_force(world)
    layout = {
        THING: {"ok": 3, "warning": 2, "nonconformant": 1},
        OTHER: {"ok": 1, "warning": 4, "nonconformant": 2},
    }
    for kind, counts in layout.items():
        for status, n in counts.items():
            for i in range(n):
                place(world, f"{kind}-{status}-{i}", type=kind, status=status, hash=current)
    found = view(world)
    assert [t.type for t in found.by_type] == [OTHER, THING]  # sorted, not in creation order
    one, two = types(found)[THING], types(found)[OTHER]
    assert (one.total, one.ok, one.warning, one.nonconformant) == (6, 3, 2, 1)
    assert (two.total, two.ok, two.warning, two.nonconformant) == (7, 1, 4, 2)
    assert one.total == one.ok + one.warning + one.nonconformant
    assert found.total == 13 == sum(t.total for t in found.by_type)
    assert (one.stale, two.stale) == (0, 0)


def test_the_ok_and_warning_counts_are_not_swapped(world: RegistryWorld) -> None:
    current = hash_in_force(world)
    place(world, "A", status="warning", hash=current)
    place(world, "B", status="warning", hash=current)
    place(world, "C", status="ok", hash=current)
    place(world, "D", status="nonconformant", hash=current)
    counted = types(view(world))[THING]
    assert (counted.ok, counted.warning, counted.nonconformant) == (1, 2, 1)


def test_a_record_checked_against_an_older_hash_or_none_is_stale(world: RegistryWorld) -> None:
    place(world, "NOW", hash=hash_in_force(world))
    place(world, "OLD", hash=OLD)
    place(world, "NEVER", hash=None)
    found = view(world)
    assert types(found)[THING].stale == 2 and types(found)[THING].total == 3


def test_stale_is_counted_per_type(world: RegistryWorld) -> None:
    current = hash_in_force(world)
    place(world, "A", type=THING, hash=current)
    place(world, "B", type=OTHER, hash=OLD)
    place(world, "C", type=OTHER, hash=current)
    found = types(view(world))
    assert (found[THING].stale, found[OTHER].stale) == (0, 1)


def test_adopting_a_package_version_makes_the_records_stale(world: RegistryWorld) -> None:
    publish_version(world, "3.3.0")
    before = hash_in_force(world)
    place(world, "A", hash=before)
    place(world, "B", hash=before)
    assert types(view(world))[THING].stale == 0
    world.do(AdoptSchemaPackage, ADMIN, project=PROJECT, package=PKG, version="3.3.0")
    after = hash_in_force(world)
    found = view(world)
    assert after != before and found.schema_hash == after
    assert types(found)[THING].stale == 2


def test_approving_a_waiver_changes_the_hash_and_makes_the_records_stale(
    world: RegistryWorld,
) -> None:
    place(world, "A", hash=hash_in_force(world))
    request = world.do(
        RequestWaiver, AUTHOR, project=PROJECT, path=PATH, reason="Legacy.", expires=days(5)
    )
    assert types(view(world))[THING].stale == 0
    world.do(ApproveWaiver, ADMIN, waiver_id=request.stream_id)
    assert types(view(world))[THING].stale == 1


def test_waivers_show_the_days_left_in_order_and_only_the_approved(world: RegistryWorld) -> None:
    later = waiver(world, "psets.valve_data.size_in", 20)
    sooner = waiver(world, "psets.valve_data.tag_no", 3)
    waiver(world, "psets.valve_data.manufacturer", 7, approve=False)  # Requested
    revoked = waiver(world, "psets.valve_data.body_material", 9)
    world.do(RevokeWaiver, ADMIN, waiver_id=revoked, reason="Fixed.")
    found = view(world)
    assert [(w.path, w.days_left, w.expires) for w in found.waivers] == [
        ("psets.valve_data.tag_no", 3, days(3)),
        ("psets.valve_data.size_in", 20, days(20)),
    ]
    assert found.waivers[0].key == world.waiver(sooner).key
    assert found.waivers[1].key == world.waiver(later).key
    assert found.expired_waivers == 0


def test_waivers_that_expire_the_same_day_are_ordered_by_key(world: RegistryWorld) -> None:
    waiver(world, "psets.valve_data.tag_no", 4)
    waiver(world, "psets.valve_data.size_in", 4)
    keys = [w.key for w in view(world).waivers]
    assert len(keys) == 2 and keys == sorted(keys)


def test_a_waiver_on_its_last_day_has_no_days_left_but_is_listed(world: RegistryWorld) -> None:
    waiver(world, PATH, 0)
    found = view(world)
    assert [w.days_left for w in found.waivers] == [0] and found.expired_waivers == 0


def test_an_approved_waiver_past_its_day_is_counted_and_not_listed(world: RegistryWorld) -> None:
    gone = waiver(world, PATH, 5)
    waiver(world, "psets.valve_data.tag_no", 5)
    set_expiry(world, gone, days(-1))
    found = view(world)
    assert found.expired_waivers == 1 and [w.path for w in found.waivers] == [
        "psets.valve_data.tag_no"
    ]
    assert all(w.days_left >= 0 for w in found.waivers)


def test_the_waivers_of_another_project_are_not_shown(world: RegistryWorld) -> None:
    made = world.do(
        RequestWaiver, AUTHOR, project="P998", path=PATH, reason="Legacy.", expires=days(5)
    )
    world.do(ApproveWaiver, ADMIN, waiver_id=made.stream_id)
    found = view(world)
    assert found.waivers == [] and found.expired_waivers == 0


def test_drift_lists_only_the_packages_the_project_is_behind_on(world: RegistryWorld) -> None:
    assert view(world).drift == []
    publish_version(world, "3.3.0")
    behind = view(world).drift
    assert [(d.package, d.project_version, d.company_version, d.behind) for d in behind] == [
        (PKG, "3.2.0", "3.3.0", True)
    ]
    world.do(AdoptSchemaPackage, ADMIN, project=PROJECT, package=PKG, version="3.3.0")
    assert view(world).drift == []


def test_voided_records_and_records_of_another_project_are_never_counted(
    world: RegistryWorld,
) -> None:
    current = hash_in_force(world)
    place(world, "LIVE", hash=current)
    place(world, "GONE", hash=OLD, status="nonconformant", voided=True)
    place(world, "ELSEWHERE", hash=OLD, status="nonconformant", scope="project:P998")
    place(world, "COMPANY", hash=OLD, status="warning", scope="company")
    found = view(world)
    assert found.total == 1 and types(found)[THING] == TypeConformance(
        type=THING, total=1, ok=1, warning=0, nonconformant=0, stale=0
    )
    assert view(world, "P998").total == 1


def test_a_waived_record_counts_in_the_total_only(world: RegistryWorld) -> None:
    place(world, "W", status="waived", hash=hash_in_force(world))
    place(world, "K", status="ok", hash=hash_in_force(world))
    counted = types(view(world))[THING]
    assert (counted.total, counted.ok, counted.warning, counted.nonconformant) == (2, 1, 0, 0)


# -- the viewer (ADR-0016) ----------------------------------------------------------------------

KLASS_TABLE = "cur_zz_klass"
SECRET = ConfidentialSource(
    record_types=frozenset({THING, VAULT}),
    table=KLASS_TABLE,
    id_column="id",
    class_column="klass",
)


@pytest.fixture
def classes(world: RegistryWorld, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Records of ``THING`` and ``VAULT`` carry a class from a small table the test fills."""
    with open_uow(world.db) as uow:
        uow.conn().execute(text(f"CREATE TABLE {KLASS_TABLE} (id TEXT PRIMARY KEY, klass TEXT)"))
    monkeypatch.setattr(cf, "confidential_sources", lambda: [SECRET])
    return {}


def classed(world: RegistryWorld, klass: str, key: str, **fields: Any) -> str:
    record = place(world, key, **fields)
    with open_uow(world.db) as uow:
        uow.conn().execute(
            text(f"INSERT INTO {KLASS_TABLE} (id, klass) VALUES (:id, :k)"),
            {"id": record, "k": klass},
        )
    return record


def test_a_restricted_record_is_not_counted_for_the_lowest_viewer(
    world: RegistryWorld, classes: dict[str, Any]
) -> None:
    current = hash_in_force(world)
    for status in ("ok", "warning", "nonconformant"):
        classed(world, "internal", f"open-{status}", status=status, hash=current)
        classed(world, "restricted", f"secret-{status}", status=status, hash=OLD)
    classed(world, "restricted", "secret-only", type=VAULT, status="warning", hash=OLD)

    lowest = view(world)  # nobody set a viewer: the lowest clearance
    assert lowest.total == 3 and list(types(lowest)) == [THING]
    assert types(lowest)[THING] == TypeConformance(
        type=THING, total=3, ok=1, warning=1, nonconformant=1, stale=0
    )
    with cf.use_viewer(READER):
        assert view(world) == lowest
    with cf.use_viewer(CONTROLLER):
        every = view(world)
    assert every.total == 7 and list(types(every)) == [THING, VAULT]
    assert types(every)[THING] == TypeConformance(
        type=THING, total=6, ok=2, warning=2, nonconformant=2, stale=3
    )
    assert types(every)[VAULT].total == 1 and types(every)[VAULT].stale == 1


def test_the_viewer_counts_nothing_it_may_not_see_not_even_as_stale(
    world: RegistryWorld, classes: dict[str, Any]
) -> None:
    classed(world, "restricted", "secret", hash=None)
    assert view(world).total == 0 and view(world).by_type == []
    with cf.use_viewer(CONTROLLER):
        assert types(view(world))[THING].stale == 1


def test_a_record_with_no_class_row_is_hidden_from_everyone(
    world: RegistryWorld, classes: dict[str, Any]
) -> None:
    place(world, "rowless", hash=hash_in_force(world))
    with cf.use_viewer(CONTROLLER):
        assert view(world).total == 0


# -- records written by the real commands --------------------------------------------------------


def write(world: RegistryWorld, record: str, **values: Any) -> None:
    from tl_core.services.psets import SetPsetValues, handle_set_pset_values

    with open_uow(world.db) as uow:
        handle_set_pset_values(
            uow,
            SetPsetValues(
                actor=ADMIN,
                source="test",
                scope=SCOPE,
                stream_id=record,
                expected_version=uow.conn()
                .execute(text("SELECT version FROM cur_core_record WHERE id = :i"), {"i": record})
                .scalar_one(),
                pset="valve_data",
                layer="standard",
                values=values,
            ),
        )


def test_records_written_through_the_commands_are_read_as_they_were_stored(
    world: RegistryWorld,
) -> None:
    fine = make_record(world, "R-OK", {})
    bad = make_record(world, "R-BAD", {})
    untouched = make_record(world, "R-NEW", {})  # created with no pset write: no hash yet
    write(world, fine, manufacturer="Acme")
    write(world, bad, size_in=500)  # above the maximum of 144
    assert world.scalar("SELECT conformance FROM cur_core_record WHERE id = :i", i=bad) == (
        "nonconformant"
    )
    sql = "SELECT effective_schema_hash FROM cur_core_record WHERE id = :i"
    assert world.scalar(sql, i=untouched) is None
    found = types(view(world))[THING]
    assert found.total == 3 and found.stale == 1  # only the untouched record is stale
    assert found.ok + found.warning + found.nonconformant == 3
    assert (found.ok, found.warning, found.nonconformant) == (2, 0, 1)
    publish_version(world, "3.3.0")
    world.do(AdoptSchemaPackage, ADMIN, project=PROJECT, package=PKG, version="3.3.0")
    assert types(view(world))[THING].stale == 3  # the hash in force moved; none re-checked
