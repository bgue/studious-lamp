"""Fixes from the fresh-context security review of 1972934: one test per finding.

Each test fails on the code the review read. Findings 1, 2 (owner switches), 4 and the transport
deadline are tested beside the code they changed (``test_int_runner_access``, ``test_transport``).
"""

from __future__ import annotations

import hashlib
import math
from datetime import timedelta
from typing import Any

import jwt
import pytest
from intworld import ADMIN, PERSON, SCOPE, World
from tl_core.integration.automation import ServerFields, plan_command
from tl_core.integration.contract import INBOUND_REPLAY_RETENTION_S
from tl_core.integration.inbound.gate import REPLAY_KEEP_S
from tl_core.integration.inbound.verify import VerifyError, verify_jwt
from tl_core.integration.rules.engine import RulesWorker
from tl_core.services import proposals
from tl_core.util import utcnow
from tl_core.webhooks.signing import SigningSecret, generate_secret

NOW = 1_800_000_000.0
BODY = b"{}"
AUD = "/in/erp/orders"


def act_rule(world: World, **fields: Any) -> str:
    rule_id = world.create_rule(**fields)
    world.revise_rule(rule_id, {"mode": "act"})
    world.switch_rule(rule_id, on=True)
    return rule_id


# --- 2. a rule switched off mid-batch stops at the next event ----------------------------------


class SwitchingWorker(RulesWorker):
    """Switches the rule off after it has handled its first event of the batch."""

    def __init__(self, world: World, rule_id: str) -> None:
        super().__init__(world.factory, world.runner, clock=world.clock)
        self._world, self._rule_id, self._done = world, rule_id, False

    def _event(self, row: Any, rules: Any, stats: Any) -> None:
        super()._event(row, rules, stats)
        if stats.fired and not self._done:
            self._done = True
            self._world.switch_rule(self._rule_id, on=False)


def test_disabling_a_rule_mid_batch_stops_it_at_the_next_event(world: World) -> None:
    rule_id = act_rule(world)
    world.post("first #safety")
    world.post("second #safety")
    SwitchingWorker(world, rule_id).run_until_idle()
    assert [p["body"] for p in world.posts() if p["actor"].startswith("svc:rule-")] == [
        "HSE notified of " + world.events("Feed.Posted")[0]["event_id"]
    ]
    assert len(world.firings()) == 1


def test_a_revised_rule_applies_to_the_rest_of_the_batch_with_its_new_version(world: World) -> None:
    rule_id = act_rule(world)
    world.post("first #safety")
    world.post("second #safety")

    class Revising(SwitchingWorker):
        def _event(self, row: Any, rules: Any, stats: Any) -> None:
            RulesWorker._event(self, row, rules, stats)  # noqa: SLF001
            if stats.fired and not self._done:
                self._done = True
                self._world.revise_rule(self._rule_id, {"title": "Notify HSE (v2)"})

    Revising(world, rule_id).run_until_idle()
    assert sorted(f["rule_version"] for f in world.firings()) == [2, 3]


# --- 8. a rule is never offered account or bookkeeping events ----------------------------------


def test_a_rule_never_sees_account_events_or_the_layers_own_bookkeeping(world: World) -> None:
    wide = ["Account.Created", "Rule.Created", "Rule.Enabled", "Feed.Posted"]
    act_rule(world, key="wide", when={"event_types": wide})
    world.account("someone")  # Account.Created
    world.create_rule(key="other")  # Rule.Created
    world.post("a post")
    world.worker().run_until_idle()
    seen = {
        r["event_type"]
        for r in world.rows(
            "SELECT e.event_type FROM rule_firing f JOIN events e ON e.event_id = f.event_id"
        )
    }
    assert seen == {"Feed.Posted"}


# --- 3. automation never supplies roles or accepts a risk --------------------------------------


@pytest.mark.parametrize("field", ["actor_roles", "accept_risk"])
def test_automation_cannot_set_roles_or_accept_a_risk(world: World, field: str) -> None:
    args: dict[str, Any] = {
        "stream_id": "x",
        "expected_version": 1,
        "transition": "go",
        field: ["admin"],
    }
    fields = ServerFields(
        actor="svc:rule-x", source="rule:x@1/d1", scope=SCOPE, correlation_id="c", causation_id="e"
    )
    planned = plan_command(
        world.runner, "TransitionWorkflow", args, fields,
        declared="controller", allowed={"TransitionWorkflow"}, link_source="rule",
    )  # fmt: skip
    assert planned.command is None
    assert planned.planned.problem is not None and planned.planned.problem.code == "forbidden_field"


def test_a_mapping_that_claims_roles_fails_the_delivery(world: World) -> None:
    mapping = (
        '{"command": "TransitionWorkflow", "args": {"stream_id": "x", "expected_version": 1, '
        '"transition": "go", "actor_roles": ["admin"]}}'
    )
    made = world.endpoint(
        mapping=mapping, allowed_commands=["TransitionWorkflow"], access="controller"
    )
    world.deliver(made.endpoint_id, {})
    world.inbound_runner().run_until_idle()
    row = world.deliveries()[0]
    assert row["state"] == "failed" and row["error_code"] == "forbidden_field"


