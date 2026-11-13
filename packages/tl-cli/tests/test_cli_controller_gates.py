"""The controller gate of the CLI (ADR-0013, module roles): `require_command` before every handler.

Three people on one ledger, each with a session file of their own: `ursula` (role user), `dora`
(user and document_controller) and `boss` (admin). Every command that was an admin's act in
ADR-0011 is tried by each: a user is refused with nothing written, a controller and an admin pass
the gate. The module signs its people in itself (the autouse sign-in of the Postgres fixture is
off), so every case runs on both adapters.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path
from unittest import mock

import pytest
from doccli_support import docs_env, world
from tl_adapters.db import DbTarget, as_target
from tl_cli import session
from tl_cli.main import app
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from tl_mod_documents.testing import DocumentsWorld
from typer.testing import CliRunner
from typer.testing import Result as RunResult

AUTO_SIGN_IN = False  # this module signs in as three different people itself
PASSWORD = "correct horse battery"
GATE = "needs the controller access word for documents"  # the module word (RM-S4)
ROLE_GATE = (
    "needs the document_controller or admin role"  # `require_controller`, kept on a condition
)
ROLE_GATED = {"doc import --apply"}
ROOT = Path(__file__).resolve().parents[3]
runner = CliRunner()
DMS_MAPPING = ROOT / "dev" / "seed" / "templates" / "document-register-dms-export.yaml"
DMS_FILE = ROOT / "dev" / "seed" / "legacy" / "dms-document-register.csv"


class Cast:
    """`env` per person: the same ledger, a session file of their own."""

    def __init__(self, env: dict[str, str], tmp_path: Path) -> None:
        self.base = env
        self.target = as_target(env["TL_DB"])
        with mock.patch.dict(os.environ, env):
            backend = session.open_backend(self.target)
            with backend() as uow:
                for name, roles in (
                    ("boss", ["admin"]),
                    ("dora", ["user", "document_controller"]),
                    ("ursula", ["user"]),
                ):
                    accounts.create_account(
                        uow, username=name, display_name=name.title(), kind="person",
                        roles=roles, password=prepare_password(PASSWORD, username=name),
                        by="svc:test",
                    )  # fmt: skip
        self.boss = self._sign_in("boss", tmp_path)
        self.dora = self._sign_in("dora", tmp_path)
        self.ursula = self._sign_in("ursula", tmp_path)

    def _sign_in(self, name: str, tmp_path: Path) -> dict[str, str]:
        mine = self.base | {"TL_SESSION_FILE": str(tmp_path / f"session-{name}.json")}
        with mock.patch.dict(os.environ, mine):
            backend = session.open_backend(self.target)
            principal, token = sessions.sign_in(backend, username=name, password=PASSWORD)
            session.save(
                session.StoredSession(
                    target=session.db_target(self.target),
                    username=name,
                    actor=principal.actor,
                    expires_at=session.expires_at_from(sessions.SESSION_TTL),
                    token=token,
                )
            )
        return mine


@pytest.fixture
def env(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    return docs_env(new_db, monkeypatch)


@pytest.fixture
def cast(env: dict[str, str], tmp_path: Path) -> Cast:
    return Cast(env, tmp_path)


@pytest.fixture
def made(env: dict[str, str], tmp_path: Path, cast: Cast) -> DocumentsWorld:
    """ISO-1234 issued as A with a draft B (the supersede target); ISO-2000 with a draft A that has
    a PDF and a review cycle on it; ISO-3000 issued as A with a signed copy (the one to replace); a
    draft transmittal of ISO-1234@A. The module gate runs once the command is built, so the record
    each site names must exist (RM-S4)."""
    docs = world(env, tmp_path)
    docs.issued_document("ISO-1234", "IFR")
    docs.create_revision("ISO-1234")  # B
    docs.issued_document("ISO-3000", "IFR")
    signed = tl(cast.boss, "doc", "rendition", "register-signed", "ISO-3000", "A", pdf(tmp_path),
                "--project", "P123")  # fmt: skip
    assert signed.exit_code == 0, signed.output
    docs.register("ISO-2000")
    docs.create_revision("ISO-2000")
    docs.attach("ISO-2000", "A")
    opened = tl(cast.boss, "review", "open", "ISO-2000", "A", "--project", "P123",
                "--reviewer", "user:dora")  # fmt: skip
    assert opened.exit_code == 0 and "ISO-2000@A/RC1" in opened.stdout, opened.output
    drafted = tl(cast.boss, "transmittal", "create", "--project", "P123", "--subject", "Isos",
                 "--purpose", "for_information", "--to", "Site:Acme:site@acme.test",
                 "--revision", "ISO-1234@A", "--number", "P123-TRN-0001")  # fmt: skip
    assert drafted.exit_code == 0, drafted.stderr
    return docs


def tl(who: dict[str, str], *args: str) -> RunResult:
    result = runner.invoke(app, list(args), env=who)
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    return result


def events(docs: DocumentsWorld) -> int:
    return int(docs.scalar("SELECT COUNT(*) FROM events"))


def pdf(tmp_path: Path) -> str:
    path = tmp_path / "signed.pdf"
    path.write_bytes(b"%PDF-1.7 signed copy")
    return str(path)


SITE_NAMES = (
    "doc confidentiality",
    "doc supersede",
    "doc void",
    "doc rev issue",
    "doc rev supersede",
    "doc rendition register-signed",
    "doc rendition replace-signed",
    "transmittal issue",
    "review on-behalf",
    "review override",
    "doc import --apply",
)


def sites(tmp_path: Path) -> dict[str, tuple[str, ...]]:
    """One command line per `require_controller` site (11 of them)."""
    why = ("--reason", "because")
    return {
        "doc confidentiality": ("doc", "confidentiality", "ISO-1234", "--project", "P123",
                                "--class", "internal", *why),
        "doc supersede": ("doc", "supersede", "ISO-1234", "--project", "P123", "--by", "ISO-2000",
                          *why),
        "doc void": ("doc", "void", "ISO-2000", "--project", "P123", *why),
        "doc rev issue": ("doc", "rev", "issue", "ISO-2000", "A", "--project", "P123",
                          "--status", "IFR"),
        "doc rev supersede": ("doc", "rev", "supersede", "ISO-1234", "A", "--project", "P123",
                              "--by", "B", *why),
        "doc rendition register-signed": ("doc", "rendition", "register-signed", "ISO-1234", "A",
                                          pdf(tmp_path), "--project", "P123"),
        "doc rendition replace-signed": ("doc", "rendition", "replace-signed", "ISO-3000", "A",
                                         pdf(tmp_path), "--project", "P123", *why),
        "transmittal issue": ("transmittal", "issue", "P123-TRN-0001", "--project", "P123"),
        "review on-behalf": ("review", "on-behalf", "ISO-2000@A/RC1", "--project", "P123",
                             "--reviewer", "user:bo", "--outcome", "approved", "--comment", "mail"),
        "review override": ("review", "override", "ISO-2000@A/RC1", "--project", "P123",
                            "--outcome", "approved", *why),
        "doc import --apply": ("doc", "import", str(DMS_FILE), "--project", "P123",
                               "--mapping", str(DMS_MAPPING), "--apply"),
    }  # fmt: skip


# `require_command(uow, command)` calls per source file: one before every `tl_mod_*` handler call
# (RM-S4; `dev/tools/gate_sweep.py --check` finds an ungated one). It replaced
# `require_controller(db)` at every controlling site that runs a module handler.
REQUIRE_COMMAND = {
    "awp_write.py": 1,
    "comm.py": 5, "corr.py": 11, "corr_clock.py": 4, "corr_registry.py": 11, "cost.py": 1,
    "derive_publish.py": 3, "derive_read.py": 1, "derive_run.py": 3, "derive_schema.py": 2,
    "doc.py": 6, "doc_link.py": 2, "doc_rendition.py": 3, "doc_rev.py": 4,
    "intent_flags.py": 1,  # P2-INT-T02 run_with_intent
    "mat_write.py": 7,
    "punch_write.py": 1,  # P2-PUNCH
    "review.py": 5,
    "rfi.py": 10, "schema_gov.py": 4, "schema_import.py": 1, "schema_pkg.py": 6,
    "schema_waiver.py": 3, "standards.py": 3, "standards_class.py": 3, "tag.py": 6,
    "transmittal.py": 5, "xer.py": 7,
}  # fmt: skip
# `require_controller(db)` that stays: a read that only a controller may make (`tl comm ls`, `show`,
# `export`), and a condition on an option (`doc import --apply`, `derive publish`, `corr void` of a
# received item, a privileged export class)
REQUIRE_CONTROLLER = {
    "comm.py": 3, "corr.py": 1, "corr_registry.py": 1, "corr_report.py": 1,
    "derive_publish.py": 1, "doc_import.py": 1,
}  # fmt: skip


def test_every_controlling_cli_path_is_gated(tmp_path: Path) -> None:
    """`require_command` stands before every module handler call, per file; `require_controller(db)`
    stays only where no handler runs (a controller's read) or the gate depends on an option."""
    src = Path(__file__).resolve().parents[1] / "src" / "tl_cli"
    gates = {}
    controllers = {}
    for p in sorted(src.glob("*.py")):
        if p.name == "session.py":
            continue
        text = p.read_text()
        if "require_command(" in text:
            gates[p.name] = len(re.findall(r"\brequire_command\(", text))
        if "require_controller(db)" in text:
            controllers[p.name] = text.count("require_controller(db)")
    assert gates == REQUIRE_COMMAND
    assert controllers == REQUIRE_CONTROLLER
    assert tuple(sites(tmp_path)) == SITE_NAMES


@pytest.mark.parametrize("name", list(SITE_NAMES))
def test_a_user_is_refused_and_nothing_is_written(
    name: str, cast: Cast, made: DocumentsWorld, tmp_path: Path
) -> None:
    before = events(made)
    refused = tl(cast.ursula, *sites(tmp_path)[name])
    assert refused.exit_code == 1, refused.output
    assert refused.stderr.startswith("error: forbidden"), refused.stderr
    assert (ROLE_GATE if name in ROLE_GATED else GATE) in refused.stderr
    written = made.rows("SELECT event_type, actor FROM events ORDER BY seq DESC LIMIT 4")
    assert events(made) == before, f"a refused user still wrote: {written}"


@pytest.mark.parametrize("who", ["dora", "boss"])
@pytest.mark.parametrize("name", list(SITE_NAMES))
def test_a_controller_and_an_admin_pass_the_gate(
    who: str, name: str, cast: Cast, made: DocumentsWorld, tmp_path: Path
) -> None:
    # the commands may still fail for their own reasons (a missing cycle, an invalid register row);
    # what they must not say is that the caller lacks the role
    result = tl(getattr(cast, who), *sites(tmp_path)[name])
    assert ROLE_GATE not in result.stderr and "forbidden" not in result.stderr, result.stderr


def test_a_controller_issues_a_revision_and_a_transmittal_without_being_an_admin(
    cast: Cast, made: DocumentsWorld, tmp_path: Path
) -> None:
    made.register("ISO-3500")  # a draft of its own: ISO-2000@A is in review in `made`
    made.create_revision("ISO-3500")
    made.attach("ISO-3500", "A")
    issued = tl(cast.dora, "doc", "rev", "issue", "ISO-3500", "A", "--project", "P123",
                "--status", "IFC")  # fmt: skip
    assert issued.exit_code == 0, issued.stderr
    assert issued.stdout.startswith("issued ISO-3500@A as IFC")
    drafted = tl(cast.ursula, "transmittal", "create", "--project", "P123", "--subject", "Isos",
                 "--purpose", "for_construction", "--to", "Site:Acme:site@acme.test",
                 "--revision", "ISO-3500@A")  # fmt: skip
    assert drafted.exit_code == 0, drafted.stderr
    number = drafted.stdout.splitlines()[0].removeprefix("created transmittal ")
    assert tl(cast.ursula, "transmittal", "issue", number, "--project", "P123").exit_code == 1
    sent = tl(cast.dora, "transmittal", "issue", number, "--project", "P123")
    assert sent.exit_code == 0, sent.stderr
    # the events name the controller, not an admin
    actors = {
        str(r["actor"])
        for r in made.rows(
            "SELECT actor FROM events WHERE event_type IN ('Revision.Issued', 'Transmittal.Issued')"
        )
    }
    assert "user:dora" in actors and "user:boss" not in actors


def test_a_controller_has_no_admin_command(cast: Cast, made: DocumentsWorld) -> None:
    before = events(made)
    for args in (
        ("admin", "user", "ls"),
        ("admin", "user", "roles", "dora", "--add", "admin"),
        ("admin", "user", "roles", "ursula", "--add", "document_controller"),
        ("admin", "token", "ls"),
    ):
        refused = tl(cast.dora, *args)
        assert refused.exit_code == 1 and refused.stderr.startswith("error: forbidden"), args
        assert "admin role" in refused.stderr
    assert events(made) == before


def test_the_gate_needs_a_controller_even_where_a_dev_actor_is_free(
    env: dict[str, str], made: DocumentsWorld, tmp_path: Path
) -> None:
    nobody = env | {"TL_SESSION_FILE": str(tmp_path / "none.json")}  # no session at all
    refused = tl(nobody, "doc", "rev", "issue", "ISO-2000", "A", "--project", "P123",
                 "--status", "IFR")  # fmt: skip
    # the free dev actor holds the `user` word only (core's dev rule), never `controller`
    assert refused.exit_code == 1 and refused.stderr.startswith("error: forbidden"), refused.stderr
    assert GATE in refused.stderr
