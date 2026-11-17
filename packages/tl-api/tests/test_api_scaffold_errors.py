"""The scaffold refusals at the API door answer with their own stable code and text (P2-I4B-T09c).

The rig, the sign-in and the ledger are the scaffold command tests' own (imported, not copied).
Each refusal is a ``ScaffoldError`` subclass with a row in ``tl_api.errors``; none answers 500.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterator

import pytest
from harness import Harness
from test_api_scaffold_commands import Rig, seed
from tl_api.errors import ERROR_TABLE
from tl_core.services.errors import ServiceError
from tl_mod_scaffold import errors as scf

OWN_CLASSES = {
    "ScaffoldError",
    "ScaffoldScopeError",
    "ScaffoldRuleError",
    "ScaffoldStateError",
    "DismantleRefused",
    "StaleVersionError",
}


@pytest.fixture(scope="module")
def rig(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Rig]:
    h = Harness.build(tmp_path_factory.mktemp("api-scaffold-errors"))
    try:
        yield Rig(seed(h))
    finally:
        h.close()


def test_a_second_register_on_one_request_is_422_scaffold_rule_with_text(rig: Rig) -> None:
    request = rig.s.world.request()
    first = rig.post("uma", "RegisterScaffold", {"request_id": request, "title": "First"})
    assert first.status_code == 200, first.text
    second = rig.post("uma", "RegisterScaffold", {"request_id": request, "title": "Second"})
    assert second.status_code == 422, second.text
    body = second.json()
    assert body["error"] == "scaffold_rule"
    assert isinstance(body["message"], str) and body["message"]


def test_release_on_an_erecting_scaffold_is_409_scaffold_state_with_text(rig: Rig) -> None:
    made = rig.s.world.register()
    rig.s.world.advance(made, "Erecting")
    before = rig.s.world.count()
    response = rig.post("uma", "ReleaseScaffold", {"scaffold": made})
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"] == "scaffold_state"
    assert isinstance(body["message"], str) and body["message"]
    assert rig.s.world.count() == before


def test_dismantle_with_a_stale_expected_version_is_409_scaffold_stale_version(rig: Rig) -> None:
    made = rig.s.world.register()
    rig.s.world.advance(made, "In Use")
    stale = rig.s.world.version(made) + 1
    before = rig.s.world.count()
    response = rig.post(
        "uma",
        "DismantleScaffold",
        {"scaffold": made, "reason": "end of pour", "expected_version": stale},
    )
    assert response.status_code == 409, response.text
    assert response.json()["error"] == "scaffold_stale_version"
    assert rig.s.world.count() == before


def test_every_scaffold_error_class_has_its_own_row() -> None:
    classes = {
        obj
        for _, obj in inspect.getmembers(scf, inspect.isclass)
        if obj.__module__ == scf.__name__ and issubclass(obj, ServiceError)
    }
    assert {c.__name__ for c in classes} == OWN_CLASSES
    mapped = {spec.exc for spec in ERROR_TABLE}
    assert classes - mapped == set(), "map the scaffold error in tl_api/errors.py"
