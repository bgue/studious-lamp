"""The isolation read routes and the gas test route of the permits module (P2-PTW-T07b).

Four GET routes on top of the T07 harness: ``/permits/isolations`` (list),
``/permits/isolations/export`` (csv or jsonl), ``/permits/isolations/{key}`` (detail) and
``/permits/{key}/gas-tests``. The ledger is the one ``test_api_permits.py`` builds (its ``seed``),
extended here with isolations and gas tests made by real commands. Readers: no token (401), the
lowest clearance (``uma``), a cleared reader (``dora``) and an agent (``bot``). The 403 branch is
tested by refusing one reader at the one ``require_word`` call, as T07 does; no view function may
run.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from harness import Harness
from test_api_permits import MISSING, NOT_FOUND, Rig, Seeded, seed
from tl_core.auth import module_roles
from tl_core.auth.errors import ForbiddenError
from tl_mod_permits import iso_views
from tl_mod_permits import routes as permit_routes
from tl_mod_permits import views as permit_views

NO_ISOLATION = "no isolation"
MISSING_ISOLATION = "P123-ISL-9999"
LIST = "/permits/isolations"
EXPORT = "/permits/isolations/export"
GAS = "/permits/{key}/gas-tests"
POINT = {
    "point_text": "Pump P-101 breaker",
    "energy": "electrical",
    "method": "Lock and tag",
    "lock_number": "L-12",
    "tag_number": "T-12",
}


def extend(s: Seeded) -> None:
    """Isolations and gas tests on top of the T07 ledger, each made by a real command."""
    world = s.world
    secret = s.ids["secret"]
    active = s.ids["active"]
    s.ids["iso_verified"] = str(world.call("uma", "ApplyIsolation", **POINT).stream_id)
    world.call("sue", "VerifyIsolation", isolation=s.ids["iso_verified"])
    approved = world.approved("general")  # an Approved permit takes a link; an Active one does not
    world.call("uma", "LinkIsolation", permit=approved, isolation=s.ids["iso_verified"])
    s.ids["iso_applied"] = str(
        world.call("rob", "ApplyIsolation", **{**POINT, "energy": "process"}).stream_id
    )
    s.ids["iso_secret"] = str(
        world.call("dora", "ApplyIsolation", **POINT, point_record_id=secret).stream_id
    )
    s.ids["iso_removed"] = str(
        world.call("uma", "ApplyIsolation", **{**POINT, "energy": "other"}).stream_id
    )
    world.call("uma", "RemoveIsolation", isolation=s.ids["iso_removed"])
    now = datetime.now(UTC)  # the handlers read the real clock here: a test is dated before it
    for minutes, co in ((-30, "2"), (-20, "30"), (-10, "3")):
        world.call(
            "uma",
            "RecordGasTest",
            permit=active,
            instrument_text="MX6",
            o2_pct="20.9",
            co_ppm=co,
            taken_at=now + timedelta(minutes=minutes),
        )
    world.call(
        "dora",
        "RecordGasTest",
        permit=s.ids["from_secret"],
        instrument_text="MX6",
        o2_pct="21",
        taken_at=now,
    )
    for name in ("iso_verified", "iso_applied", "iso_secret", "iso_removed"):
        s.keys[name] = str(
            world.scalar("SELECT key FROM cur_core_record WHERE id = :id", id=s.ids[name])
        )


@pytest.fixture(scope="module")
def iso(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Rig]:
    h = Harness.build(tmp_path_factory.mktemp("api-permit-iso"))
    try:
        s = seed(h)
        extend(s)
        yield Rig(s)
    finally:
        h.close()


def _paths(rig: Rig) -> list[tuple[str, dict[str, Any]]]:
    """The four new routes, each with one reachable key."""
    permit = rig.s.keys["active"]
    return [
        (LIST, {}),
        (EXPORT, {"format": "csv"}),
        (f"/permits/isolations/{rig.s.keys['iso_verified']}", {}),
        (f"/permits/{permit}/gas-tests", {}),
    ]


# --- the readers ---------------------------------------------------------------------------------


def test_no_token_is_401_on_every_new_route(iso: Rig) -> None:
    for path, params in _paths(iso):
        assert iso.get(None, path, **params).status_code == 401, path


def test_the_lowest_clearance_reader_gets_no_restricted_point(iso: Rig) -> None:
    secret = iso.s.keys["iso_secret"]
    lowest = iso.ok("uma", LIST)
    cleared = iso.ok("dora", LIST)
    assert secret not in [r["key"] for r in lowest["rows"]]
    assert secret in [r["key"] for r in cleared["rows"]]
    assert lowest["total"] == len(lowest["rows"])
    assert cleared["total"] == lowest["total"] + 1


def test_the_restricted_point_is_not_in_the_export(iso: Rig) -> None:
    secret = iso.s.keys["iso_secret"]
    lowest = iso.get("uma", EXPORT, format="csv").text
    cleared = iso.get("dora", EXPORT, format="csv").text
    assert secret not in lowest
    assert secret in cleared


def test_a_restricted_isolation_answers_as_an_unknown_key_on_the_detail_route(iso: Rig) -> None:
    hidden = iso.get("uma", f"/permits/isolations/{iso.s.keys['iso_secret']}")
    missing = iso.get("uma", f"/permits/isolations/{MISSING_ISOLATION}")
    assert hidden.status_code == missing.status_code == 404
    assert hidden.json() == missing.json()
    assert "record_not_found" in hidden.text
    assert NO_ISOLATION in hidden.text
    assert iso.s.keys["iso_secret"] not in hidden.text
    cleared = iso.ok("dora", f"/permits/isolations/{iso.s.keys['iso_secret']}")
    assert cleared["row"]["key"] == iso.s.keys["iso_secret"]


def test_a_hidden_permit_has_no_gas_tests_as_an_unknown_permit(iso: Rig) -> None:
    hidden = iso.get("uma", f"/permits/{iso.s.keys['from_secret']}/gas-tests")
    missing = iso.get("uma", f"/permits/{MISSING}/gas-tests")
    assert hidden.status_code == missing.status_code == 404
    assert hidden.json() == missing.json()
    assert NOT_FOUND in hidden.text
    assert iso.s.keys["from_secret"] not in hidden.text
    assert len(iso.ok("dora", f"/permits/{iso.s.keys['from_secret']}/gas-tests")) == 1


def test_the_agent_reader_gets_no_restricted_point(iso: Rig) -> None:
    """``document.read`` is open to agents (as the T07 list is), so the agent reads the rows the
    lowest viewer reads: the restricted point is left out and its detail is the unknown answer."""
    secret = iso.s.keys["iso_secret"]
    assert secret not in [r["key"] for r in iso.ok("bot", LIST)["rows"]]
    assert iso.get("bot", f"/permits/isolations/{secret}").status_code == 404


# --- the view word is checked before any read -----------------------------------------------------


def test_the_view_word_is_checked_before_any_read(
    iso: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_require_word = module_roles.require_word

    def refuse_uma(conn: Any, holder: Any, **kwargs: Any) -> None:
        if holder.actor != "user:uma":
            return real_require_word(conn, holder, **kwargs)
        raise ForbiddenError(
            f"{kwargs['what']} needs the {kwargs['word']} access word for "
            f"{kwargs['module']} on {kwargs['scope']}"
        )

    looked: list[str] = []

    def spy(name: str) -> Any:
        def fail(*args: Any, **kwargs: Any) -> Any:
            looked.append(name)
            raise AssertionError(f"{name} ran without the view word")

        return fail

    monkeypatch.setattr(permit_routes, "require_word", refuse_uma)
    for name in ("isolation_list", "isolation_detail", "isolation_export_rows", "gas_tests_for"):
        monkeypatch.setattr(iso_views, name, spy(name))
    monkeypatch.setattr(permit_views, "permit_detail", spy("permit_detail"))
    responses = [
        iso.get("uma", LIST),
        iso.get("uma", EXPORT, format="csv"),
        iso.get("uma", f"/permits/isolations/{iso.s.keys['iso_verified']}"),
        iso.get("uma", f"/permits/{iso.s.keys['active']}/gas-tests"),
    ]
    for response in responses:
        assert response.status_code == 403, response.text
        assert response.json()["error"] == "forbidden"
        assert "permits.view" in response.text
    assert looked == []


# --- the paths, the exports and the empty answer -------------------------------------------------


def test_the_fixed_isolation_paths_are_not_taken_for_a_key(iso: Rig) -> None:
    assert "rows" in iso.ok("uma", LIST)
    assert (
        iso.get("uma", EXPORT, format="jsonl")
        .headers["content-type"]
        .startswith("application/x-ndjson")
    )


def test_the_export_rows_equal_the_list_rows(iso: Rig) -> None:
    listed = [r["key"] for r in iso.ok("uma", LIST, limit=500)["rows"]]
    from_csv = list(csv.DictReader(io.StringIO(iso.get("uma", EXPORT, format="csv").text)))
    jsonl = iso.get("uma", EXPORT, format="jsonl")
    assert jsonl.status_code == 200
    from_jsonl = [json.loads(line) for line in jsonl.text.splitlines() if line]
    assert [row["number"] for row in from_csv] == listed
    assert [row["number"] for row in from_jsonl] == listed


def test_the_export_filters_reach_the_list_view(iso: Rig) -> None:
    listed = [r["key"] for r in iso.ok("uma", LIST, state="Applied", energy="process")["rows"]]
    text = iso.get("uma", EXPORT, format="csv", state="Applied", energy="process").text
    rows = list(csv.DictReader(io.StringIO(text)))
    assert [row["number"] for row in rows] == listed == [iso.s.keys["iso_applied"]]


def test_a_visible_permit_with_no_gas_test_is_an_empty_list(iso: Rig) -> None:
    response = iso.get("uma", f"/permits/{iso.s.keys['lapsed']}/gas-tests")
    assert response.status_code == 200
    assert response.json() == []


def test_gas_tests_are_listed_newest_first_and_exported(iso: Rig) -> None:
    path = f"/permits/{iso.s.keys['active']}/gas-tests"
    listed = iso.ok("uma", path)
    assert len(listed) == 3
    taken = [row["taken_at"] for row in listed]
    assert taken == sorted(taken, reverse=True)
    text = iso.get("uma", path, format="csv")
    assert text.status_code == 200
    assert text.headers["content-type"].startswith("text/csv")
    assert len(list(csv.DictReader(io.StringIO(text.text)))) == 3
    lines = iso.get("uma", path, format="jsonl").text.splitlines()
    assert len(lines) == 3


# --- bad values ----------------------------------------------------------------------------------


def test_bad_isolation_state_energy_format_and_limit_are_422(iso: Rig) -> None:
    assert iso.get("uma", LIST, state="Active").status_code == 422
    assert iso.get("uma", LIST, state="Bogus").status_code == 422
    assert iso.get("uma", LIST, energy="gas").status_code == 422
    assert iso.get("uma", LIST, limit=0).status_code == 422
    assert iso.get("uma", LIST, limit=501).status_code == 422
    assert iso.get("uma", EXPORT, format="xml").status_code == 422
    assert iso.get("uma", EXPORT, format="csv", state="Bogus").status_code == 422
    gas = f"/permits/{iso.s.keys['active']}/gas-tests"
    assert iso.get("uma", gas, format="xml").status_code == 422


# --- the routes are declared and documented ------------------------------------------------------


def test_the_new_routes_are_in_the_openapi_document(iso: Rig) -> None:
    paths = iso.h.app.openapi()["paths"]
    assert paths["/permits/isolations"]["get"]["operationId"] == "list_isolations"
    assert paths["/permits/isolations/export"]["get"]["operationId"] == "export_isolations"
    assert paths["/permits/isolations/{key}"]["get"]["operationId"] == "get_isolation"
    assert paths["/permits/{key}/gas-tests"]["get"]["operationId"] == "list_gas_tests"
    assert paths["/permits/{key}"]["get"]["operationId"] == "get_permit"
