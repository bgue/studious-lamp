"""`tl wf` and `tl proposal accept` take workflow roles from the session (ADR-0013, P1-SEC1).

Three people on one ledger, each with a session file of their own: `ursula` (user), `dora` (user
and document_controller) and `boss` (admin). The fixture workflow lets only a controller or an
admin `issue`. A person who holds the role passes; a user is blocked and nothing is written; a
`--role` claim adds nothing anywhere but the local dev path (a ledger file in a dev, test or ci
setup, exactly where `--actor` is honoured): on a Postgres target, and on a file under any other
`TL_ENV`, it is refused unless the session holds the role. Runs on both adapters; the dev-path
expectations follow the adapter. The module signs its people in itself.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from unittest import mock

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, as_target, is_postgres, open_uow
from tl_cli import session
from tl_cli.main import app
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from tl_core.services import proposals
from tl_core.services.workflow import TransitionWorkflow
from typer.testing import CliRunner
from typer.testing import Result as RunResult

AUTO_SIGN_IN = False  # this module signs in as different people itself
PASSWORD = "correct horse battery"
P = "P123"
SCOPE = f"project:{P}"
AGENT = "agent:triage"
CLAIM_REFUSED = "does not hold it"
runner = CliRunner()


class Cast:
    """`env` per person: the same ledger, a session file of their own."""

    def __init__(self, base: dict[str, str], tmp_path: Path) -> None:
        self.base = base
        self.target = as_target(base["TL_DB"])
        with mock.patch.dict(os.environ, base):
            with session.open_backend(self.target)() as uow:
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
        self.people = {name: self._sign_in(name, tmp_path) for name in ("boss", "dora", "ursula")}
        self.nobody = base | {"TL_SESSION_FILE": str(tmp_path / "session-nobody.json")}

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

    def __getitem__(self, name: str) -> dict[str, str]:
        return self.people[name]


@pytest.fixture
def base(new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    monkeypatch.delenv("TL_AGENT_DAILY_PROPOSALS", raising=False)
    values = {"TL_DB": str(new_db()), "TL_ENV": "dev"}
    assert runner.invoke(app, ["init"], env=values).exit_code == 0
    return values


@pytest.fixture
def cast(base: dict[str, str], tmp_path: Path) -> Cast:
    return Cast(base, tmp_path)


def tl(who: dict[str, str], *args: str) -> RunResult:
    result = runner.invoke(app, list(args), env=who)
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    return result


def create(who: dict[str, str], title: str) -> str:
    result = tl(who, "record", "create", "--project", P, "--title", title)
    assert result.exit_code == 0, result.output
    return next(line.split()[1] for line in result.stdout.splitlines() if line.startswith("key "))


def link(who: dict[str, str], from_key: str, to_key: str) -> None:
    """An active `references` link between two records, written straight into the ledger."""
    with open_uow(who["TL_DB"]) as uow:
        ids = {
            row.key: row.id
            for row in uow.conn().execute(text("SELECT id, key FROM cur_core_record")).all()
        }
        uow.conn().execute(
            text(
                "INSERT INTO cur_links (link_id, scope, from_id, to_id, relation, status, source, "
                "declined, created_by, created_at, updated_at, version, last_seq) VALUES "
                "(:link_id, 'project:P123', :from_id, :to_id, 'references', 'active', 'manual', "
                "FALSE, 'u', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', 1, 1)"
            ),
            {"link_id": f"L-{from_key}", "from_id": ids[from_key], "to_id": ids[to_key]},
        )


def approved(cast: Cast, title: str = "NCR") -> str:
    """The key of a record in `Approved`, whose `issue` is role-guarded."""
    ursula = cast["ursula"]
    key, other = create(ursula, title), create(ursula, f"{title} support")
    link(ursula, key, other)
    for name in ("submit", "approve"):
        done = tl(ursula, "wf", "transition", "--project", P, key, name)
        assert done.exit_code == 0, done.output
    return key


def state(cast: Cast, key: str) -> str:
    shown = tl(cast["boss"], "record", "show", "--project", P, key).stdout
    return next(line.split(": ", 1)[1] for line in shown.splitlines() if line.startswith("status:"))


def issue(who: dict[str, str], key: str, *extra: str) -> RunResult:
    return tl(who, "wf", "transition", "--project", P, key, "issue", *extra)


def show(who: dict[str, str], key: str, *extra: str) -> RunResult:
    return tl(who, "wf", "show", "--project", P, key, *extra)


# --- the session decides ---------------------------------------------------------------------


def test_show_judges_the_guard_for_the_signed_in_person(cast: Cast) -> None:
    key = approved(cast)
    blocked = show(cast["ursula"], key).stdout
    assert "option issue -> Issued blocked" in blocked
    assert "guard roles FAILED needs one of the roles: document_controller" in blocked
    for who in ("dora", "boss"):
        allowed = show(cast[who], key).stdout
        assert "option issue -> Issued allowed" in allowed, who
        assert "guard roles ok role document_controller held" in allowed, who


def test_a_user_is_blocked_and_nothing_is_written(cast: Cast) -> None:
    key = approved(cast)
    refused = issue(cast["ursula"], key)
    assert refused.exit_code == 1
    assert "guard roles FAILED needs one of the roles: document_controller" in refused.stderr
    assert state(cast, key) == "Approved"


@pytest.mark.parametrize("who", ["dora", "boss"])
def test_a_person_who_holds_the_role_passes(cast: Cast, who: str) -> None:
    key = approved(cast)
    done = issue(cast[who], key)
    assert done.exit_code == 0, done.output
    assert done.stdout.splitlines()[0] == f"transitioned {key} Approved -> Issued"
    assert state(cast, key) == "Issued"


# --- a claim adds nothing outside the local dev path ---------------------------------------------


def test_a_claim_is_honoured_only_where_actor_is_the_local_dev_path(cast: Cast) -> None:
    key = approved(cast)
    on_server = is_postgres(cast.target)  # a database server is never a file the caller owns
    for who, label in ((cast["ursula"], "a user's session"), (cast.nobody, "no session")):
        done = issue(who, key, "--role", "document_controller")
        if on_server:
            assert done.exit_code == 1, label
            assert state(cast, key) == "Approved", label
            assert show(who, key, "--role", "document_controller").exit_code == 1, label
            if who is cast.nobody:
                assert "not signed in" in done.stderr
        else:
            assert done.exit_code == 0, (label, done.output)  # a ledger file in a dev setup
            assert state(cast, key) == "Issued", label
            key = approved(cast, f"After {label}")


def test_show_takes_a_role_claim_only_on_the_local_dev_path(cast: Cast) -> None:
    key = approved(cast)
    for who, label in ((cast["ursula"], "a user's session"), (cast.nobody, "no session")):
        shown = show(who, key, "--role", "document_controller")
        if is_postgres(cast.target):
            assert shown.exit_code == 1, label
            continue
        assert shown.exit_code == 0, (label, shown.output)  # a ledger file in a dev setup
        assert "option issue -> Issued allowed" in shown.stdout, label
        assert "guard roles ok role document_controller held" in shown.stdout, label
    plain = show(cast["ursula"], key).stdout  # without the claim the session decides
    assert "option issue -> Issued blocked" in plain


def test_a_claim_over_a_session_that_lacks_the_role_is_refused(cast: Cast) -> None:
    """Outside a dev setup (here TL_ENV=prod on the file, always so on Postgres)."""
    key = approved(cast)
    prod = lambda who: who | {"TL_ENV": "prod"}  # noqa: E731
    done = issue(prod(cast["ursula"]), key, "--role", "document_controller")
    assert done.exit_code == 1, done.output
    assert "--role document_controller" in done.stderr and CLAIM_REFUSED in done.stderr
    shown = show(prod(cast["ursula"]), key, "--role", "admin")
    assert shown.exit_code == 1 and CLAIM_REFUSED in shown.stderr
    assert state(cast, key) == "Approved"


def test_a_claim_of_a_role_the_session_holds_is_accepted_everywhere(cast: Cast) -> None:
    key = approved(cast)
    prod = cast["dora"] | {"TL_ENV": "prod"}
    done = issue(prod, key, "--role", "document_controller", "--role", "user")
    assert done.exit_code == 0, done.output
    assert state(cast, key) == "Issued"


def test_with_a_session_that_is_not_the_actors_the_session_roles_do_not_apply(
    cast: Cast,
) -> None:
    """--actor names someone else: dora's roles are not his (the dev path), or it is refused."""
    key = approved(cast)
    done = issue(cast["dora"], key, "--actor", "user:somebody-else")
    assert done.exit_code == 1
    if is_postgres(cast.target):
        assert "is not the signed-in user" in done.stderr  # ADR-0009 section 7
    else:
        assert "guard roles FAILED" in done.stderr
    assert state(cast, key) == "Approved"


