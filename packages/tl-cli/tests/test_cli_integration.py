"""`tl integration serve --once` and `status`: the workers make the layer work end to end (P1-I7).

Setup goes through the services, so these tests do not depend on the command groups of the tickets.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from intcli_support import (
    ADMIN,
    SCOPE,
    deliver,
    lines,
    make_endpoint,
    make_record,
    new_env,
    ok,
    plugins,  # noqa: F401  (a fixture)
    post,
    register_app,
    run,
    sql,
)
from tl_adapters.db import DbTarget, open_uow
from tl_core.integration.actions.service import DefineAction, define_action, handle_invoke_action
from tl_core.integration.contract import InvokeAction
from tl_core.integration.enrichers.service import (
    RegisterEnricher,
    SetEnricherEnabled,
    handle_register_enricher,
    handle_set_enricher_enabled,
)
from tl_core.integration.rules.service import (
    CreateRule,
    EnableRule,
    ReviseRule,
    handle_create_rule,
    handle_enable_rule,
    handle_revise_rule,
)
from tl_core.services.settings import ChangeSetting, handle_change_setting


@pytest.fixture
def env(new_db: Callable[[], DbTarget], tmp_path: Path, plugins: None) -> dict[str, str]:  # noqa: F811
    values = new_env(new_db, tmp_path)
    register_app(values)
    return values


def act_rule(env: dict[str, str]) -> None:
    with open_uow(env["TL_DB"]) as uow:
        made = handle_create_rule(
            uow,
            CreateRule(
                actor=ADMIN, source="test", scope=SCOPE, key="hse-notify", title="Notify HSE",
                when={"event_types": ["Feed.Posted"], "hashtags": ["safety"]},
                then=[{"command": "PostToFeed", "args": {"body": "HSE notified"}}],
            ),
        )  # fmt: skip
    with open_uow(env["TL_DB"]) as uow:
        handle_revise_rule(
            uow,
            ReviseRule(
                actor=ADMIN, source="test", scope=SCOPE, rule_id=made.stream_id,
                changes={"mode": "act"}, reason="go",
            ),
        )  # fmt: skip
        handle_enable_rule(
            uow, EnableRule(actor=ADMIN, source="test", scope=SCOPE, rule_id=made.stream_id)
        )


def serve(env: dict[str, str]) -> dict[str, str]:
    """``rules 3 enrich 5 jobs 1 killed 0`` as a dict."""
    parts = ok(run(env, "integration", "serve", "--once")).stdout.split()
    return dict(zip(parts[::2], parts[1::2], strict=True))


def posts(env: dict[str, str]) -> list[str]:
    rows = sql(env, "SELECT payload FROM events WHERE event_type = 'Feed.Posted' ORDER BY seq")
    return [str(r["payload"]) for r in rows]


def test_serve_once_runs_a_rule_as_its_service_actor(env: dict[str, str]) -> None:
    act_rule(env)
    post(env, "pump 7 tripped #safety")
    result = serve(env)
    assert int(result["rules"]) > 0
    made = sql(env, "SELECT actor, source FROM events WHERE actor = 'svc:rule-hse-notify'")
    assert [(m["actor"], m["source"].split("/")[0]) for m in made] == [
        ("svc:rule-hse-notify", "rule:hse-notify@2")
    ]
    assert any("HSE notified" in p for p in posts(env))
    assert serve(env)["rules"] == "0"  # nothing new: idle


def test_serve_once_maps_a_received_delivery(env: dict[str, str]) -> None:
    make_endpoint(env, "erp/orders", '{"command": "PostToFeed", "args": {"body": $.text}}')
    deliver(env, "erp/orders", {"text": "order 1 shipped"})
    result = serve(env)
    assert result["jobs"] == "1"
    assert sql(env, "SELECT state FROM int_delivery")[0]["state"] == "applied"
    assert any("order 1 shipped" in p for p in posts(env))


def test_serve_once_lets_an_enricher_propose(env: dict[str, str]) -> None:
    with open_uow(env["TL_DB"]) as uow:
        made = handle_register_enricher(
            uow,
            RegisterEnricher(
                actor=ADMIN, source="test", scope=SCOPE, name="fake",
                when={"event_types": ["Record.Created"]},
                properties=[{"name": "label", "kind": "string"}],
            ),
        )  # fmt: skip
        handle_set_enricher_enabled(
            uow,
            SetEnricherEnabled(
                actor=ADMIN, source="test", scope=SCOPE, enricher_id=made.stream_id, enabled=True
            ),
        )
    make_record(env, "ISD-001", "Pump datasheet")
    serve(env)
    values = sql(env, "SELECT acceptance_state, property_path FROM cur_enrichment_value")
    assert [(v["acceptance_state"], v["property_path"]) for v in values] == [
        ("proposed", "enrich.fake.label")
    ]


def test_serve_once_runs_an_invoked_action(env: dict[str, str]) -> None:
    with open_uow(env["TL_DB"]) as uow:
        define_action(
            uow,
            DefineAction(
                actor=ADMIN, source="test", scope=SCOPE, name="echo_it", label="Echo",
                executor="job", executor_config={"job": "echo"}, side_effect_class="read",
            ),
        )  # fmt: skip
    record = make_record(env, "W-1")
    with open_uow(env["TL_DB"]) as uow:
        handle_invoke_action(
            uow,
            InvokeAction(
                actor=ADMIN, source="test", scope=SCOPE, action="echo_it", targets=[record]
            ),
        )
    serve(env)
    assert sql(env, "SELECT status FROM cur_action_invocation")[0]["status"] == "completed"


def test_the_kill_switch_stops_the_workers_and_status_says_so(env: dict[str, str]) -> None:
    act_rule(env)
    make_endpoint(env, "erp/orders", '{"command": "PostToFeed", "args": {"body": $.text}}')
    post(env, "pump 7 tripped #safety")
    deliver(env, "erp/orders", {"text": "order 1"})
    with open_uow(env["TL_DB"]) as uow:
        handle_change_setting(
            uow,
            ChangeSetting(
                actor=ADMIN, source="test", scope="company", key="integration.kill_switch",
                layer="company", value=True, reason="test", accept_risk=True,
            ),
        )  # fmt: skip
    result = serve(env)
    assert int(result["killed"]) >= 1
    assert sql(env, "SELECT state FROM int_delivery")[0]["state"] == "killed"
    assert not any("HSE notified" in p for p in posts(env))
    assert lines(run(env, "integration", "status"))[0] == "kill_switch on"


def test_status_prints_cursors_queues_and_deliveries(env: dict[str, str]) -> None:
    make_endpoint(env, "erp/orders", '{"command": "PostToFeed", "args": {"body": $.text}}')
    deliver(env, "erp/orders", {"text": "order 1"})
    before = lines(ok(run(env, "integration", "status")))
    assert before[0] == "kill_switch off" and before[1] == "cursor rules 0"
    assert before[2] == "cursor enrichers 0" and before[3].startswith("last_seq ")
    assert "jobs inbound.map queued 1" in before and "deliveries queued 1" in before
    serve(env)
    after = lines(ok(run(env, "integration", "status")))
    assert after[1] != "cursor rules 0" and "deliveries applied 1" in after
    assert "jobs inbound.map done 1" in after
