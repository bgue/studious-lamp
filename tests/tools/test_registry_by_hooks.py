"""The four registries build from the module hooks and hold no hand registration (P2-X4 D10).

``tl_api/commands.py``, ``tl_api/app.py``, ``tl_mcp/server.py`` and ``tl_cli/main.py`` are read as
text (``ast``, no import of the app). A module's command table, read router, tool registrar or CLI
group that a spec's hook supplies must not also be imported or registered by hand there. A line may
be exempt only if ``prehook_lines.toml`` lists it; an entry that exempts nothing is stale.
"""

from __future__ import annotations

import ast
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from tl_core.modules import load_modules

ROOT = Path(__file__).resolve().parents[2]
REGISTRIES = (
    "packages/tl-api/src/tl_api/commands.py",
    "packages/tl-api/src/tl_api/app.py",
    "packages/tl-mcp/src/tl_mcp/server.py",
    "packages/tl-cli/src/tl_cli/main.py",
)
PREHOOK = Path(__file__).with_name("prehook_lines.toml")
REGISTER_METHODS = frozenset({"include_router", "add_typer"})


class Hooks(NamedTuple):
    commands: frozenset[str]  # "pkg.mod:NAME" of every commands hook
    targets: frozenset[str]  # "pkg.mod:attr" of every router, tool registrar and CLI group


def hooks_of_modules() -> Hooks:
    commands: set[str] = set()
    targets: set[str] = set()
    for spec in load_modules():
        if spec.commands:
            commands.add(spec.commands)
        for refs in (spec.read_routers, spec.tools, spec.cli_groups):
            targets.update(refs)
    return Hooks(frozenset(commands), frozenset(targets))


@dataclass(frozen=True)
class Violation:
    line: int
    what: str
    names: frozenset[str]  # what a prehook entry may call this line

    def __str__(self) -> str:
        return f"line {self.line}: {self.what}"


class _Alias(NamedTuple):
    module: str  # the dotted path the local name stands for, as a module
    parent: str  # for ``from a.b import c``: ``a.b`` (else empty)
    attr: str  # ``c`` (else empty)


def _aliases(tree: ast.AST) -> dict[str, _Alias]:
    found: dict[str, _Alias] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for item in node.names:
                found[item.asname or item.name] = _Alias(
                    f"{node.module}.{item.name}", node.module, item.name
                )
        elif isinstance(node, ast.Import):
            for item in node.names:
                found[item.asname or item.name.split(".")[0]] = _Alias(item.name, "", "")
    return found


def _loop_names(tree: ast.AST) -> dict[str, list[str]]:
    """``for module in (a, b, c)``: the loop variable stands for each of a, b and c."""
    found: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.For)
            and isinstance(node.target, ast.Name)
            and isinstance(node.iter, ast.Tuple | ast.List)
        ):
            names = [e.id for e in node.iter.elts if isinstance(e, ast.Name)]
            found.setdefault(node.target.id, []).extend(names)
    return found


def scan_source(source: str, hooks: Hooks) -> list[Violation]:
    """Every line of ``source`` that imports a module command table or registers by hand what a
    hook supplies. Each carries the names a ``prehook_lines.toml`` entry may use for it."""
    tree = ast.parse(source)
    aliases = _aliases(tree)
    loops = _loop_names(tree)
    command_modules = {ref.split(":", 1)[0] for ref in hooks.commands}
    command_names = {ref.split(":", 1)[1] for ref in hooks.commands}
    found: list[Violation] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("tl_mod_"):
            for item in node.names:
                table = (
                    item.name in command_names
                    or item.name.endswith("COMMANDS")
                    or node.module in command_modules
                    or node.module.endswith(".commands")
                )
                if table:
                    found.append(
                        Violation(
                            node.lineno,
                            f"imports the command table {item.name} of {node.module}",
                            frozenset({node.module, item.name, f"{node.module}:{item.name}"}),
                        )
                    )
        elif isinstance(node, ast.Import):
            for item in node.names:
                if item.name.startswith("tl_mod_") and item.name.endswith(".commands"):
                    found.append(
                        Violation(
                            node.lineno,
                            f"imports the command module {item.name}",
                            frozenset({item.name}),
                        )
                    )
        elif isinstance(node, ast.Call):
            found += _registration(node, aliases, loops, hooks)
    return sorted(found, key=lambda v: (v.line, v.what))


def _resolve(
    name: str, aliases: Mapping[str, _Alias], loops: Mapping[str, list[str]]
) -> list[_Alias]:
    stand_for = loops.get(name, [name])
    return [aliases[n] for n in stand_for if n in aliases]


def _registration(
    call: ast.Call,
    aliases: Mapping[str, _Alias],
    loops: Mapping[str, list[str]],
    hooks: Hooks,
) -> list[Violation]:
    found: list[Violation] = []
    func = call.func
    # ``register_x(server, ctx)``: a tool registrar the hooks already name
    if isinstance(func, ast.Name) and func.id in aliases:
        alias = aliases[func.id]
        ref = f"{alias.parent}:{alias.attr}"
        if ref in hooks.targets:
            found.append(
                Violation(
                    call.lineno,
                    f"calls {func.id}, which a module hook supplies",
                    frozenset({alias.parent, func.id, ref}),
                )
            )
    # ``app.include_router(x.router)`` and ``app.add_typer(x.app, name=...)``
    if isinstance(func, ast.Attribute) and func.attr in REGISTER_METHODS and call.args:
        arg = call.args[0]
        candidates: list[tuple[str, _Alias, str]] = []
        if isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name):
            for alias in _resolve(arg.value.id, aliases, loops):
                candidates.append((arg.value.id, alias, arg.attr))
        elif isinstance(arg, ast.Name) and arg.id in aliases:
            alias = aliases[arg.id]
            candidates.append((arg.id, _Alias(alias.parent, "", ""), alias.attr))
        for local, alias, attr in candidates:
            ref = f"{alias.module}:{attr}"
            if ref in hooks.targets:
                found.append(
                    Violation(
                        call.lineno,
                        f"{func.attr}({local}.{attr}) registers what a module hook supplies",
                        frozenset({alias.module, local, ref}),
                    )
                )
    return found