# --- accepting a proposal ----------------------------------------------------------------


def propose_issue(cast: Cast, key: str) -> str:
    with open_uow(cast.base["TL_DB"], readonly=True) as uow:
        row = (
            uow.conn()
            .execute(text("SELECT id, version FROM cur_core_record WHERE key = :k"), {"k": key})
            .one()
        )

    def factory(readonly: bool = False):  # type: ignore[no-untyped-def]
        return open_uow(cast.base["TL_DB"], readonly=readonly)

    command = TransitionWorkflow(
        actor=AGENT, source="mcp:triage", scope=SCOPE, stream_id=row.id,
        expected_version=row.version, transition="issue",
    )  # fmt: skip
    made = proposals.submit(
        factory, tool="transition_workflow", agent=AGENT, command=command, summary="Issue it"
    )
    return made.proposal_id


def test_a_user_accepting_a_proposal_does_not_pass_the_role_guard(cast: Cast) -> None:
    key = approved(cast)
    refused = tl(cast["ursula"], "proposal", "accept", propose_issue(cast, key))
    assert refused.exit_code == 1 and "GuardFailedError" in refused.stderr
    assert state(cast, key) == "Approved"


def test_a_controller_accepting_a_proposal_passes_with_her_own_roles(cast: Cast) -> None:
    key = approved(cast)
    done = tl(cast["dora"], "proposal", "accept", propose_issue(cast, key))
    assert done.exit_code == 0, done.output
    assert done.stdout.startswith("accepted ")
    assert state(cast, key) == "Issued"


