"""The five module role calls of `ClientInterface`: the embedded client over the real services, and
the fake the screens are tested against (RM-S3).

One script runs on both and what comes back is compared (error classes and messages, the fields of a
view that do not depend on the clock or an id), so the fake cannot drift from the services. The rest
checks the embedded client alone: only an active admin may call the first four, ``my_roles`` is the
signed-in person's own and takes no account id, and a refused call writes nothing.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeClient
from tl_adapters.sqlite.uow import create_schema
from tl_core.auth import accounts
from tl_core.auth.errors import (
    AccountNotFoundError,
    ForbiddenError,
    InvalidAccountError,
    NoCompanyRolesError,
    NoSuchGrantError,
    UnknownModuleError,
    UnknownRoleError,
)
from tl_core.auth.password import prepare_password
from tl_core.modules import load_modules
from tl_tui.embedded import EmbeddedClient

GOOD = "correct horse battery"
P1, P2 = "project:P1", "project:P2"
MODULES = [spec.name for spec in load_modules()]


def make_embedded(
    tmp_path: Path, actor: str = "user:boss"
) -> tuple[EmbeddedClient, dict[str, str]]:
    db = tmp_path / "tl.db"
    create_schema(db)
    client = EmbeddedClient.for_sqlite(db, actor=actor)
    ids: dict[str, str] = {}
    with client._uow(False) as uow:  # pyright: ignore[reportPrivateUsage]
        for name, roles, kind in (
            ("boss", ["admin"], "person"),
            ("amy", ["user"], "person"),
            ("dora", ["document_controller"], "person"),
            ("bot", ["user"], "agent"),
        ):
            password = None if kind == "agent" else prepare_password(GOOD, username=name)
            view = accounts.create_account(
                uow, username=name, display_name=name.title(), kind=kind,  # type: ignore[arg-type]
                roles=roles, password=password, by="svc:test",
            )  # fmt: skip
            ids[name] = view.account_id
    return client, ids


def make_fake() -> tuple[FakeClient, dict[str, str]]:
    fake = FakeClient()
    ids = {
        "boss": fake.seed_account("boss", roles=["admin"]).account_id,
        "amy": fake.seed_account("amy").account_id,
        "dora": fake.seed_account("dora", roles=["document_controller"]).account_id,
        "bot": fake.seed_account("bot", kind="agent").account_id,
    }
    fake.me_account_id = ids["boss"]
    return fake, ids


def shown(call: Callable[[], Any]) -> Any:
    """What a call answers, without ids and clocks: error class and text, or the view's fields."""
    try:
        value = call()
    except Exception as exc:  # noqa: BLE001 - the class and the text are the answer
        return f"{type(exc).__name__}: {exc}"
    if isinstance(value, list):
        return [v.model_dump(exclude={"account_id", "granted_at", "granted_by"}) for v in value]
    return {"changed": value.changed}


Call = Callable[[Any, dict[str, str]], Any]


def grant(who: str, role: str, module: str = "documents", project: str = P1) -> Call:
    return lambda c, i: c.grant_module_role(i.get(who, who), project, module, role, "demo")


def revoke(who: str, role: str, why: str = "demo") -> Call:
    return lambda c, i: c.revoke_module_role(i[who], P1, "documents", role, why)


def script(who: str) -> list[tuple[str, Call]]:
    return [
        ("grant", grant(who, "superuser")),
        ("grant again", grant(who, "superuser")),
        ("list", lambda c, i: c.list_module_roles(P1)),
        ("list other project", lambda c, i: c.list_module_roles(P2)),
        ("list by module", lambda c, i: c.list_module_roles(module="documents")),
        ("list by account", lambda c, i: c.list_module_roles(account_id=i[who])),
        ("effective", lambda c, i: c.effective_roles(i[who], P1)),
        ("effective other project", lambda c, i: c.effective_roles(i[who], P2)),
        ("my roles (the admin)", lambda c, i: c.my_roles(P1)),
        ("unknown role", grant(who, "boss")),
        ("unknown module", grant(who, "user", module="nowhere")),
        ("company grant", grant(who, "user", project="company")),
        ("agent superuser", grant("bot", "superuser")),
        ("unknown account", grant("NOSUCH", "user")),
        ("revoke", revoke(who, "superuser")),
        ("revoke again", revoke(who, "superuser", "x")),
        ("list after", lambda c, i: c.list_module_roles()),
    ]


def test_the_embedded_client_and_the_fake_answer_the_five_calls_alike(tmp_path: Path) -> None:
    embedded, e_ids = make_embedded(tmp_path)
    fake, f_ids = make_fake()
    for label, call in script("amy"):
        got_e = shown(lambda call=call: call(embedded, e_ids))
        got_f = shown(lambda call=call: call(fake, f_ids))
        assert got_e == got_f, (label, got_e, got_f)


