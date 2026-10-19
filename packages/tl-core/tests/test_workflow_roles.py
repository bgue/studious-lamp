"""Where workflow roles come from (ADR-0013, addendum P1-SEC1): derived, never claimed."""

from __future__ import annotations

import pytest
from tl_core.auth.types import AccountView, Principal
from tl_core.services.errors import RoleClaimError
from tl_core.services.reserved import ROLE_CLAIM_MESSAGE, refuse_role_claim
from tl_core.services.workflow import TransitionWorkflow
from tl_core.workflow.roles import workflow_roles


def principal(kind: str, *roles: str) -> Principal:
    return Principal(
        actor=f"{'agent' if kind == 'agent' else 'user'}:x",
        account_id="a-1",
        kind=kind,  # type: ignore[arg-type]
        roles=list(roles),  # type: ignore[arg-type]
        via="session",
    )


@pytest.mark.parametrize(
    ("kind", "roles", "expected"),
    [
        ("person", ("user",), ("user",)),
        ("person", ("document_controller",), ("document_controller", "user")),
        ("person", ("user", "document_controller"), ("document_controller", "user")),
        ("person", ("admin",), ("admin", "document_controller", "user")),
        (
            "person",
            ("admin", "document_controller", "user"),
            ("admin", "document_controller", "user"),
        ),
        ("sim", ("user", "document_controller"), ("document_controller", "user")),
        ("sim", ("user",), ("user",)),
        ("person", (), ()),
    ],
)
def test_a_person_holds_the_roles_of_the_account(
    kind: str, roles: tuple[str, ...], expected: tuple[str, ...]
) -> None:
    assert workflow_roles(principal(kind, *roles)) == expected


@pytest.mark.parametrize("roles", [("user",), ("admin",), ("document_controller",), ()])
def test_an_agent_holds_no_workflow_role_whatever_its_account_says(roles: tuple[str, ...]) -> None:
    assert workflow_roles(principal("agent", *roles)) == ()


def test_an_account_view_derives_the_same_roles_as_its_principal() -> None:
    view = AccountView(
        account_id="a-1", username="dora", display_name="Dora", kind="person",
        roles=["document_controller", "user"], status="active", locked_until=None,
        created_at="2026-10-17T00:00:00Z", seq=1,
    )  # fmt: skip
    assert workflow_roles(view) == workflow_roles(
        principal("person", "document_controller", "user")
    )


def test_a_name_no_account_can_hold_is_never_derived() -> None:
    held = set(workflow_roles(principal("person", "admin", "document_controller", "user")))
    assert held.isdisjoint({"manager", "lifting_supervisor", "engineer", "reviewer"})


def test_a_transition_command_has_no_roles_field_and_drops_a_claim() -> None:
    assert "actor_roles" not in TransitionWorkflow.model_fields
    cmd = TransitionWorkflow.model_validate(
        {"actor": "user:u", "source": "t", "scope": "company", "stream_id": "s",
         "expected_version": 1, "transition": "issue", "actor_roles": ["manager"]}
    )  # fmt: skip
    assert "actor_roles" not in cmd.model_dump()
    assert "manager" not in cmd.model_dump_json()


def test_the_refusal_is_fixed_and_repeats_nothing() -> None:
    with pytest.raises(RoleClaimError) as caught:
        refuse_role_claim({"scope": "company", "actor_roles": ["secret-role-name"]})
    assert str(caught.value) == ROLE_CLAIM_MESSAGE
    assert "secret-role-name" not in str(caught.value)
    refuse_role_claim({"scope": "company", "roles": ["x"]})  # only the named fields are claims
