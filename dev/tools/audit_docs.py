#!/usr/bin/env python3
"""Audit every package's AGENTS.md and README.md against the code (P0-I8, brief 25.2).

    uv run python dev/tools/audit_docs.py [--package tl-core] [--strict]

For each document it checks the backticked references that can be checked mechanically:

* a repository path (``packages/tl-core/src/...``, ``docs/runbooks/x.md``) exists;
* a dotted Python name (``tl_core.ledger.Event``) imports and resolves;
* ``just <recipe>`` is a recipe of the justfile;
* ``tl <group> [<command>]`` is a command of the CLI;
* a ``TL_*`` variable appears in the code, the justfile or a script;
* the package has a README.md and an AGENTS.md, and the README stays under 150 lines;
* every top-level module or subpackage of the package, every ``tl`` command group and every MCP
  tool name is mentioned in the package's README.md or AGENTS.md (reported as ``undocumented``).

It cannot judge a rule's meaning, so a clean run is necessary, not sufficient: a person still reads
each rule against the code it names. Exit code 1 with ``--strict`` when there is a finding.
"""

from __future__ import annotations

import argparse
import importlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README_MAX_LINES = 150
_TICK = re.compile(r"`([^`\n]+)`")
_FILE_SUFFIXES = (".py", ".md", ".yaml", ".yml", ".sh", ".toml", ".json", ".sql", ".tcss", ".html")
_RUNTIME_PREFIXES = ("dev/data/", "./dev/data/", "dev/seed/scenarios/seed-", "/tmp/")
_DOTTED = re.compile(r"^(tl_[a-z0-9_]+)(\.[A-Za-z_][A-Za-z0-9_]*)+(\(\))?$")
_ENV = re.compile(r"^TL_[A-Z0-9_]+$")
_PLANNED = re.compile(r"not done|not built|follow-up|filed as|planned|not yet", re.IGNORECASE)


