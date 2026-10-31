#!/usr/bin/env python3
"""Gate sweep (P2-W0 RM-S4): a module command handler never runs before its access check.

    uv run python dev/tools/gate_sweep.py            # rewrite the ungated sites (idempotent)
    uv run python dev/tools/gate_sweep.py --check    # exit 1, list file:line of each ungated call

A *module handler call* in ``packages/tl-cli/src/tl_cli`` or ``tl_tui/embedded.py``
is a call with a command as its second argument to

- a name imported from a ``tl_mod_*`` module that starts with ``handle_`` (or ``alias.handle_x`` on
  such an import), or is listed in ``EXTRA_HANDLERS``,
- ``<something>.handler`` (a ``CommandSpec.handler`` reference), or
- a function parameter called ``handler``.

It is *gated* when an earlier call in the same function passes the same variable to
``require_command`` (the CLI) or ``self._command_gate`` (the embedded client), both of which end in
``tl_core.auth.module_roles.require_command_access``. The sweep puts the gate on the line before the
statement that holds the call. A command built inline as the argument is first bound to a name, so
the gate and the handler see the same object. An unconditional ``require_controller(db)`` (or
``self._controller_gate(uow)``) in a function the sweep gated is removed: the module word replaces
it. A site it cannot place prints ``MANUAL file:line reason``; the run exits 2 and that file is left
alone. A call to a bulk helper in ``HELPERS`` (``apply_plan``, ``load_standards``: they build and
run commands inside) needs ``require_commands(uow, <classes>, ...)`` earlier in the same function;
the sweep does not place it (``MANUAL``), ``--check`` lists it. Standard library only; the
acceptance pin of RM-S4 reuses :func:`find_calls`.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLI_DIR = ROOT / "packages" / "tl-cli" / "src" / "tl_cli"
EMBEDDED = ROOT / "packages" / "tl-tui" / "src" / "tl_tui" / "embedded.py"
# written by RM-S3 in parallel; never touched by this tool
SKIP = {"admin_roles.py", "main.py"}

CLI_GATE = "require_command"
EMBEDDED_GATE = "_command_gate"
GATE_NAMES = {CLI_GATE, EMBEDDED_GATE}
# tl_mod_* entry points that are not called handle_* but take a command as their second argument
EXTRA_HANDLERS = {"sweep_clocks", "ingest_email"}
OLD_GATES = {"require_controller", "_controller_gate"}
# bulk helpers of a tl_mod_* package that issue several commands inside (the CLI cannot gate each
# one): the call must be preceded, in the same function, by the pre-flight over their classes
HELPERS = {"apply_plan", "load_standards"}
PREFLIGHT = "require_commands"
_BAD_BETWEEN = (
    ast.Lambda,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
    ast.IfExp,
    ast.BoolOp,
    ast.NamedExpr,
)


@dataclass(frozen=True)
class Call:
    """One module handler call: where it is, and whether a gate comes before it."""

    file: str
    function: str
    line: int
    variable: str | None  # the second argument when it is a bare name
    gated: bool


@dataclass(frozen=True)
class Manual:
    file: str
    line: int
    reason: str


def target_files() -> list[Path]:
    files = [p for p in sorted(CLI_DIR.rglob("*.py")) if p.name not in SKIP]
    return [*files, EMBEDDED]


def _imports(tree: ast.AST) -> tuple[set[str], set[str]]:
    """Names imported from a ``tl_mod_*`` module, and plain module aliases of one."""
    names: set[str] = set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0].startswith(
            "tl_mod_"
        ):
            names.update(a.asname or a.name for a in node.names)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0].startswith("tl_mod_"):
                    modules.add(a.asname or a.name.split(".")[0])
    return names, modules


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}


def _function_of(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> ast.AST | None:
    cur = parents.get(node)
    while cur is not None and not isinstance(cur, ast.FunctionDef | ast.AsyncFunctionDef):
        cur = parents.get(cur)
    return cur


def _qualname(fn: ast.AST | None, parents: dict[ast.AST, ast.AST]) -> str:
    parts: list[str] = []
    cur = fn
    while cur is not None:
        if isinstance(cur, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            parts.append(cur.name)
        cur = parents.get(cur)
    return ".".join(reversed(parts)) or "<module>"


def _is_handler_call(call: ast.Call, names: set[str], modules: set[str], params: set[str]) -> bool:
    f = call.func
    if isinstance(f, ast.Name):
        return (
            f.id in names and (f.id.startswith("handle_") or f.id in EXTRA_HANDLERS)
        ) or f.id in params & {"handler"}
    if isinstance(f, ast.Attribute):
        if f.attr == "handler":
            return True
        root = f.value
        return (
            f.attr.startswith("handle_")
            and isinstance(root, ast.Name)
            and (root.id in names or root.id in modules)
        )
    return False


def _gate_calls(fn: ast.AST, names: set[str] = GATE_NAMES) -> list[ast.Call]:
    """Calls to a gate in ``fn``, not descending into nested functions."""
    found: list[ast.Call] = []

    def walk(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
                continue
            if isinstance(child, ast.Call):
                f = child.func
                name = (
                    f.id
                    if isinstance(f, ast.Name)
                    else f.attr
                    if isinstance(f, ast.Attribute)
                    else ""
                )
                if name in names:
                    found.append(child)
            walk(child)

    walk(fn)
    return found


def _arg_name(node: ast.expr | None) -> str | None:
    return node.id if isinstance(node, ast.Name) else None


def _scan(tree: ast.Module) -> list[tuple[ast.Call, ast.AST | None, bool]]:
    """Every module handler call with its function and whether a gate precedes it."""
    names, modules = _imports(tree)
    parents = _parents(tree)
    out: list[tuple[ast.Call, ast.AST | None, bool]] = []
    for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
        fn = _function_of(call, parents)
        params: set[str] = set()
        if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
            a = fn.args
            params = {x.arg for x in [*a.posonlyargs, *a.args, *a.kwonlyargs]}
        if not _is_handler_call(call, names, modules, params):
            continue
        var = _arg_name(call.args[1]) if len(call.args) >= 2 else None
        gated = False
        if var is not None and fn is not None:
            for gate in _gate_calls(fn):
                if (gate.lineno, gate.col_offset) < (call.lineno, call.col_offset) and any(
                    _arg_name(a) == var for a in gate.args[1:]
                ):
                    gated = True
        out.append((call, fn, gated))
    return out


def find_calls(source: str, filename: str = "<memory>") -> list[Call]:
    """The finder the sweep, ``--check`` and the acceptance pin share."""
    tree = ast.parse(source, filename)
    parents = _parents(tree)
    calls = [
        Call(
            file=filename,
            function=_qualname(fn, parents),
            line=call.lineno,
            variable=_arg_name(call.args[1]) if len(call.args) >= 2 else None,
            gated=gated,
        )
        for call, fn, gated in _scan(tree)
    ]
    return sorted(calls, key=lambda c: c.line)


def find_helper_calls(source: str, filename: str = "<memory>") -> list[Call]:
    """Calls to a bulk helper (``HELPERS`` imported from ``tl_mod_*``) and whether the pre-flight
    ``require_commands(uow, <classes>, ...)`` comes earlier in the same function.

    "Earlier" is position in the source, as for the handler pin: a pre-flight in a sibling branch
    or loop of the function counts. The sweep does not place these; a person does.
    """
    tree = ast.parse(source, filename)
    names, _ = _imports(tree)
    parents = _parents(tree)
    out: list[Call] = []
    for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
        if not (isinstance(call.func, ast.Name) and call.func.id in HELPERS & names):
            continue
        fn = _function_of(call, parents)
        gated = fn is not None and any(
            (g.lineno, g.col_offset) < (call.lineno, call.col_offset)
            for g in _gate_calls(fn, {PREFLIGHT})
        )
        out.append(Call(filename, _qualname(fn, parents), call.lineno, call.func.id, gated))
    return sorted(out, key=lambda c: c.line)


# --- the rewrite ------------------------------------------------------------------------------


def _segment(lines: list[bytes], node: ast.AST) -> bytes:
    l0, l1 = node.lineno - 1, node.end_lineno - 1  # type: ignore[attr-defined]
    c0, c1 = node.col_offset, node.end_col_offset  # type: ignore[attr-defined]
    if l0 == l1:
        return lines[l0][c0:c1]
    return lines[l0][c0:] + b"".join(lines[l0 + 1 : l1]) + lines[l1][:c1]


def _fresh(fn: ast.AST, taken_extra: set[str]) -> str:
    used = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)} | taken_extra
    used |= {
        a.arg
        for n in ast.walk(fn)
        if isinstance(n, ast.arguments)
        for a in ast.walk(n)
        if isinstance(a, ast.arg)
    }
    if "command" not in used:
        return "command"
    i = 2
    while f"command_{i}" in used:
        i += 1
    return f"command_{i}"


def rewrite(source: str, filename: str = "<memory>") -> tuple[str, list[Manual]]:
    """The source with every placeable ungated call gated, and the sites it could not place.

    With any ``MANUAL`` site the source is returned unchanged.
    """
    embedded = Path(filename).name == "embedded.py"
    gate = f"self.{EMBEDDED_GATE}" if embedded else CLI_GATE
    tree = ast.parse(source, filename)
    parents = _parents(tree)
    lines = [ln.encode() for ln in source.splitlines(keepends=True)]
    manual: list[Manual] = []
    inserts: list[tuple[int, bytes]] = []  # (0-based line index, text) put before that line
    replaces: list[tuple[ast.expr, bytes]] = []  # (node, new text)
    removals: set[int] = set()
    gated_functions: dict[ast.AST, int] = {}
    per_stmt: dict[ast.stmt, int] = {}
    work = [(c, fn) for c, fn, g in _scan(tree) if not g]
    taken: dict[ast.AST, set[str]] = {}
    for call, fn in work:
        if fn is None or len(call.args) < 2:
            manual.append(Manual(filename, call.lineno, "no command argument or no function"))
            continue
        stmt: ast.AST = call
        crossed_bad = False
        while not isinstance(stmt, ast.stmt):
            stmt = parents[stmt]
            if isinstance(stmt, _BAD_BETWEEN):
                crossed_bad = True
        assert isinstance(stmt, ast.stmt)
        if crossed_bad:
            manual.append(
                Manual(
                    filename,
                    call.lineno,
                    "call inside a lambda, comprehension or conditional expression",
                )
            )
            continue
        if hasattr(stmt, "body") and not isinstance(stmt, ast.FunctionDef | ast.ClassDef):
            manual.append(Manual(filename, call.lineno, "call in a compound statement header"))
            continue
        if lines[stmt.lineno - 1][: stmt.col_offset].strip():
            manual.append(Manual(filename, call.lineno, "statement shares its line"))
            continue
        per_stmt[stmt] = per_stmt.get(stmt, 0) + 1
        if per_stmt[stmt] > 1:
            manual.append(Manual(filename, call.lineno, "two handler calls in one statement"))
            continue
        indent = lines[stmt.lineno - 1][: stmt.col_offset]
        uow_src = _segment(lines, call.args[0])
        arg = call.args[1]
        if isinstance(arg, ast.Name):
            text = indent + f"{gate}(".encode() + uow_src + b", " + arg.id.encode() + b")\n"
        else:
            var = _fresh(fn, taken.setdefault(fn, set()))
            taken[fn].add(var)
            text = (
                indent
                + var.encode()
                + b" = "
                + _segment(lines, arg)
                + b"\n"
                + indent
                + f"{gate}(".encode()
                + uow_src
                + f", {var})\n".encode()
            )
            if len(call.args) == 2 and not call.keywords:  # keep the call on one line
                shortened = _segment(lines, call.func) + b"(" + uow_src + f", {var})".encode()
                replaces.append((call, shortened))
            else:
                replaces.append((arg, var.encode()))
        inserts.append((stmt.lineno - 1, text))
        gated_functions[fn] = gated_functions.get(fn, 0) + 1
    if manual:
        return source, manual
    # an unconditional old gate in a function we gated is replaced (it is the same check, by role)
    for fn in gated_functions:
        for node in fn.body:  # type: ignore[attr-defined]
            if (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Call)
                and (
                    (isinstance(node.value.func, ast.Name) and node.value.func.id in OLD_GATES)
                    or (
                        isinstance(node.value.func, ast.Attribute)
                        and node.value.func.attr in OLD_GATES
                    )
                )
            ):
                removals.update(range(node.lineno - 1, node.end_lineno))  # type: ignore[attr-defined]
    return _apply_inserts(source, filename, inserts, replaces, removals), manual


def _apply_inserts(
    source: str,
    filename: str,
    inserts: list[tuple[int, bytes]],
    replaces: list[tuple[ast.expr, bytes]],
    removals: set[int],
) -> str:
    """Do all edits against the original line numbers in one pass (replacements, then inserts)."""
    lines = [ln.encode() for ln in source.splitlines(keepends=True)]
    # 1. replacements: a replaced span may cover several lines; mark the extra lines as dropped
    dropped: set[int] = set()
    for arg, name in sorted(replaces, key=lambda r: (r[0].lineno, r[0].col_offset), reverse=True):
        l0, l1 = arg.lineno - 1, arg.end_lineno - 1  # type: ignore[attr-defined]
        c0, c1 = arg.col_offset, arg.end_col_offset  # type: ignore[attr-defined]
        lines[l0] = lines[l0][:c0] + name + lines[l1][c1:]
        dropped.update(range(l0 + 1, l1 + 1))
    out: list[bytes] = []
    before: dict[int, list[bytes]] = {}
    for idx, text in inserts:
        before.setdefault(idx, []).append(text)
    for i, ln in enumerate(lines):
        out.extend(before.get(i, []))
        if i in dropped or i in removals:
            continue
        out.append(ln)
    return b"".join(out).decode()


# --- imports ----------------------------------------------------------------------------------


def _fix_imports(source: str) -> str:
    """CLI files: import ``require_command``; drop ``require_controller`` once nothing uses it."""
    tree = ast.parse(source)
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    lines = source.splitlines(keepends=True)
    imp = next(
        (n for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == "tl_cli.session"),
        None,
    )
    needs = CLI_GATE in used
    if imp is None:
        if not needs:
            return source
        last = max(
            (n.end_lineno for n in tree.body if isinstance(n, ast.Import | ast.ImportFrom)),
            default=0,
        )
        lines.insert(last, f"from tl_cli.session import {CLI_GATE}\n")
        return "".join(lines)
    names = [a.name for a in imp.names]
    if needs and CLI_GATE not in names:
        names.append(CLI_GATE)
    keep = [n for n in names if n not in OLD_GATES or n in used]
    keep = sorted(set(keep))
    if keep == sorted(a.name for a in imp.names):
        return source
    new = f"from tl_cli.session import {', '.join(keep)}\n" if keep else ""
    lines[imp.lineno - 1 : imp.end_lineno] = [new] if new else []
    return "".join(lines)


def sweep_file(path: Path, *, write: bool) -> tuple[list[Call], list[Manual], bool]:
    """Sweep one file: its ungated calls before, the MANUAL sites, whether it changed."""
    source = path.read_text(encoding="utf-8")
    name = str(path.relative_to(ROOT))
    before = [c for c in find_calls(source, name) if not c.gated]
    if not before:
        return [], [], False
    new, manual = rewrite(source, name)
    if manual or new == source:
        return before, manual, False
    if path.name != "embedded.py":
        new = _fix_imports(new)
    if write:
        path.write_text(new, encoding="utf-8")
    return before, manual, True


def main(argv: list[str]) -> int:
    check = "--check" in argv
    pending: list[Call] = []
    manual: list[Manual] = []
    changed = 0
    for path in target_files():
        calls, man, did = sweep_file(path, write=not check)
        pending.extend(calls)
        manual.extend(man)
        changed += len(calls) if did else 0
        name = str(path.relative_to(ROOT))
        bulk = [c for c in find_helper_calls(path.read_text(encoding="utf-8"), name) if not c.gated]
        pending.extend(bulk)
        if not check:
            manual.extend(Manual(c.file, c.line, f"{c.variable} without {PREFLIGHT}") for c in bulk)
    if check:
        for c in pending:
            what = c.variable if c.variable in HELPERS else (c.variable or "inline command")
            print(f"{c.file}:{c.line} ungated {c.function} ({what})")
        print(f"{len(pending)} ungated module handler or bulk helper call(s)")
        return 1 if pending else 0
    for m in manual:
        print(f"MANUAL {m.file}:{m.line} {m.reason}")
    print(f"gated {changed} call(s); {len(manual)} MANUAL")
    return 2 if manual else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
