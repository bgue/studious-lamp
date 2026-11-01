"""Acceptance script for P2-WEB1 S2: ``run_command`` and the Textual-free ``tl_tui.action_ui``.

SQLite temp ledger, ``TL_ENV=test``. Prints one ``PASS <check>`` line per check; exits 0 when every
check passes. Checks (a) to (f) are in ``docs/tickets/P2-WEB1/S2-run-command-action-ui.md``.
"""

from __future__ import annotations

import dataclasses
import inspect
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

os.environ.setdefault("TL_ENV", "test")

from tl_adapters.backend import open_backend  # noqa: E402
from tl_adapters.db import create_schema  # noqa: E402
from tl_api import commands  # noqa: E402
from tl_api.app import create_app  # noqa: E402
from tl_api.commands import COMMANDS, CommandSpec, command_spec, run_command  # noqa: E402
from tl_api.context import ApiContext  # noqa: E402
from tl_api.settings import ApiSettings  # noqa: E402
from tl_api.tokens import TokenStore  # noqa: E402
from tl_core.auth import accounts  # noqa: E402
from tl_core.auth.errors import ForbiddenError  # noqa: E402
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role  # noqa: E402
from tl_core.auth.password import prepare_password  # noqa: E402
from tl_core.auth.types import Principal  # noqa: E402
from tl_core.services.commands import CommandResult  # noqa: E402
from tl_core.services.reserved import ReservedIdentifierError  # noqa: E402

P1 = "project:P1"
PASSWORD = "correct horse battery"
OK = CommandResult(stream_id="stub", key=None, version=1, events=[])

#: The sorted ``ACTION_UI`` keys at the branch point (taken before the move).
ACTION_UI_KEYS = [
    "AnswerTechnical", "AssessCommercial", "CloseCommercial", "CloseCorrespondence",
    "CloseTechnical", "EscalateTechnical", "IssueCommercial", "IssueCorrespondence",
    "IssueTechnical", "ReclassifyTag", "ReferCommercialToLegal", "ReissueTechnical", "RenameTag",
    "ReturnCommercial", "ReturnTechnical", "ReviewCommercial", "ReviewTechnicalAnswer",
    "SubmitCommercial", "SubmitTechnical", "VoidCorrespondence", "VoidDraft",
]  # fmt: skip


def passed(check: str) -> None:
    print(f"PASS {check}")


def refuses(error: type[BaseException], call: Callable[[], Any]) -> BaseException:
    try:
        call()
    except error as exc:
        return exc
    raise AssertionError(f"expected {error.__name__}")


def stub(name: str) -> CommandSpec:
    """The row named ``name`` with a handler that answers 200: only the checks in front show."""
    spec = command_spec(name)
    assert spec is not None, name
    return dataclasses.replace(spec, handler=lambda *a, **k: OK)


def command_of(spec: CommandSpec, *, actor: str, scope: str, **more: Any) -> Any:
    return spec.model.model_construct(actor=actor, source="accept", scope=scope, **more)


def check_source() -> None:
    endpoint_src = inspect.getsource(commands._make_endpoint)  # pyright: ignore[reportPrivateUsage]
    run_src = inspect.getsource(run_command)
    for word in ("require_command_access", "refuse_reserved", "resolve_effective_at"):
        assert word not in endpoint_src, f"_make_endpoint still has {word}"
        assert run_src.count(word) == 1, f"run_command has {word} {run_src.count(word)} times"
    assert "run_command(" in endpoint_src
    passed("(a) _make_endpoint holds none of the three checks; run_command holds each once")


