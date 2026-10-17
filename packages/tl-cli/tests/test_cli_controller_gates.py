"""The document controller gate of the CLI (ADR-0013): `require_controller` at every site.

Three people on one ledger, each with a session file of their own: `ursula` (role user), `dora`
(user and document_controller) and `boss` (admin). Every command that was an admin's act in
ADR-0011 is tried by each: a user is refused with nothing written, a controller and an admin pass
the gate. The module signs its people in itself (the autouse sign-in of the Postgres fixture is
off), so every case runs on both adapters.
"""

from __future__ import annotations

import os
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
GATE = "needs the document_controller or admin role"
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
    """ISO-1234 issued as A; ISO-2000 with a draft A that has a PDF; a draft transmittal."""
    docs = world(env, tmp_path)
    docs.issued_document("ISO-1234", "IFR")
    docs.register("ISO-2000")
    docs.create_revision("ISO-2000")
    docs.attach("ISO-2000", "A")
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
        "doc rendition replace-signed": ("doc", "rendition", "replace-signed", "ISO-1234", "A",
                                         pdf(tmp_path), "--project", "P123", *why),
        "transmittal issue": ("transmittal", "issue", "P123-TRN-0001", "--project", "P123"),
        "review on-behalf": ("review", "on-behalf", "P123-RC-1", "--project", "P123",
                             "--reviewer", "user:bo", "--outcome", "approved", "--comment", "mail"),
        "review override": ("review", "override", "P123-RC-1", "--project", "P123",
                            "--outcome", "approved", *why),
        "doc import --apply": ("doc", "import", str(DMS_FILE), "--project", "P123",
                               "--mapping", str(DMS_MAPPING), "--apply"),
    }  # fmt: skip


def test_there_are_eleven_controller_sites(tmp_path: Path) -> None:
    """The sites below are all of them: `require_controller` appears 11 times in `tl doc` and
    friends, and once more in `tl derive publish` (a controller publishes documents; its own test
    is `test_cli_derive_publish.py`)."""
    src = Path(__file__).resolve().parents[1] / "src" / "tl_cli"
    found = {
        p.name: p.read_text().count("require_controller(db)")
        for p in src.glob("*.py")
        if "require_controller(db)" in p.read_text()
    }
    assert found.pop("derive_publish.py") == 1
    assert sum(found.values()) == 11
    assert tuple(sites(tmp_path)) == SITE_NAMES


@pytest.mark.parametrize("name", list(SITE_NAMES))
def test_a_user_is_refused_and_nothing_is_written(
    name: str, cast: Cast, made: DocumentsWorld, tmp_path: Path
) -> None:
    before = events(made)
    refused = tl(cast.ursula, *sites(tmp_path)[name])
    assert refused.exit_code == 1, refused.output
    assert refused.stderr.startswith("error: forbidden"), refused.stderr
    assert GATE in refused.stderr
    assert events(made) == before


@pytest.mark.parametrize("who", ["dora", "boss"])
@pytest.mark.parametrize("name", list(SITE_NAMES))
def test_a_controller_and_an_admin_pass_the_gate(
    who: str, name: str, cast: Cast, made: DocumentsWorld, tmp_path: Path
) -> None:
    # the commands may still fail for their own reasons (a missing cycle, an invalid register row);
    # what they must not say is that the caller lacks the role
    result = tl(getattr(cast, who), *sites(tmp_path)[name])
    assert GATE not in result.stderr and "forbidden" not in result.stderr, result.stderr


def test_a_controller_issues_a_revision_and_a_transmittal_without_being_an_admin(
    cast: Cast, made: DocumentsWorld, tmp_path: Path
) -> None:
    issued = tl(cast.dora, "doc", "rev", "issue", "ISO-2000", "A", "--project", "P123",
                "--status", "IFC")  # fmt: skip
    assert issued.exit_code == 0, issued.stderr
    assert issued.stdout.startswith("issued ISO-2000@A as IFC")
    drafted = tl(cast.ursula, "transmittal", "create", "--project", "P123", "--subject", "Isos",
                 "--purpose", "for_construction", "--to", "Site:Acme:site@acme.test",
                 "--revision", "ISO-2000@A")  # fmt: skip
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


def test_the_gate_needs_a_session_even_where_a_dev_actor_is_free(
    env: dict[str, str], made: DocumentsWorld, tmp_path: Path
) -> None:
    nobody = env | {"TL_SESSION_FILE": str(tmp_path / "none.json")}  # no session at all
    refused = tl(nobody, "doc", "rev", "issue", "ISO-2000", "A", "--project", "P123",
                 "--status", "IFR")  # fmt: skip
    assert refused.exit_code == 1 and refused.stderr.startswith("error: not signed in")
