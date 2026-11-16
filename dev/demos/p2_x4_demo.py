"""Driver for dev/demos/p2_x4_demo.py: the scaffolded module and its failing hook (P2-X4 T05a).

Clause 1 imports the module that `tl new module probe` wrote into P2_X4_WORKDIR and checks its
spec and hooks. Clause 2 installs the module for one block and checks its route, its agent tool
and its CLI group. Clause 6 installs a fake module whose `commands` hook cannot resolve and
checks that the platform reports it and carries on. Each mode prints ``ok`` lines, or ``FAIL``
and exits 1. Values pass to the shell through the environment (TL_DB, P2_X4_WORKDIR).
"""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
from pathlib import Path
from typing import Any, NoReturn

import typer
from tl_adapters.backend import open_backend
from tl_adapters.db import as_target, make_uow_factory
from tl_cli.main import _add_module_groups  # pyright: ignore[reportPrivateUsage]
from tl_core.modules import (
    ModuleSpec,
    hook_failures,
    load_modules,
    module_commands,
    resolve_hook,
    use_modules,
)
from tl_mcp.server import build_server
from typer.testing import CliRunner

PACKAGE = "tl_mod_probe"
GHOST = "ghost"
MODES = ("clause1", "clause2", "clause6")
REPO = Path(__file__).resolve().parents[2]
PLATFORM_SRC = ("packages/tl-api/src", "packages/tl-mcp/src", "packages/tl-cli/src")


def ok(text_: str) -> None:
    print(f"ok {text_}", flush=True)


def miss(what: str) -> NoReturn:
    print(f"FAIL {what}", flush=True)
    raise SystemExit(1)


def check(condition: bool, what: str) -> None:
    if not condition:
        miss(what)


def probe_spec() -> ModuleSpec:
    """The spec of the module `tl new module probe` wrote under P2_X4_WORKDIR/scaf."""
    workdir = Path(os.environ["P2_X4_WORKDIR"])
    src = workdir / "scaf" / "packages" / "tl-modules" / "probe" / "src"
    check(src.is_dir(), f"no scaffolded probe module under {workdir / 'scaf'}")
    sys.path.insert(0, str(src))
    module = importlib.import_module(f"{PACKAGE}.module")
    spec: ModuleSpec = module.spec()
    return spec


def allow_all(who: str, action: str, resource: str) -> None:
    """The authorize hook of the agent server in clause 2: every action is allowed."""


def app_paths(target: Any) -> list[str]:
    """The OpenAPI paths of the app over ``target``; the app is built inside the caller's block."""
    # The command table is made once per import of tl_api.commands: reload it in the block.
    importlib.reload(importlib.import_module("tl_api.commands"))
    from tl_api.app import create_app

    app = create_app(open_backend(target))
    return list(app.openapi()["paths"])


def clause1() -> None:
    spec = probe_spec()
    check(spec.name == "probe", f"the spec is named {spec.name!r}, not 'probe'")
    ok(f"spec name {spec.name}")
    check(resolve_hook(spec, "commands") == (), "the scaffold's COMMANDS table has rows")
    ok("commands none: the scaffold table is empty")
    check(spec.read_routers == (f"{PACKAGE}.routes:router",), f"read_routers {spec.read_routers}")
    check(spec.tools == (f"{PACKAGE}.tools:register_tools",), f"tools {spec.tools}")
    check(spec.cli_groups == (f"{PACKAGE}.cli:probe_app",), f"cli_groups {spec.cli_groups}")
    ok("hooks read_routers tools cli_groups name the package")
    for kind in ("read_routers", "tools", "cli_groups"):
        check(len(resolve_hook(spec, kind)) == 1, f"hook {kind} did not resolve to one object")
    ok("hooks resolve through resolve_hook")
    for root in PLATFORM_SRC:
        for path in (REPO / root).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            check(f"{PACKAGE}" not in text, f"{path} names the probe package")
            check('"probe"' not in text, f"{path} names the probe module")
    ok("no platform source names the probe module (tl-api, tl-mcp, tl-cli)")


def clause2() -> None:
    spec = probe_spec()
    target = as_target(os.environ["TL_DB"])
    with use_modules([*load_modules(), spec]):
        check(hook_failures() == {}, f"hook failures with probe installed: {hook_failures()}")
        ok("hook_failures empty with the probe module installed")
        paths = app_paths(target)
        check("/modules/probe/ping" in paths, "no /modules/probe/ping path in openapi")
        ok("openapi has /modules/probe/ping")
        factory = make_uow_factory(target)
        server = build_server(factory, actor="agent:probe", authorize_hook=allow_all)
        names = [tool.name for tool in asyncio.run(server.list_tools())]
        check("probe_ping" in names, f"no probe_ping tool in {names}")
        ok("agent server lists probe_ping")
        root = typer.Typer()
        root.command("other")(lambda: None)
        _add_module_groups(root, [spec])
        result = CliRunner().invoke(root, ["probe", "ping"])
        check(result.exit_code == 0, f"probe ping exited {result.exit_code}")
        check(result.stdout == "probe\n", f"probe ping printed {result.stdout!r}")
        ok("cli probe ping prints probe and exits 0")


def clause6() -> None:
    target = as_target(os.environ["TL_DB"])
    ghost = ModuleSpec(
        name=GHOST,
        record_types=frozenset(),
        projectors=list,
        commands=f"tl_mod_{GHOST}.commands:COMMANDS",
    )
    real = [row.name for row in module_commands()]
    with use_modules([*load_modules()]):
        without = app_paths(target)
    with use_modules([*load_modules(), ghost]):
        failures = hook_failures()
        expected = {GHOST: "module 'ghost': hook 'commands' cannot be resolved"}
        check(failures == expected, f"hook failures {failures}")
        ok(f"hook_failures names the ghost: {failures[GHOST]}")
        check(f"tl_mod_{GHOST}" not in failures[GHOST], "the failure text names the ghost package")
        ok("the failure text names no ghost package")
        names = [row.name for row in module_commands()]
        check(names == real, "module_commands changed with the ghost installed")
        ok(f"module_commands unchanged: {len(names)} rows")
        with_ghost = app_paths(target)
        check(len(with_ghost) == len(without), "the openapi path count changed with the ghost")
        ok(f"create_app builds with the ghost: {len(with_ghost)} paths, as without it")


def main(argv: list[str]) -> None:
    mode = argv[1] if len(argv) > 1 else ""
    if mode not in MODES or len(argv) != 2:
        raise SystemExit(f"usage: p2_x4_demo.py {{{'|'.join(MODES)}}}")
    globals()[mode]()


if __name__ == "__main__":
    main(sys.argv)