def check_run_command(work: Path) -> None:
    db = work / "ledger.db"
    create_schema(db)
    backend = open_backend(db)
    try:
        settings = ApiSettings(db_path=db, tokens_path=work / "tokens.json")
        app = create_app(backend, settings=settings, tokens=TokenStore(work / "tokens.json"))
        ctx: ApiContext = app.state.ctx
        principals: dict[str, Principal] = {}
        ids: dict[str, str] = {}
        for name, roles in (("uma", ["user"]), ("sue", ["user"]), ("ada", ["admin"])):
            with backend() as uow:
                view = accounts.create_account(
                    uow, username=name, display_name=name.title(), kind="person", roles=roles,
                    password=prepare_password(PASSWORD, username=name), by="svc:accept",
                )  # fmt: skip
            ids[name] = view.account_id
            principals[name] = Principal(
                actor=f"user:{name}", account_id=view.account_id, kind="person", roles=roles,
                via="session",
            )  # fmt: skip
        with backend() as uow:
            grant_module_role(
                uow,
                GrantModuleRole(
                    actor="user:ada", source="accept", scope="company", account_id=ids["sue"],
                    project=P1, module="*", role="superuser", reason="acceptance",
                ),
            )  # fmt: skip

        controller = stub("IssueRevision")  # a documents `controller` command
        spec_words = command_spec("IssueRevision")
        assert spec_words is not None and spec_words.module == "documents"
        for who, allowed in (("uma", False), ("sue", True), ("ada", True)):
            cmd = command_of(controller, actor=f"user:{who}", scope=P1)
            call = lambda w=who, c=cmd: run_command(  # noqa: E731
                ctx, controller, c, principal=principals[w], path="/commands/IssueRevision"
            )
            if allowed:
                assert call() is OK
            else:
                refuses(ForbiddenError, call)
        passed("(b) controller command: no grant refused (ForbiddenError); the word's holder runs")

        company = stub("AddCodeValue")
        assert company.access == "company"
        for who, allowed in (("uma", False), ("ada", True)):
            cmd = command_of(company, actor=f"user:{who}", scope="company")
            call = lambda w=who, c=cmd: run_command(  # noqa: E731
                ctx, company, c, principal=principals[w], path="/commands/AddCodeValue"
            )
            if allowed:
                assert call() is OK
            else:
                refuses(ForbiddenError, call)
        passed("(b) company command at company scope: a non-admin is refused, an admin runs")

        # the admin check is its own layer: the authorizer is asked, with the path, at company scope
        asked: list[tuple[str, str]] = []

        class Spy:
            def authorize(self, principal: Principal, action: str, resource: str) -> None:
                asked.append((action, resource))

        spied = dataclasses.replace(ctx, authorizer=Spy())  # type: ignore[arg-type]
        for scope, expect in (("company", True), (P1, False)):
            asked.clear()
            cmd = command_of(company, actor="user:ada", scope=scope)
            run_command(spied, company, cmd, principal=principals["ada"], path="/p")
            assert asked == ([("admin.command.AddCodeValue", "/p")] if expect else []), asked
        passed("(b) the company-admin authorizer is asked at company scope, with the path, only")

        for field_name, value in (("source", "svc:x"), ("correlation_id", "load:1")):
            cmd = command_of(company, actor="user:ada", scope=P1)
            cmd = cmd.model_copy(update={field_name: value})
            refuses(
                ReservedIdentifierError,
                lambda c=cmd: run_command(ctx, company, c, principal=principals["ada"]),
            )
        passed("(b) a command carrying a reserved field is refused")
    finally:
        backend.close()


def check_lookup() -> None:
    row = command_spec("AnswerTechnical")
    assert row is not None and row in COMMANDS and row.name == "AnswerTechnical"
    assert command_spec("Nope") is None
    passed("(c) command_spec finds the COMMANDS row and answers None for an unknown name")


def check_no_textual() -> None:
    code = "import sys, tl_tui.action_ui; bad = sorted(m for m in sys.modules if m.split('.')[0] == 'textual' or m.startswith('tl_tui.') and m != 'tl_tui.action_ui'); print(bad); sys.exit(1 if bad else 0)"  # noqa: E501
    done = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stdout + done.stderr
    passed("(d) a fresh `import tl_tui.action_ui` loads no textual and no other tl_tui module")


def check_reexports() -> None:
    from tl_tui import action_ui, log_actions
    from tl_tui.widgets import action_form

    assert log_actions.ACTION_UI is action_ui.ACTION_UI
    assert log_actions.ActionUi is action_ui.ActionUi
    assert action_form.FormField is action_ui.FormField
    assert log_actions.FormField is action_ui.FormField
    assert log_actions.ENVELOPE is action_ui.ENVELOPE
    assert log_actions.stamp is action_ui.stamp
    assert log_actions.without_keys is action_ui.without_keys
    assert sorted(action_ui.ACTION_UI) == ACTION_UI_KEYS
    passed("(e) the moved names are the same objects through log_actions and action_form")
    passed("(e) ACTION_UI has the keys it had at the branch point")


def check_build() -> None:
    from tl_tui.action_ui import ACTION_UI, ENVELOPE

    plain = {name: ui for name, ui in ACTION_UI.items() if not ui.fields}
    assert plain, "no field-less entry"
    for name, ui in plain.items():
        cmd = ui.build({}, "rec-1", 3)
        assert cmd.stream_id == "rec-1", name
        assert (cmd.actor, cmd.source, cmd.scope) == tuple(ENVELOPE.values()), name
    passed(f"(f) {len(plain)} field-less entries build a command on stream rec-1 with the envelope")


def main() -> int:
    check_source()
    check_run_command(Path(tempfile.mkdtemp(prefix="web1-s2-")))
    check_lookup()
    check_no_textual()
    check_reexports()
    check_build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