def load_prehook(path: Path = PREHOOK) -> dict[str, list[str]]:
    return {k: list(v) for k, v in tomllib.loads(path.read_text()).get("lines", {}).items()}


def drift_problems(
    sources: Mapping[str, str], hooks: Hooks, exempt: Mapping[str, Sequence[str]]
) -> list[str]:
    """Violations not exempted, plus every exemption that exempts nothing (stale)."""
    problems: list[str] = []
    for path in sorted(set(exempt) - set(sources)):
        problems.append(f"{path}: prehook_lines.toml names a file that is not a registry")
    for path, source in sources.items():
        allowed = list(exempt.get(path, ()))
        used: set[str] = set()
        for violation in scan_source(source, hooks):
            hit = violation.names & set(allowed)
            if hit:
                used |= hit
            else:
                problems.append(f"{path}: {violation}")
        problems += [f"{path}: stale prehook entry {e!r}" for e in allowed if e not in used]
    return problems


def read_registries() -> dict[str, str]:
    return {path: (ROOT / path).read_text() for path in REGISTRIES}


# --- the tests ---------------------------------------------------------------------------------

HOOKS = Hooks(
    commands=frozenset({"tl_mod_cor.commands:API_COMMANDS"}),
    targets=frozenset(
        {
            "tl_api.routes.cor:router",
            "tl_mcp.cor_tools:register_cor_tools",
            "tl_cli.cor:app",
            "tl_cli.cor:wo_app",
        }
    ),
)


def test_the_four_registries_hold_no_hand_registration_of_what_a_hook_supplies() -> None:
    hooks = hooks_of_modules()
    assert hooks.targets and hooks.commands  # the hooks were read
    assert drift_problems(read_registries(), hooks, load_prehook()) == []


def test_the_prehook_file_starts_with_no_exemption_and_names_only_registries() -> None:
    assert set(load_prehook()) <= set(REGISTRIES)


def test_the_scan_sees_a_hand_registered_router_in_a_loop_and_alone() -> None:
    loop = "from tl_api.routes import cor\nfor m in (cor,):\n    app.include_router(m.router)\n"
    alone = "from tl_api.routes import cor\napp.include_router(cor.router)\n"
    renamed = "from tl_api.routes.cor import router as r\napp.include_router(r)\n"
    for source in (loop, alone, renamed):
        assert len(scan_source(source, HOOKS)) == 1, source


def test_the_scan_sees_a_hand_registered_tool_registrar_and_cli_group() -> None:
    tool = "from tl_mcp.cor_tools import register_cor_tools\nregister_cor_tools(server, ctx)\n"
    group = "from tl_cli import cor\napp.add_typer(cor.app, name='cor')\n"
    other = "from tl_cli import cor\napp.add_typer(cor.wo_app, name='wo')\n"
    assert len(scan_source(tool, HOOKS)) == len(scan_source(group, HOOKS)) == 1
    assert len(scan_source(other, HOOKS)) == 1


def test_the_scan_sees_an_imported_module_command_table() -> None:
    by_name = "from tl_mod_cor.commands import API_COMMANDS\n"
    by_suffix = "from tl_mod_other.stuff import OTHER_COMMANDS\n"
    plain = "import tl_mod_other.commands\n"
    for source in (by_name, by_suffix, plain):
        assert len(scan_source(source, HOOKS)) == 1, source


def test_the_scan_lets_unrelated_imports_and_registrations_pass() -> None:
    source = (
        "from tl_mod_documents.derivation import store\n"
        "from tl_api.routes import health\n"
        "from tl_cli import cor\n"
        "app.include_router(health.router)\n"
        "cor.app.add_typer(sub.app, name='clock')\n"  # a sub-group under a hooked group
    )
    assert scan_source(source, HOOKS) == []


def test_a_listed_line_is_exempt_and_an_entry_with_no_such_line_is_stale() -> None:
    source = "from tl_api.routes import cor\napp.include_router(cor.router)\n"
    files = {"f.py": source}
    assert drift_problems(files, HOOKS, {}) != []
    assert drift_problems(files, HOOKS, {"f.py": ["tl_api.routes.cor"]}) == []
    stale = drift_problems(files, HOOKS, {"f.py": ["tl_api.routes.cor", "tl_api.routes.gone"]})
    assert len(stale) == 1 and "stale" in stale[0]
    assert any("stale" in p for p in drift_problems({"f.py": "x = 1\n"}, HOOKS, {"f.py": ["a"]}))
    assert any("not a registry" in p for p in drift_problems(files, HOOKS, {"g.py": ["a"]}))


def names_of(violations: Iterable[Violation]) -> set[str]:
    return set().union(*(v.names for v in violations))


def test_a_violation_can_be_exempted_by_its_module_path_its_name_or_its_ref() -> None:
    source = "from tl_api.routes import cor\napp.include_router(cor.router)\n"
    names = names_of(scan_source(source, HOOKS))
    assert {"tl_api.routes.cor", "cor", "tl_api.routes.cor:router"} <= names