def test_proposal_accept_takes_a_role_claim_only_on_the_local_dev_path(cast: Cast) -> None:
    key = approved(cast)
    done = tl(
        cast["ursula"],
        "proposal",
        "accept",
        propose_issue(cast, key),
        "--role",
        "document_controller",
    )
    if is_postgres(cast.target):
        assert done.exit_code == 1 and CLAIM_REFUSED in done.stderr
        assert state(cast, key) == "Approved"
        return
    assert done.exit_code == 0, done.output  # a ledger file in a dev setup, as for --actor
    assert done.stdout.startswith("accepted ")
    assert state(cast, key) == "Issued"


def test_proposal_accept_refuses_a_claim_outside_the_dev_path(cast: Cast) -> None:
    key = approved(cast)
    prod = cast["ursula"] | {"TL_ENV": "prod"}
    done = tl(prod, "proposal", "accept", propose_issue(cast, key), "--role", "document_controller")
    assert done.exit_code == 1 and CLAIM_REFUSED in done.stderr
    assert state(cast, key) == "Approved"


# --- the guard: take the derivation away and the controller is refused ----------------------------


def test_the_derivation_is_what_lets_a_controller_pass(
    cast: Cast, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = approved(cast)
    monkeypatch.setattr(session, "workflow_roles", lambda _who: ())
    blocked = issue(cast["boss"], key)
    assert blocked.exit_code == 1 and "guard roles FAILED" in blocked.stderr
    assert state(cast, key) == "Approved"
    monkeypatch.undo()
    assert issue(cast["boss"], key).exit_code == 0
