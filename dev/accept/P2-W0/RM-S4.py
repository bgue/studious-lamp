"""Acceptance script for P2-W0 RM-S4: the module-role gate in the CLI and the embedded TUI.

Runs on SQLite with a temp ledger and prints one ``PASS <check>`` line per check; exit 0 when every
check passes, 1 on the first failure.

1. the AST pin (``dev/tools/gate_sweep.py``'s finder): every ``tl_mod_*`` handler call in
   ``tl_cli`` and in ``embedded.py`` has a gate on the same variable earlier in its function; a
   deliberately ungated copy is reported, so the pin can fail;
2. ``tl`` through ``CliRunner``, per module, for a plain user, a document controller, a superuser
   grant on one project, and ``user:dev`` with no session;
3. the same for one command of each module through ``EmbeddedClient``;
4. ``tl proposal accept`` and ``allowed_actions`` with the accepter's module word;
5. ``embedded.py`` no longer reads a raw ``.access``.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
TMP = Path(tempfile.mkdtemp(prefix="rm-s4-"))
os.environ["TL_ENV"] = "dev"
os.environ.pop("TL_SCHEMA_DIR", None)

import typer  # noqa: E402
from tl_adapters.db import as_target, open_uow  # noqa: E402
from tl_cli import session  # noqa: E402
from tl_cli.main import app  # noqa: E402
from tl_core.actions import allowed_actions  # noqa: E402
from tl_core.auth import accounts, sessions  # noqa: E402
from tl_core.auth.errors import ForbiddenError  # noqa: E402
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role  # noqa: E402
from tl_core.auth.module_roles import command_index, holder_for_actor  # noqa: E402
from tl_core.auth.password import prepare_password  # noqa: E402
from tl_core.services import proposals  # noqa: E402
from tl_core.services.commands import Command, UpdateRecord  # noqa: E402
from tl_mod_correspondence.handlers.clocks import SweepClocks  # noqa: E402
from tl_mod_documents.handlers.documents import (  # noqa: E402
    RegisterDocument,
    VoidDocument,
    handle_register_document,
)
from tl_mod_engineering.commands import API_COMMANDS as ENGINEERING_COMMANDS  # noqa: E402
from tl_mod_engineering.handlers.tags import ReclassifyTag, RecordTag  # noqa: E402
from tl_mod_schedule.handlers.publish import PublishScheduleSnapshot  # noqa: E402
from tl_mod_schemareg.commands import API_COMMANDS as SCHEMAREG_COMMANDS  # noqa: E402
from tl_tui.embedded import EmbeddedClient  # noqa: E402
from tl_xer.synth import make_xer, week_pair  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

PASSWORD = "correct horse battery"
P1, P2 = "P1", "P2"
runner = CliRunner()
DB = TMP / "ledger.db"
BASE_ENV = {"TL_DB": str(DB), "TL_ENV": "dev", "TL_OBJECT_ROOT": str(TMP / "objects")}


def passed(check: str) -> None:
    print(f"PASS {check}")


def need(ok: bool, what: str) -> None:
    if not ok:
        raise AssertionError(what)


def tl(env: dict[str, str], *args: str) -> Any:
    result = runner.invoke(app, list(args), env=env)
    need(
        result.exception is None or isinstance(result.exception, SystemExit),
        f"{args}: {result.exception!r}",
    )
    return result


def refused(result: Any, what: str) -> None:
    need(
        result.exit_code == 1 and result.stderr.startswith("error: forbidden"),
        f"{what}: expected a refusal, got {result.exit_code} {result.stderr!r}",
    )


def ran(result: Any, what: str) -> None:
    need(result.exit_code == 0, f"{what}: expected success, got {result.stderr!r}")


def not_refused(result: Any, what: str) -> None:
    need("forbidden" not in result.stderr, f"{what}: refused: {result.stderr!r}")


# --- the ledger -------------------------------------------------------------------------------

need(tl(BASE_ENV, "init").exit_code == 0, "tl init")
TARGET = as_target(str(DB))
ENV: dict[str, str] = {}
IDS: dict[str, str] = {}
backend = session.open_backend(TARGET)
for name, roles in (
    ("boss", ["admin"]),
    ("dora", ["user", "document_controller"]),
    ("ursula", ["user"]),
    ("sue", ["user"]),
):
    with backend() as uow:
        view = accounts.create_account(
            uow, username=name, display_name=name.title(), kind="person", roles=roles,
            password=prepare_password(PASSWORD, username=name), by="svc:accept",
        )  # fmt: skip
    IDS[name] = view.account_id
    mine = BASE_ENV | {"TL_SESSION_FILE": str(TMP / f"session-{name}.json")}
    os.environ["TL_SESSION_FILE"] = mine["TL_SESSION_FILE"]
    principal, token = sessions.sign_in(backend, username=name, password=PASSWORD)
    session.save(
        session.StoredSession(
            target=session.db_target(TARGET),
            username=name,
            actor=principal.actor,
            expires_at=session.expires_at_from(sessions.SESSION_TTL),
            token=token,
        )
    )
    ENV[name] = mine
os.environ.pop("TL_SESSION_FILE", None)
ENV["dev"] = BASE_ENV | {"TL_SESSION_FILE": str(TMP / "none.json")}  # no session at all

with backend() as uow:  # sue: a superuser grant on P1 (every module), nothing on P2
    grant_module_role(
        uow,
        GrantModuleRole(
            actor="user:boss", source="accept", scope="company", account_id=IDS["sue"],
            project=f"project:{P1}", module="*", role="superuser", reason="acceptance",
        ),
    )  # fmt: skip

SEED: dict[str, str] = {}
with open_uow(TARGET) as uow:
    for project, number in (
        (P1, "ISO-1"), (P1, "ISO-2"), (P1, "ISO-3"), (P1, "ISO-4"), (P1, "ISO-5"), (P2, "ISO-6"),
        (P2, "ISO-7"),
    ):  # fmt: skip
        made = handle_register_document(
            uow,
            RegisterDocument(
                actor="user:seed", source="accept", scope=f"project:{project}", number=number,
                title="Isometric", doc_type="ISO", discipline="PIP",
            ),
        )  # fmt: skip
        SEED[number] = made.stream_id

# --- 1. the AST pin -----------------------------------------------------------------------------

spec = importlib.util.spec_from_file_location(
    "gate_sweep", ROOT / "dev" / "tools" / "gate_sweep.py"
)
assert spec is not None and spec.loader is not None
sweep = importlib.util.module_from_spec(spec)
sys.modules["gate_sweep"] = sweep  # dataclasses look the module up by name
spec.loader.exec_module(sweep)

total = gated = 0
for path in sweep.target_files():
    calls = sweep.find_calls(path.read_text(encoding="utf-8"), str(path.relative_to(ROOT)))
    ungated = [c for c in calls if not c.gated]
    need(not ungated, f"ungated: {[(c.file, c.line) for c in ungated]}")
    total += len(calls)
    gated += sum(c.gated for c in calls)
    if calls:
        print(f"  {path.relative_to(ROOT)}: {len(calls)} handler calls, {len(calls)} gated")
manual = sum(
    len(sweep.rewrite(p.read_text(encoding="utf-8"), str(p.relative_to(ROOT)))[1])
    for p in sweep.target_files()
)
need(total == gated and total > 100, f"{total} calls, {gated} gated")
print(f"  total: {total} handler calls, {gated} gated, {manual} MANUAL-placed")
doc_src = (ROOT / "packages/tl-cli/src/tl_cli/doc.py").read_text(encoding="utf-8")
mutant = re.sub(r"^\s*require_command\(uow, command\)\n", "", doc_src, count=1, flags=re.M)
need(mutant != doc_src, "the in-memory mutant must differ")
seen = [c for c in sweep.find_calls(mutant, "doc.py(mutant)") if not c.gated]
need(len(seen) == 1, f"the pin must report the ungated copy, saw {seen}")
passed(f"AST pin: {total} handler calls all gated; a deliberately ungated copy is reported")

# the bulk helpers (`apply_plan`, `load_standards`) run handlers inside: each call needs the
# pre-flight `require_commands(uow, <classes>, ...)` earlier in its function, and the classes in
# that tuple are exactly the commands the helper builds
helpers = {
    "tl_cli/doc_import.py": ("_APPLY_PLAN_COMMANDS", "tl_mod_documents.imports.apply"),
    "tl_cli/tag_import.py": ("_APPLY_PLAN_COMMANDS", "tl_mod_engineering.imports.apply"),
    "tl_cli/standards.py": ("_LOAD_STANDARDS_COMMANDS", "tl_mod_engineering.loader"),
}
bulk_total = 0
for rel, (const, helper_module) in helpers.items():
    path = ROOT / "packages" / "tl-cli" / "src" / rel
    src = path.read_text(encoding="utf-8")
    found = sweep.find_helper_calls(src, rel)
    need(len(found) == 1 and found[0].gated, f"{rel}: the bulk helper call is ungated: {found}")
    bulk_total += len(found)
    pre = re.search(r"^\s*require_commands\(uow, " + const + r",.*\n", src, flags=re.M)
    need(pre is not None, f"{rel}: the pre-flight names {const}")
    removed = src.replace(pre.group(0), "", 1)  # type: ignore[union-attr]
    again = sweep.find_helper_calls(removed, rel + "(mutant)")
    need(len(again) == 1 and not again[0].gated, f"{rel}: removing the pre-flight must be reported")
    # the tuple holds every Command class the helper module builds
    cli_module = importlib.import_module(rel[:-3].replace("/", "."))
    held = {c.__name__ for c in getattr(cli_module, const)}
    mod = importlib.import_module(helper_module)
    built = {
        n.func.id
        for n in ast.walk(ast.parse(Path(mod.__file__).read_text(encoding="utf-8")))  # type: ignore[arg-type]
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and isinstance(getattr(mod, n.func.id, None), type)
        and issubclass(getattr(mod, n.func.id), Command)
    }
    need(held == built, f"{rel}: {const} {sorted(held)} but the helper builds {sorted(built)}")
need(bulk_total == 3, f"bulk helper calls: {bulk_total}")
passed(
    "AST pin: the 3 bulk helper calls (apply_plan x2, load_standards) are preceded by "
    "require_commands over exactly the commands they build; removing one is reported"
)

# `class grant` / `class withdraw` look the item up without the viewer filter (`control_item_id`,
# ADR-0016 section 2): their gate must come before that lookup, or "forbidden" against "no item"
# tells a plain user which hidden numbers exist
reg_path = ROOT / "packages/tl-cli/src/tl_cli/corr_registry.py"


def gate_before_lookup(source: str, function: str) -> bool:
    fn = next(
        n
        for n in ast.walk(ast.parse(source))
        if isinstance(n, ast.FunctionDef) and n.name == function
    )

    def lines(name: str) -> list[int]:
        return [
            n.lineno
            for n in ast.walk(fn)
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == name
        ]

    gates, lookups = lines("require_commands"), lines("control_item_id")
    return bool(gates) and bool(lookups) and min(gates) < min(lookups)


reg_src = reg_path.read_text(encoding="utf-8")
for function in ("class_grant", "class_withdraw"):
    need(gate_before_lookup(reg_src, function), f"{function}: the gate must precede the lookup")
    swapped = re.sub(
        r"^(\s*# the gate first.*\n\s*require_commands\(.*\n)(\s*item_id = control_item_id\(.*\n)",
        r"\2\1",
        reg_src,
        flags=re.M,
    )
    need(not gate_before_lookup(swapped, function), f"{function}: a swapped copy is reported")
unknown = tl(ENV["ursula"], "corr", "class", "grant", "P1-NO-SUCH-9", "--project", P1,
             "--account", "user:bo", "--reason", "x")  # fmt: skip
refused(unknown, "ursula class grant on an unknown number")
need("no item" not in unknown.stderr, "forbidden, not a no-item oracle: " + unknown.stderr)
passed("class grant / class withdraw gate before the unfiltered lookup (AST order); an unknown "
       "number is refused as forbidden, not as no-item")  # fmt: skip

# the pre-flight itself: a plain user is refused an engineering admin word before any write
with open_uow(TARGET, readonly=True) as _uow:
    try:
        session.require_commands(_uow, (RecordTag,), actor="user:ursula", scope="project:P1")
    except typer.Exit:
        pass
    else:
        need(False, "require_commands must refuse a plain user the RecordTag admin word")
    session.require_commands(
        _uow, (ReclassifyTag, UpdateRecord), actor="user:ursula", scope="project:P1"
    )
passed("require_commands refuses a plain user a class whose word it lacks and passes the others")

# --- 2. the CLI, per module -----------------------------------------------------------------------

DEF = ("xer", "define", "MAIN", "--project")
# documents: a user command runs, a controller command is refused
ran(tl(ENV["ursula"], "doc", "update", "ISO-1", "--project", P1, "--title", "T", "--reason", "r"),
    "ursula doc update")  # fmt: skip
r = tl(ENV["ursula"], "doc", "void", "ISO-1", "--project", P1, "--reason", "r")
refused(r, "ursula doc void")
need("controller access word for documents" in r.stderr, r.stderr)
# correspondence: a user command runs, a controller command is refused
ran(tl(ENV["ursula"], "corr", "draft", "--project", P1, "--subject", "S", "--to", "Site"),
    "ursula corr draft")  # fmt: skip
refused(tl(ENV["ursula"], "corr", "clock", "sweep", "--project", P1), "ursula corr clock sweep")
# schedule: a controller command is refused, then a user command (an upload) runs
refused(tl(ENV["ursula"], *DEF, P1, "--name", "Main"), "ursula xer define")
ran(tl(ENV["dora"], *DEF, P1, "--name", "Main"), "dora xer define")
xer_path = TMP / "update-1.xer"
xer_path.write_bytes(make_xer(week_pair()[0]))
ran(tl(ENV["ursula"], "xer", "upload", str(xer_path), "--project", P1, "--schedule", "MAIN",
       "--no-start"), "ursula xer upload")  # fmt: skip
# engineering: a user command runs; schemareg and cost: the CLI asks the admin account first, so a
# plain user is refused their admin-word commands (the module gate follows for an admin)
ran(tl(ENV["ursula"], "tag", "create", "47-FV-1001", "--project", P1), "ursula tag create")
refused(
    tl(ENV["ursula"], "schema", "package", "approve", "co.acme.nothing@1.0.0"),
    "ursula schema approve",
)
refused(tl(ENV["ursula"], "cost", "import", str(xer_path), "--project", P1, "--period", "2026-07",
           "--as-of", "2026-07-31", "--apply"), "ursula cost import --apply")  # fmt: skip
passed("CLI: a plain user runs a user command and is refused a controller (or admin) one in "
       "documents, correspondence, schedule, engineering, schemareg and cost")  # fmt: skip

# a document controller: its derived controller commands in documents, correspondence, schedule
ran(tl(ENV["dora"], "doc", "void", "ISO-2", "--project", P1, "--reason", "r"), "dora doc void")
ran(tl(ENV["dora"], "corr", "clock", "sweep", "--project", P1), "dora corr clock sweep")
passed("CLI: a document controller runs its derived controller commands (documents, "
       "correspondence, schedule)")  # fmt: skip

# a superuser grant on P1 allows P1 and still refuses P2
ran(tl(ENV["sue"], "doc", "void", "ISO-3", "--project", P1, "--reason", "r"), "sue P1 doc void")
refused(tl(ENV["sue"], "doc", "void", "ISO-6", "--project", P2, "--reason", "r"), "sue P2 doc void")
ran(tl(ENV["sue"], "corr", "clock", "sweep", "--project", P1), "sue P1 sweep")
refused(tl(ENV["sue"], "corr", "clock", "sweep", "--project", P2), "sue P2 sweep")
passed("CLI: a superuser grant on P1 allows P1 and still refuses P2")

# user:dev with no session on the dev file
ran(tl(ENV["dev"], "doc", "update", "ISO-4", "--project", P1, "--title", "T", "--reason", "r"),
    "dev doc update")  # fmt: skip
refused(tl(ENV["dev"], "doc", "void", "ISO-4", "--project", P1, "--reason", "r"), "dev doc void")
passed("CLI: user:dev with no session runs a user command and is refused a controller one")

# --- 3. the embedded client -----------------------------------------------------------------------


def embedded(who: str) -> EmbeddedClient:
    return EmbeddedClient.for_sqlite(DB, actor=f"user:{who}")


def command(model: Any, who: str, project: str, **fields: Any) -> Any:
    """A command with no validation: only the access decision shows (the handler is never reached
    by a refused person; a permitted person may fail later for the missing fields)."""
    return model.model_construct(
        actor=f"user:{who}", source="accept", scope=f"project:{project}", **fields
    )


def forbidden(call: Any) -> bool:
    try:
        call()
    except ForbiddenError:
        return True
    except Exception:  # noqa: BLE001 - the gate let it through and the handler failed for itself
        return False
    return False


def void_call(who: str, number: str, project: str) -> Any:
    cmd = VoidDocument(
        actor=f"user:{who}", source="accept", scope=f"project:{project}",
        stream_id=SEED[number], reason="r",
    )  # fmt: skip
    return lambda: embedded(who).document_command("VoidDocument", cmd)


def sweep_call(who: str, project: str) -> Any:
    cmd = SweepClocks(actor=f"user:{who}", source="accept", scope=f"project:{project}")
    return lambda: embedded(who).correspondence_command("SweepClocks", cmd)


def publish_call(who: str) -> Any:
    cmd = command(PublishScheduleSnapshot, who, P1, snapshot_id="nope")
    return lambda: embedded(who).publish_schedule_snapshot(cmd)


def engineering_call(who: str, name: str, **fields: Any) -> Any:
    model = {c.model.__name__: c.model for c in ENGINEERING_COMMANDS}[name]
    return lambda: embedded(who).engineering_command(name, command(model, who, P1, **fields))


def schemareg_call(who: str) -> Any:
    model = {c.model.__name__: c.model for c in SCHEMAREG_COMMANDS}["ApproveSchemaPackage"]
    cmd = command(model, who, "company")
    return lambda: embedded(who).schemareg_command("ApproveSchemaPackage", cmd)


# documents
need(forbidden(void_call("ursula", "ISO-5", P1)), "embedded: ursula VoidDocument")
need(not forbidden(void_call("dora", "ISO-5", P1)), "embedded: dora VoidDocument")
need(forbidden(void_call("sue", "ISO-7", P2)), "embedded: sue on P2")
need(not forbidden(void_call("sue", "ISO-4", P1)), "embedded: sue on P1")
need(forbidden(void_call("dev", "ISO-1", P1)), "embedded: user:dev VoidDocument")
# correspondence
need(forbidden(sweep_call("ursula", P1)), "embedded: ursula SweepClocks")
need(not forbidden(sweep_call("dora", P1)), "embedded: dora SweepClocks")
need(forbidden(sweep_call("sue", P2)) and not forbidden(sweep_call("sue", P1)), "embedded: sue")
# schedule
need(forbidden(publish_call("ursula")), "embedded: ursula PublishScheduleSnapshot")
need(not forbidden(publish_call("dora")), "embedded: dora PublishScheduleSnapshot")
# engineering (an admin word and a user word) and schemareg (an admin word)
need(forbidden(engineering_call("ursula", "DefineTagClass")), "embedded: ursula DefineTagClass")
need(not forbidden(engineering_call("boss", "DefineTagClass")), "embedded: boss DefineTagClass")
need(not forbidden(engineering_call("ursula", "CreateTag", number="47-FV-2001")), "embedded: tag")
need(forbidden(schemareg_call("dora")), "embedded: dora ApproveSchemaPackage")
need(not forbidden(schemareg_call("boss")), "embedded: boss ApproveSchemaPackage")
passed(
    "embedded: documents, correspondence, schedule, engineering and schemareg gate by the module "
    "word; a superuser grant on P1 refuses P2; user:dev is refused a controller one"
)

# --- 4. proposals and allowed_actions -------------------------------------------------------------


def pending(proposal_id: str) -> bool:
    with open_uow(TARGET, readonly=True) as uow:
        return proposals.get_proposal(uow.conn(), proposal_id).status == "pending"


def propose(project: str = P1) -> str:
    cmd = PublishScheduleSnapshot(
        actor="agent:triage", source="mcp:triage", scope=f"project:{project}", snapshot_id="NOSUCH"
    )
    with open_uow(TARGET) as uow:
        return proposals.propose(
            uow, tool="propose_publish_schedule_snapshot", agent="agent:triage", command=cmd,
            summary="publish",
        ).proposal_id  # fmt: skip


first = propose()
for who in ("ursula", "sue"):  # no controller account role, or no document_controller with it
    result = tl(ENV[who], "proposal", "accept", first)
    need(result.exit_code == 1 and pending(first), f"{who} accept: {result.output!r}")
result = tl(ENV["dora"], "proposal", "accept", first)  # the module word and the account role
need(not pending(first), f"dora accept: {result.output!r}")
with backend() as uow:  # dora is a document controller by account, but only a viewer on P2
    grant_module_role(
        uow,
        GrantModuleRole(
            actor="user:boss", source="accept", scope="company", account_id=IDS["dora"],
            project=f"project:{P2}", module="schedule", role="viewer", reason="acceptance",
        ),
    )  # fmt: skip
second = propose(P2)
result = tl(ENV["dora"], "proposal", "accept", second)
need(result.exit_code == 1 and pending(second), f"dora accept on P2: {result.output!r}")
passed("proposal accept: refused without the module word (proposal stays pending), runs with it")

controller_names = {n for n, (_, word) in command_index().items() if word == "controller"}


def offers(who: str, number: str = "ISO-1") -> set[str]:
    return {a.command for a in embedded(who).allowed_actions(SEED[number]).actions}


need(not offers("ursula") & controller_names, f"ursula is offered {offers('ursula')}")
need(offers("dora") & controller_names, "dora is offered no controller command")
with open_uow(TARGET, readonly=True) as uow:  # what the API computes: the same function, a holder
    api = allowed_actions(
        uow, SEED["ISO-1"], actor="user:dora", holds=lambda level: level != "admin",
        holder=holder_for_actor(uow.conn(), "user:dora"),
    )  # fmt: skip
need({a.command for a in api.actions} == offers("dora"), "embedded offers what the API would")
with backend() as uow:  # a viewer grant on P2 documents takes the derived controller word away
    grant_module_role(
        uow,
        GrantModuleRole(
            actor="user:boss", source="accept", scope="company", account_id=IDS["dora"],
            project=f"project:{P2}", module="documents", role="viewer", reason="acceptance",
        ),
    )  # fmt: skip
need(
    not offers("dora", "ISO-6") & controller_names,
    f"dora (viewer on P2 documents) is offered {offers('dora', 'ISO-6')}",
)
passed("allowed_actions: a controller is offered only what the module word gives")

# --- 5. no raw .access in embedded.py -------------------------------------------------------------

emb = (ROOT / "packages/tl-tui/src/tl_tui/embedded.py").read_text(encoding="utf-8")
need(re.search(r"\bspec\.access\b|\.access\s*==", emb) is None, "embedded.py reads a raw .access")
need("_controller_gate(uow)" not in emb.split("def _command_gate")[0].split("def _gate_holds")[1],
     "a module path still uses the account-role gate")  # fmt: skip
passed("embedded.py reads no raw `.access`")
print(f"ledger and sessions under {TMP}")