_SKIP_DIRS = {".venv", ".git", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache"}
_MIME_TYPES = {"application", "text", "image", "audio", "video", "multipart"}


def file_names() -> set[str]:
    """Names of every file and directory in the repository (without the virtual environment)."""
    names: set[str] = set()
    stack = [ROOT]
    while stack:
        for entry in stack.pop().iterdir():
            if entry.name in _SKIP_DIRS:
                continue
            names.add(entry.name)
            if entry.is_dir():
                stack.append(entry)
    return names


def packages() -> list[Path]:
    found = [p for p in (ROOT / "packages").iterdir() if (p / "pyproject.toml").is_file()]
    modules = ROOT / "packages" / "tl-modules"
    if modules.is_dir():  # scaffolded modules (`tl new module`)
        found += [p for p in modules.iterdir() if (p / "pyproject.toml").is_file()]
    return sorted(found)


def source_text() -> str:
    """Concatenated text of every file an environment variable could be read in."""
    parts: list[str] = []
    for pattern in ("packages/**/*.py", "dev/**/*.sh", "dev/**/*.py", "justfile", "conftest.py"):
        for path in ROOT.glob(pattern):
            if ".venv" not in path.parts and path.is_file():
                parts.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(parts)


def recipes() -> set[str]:
    names: set[str] = set()
    for line in (ROOT / "justfile").read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([a-z][a-z0-9-]*)\b[^:]*:(?!=)", line)
        if match:
            names.add(match.group(1))
    return names


def cli_commands() -> dict[str, set[str]]:
    """``{group: {subcommands}}`` of the ``tl`` typer app; a top-level command maps to ``set()``."""
    import typer
    from tl_cli.main import app

    tree: dict[str, set[str]] = {}
    click_app = typer.main.get_command(app)
    for name, command in getattr(click_app, "commands", {}).items():
        tree[name] = set(getattr(command, "commands", {}).keys())
    return tree


def resolve_dotted(name: str) -> str | None:
    """None when ``name`` resolves, else a short reason."""
    parts = name.removesuffix("()").split(".")
    for cut in range(len(parts), 0, -1):
        module_name = ".".join(parts[:cut])
        try:
            obj: object = importlib.import_module(module_name)
        except ImportError:
            continue
        except Exception as exc:  # a module that fails to import is itself a finding
            return f"importing {module_name} raised {type(exc).__name__}"
        for attr in parts[cut:]:
            if not hasattr(obj, attr):
                return f"{module_name} has no {'.'.join(parts[cut:])}"
            obj = getattr(obj, attr)
        return None
    return "no such module"


def path_candidates(token: str, package: Path) -> list[Path]:
    src = package / "src"
    inner = next(iter(sorted(src.iterdir())), src) if src.is_dir() else package
    return [
        ROOT / token,
        package / token,
        src / token,
        inner / token,
        inner / "generated" / token,
        package / "tests" / token,
    ]


def looks_like_path(token: str) -> bool:
    if any(ch in token for ch in " <>{}*$~=|;,()\"'") or token.startswith(("http", "-", "@", "/")):
        return False
    if "://" in token or token.split("/")[0] in _MIME_TYPES:
        return False
    if all(len(part) == 1 for part in token.split("/")):  # key pairs such as j/k
        return False
    if token.startswith(_RUNTIME_PREFIXES):
        return False
    if token.endswith("/") or "/" in token or token.endswith(_FILE_SUFFIXES):
        return "/" in token or token.endswith(_FILE_SUFFIXES)
    return False


def path_exists(token: str, package: Path, names: set[str], sources: str) -> bool:
    """Whether a documented path is real. Loose on purpose: a bare name counts when a file of that
    name exists anywhere, or the code mentions it (files a program writes at run time); a bare
    directory name is a layout description and is not checked."""
    if token.endswith("/") and "/" not in token.rstrip("/"):
        return True
    trimmed = token.rstrip("/")
    if any(c.exists() for c in path_candidates(trimmed, package)):
        return True
    stem, dot, _ = trimmed.rpartition(".")
    if dot and any(c.exists() for c in path_candidates(stem + ".py", package)):
        return True  # tests/helpers.run_pilot: a name inside tests/helpers.py
    if "/" not in trimmed:
        return trimmed in names or trimmed in sources
    return False


def audit_document(
    path: Path,
    package: Path,
    *,
    names: set[str],
    sources: str,
    just_recipes: set[str],
    commands: dict[str, set[str]],
) -> list[str]:
    findings: list[str] = []
    text = path.read_text(encoding="utf-8")
    seen: set[str] = set()
    for number, line in enumerate(text.splitlines(), start=1):
        for token in _TICK.findall(line):
            token = token.strip()
            if token in seen:
                continue
            seen.add(token)
            where = f"{path.relative_to(ROOT)}:{number}"
            first = token.split()[0] if token.split() else ""
            if _DOTTED.match(token):
                reason = resolve_dotted(token)
                if reason and token.rsplit(".", 1)[1] in ("sql", "py", "md", "yaml", "json"):
                    dotted = token.split(".")
                    file_path = "/".join(dotted[:-2]) + "/" + ".".join(dotted[-2:])
                    if any(c.exists() for c in path_candidates(file_path, package)):
                        reason = None
                if reason:
                    findings.append(f"{where}: `{token}`: {reason}")
            elif token.startswith("just ") and len(token.split()) >= 2:
                recipe = token.split()[1]
                if re.match(r"^[a-z][a-z0-9-]*$", recipe) and recipe not in just_recipes:
                    findings.append(f"{where}: `{token}`: no such just recipe")
            elif (first == "tl" or token.startswith("uv run tl ")) and not _PLANNED.search(line):
                words = token.removeprefix("uv run ").split()
                if len(words) >= 2 and re.match(r"^[a-z][a-z-]*$", words[1]):
                    group = words[1]
                    if group not in commands:
                        findings.append(f"{where}: `{token}`: no such tl command")
                    elif (
                        commands[group]
                        and len(words) >= 3
                        and re.match(r"^[a-z][a-z-]*$", words[2])
                        and words[2] not in commands[group]
                    ):
                        findings.append(f"{where}: `{token}`: `tl {group}` has no `{words[2]}`")
            elif _ENV.match(token):
                if token not in sources:
                    findings.append(f"{where}: `{token}`: not read anywhere in the code")
            elif looks_like_path(token):
                bare = token.split("::")[0].split(":")[0]
                if not path_exists(bare, package, names, sources):
                    findings.append(f"{where}: `{token}`: no such path")
    return findings


def audit_package(
    package: Path,
    *,
    names: set[str],
    sources: str,
    just_recipes: set[str],
    commands: dict[str, set[str]],
) -> list[str]:
    findings: list[str] = []
    readme, agents = package / "README.md", package / "AGENTS.md"
    for doc in (readme, agents):
        if not doc.is_file():
            findings.append(f"{package.relative_to(ROOT)}: missing {doc.name}")
    if readme.is_file():
        lines = len(readme.read_text(encoding="utf-8").splitlines())
        if lines > README_MAX_LINES:
            findings.append(f"{readme.relative_to(ROOT)}: {lines} lines (limit {README_MAX_LINES})")
    for doc in (readme, agents):
        if doc.is_file():
            findings += audit_document(
                doc,
                package,
                names=names,
                sources=sources,
                just_recipes=just_recipes,
                commands=commands,
            )
    return findings


def undocumented(package: Path, commands: dict[str, set[str]]) -> list[str]:
    """Modules, ``tl`` groups and MCP tools the package's two documents never mention."""
    text = "\n".join(
        doc.read_text(encoding="utf-8")
        for doc in (package / "README.md", package / "AGENTS.md")
        if doc.is_file()
    )
    findings: list[str] = []
    src = package / "src"
    inner = next(iter(sorted(src.iterdir())), None) if src.is_dir() else None
    if inner is not None and inner.is_dir():
        for entry in sorted(inner.iterdir()):
            stem = entry.stem if entry.is_file() else entry.name
            if (
                stem.startswith("_")
                or stem in ("py", "generated")
                or entry.suffix not in ("", ".py")
            ):
                continue
            if entry.is_dir() and not (entry / "__init__.py").is_file():
                continue
            if not re.search(rf"(?<![A-Za-z0-9_]){re.escape(stem)}(?![A-Za-z0-9_])", text):
                findings.append(f"undocumented: module {inner.name}.{stem}")
    if package.name == "tl-cli":
        for group in sorted(commands):
            if not re.search(rf"tl {re.escape(group)}\b", text):
                findings.append(f"undocumented: command `tl {group}`")
    if package.name == "tl-mcp":
        import asyncio
        import tempfile

        from tl_adapters.sqlite.factory import SqliteUowFactory
        from tl_mcp.server import build_server

        with tempfile.TemporaryDirectory() as tmp:
            from tl_adapters.sqlite.uow import create_schema

            create_schema(Path(tmp) / "x.db")
            factory = SqliteUowFactory(Path(tmp) / "x.db")
            try:
                server = build_server(factory, actor="agent:audit")
                for tool in asyncio.run(server.list_tools()):
                    if tool.name not in text:
                        findings.append(f"undocumented: MCP tool {tool.name}")
            finally:
                factory.close()
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit package docs against the code.")
    parser.add_argument("--package", action="append", help="only this package directory name")
    parser.add_argument("--strict", action="store_true", help="exit 1 when there is a finding")
    args = parser.parse_args(argv)
    names, sources = file_names(), source_text()
    just_recipes, commands = recipes(), cli_commands()
    total = 0
    for package in packages():
        if args.package and package.name not in args.package:
            continue
        findings = audit_package(
            package, names=names, sources=sources, just_recipes=just_recipes, commands=commands
        ) + undocumented(package, commands)
        print(f"{package.name}: {len(findings)} finding(s)")
        for finding in findings:
            print(f"  {finding}")
        total += len(findings)
    print(f"{total} finding(s)")
    return 1 if args.strict and total else 0


if __name__ == "__main__":
    sys.exit(main())
