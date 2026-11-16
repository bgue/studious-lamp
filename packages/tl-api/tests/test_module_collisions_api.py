"""A module never shadows a core command or route; its routes are closed (SR-X4 F1, F2)."""

from __future__ import annotations

import importlib
import logging
import re
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import tl_api.commands as commands_module
from fastapi import APIRouter, Depends
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from harness import Harness
from tl_api.app import create_app
from tl_api.auth import Forbidden, guard
from tl_api.tokens import TokenStore
from tl_core import intent
from tl_core.modules import ModuleSpec, load_modules, resolve_hook, use_modules
from tl_core.services.commands import Command

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests" / "ext_demo"))

from load import ext_demo_spec  # noqa: E402  # pyright: ignore[reportMissingImports]


class ChangeSetting(Command):  # the name of a core command
    pass


CLASH_WORDS = {"X6Other": "user", "ChangeSetting": "user"}


class X6Fine(Command):
    pass


class X6Other(Command):
    pass


def _handler(uow: Any, command: Any) -> Any:
    raise AssertionError("never run")


def _spec(name: str, **hooks: Any) -> ModuleSpec:
    return ModuleSpec(
        name=name, record_types=frozenset({f"{name}.Thing"}), projectors=list, **hooks
    )


@pytest.fixture
def reimport() -> Iterator[Any]:
    bodies = set(commands_module.COMMAND_BODIES)
    registered = set(intent._REGISTERED)  # noqa: SLF001
    saved = dict(vars(commands_module))  # the objects other modules hold (COMMANDS, COMMAND_BODIES)

    def run() -> Any:
        return importlib.reload(commands_module)

    try:
        yield run
    finally:
        importlib.reload(commands_module)
        for name in set(commands_module.COMMAND_BODIES) - bodies:
            commands_module.COMMAND_BODIES.pop(name)
        intent._REGISTERED.intersection_update(registered)  # noqa: SLF001
        # back to the original objects, not the reloaded ones
        commands_module.__dict__.update(saved)


@pytest.fixture
def fakes() -> Iterator[None]:
    mods: dict[str, types.ModuleType] = {}

    def add(name: str, **attrs: Any) -> None:
        mod = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(mod, key, value)
        mods[name] = mod
        sys.modules[name] = mod

    row = types.SimpleNamespace
    add(
        "tl_mod_x6clash",
        COMMANDS=(
            row(model=X6Other, handler=_handler, access="user"),
            row(model=ChangeSetting, handler=_handler, access="user"),
        ),
    )
    add("tl_mod_x6fine", COMMANDS=(row(model=X6Fine, handler=_handler, access="user"),))

    def router(*paths: str, guarded: bool = True) -> APIRouter:
        rt = APIRouter()
        for i, path in enumerate(paths):
            if guarded:

                @rt.get(path, name=f"x6_{i}")
                def ok(actor: str = Depends(guard("x6.read"))) -> dict[str, str]:
                    return {"ok": "yes"}

            else:

                @rt.get(path, name=f"x6_{i}")
                def open_() -> dict[str, str]:
                    return {"ok": "open"}

        return rt

    add("tl_mod_x6a", R=router("/x6/fine", "/health"))
    add("tl_mod_x6b", R=router("/x6/fine2", "/records/{other}/history"))
    add("tl_mod_x6c", R=router("/x6/fine3"))
    add("tl_mod_x6d", R=router("/x6/fine3"))
    add("tl_mod_x6e", R=router("/x6/open", guarded=False))
    add("tl_mod_x6f", R=router("/projects/{project}/{any}/groups"))  # would catch a core literal
    try:
        yield
    finally:
        for name in mods:
            sys.modules.pop(name, None)


def _flat(routes: Any) -> list[Any]:
    found: list[Any] = []
    for route in routes:
        inner = getattr(route, "original_router", None)
        found.extend(_flat(inner.routes) if inner is not None else [route])
    return found


def _lines(app: Any) -> list[str]:
    return [
        f"{m} {r.path}"
        for r in _flat(app.routes)
        if isinstance(r, APIRoute)
        for m in sorted(r.methods or ())
    ]


def _app(h: Harness) -> Any:
    return create_app(h.backend, settings=h.settings, tokens=TokenStore(h.settings.tokens_path))