def test_the_script_covers_both_a_success_and_each_refusal(tmp_path: Path) -> None:
    embedded, ids = make_embedded(tmp_path)
    answers = {label: shown(lambda call=call: call(embedded, ids)) for label, call in script("amy")}
    assert answers["grant"] == {"changed": True}
    assert answers["grant again"] == {"changed": False}
    assert answers["revoke"] == {"changed": True}
    assert answers["list"][0]["role"] == "superuser" and len(answers["list"]) == 1
    assert answers["list other project"] == [] and answers["list after"] == []
    assert answers["unknown role"].startswith("UnknownRoleError")
    assert answers["unknown module"].startswith("UnknownModuleError")
    assert answers["company grant"].startswith("NoCompanyRolesError")
    assert answers["agent superuser"].startswith("InvalidAccountError")
    assert answers["unknown account"].startswith("AccountNotFoundError")
    assert answers["revoke again"].startswith("NoSuchGrantError")


@pytest.mark.parametrize("make", ["embedded", "fake"])
def test_each_failure_is_the_service_error_class(tmp_path: Path, make: str) -> None:
    client, ids = make_embedded(tmp_path) if make == "embedded" else make_fake()

    def grant(account: str, project: str, module: str, role: str) -> Any:
        return client.grant_module_role(account, project, module, role, "d")

    for error, args in (
        (UnknownRoleError, (ids["amy"], P1, "documents", "boss")),
        (UnknownModuleError, (ids["amy"], P1, "nowhere", "user")),
        (NoCompanyRolesError, (ids["amy"], "company", "documents", "user")),
        (InvalidAccountError, (ids["bot"], P1, "documents", "superuser")),
        (AccountNotFoundError, ("NOSUCH", P1, "documents", "user")),
    ):
        with pytest.raises(error):
            grant(*args)
    with pytest.raises(NoSuchGrantError):
        client.revoke_module_role(ids["amy"], P1, "documents", "user", "d")


def test_the_embedded_client_refuses_the_admin_four_to_a_plain_account(tmp_path: Path) -> None:
    _, ids = make_embedded(tmp_path)
    plain = EmbeddedClient.for_sqlite(tmp_path / "tl.db", actor="user:amy")
    for call in (
        lambda: plain.list_module_roles(P1),
        lambda: plain.effective_roles(ids["amy"], P1),
        lambda: plain.grant_module_role(ids["amy"], P1, "documents", "user", "x"),
        lambda: plain.revoke_module_role(ids["amy"], P1, "documents", "user", "x"),
    ):
        with pytest.raises(ForbiddenError):
            call()


def test_a_refused_grant_writes_nothing(tmp_path: Path) -> None:
    admin, ids = make_embedded(tmp_path)
    plain = EmbeddedClient.for_sqlite(tmp_path / "tl.db", actor="user:amy")
    with pytest.raises(ForbiddenError):
        plain.grant_module_role(ids["amy"], P1, "documents", "superuser", "x")
    assert admin.list_module_roles() == []


@pytest.mark.parametrize("actor", ["user:dora", "user:nobody", "user:AMY"])
def test_the_admin_four_refuse_a_controller_a_ghost_and_an_inexact_name(
    tmp_path: Path, actor: str
) -> None:
    _, ids = make_embedded(tmp_path)
    other = EmbeddedClient.for_sqlite(tmp_path / "tl.db", actor=actor)
    with pytest.raises(ForbiddenError):
        other.list_module_roles()
    with pytest.raises(ForbiddenError):
        other.grant_module_role(ids["amy"], P1, "documents", "user", "x")


def test_my_roles_are_the_signed_in_persons_own(tmp_path: Path) -> None:
    embedded, ids = make_embedded(tmp_path)
    embedded.grant_module_role(ids["amy"], P1, "documents", "superuser", "demo")
    as_amy = EmbeddedClient.for_sqlite(tmp_path / "tl.db", actor="user:amy")
    mine = as_amy.my_roles(P1)
    assert [v.module for v in mine] == MODULES
    assert {v.module: (v.roles, v.source) for v in mine}["documents"] == (["superuser"], "granted")
    assert {v.module: (v.roles, v.source) for v in mine}["cost"] == (["user"], "derived")
    as_dora = EmbeddedClient.for_sqlite(tmp_path / "tl.db", actor="user:dora")
    dora = {v.module: v.roles for v in as_dora.my_roles(P1)}
    assert {m for m, r in dora.items() if "superuser" in r} == {
        "documents", "correspondence", "schedule",
    }  # fmt: skip
    assert [v.roles for v in as_amy.my_roles(P2)] == [["user"]] * len(MODULES)


def test_my_roles_takes_the_project_alone() -> None:
    import inspect

    from tl_tui.client import ClientInterface

    parameters = list(inspect.signature(ClientInterface.my_roles).parameters)
    assert parameters == ["self", "project"]
    assert list(inspect.signature(EmbeddedClient.my_roles).parameters) == ["self", "project"]


def test_the_fake_records_each_admin_call_and_my_roles_is_not_an_admin_call() -> None:
    fake, ids = make_fake()
    fake.grant_module_role(ids["amy"], P1, "documents", "user", "x")
    fake.list_module_roles(P1)
    fake.my_roles(P1)
    names = [m for m, _ in fake.admin_calls]
    assert names.count("grant_module_role") == 1 and names.count("list_module_roles") == 1
    assert names.count("my_roles") == 1


def test_the_embedded_client_is_never_an_agent(tmp_path: Path) -> None:
    make_embedded(tmp_path)
    with pytest.raises(ValueError, match="agent_must_propose"):
        EmbeddedClient.for_sqlite(tmp_path / "tl.db", actor="agent:bot")