# --- 7. JWT numeric claims ---------------------------------------------------------------------


def _token(secret: SigningSecret, **claims: Any) -> dict[str, str]:
    data: dict[str, Any] = {
        "iat": int(NOW), "exp": int(NOW) + 60, "aud": AUD, "jti": "j",
        "body_sha256": hashlib.sha256(BODY).hexdigest(),
    }  # fmt: skip
    data.update(claims)
    return {"Authorization": "Bearer " + jwt.encode(data, secret.key(), algorithm="HS256")}


@pytest.mark.parametrize(
    "claims",
    [
        {"iat": math.nan},
        {"exp": math.nan},
        {"exp": math.inf},
        {"iat": -math.inf},
        {"exp": 10**400},
        {"iat": 10**400, "exp": 10**400 + 1},
    ],
)
def test_a_non_finite_or_huge_claim_is_a_fixed_refusal_not_a_crash(claims: dict[str, Any]) -> None:
    secret = SigningSecret(generate_secret())
    with pytest.raises(VerifyError) as caught:
        verify_jwt(_token(secret, **claims), BODY, [secret], audience=AUD, now=NOW)
    assert caught.value.code in ("bad_claims", "expired")


# --- 7b. the replay row outlives the window a request is acceptable in -------------------------


def test_a_replay_row_is_kept_past_the_acceptance_window(world: World) -> None:
    from test_int_inbound_worker import accept_again  # type: ignore[import-not-found]
    from tl_core.integration.inbound.gate import ReplayError

    assert REPLAY_KEEP_S > INBOUND_REPLAY_RETENTION_S
    made = world.endpoint()
    seen = utcnow() - timedelta(seconds=INBOUND_REPLAY_RETENTION_S + 30)
    accept_again(world, made.endpoint_id, "m1", now=seen)
    with pytest.raises(ReplayError):  # 30 s past the old retention, inside the margin
        accept_again(world, made.endpoint_id, "m1")


# --- 9. a rule's link proposal can be accepted -------------------------------------------------


def test_a_person_accepts_a_rules_link_proposal(world: World) -> None:
    a, b = world.record("L-1"), world.record("L-2")
    step = {
        "command": "AddLink",
        "args": {"from_id": "${subject_id}", "to_id": b, "relation": "references"},
    }
    rule_id = world.create_rule(
        key="linker", when={"event_types": ["Feed.Posted"], "hashtags": ["link"]}, then=[step],
    )  # fmt: skip
    world.switch_rule(rule_id, on=True)
    post = world.post("connect #link")
    world.worker().run_until_idle()
    [pending] = world.rows("SELECT proposal_id FROM cur_proposals WHERE status = 'pending'")
    assert post and a
    done = proposals.accept_or_fail(world.factory, proposal_id=pending["proposal_id"], by=PERSON)
    assert done.status == "accepted", done
    [link] = world.rows("SELECT source, status FROM cur_links WHERE to_id = :b", b=b)
    assert link["source"] == "rule"


def test_only_a_rules_own_proposal_may_carry_the_rule_link_source(world: World) -> None:
    from tl_core.services.commands import CreateRecord  # noqa: F401
    from tl_core.services.errors import InvalidProposalError
    from tl_core.services.links import AddLink

    a, b = world.record("L-1"), world.record("L-2")
    with world.factory() as uow, pytest.raises(InvalidProposalError):
        proposals.propose_for_rule(
            uow, proposer="svc:rule-x",
            command=AddLink(actor="svc:rule-x", source="proposal", scope=SCOPE, from_id=a, to_id=b,
                            link_source="manual"),
            summary="s", trigger_event_id="e", correlation_id="c",
        )  # fmt: skip
    assert ADMIN


# --- 9b. the hashtags the outbox reads (kept for D7; recorded in ADR-0017) ---------------------


def test_existing_webhook_filters_keep_their_meaning_and_hashtags_now_match_real_posts(
    world: World,
) -> None:
    from tl_core.integration.rules.engine import read_outbox
    from tl_core.webhooks.filters import WebhookFilter

    world.record("H-1")
    world.post("pump trip #safety")
    with world.factory(readonly=True) as uow:
        rows = read_outbox(uow.conn(), 0, 1_000)
    post = next(r for r in rows if r.event_type == "Feed.Posted")
    created = next(r for r in rows if r.event_type == "Record.Created")
    assert "safety" in post.hashtags
    assert WebhookFilter.from_dict({"hashtags": ["safety"]}).matches_row(post)
    assert not WebhookFilter.from_dict({"hashtags": ["other"]}).matches_row(post)
    assert not WebhookFilter.from_dict({"hashtags": ["safety"]}).matches_row(created)
    assert WebhookFilter.from_dict({"event_types": ["Feed.Posted"]}).matches_row(post)
    assert not WebhookFilter.from_dict({"event_types": ["Record.Created"]}).matches_row(post)
    assert created.hashtags == ()
