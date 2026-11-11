"""core section: the people of the project, their module roles and the project's own records.

People (README of P2-SEED): an admin, a document controller, a project engineer, a materials
coordinator, two foremen, a quality inspector, an RFI author and a read-only client rep. Every
account has the demo password ``PASSWORD`` (documented in the demo-project runbook, piece T04); the
accounts are made with the account service, the hash before the write transaction.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from tl_adapters.db import open_uow
from tl_core.auth import accounts
from tl_core.auth.module_grants import GrantModuleRole, grant_module_role
from tl_core.auth.password import prepare_password
from tl_core.modules import load_modules
from tl_core.services.commands import CreateRecord
from tl_core.services.records import handle_create_record

from dev.seed.demo_project.registry import register
from dev.seed.demo_project.world import PROJECT, SOURCE, START, World

PASSWORD = "p200-demo-pass"  # demo data only; the same for every demo account
ADMIN = "mokafor"


@dataclass(frozen=True)
class Person:
    username: str
    name: str
    job: str
    roles: tuple[str, ...]
    grants: tuple[tuple[str, str], ...] = ()  # (module, role); module "*" is every module


PEOPLE: tuple[Person, ...] = (
    Person("mokafor", "Marta Okafor", "Project administrator", ("admin",)),
    Person("ipetrov", "Ivan Petrov", "Document controller", ("user", "document_controller")),
    Person("lhartmann", "Lena Hartmann", "Project engineer", ("user",), (("awp", "user"),)),
    Person(
        "treyes",
        "Tomas Reyes",
        "Materials coordinator",
        ("user",),
        (("materials", "superuser"), ("awp", "user")),
    ),
    Person("cbrooks", "Callum Brooks", "Foreman, piping", ("user",), (("awp", "user"),)),
    Person("pnair", "Priya Nair", "Foreman, civil", ("user",), (("awp", "user"),)),
    Person("hsato", "Hana Sato", "Quality inspector", ("user",), (("quality", "superuser"),)),
    Person("odoyle", "Owen Doyle", "RFI author", ("user",)),
    Person(
        "gwhitfield",
        "Grace Whitfield",
        "Client representative (read only)",
        ("user",),
        (("*", "viewer"),),
    ),
)

AREAS: tuple[tuple[str, str], ...] = (
    ("100", "Pipe rack"),
    ("200", "Process unit (reactor and fractionation)"),
    ("300", "Tank farm"),
    ("400", "Utilities (cooling water, steam, nitrogen)"),
    ("500", "Substation and control room"),
    ("600", "Tie-ins to the live plant"),
)


def build(world: World, rng: random.Random) -> None:
    for person in PEOPLE:
        prepared = prepare_password(PASSWORD, username=person.username)  # hash before the write
        with open_uow(world.target) as uow:
            accounts.create_account(
                uow,
                username=person.username,
                display_name=person.name,
                kind="person",
                roles=list(person.roles),
                password=prepared,
                by="svc:demo-project",
            )
    modules = {spec.name for spec in load_modules()}
    for person in PEOPLE:
        account = world.scalar(
            "SELECT account_id FROM cur_account WHERE username = :u", u=person.username
        )
        for module, role in person.grants:
            if module != "*" and module not in modules:
                continue
            with open_uow(world.target) as uow:
                grant_module_role(
                    uow,
                    GrantModuleRole(
                        actor=f"user:{ADMIN}",
                        source=SOURCE,
                        account_id=str(account),
                        project=PROJECT,
                        module=module,
                        role=role,
                        reason="demo project roster",
                    ),
                )
    with world.on(START):
        world.run(
            handle_create_record,
            CreateRecord,
            by=ADMIN,
            record_type="core.Record",
            title="P200 North Refinery, Hydrotreater Unit 2 expansion (brownfield)",
            description="Demo project: six areas, eight disciplines, four contractors.",
        )
        for code, title in AREAS:
            world.run(
                handle_create_record,
                CreateRecord,
                by=ADMIN,
                record_type="core.Record",
                title=f"Area {code}, {title}",
            )


register("core", build)
