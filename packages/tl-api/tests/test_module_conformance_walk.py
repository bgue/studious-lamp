"""The confidentiality walk enumerates a module added through ``use_modules`` (P2-X4 S4, test 9).

A module that is not one of the installed ones brings one read route. The walk's own enumerator
(``get_routes``) must list it, and the walk's own test must fail on a route whose path argument it
cannot fill, and pass on one it can.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator

import pytest
import test_confidentiality_walk as walk
from fastapi import APIRouter
from harness import Harness
from test_confidentiality_walk import Seed, harness, seeded, week_seeded  # noqa: F401
from tl_api.app import create_app
from tl_api.tokens import TokenStore
from tl_core.modules import ModuleSpec, load_modules, use_modules

UNFILLABLE = "/0x4walk/{mystery}"
FILLABLE = "/0x4walk/{key}"


@pytest.fixture
def fake_package() -> Iterator[None]:
    package = types.ModuleType("tl_mod_x4walk")

    def mystery(mystery: str) -> dict[str, str]:  # the walk has no values for this name
        return {"ok": mystery}

    def keyed(key: str) -> dict[str, str]:
        return {"ok": key}

    package.UNFILLABLE_ROUTER = APIRouter()  # type: ignore[attr-defined]
    package.UNFILLABLE_ROUTER.add_api_route(  # type: ignore[attr-defined]
        UNFILLABLE, mystery, methods=["GET"]
    )
    package.FILLABLE_ROUTER = APIRouter()  # type: ignore[attr-defined]
    package.FILLABLE_ROUTER.add_api_route(FILLABLE, keyed, methods=["GET"])  # type: ignore[attr-defined]
    sys.modules["tl_mod_x4walk"] = package
    try:
        yield
    finally:
        sys.modules.pop("tl_mod_x4walk", None)


def spec_with(router: str) -> ModuleSpec:
    return ModuleSpec(
        name="x4walk",
        record_types=frozenset({"x4walk.Thing"}),
        projectors=list,
        read_routers=(f"tl_mod_x4walk:{router}",),
    )


def rebuilt_paths(h: Harness) -> list[str]:
    """Rebuild the app inside ``use_modules``; the walk's own enumerator lists what it serves."""
    h.app = create_app(
        h.backend,
        settings=h.settings,
        tokens=TokenStore(h.settings.tokens_path),
        files_service=h.service,
        object_store=h.store,
    )
    return [path for path, _, _ in walk.get_routes(h)]


def test_the_walk_lists_an_added_module_route_and_fails_on_one_it_cannot_fill(
    harness: Harness,  # noqa: F811
    week_seeded: Seed,  # noqa: F811
    fake_package: None,
) -> None:
    with use_modules([*load_modules(), spec_with("UNFILLABLE_ROUTER")]):
        assert UNFILLABLE in rebuilt_paths(harness)
        with pytest.raises(AssertionError, match="add values for the path parameter 'mystery'"):
            walk.test_no_get_route_shows_a_reader_what_they_may_not_read(
                harness, week_seeded, "bob"
            )


def test_the_walk_lists_an_added_module_route_it_can_fill_and_passes_it(
    harness: Harness,  # noqa: F811
    week_seeded: Seed,  # noqa: F811
    fake_package: None,
) -> None:
    with use_modules([*load_modules(), spec_with("FILLABLE_ROUTER")]):
        paths = rebuilt_paths(harness)
        assert FILLABLE in paths and UNFILLABLE not in paths
        walk.test_no_get_route_shows_a_reader_what_they_may_not_read(harness, week_seeded, "bob")