def test_a_module_command_named_like_a_core_command_is_refused_whole(
    fakes: None, reimport: Any, caplog: pytest.LogCaptureFixture
) -> None:
    core = {c.name: c for c in commands_module.COMMANDS if c.module is None}
    specs = [
        _spec("x6clash", commands="tl_mod_x6clash:COMMANDS", command_words=CLASH_WORDS),
        _spec("x6fine", commands="tl_mod_x6fine:COMMANDS", command_words={"X6Fine": "user"}),
    ]
    with caplog.at_level(logging.WARNING), use_modules(specs):
        reimport()
        rows = {c.name: c for c in commands_module.COMMANDS}
    assert rows["ChangeSetting"].handler is core["ChangeSetting"].handler  # the core row stays
    assert rows["ChangeSetting"].module is None
    assert rows["X6Fine"].module == "x6fine"
    assert "X6Other" not in rows  # the clashing module's other command is not served either
    messages = [r.getMessage() for r in caplog.records if r.name == "tl_core.modules"]
    assert messages == ["module 'x6clash': hook 'commands' cannot be resolved"]


def test_a_module_route_on_a_core_path_is_refused_whole_even_with_other_parameter_names(
    harness: Harness, fakes: None, caplog: pytest.LogCaptureFixture
) -> None:
    specs = [
        _spec("x6a", read_routers=("tl_mod_x6a:R",)),
        _spec("x6b", read_routers=("tl_mod_x6b:R",)),
        _spec("x6c", read_routers=("tl_mod_x6c:R",)),
    ]
    with caplog.at_level(logging.WARNING, logger="tl_api"), use_modules(specs):
        lines = _lines(_app(harness))
    assert "GET /x6/fine3" in lines
    assert "GET /x6/fine" not in lines and "GET /x6/fine2" not in lines
    assert lines.count("GET /health") == 1
    assert not any(line.startswith("GET /records/{other}/history") for line in lines)
    assert [r.getMessage() for r in caplog.records if r.name == "tl_api"] == [
        "module 'x6a': hook 'read_routers' cannot be resolved",
        "module 'x6b': hook 'read_routers' cannot be resolved",
    ]


def test_a_module_route_path_an_earlier_module_has_is_refused(
    harness: Harness, fakes: None
) -> None:
    specs = [
        _spec("x6c", read_routers=("tl_mod_x6c:R",)),
        _spec("x6d", read_routers=("tl_mod_x6d:R",)),
    ]
    with use_modules(specs):
        lines = _lines(_app(harness))
    assert lines.count("GET /x6/fine3") == 1


def test_a_module_route_without_a_guard_is_refused_at_mount(
    harness: Harness, fakes: None, caplog: pytest.LogCaptureFixture
) -> None:
    specs = [_spec("x6e", read_routers=("tl_mod_x6e:R",))]
    with caplog.at_level(logging.WARNING, logger="tl_api"), use_modules(specs):
        lines = _lines(_app(harness))
    assert "GET /x6/open" not in lines
    assert [r.getMessage() for r in caplog.records if r.name == "tl_api"] == [
        "module 'x6e': hook 'read_routers' cannot be resolved"
    ]


def _walk_module_routes_denied(h: Harness, specs: list[ModuleSpec]) -> None:
    """Every module route answers 401/403 under a deny-all authorizer, before its body runs."""
    seen: list[str] = []

    def deny_all(actor: str, action: str, resource: str) -> None:
        seen.append(action)
        raise Forbidden("closed")

    routes = [
        route
        for spec in specs
        for router in resolve_hook(spec, "read_routers")
        for route in _flat(router.routes)  # type: ignore[attr-defined]
        if isinstance(route, APIRoute)
    ]
    assert routes, "the walk found no module route"
    with use_modules(specs):
        app = create_app(
            h.backend,
            settings=h.settings,
            tokens=TokenStore(h.settings.tokens_path),
            authorize_hook=deny_all,
        )

    client = TestClient(app, raise_server_exceptions=False)
    client.headers.update(h.headers())
    for route in routes:
        url = re.sub(r"\{[^}]*\}", "x", route.path)
        for method in sorted(route.methods or ()):
            seen.clear()
            response = client.request(method, url, json={} if method != "GET" else None)
            assert response.status_code in (401, 403), (method, route.path, response.status_code)
    client.close()


def test_every_installed_module_route_is_denied_by_a_deny_all_authorizer(harness: Harness) -> None:
    _walk_module_routes_denied(harness, list(load_modules()))


def test_every_ext_demo_route_is_denied_by_a_deny_all_authorizer(harness: Harness) -> None:
    _walk_module_routes_denied(harness, [ext_demo_spec()])


def test_a_core_literal_path_beats_a_module_parameter_path_that_could_match_it(
    harness: Harness, fakes: None
) -> None:
    specs = [_spec("x6f", read_routers=("tl_mod_x6f:R",))]
    with use_modules(specs):
        app = _app(harness)
    client = TestClient(app, raise_server_exceptions=False)
    client.headers.update(harness.headers())
    core = client.get("/projects/P123/constraints/groups")
    assert core.json() != {"ok": "yes"}  # the core route answered, not the module's
    assert client.get("/projects/P123/other/groups").json() == {"ok": "yes"}
    client.close()
