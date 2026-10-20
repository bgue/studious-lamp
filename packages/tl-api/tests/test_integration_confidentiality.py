"""ADR-0016 for the integration layer and the record threads (P1-I7 catch-up, FANOUT D17).

The ledger is the one of the walking test: an internal, a restricted, a privileged and an
unknown-class correspondence item, with their tokens. Automation (a rule, an enricher, a mapping)
acts as its service actor and must not read or act on what that actor may not read; the registry,
the event log and the webhooks must not carry what a value, an invocation or a thread says about a
record the reader may not read; a thread, a dispatch, a key and a mention must not be an oracle for
one. Readers: ``bob`` (a user), ``ctl`` (a document controller named on the privileged item),
``boss`` (an admin: restricted, not privileged), ``amy`` (a user named on the privileged item) and
``bot`` (an agent).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from harness import SCOPE, Harness
from sqlalchemy import text
from tl_core import confidentiality
from tl_core.confidentiality import Viewer, hidden_event_streams, use_viewer
from tl_core.integration.contract import RecordRef
from tl_core.integration.inbound.worker import RecordKeyLookup
from tl_core.integration.registry import list_registry
from tl_core.ledger import NewEvent
from tl_core.threads.dispatch import DispatchFromThread
from tl_core.threads.messages import post_message
from tl_core.threads.visibility import ThreadRecord, readable_record


def _walk() -> Any:
    """The confidentiality walk's cast and seed, loaded by path.

    ``tl-mcp`` has a test file with the same name, so a plain ``import test_confidentiality_walk``
    finds the wrong one when both packages are collected in one run.
    """
    import importlib.util
    import sys

    name = "tl_api_confidentiality_walk"
    if name not in sys.modules:
        path = Path(__file__).with_name("test_confidentiality_walk.py")
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


_WALK = _walk()
MAY_READ = _WALK.MAY_READ
Seed = _WALK.Seed
seed = _WALK.seed


@pytest.fixture
def harness(parity_harness: Harness) -> Harness:
    return parity_harness


@pytest.fixture
def world(harness: Harness, tmp_path: Path) -> Seed:
    return seed(harness, tmp_path)


def as_(harness: Harness, world: Seed, name: str) -> TestClient:
    client = harness.client_for(None)
    client.headers.update({"Authorization": f"Bearer {world.tokens[name]}"})
    return client


def threads_on(harness: Harness) -> None:
    """Switch the record threads on for the correspondence record type."""
    from tl_core import settings

    with harness.backend(False) as uow, confidentiality.system_view():
        for key, value in (
            ("threads.enabled", True),
            ("threads.enabled_types", ["correspondence.Correspondence"]),
        ):
            settings.set_setting(
                uow, key=key, layer="company", value=value, actor="user:a", source="t", reason="t"
            )


def readable(name: str, kind: str) -> bool:
    return kind in MAY_READ[name]


READERS = ["bob", "ctl", "boss", "amy", "bot"]
KINDS = ["open", "restricted", "privileged"]


def enrichment(value_id: str, target: str, state: str, value: str) -> NewEvent:
    return NewEvent(
        event_type="Enrichment.Proposed",
        payload={
            "value_id": value_id,
            "target": {"id": target, "record_type": "correspondence.Item"},
            "property_path": "enrich.e.p",
            "value": value,
            "enricher": "e",
            "enricher_version": "1",
            "confidence": 0.5,
            "inputs": [],
            "model_ref": None,
            "produced_at": "2026-10-19T00:00:00Z",
            "acceptance_state": state,
        },
    )


def propose(harness: Harness, world: Seed, kind: str, state: str = "proposed") -> str:
    value_id = f"V-{kind}-{state}".upper().ljust(26, "0")[:26]
    with harness.backend(False) as uow, confidentiality.system_view():
        uow.append(
            stream_id=value_id,
            stream_type="core.EnrichmentValue",
            scope=SCOPE,
            expected_version=0,
            events=[enrichment(value_id, world.ids[kind], state, f"VALUE-{kind}-{state}")],
            actor="svc:enricher-e",
            source="enricher:e@1",
            correlation_id="C" * 26,
        )
    return value_id


# --- the registry and the event log -----------------------------------------------------------


@pytest.mark.parametrize("reader", READERS)
def test_enrichment_values_follow_their_records_on_every_surface(
    harness: Harness, world: Seed, reader: str
) -> None:
    for kind in KINDS:
        propose(harness, world, kind)
    propose(harness, world, "restricted", "shadow")
    client = as_(harness, world, reader)
    answer = client.get("/integration/enrichments")
    if reader == "bot":  # an agent has no registry reads (FANOUT D12)
        assert answer.status_code == 403
    listed = answer.json().get("rows", [])
    events = client.get("/events", params={"type": "Enrichment.*"}).json()["events"]
    shown = {row["target_id"] for row in listed}
    seen = {str(e["payload"]["target"]["id"]) for e in events}
    admin = reader == "boss"  # the only admin: shadow values are the admin's
    for kind in KINDS:
        wanted = readable(reader, kind)
        assert (world.ids[kind] in shown) is (wanted and reader != "bot"), (reader, kind, "reg")
        assert (world.ids[kind] in seen) is wanted, (reader, kind, "events")
    shadows = [r for r in listed if r["acceptance_state"] == "shadow"]
    assert bool(shadows) is (admin and readable(reader, "restricted") and reader != "bot")
    assert bool([e for e in events if e["payload"]["acceptance_state"] == "shadow"]) is (
        admin and readable(reader, "restricted")
    )
    text_out = json.dumps([listed, events])
    for kind in KINDS:
        if not readable(reader, kind):
            assert f"VALUE-{kind}" not in text_out and world.ids[kind] not in text_out


def invocation(harness: Harness, world: Seed, kind: str) -> str:
    invocation_id = f"INV-{kind}".upper().ljust(26, "0")[:26]
    ref = {"id": world.ids[kind], "key": world.numbers[kind], "record_type": "x"}
    with harness.backend(False) as uow:
        uow.append(
            stream_id=invocation_id,
            stream_type="core.ActionInvocation",
            scope=SCOPE,
            expected_version=0,
            events=[
                NewEvent(
                    event_type="Action.Requested",
                    payload={
                        "invocation_id": invocation_id,
                        "action": "send_to_nde",
                        "action_version": 1,
                        "definition_id": "D" * 26,
                        "targets": [ref],
                        "parameters": {"note": f"PARAM-{kind}"},
                        "invoked_by": "user:ctl",
                        "invoked_at": "2026-10-19T00:00:00Z",
                        "requires_approval": False,
                    },
                )
            ],
            actor="user:ctl",
            source="api",
            correlation_id="C" * 26,
        )
    return invocation_id


@pytest.mark.parametrize("reader", READERS)
def test_action_invocations_follow_their_targets(
    harness: Harness, world: Seed, reader: str
) -> None:
    made = {kind: invocation(harness, world, kind) for kind in KINDS}
    client = as_(harness, world, reader)
    answer = client.get("/integration/invocations")
    listed = answer.json().get("rows", [])
    events = client.get("/events", params={"type": "Action.*"}).json()["events"]
    for kind in KINDS:
        wanted = readable(reader, kind)
        shown = made[kind] in {r["invocation_id"] for r in listed}
        assert shown is (wanted and reader != "bot"), (reader, kind)
        assert (made[kind] in {e["stream_id"] for e in events}) is wanted, (reader, kind)
    out = json.dumps([listed, events])
    for kind in KINDS:
        if not readable(reader, kind):
            assert f"PARAM-{kind}" not in out and world.numbers[kind] not in out


# --- automation reads as its service actor ----------------------------------------------------


def key_lookup(harness: Harness, viewer: Viewer, key: str) -> list[RecordRef]:
    with harness.backend(True) as uow, use_viewer(viewer):
        return RecordKeyLookup(uow.conn(), SCOPE).find(key, None)


def test_a_mapping_resolves_keys_as_its_endpoint_not_as_the_job_runner(
    harness: Harness, world: Seed
) -> None:
    user = Viewer(actor="svc:inbound-a.b", level=0, account="svc:inbound-a.b")
    controller = Viewer(actor="svc:inbound-a.c", level=1, account="svc:inbound-a.c")
    for kind, may_user, may_controller in (
        ("open", True, True),
        ("restricted", False, True),
        ("privileged", False, False),
        ("bogus", False, False),
    ):
        found_user = key_lookup(harness, user, world.numbers[kind])
        found_controller = key_lookup(harness, controller, world.numbers[kind])
        assert bool(found_user) is may_user, kind
        assert bool(found_controller) is may_controller, kind


def test_the_registry_reads_a_viewer_with_a_system_view_to_nothing_hidden(
    harness: Harness, world: Seed
) -> None:
    propose(harness, world, "restricted")
    with harness.backend(True) as uow:
        assert list_registry(uow.conn(), "enrichments") == []  # the default viewer is the lowest
        with confidentiality.system_view():
            assert len(list_registry(uow.conn(), "enrichments")) == 1


def synthetic_event(harness: Harness, subject: str, label: str) -> str:
    """A ledger event about ``subject`` of a type with no handler (it only reaches the outbox)."""
    with harness.backend(False) as uow, confidentiality.system_view():
        version = uow.ledger.stream_version(subject)
        made = uow.append(
            stream_id=subject,
            stream_type="probe.Probe",
            scope=SCOPE,
            expected_version=version,
            events=[NewEvent(event_type="Probe.Happened", payload={"label": label})],
            actor="user:ctl",
            source="test",
            correlation_id="C" * 26,
        )
    return made.events[0].event_id


def rule_of(harness: Harness, access: str) -> str:
    from tl_core.integration.rules.service import (
        CreateRule,
        EnableRule,
        handle_create_rule,
        handle_enable_rule,
    )

    with harness.backend(False) as uow:
        made = handle_create_rule(
            uow,
            CreateRule(
                actor="user:boss", source="test", scope=SCOPE, key=f"probe-{access}",
                title="Probe", access=access,  # type: ignore[arg-type]
                when={"event_types": ["Probe.Happened"]},
                then=[{"command": "PostToFeed", "args": {"body": "seen ${subject_id}"}}],
            ),
        )  # fmt: skip
        from tl_core.integration.rules.service import ReviseRule, handle_revise_rule

        handle_revise_rule(
            uow,
            ReviseRule(
                actor="user:boss", source="test", scope=SCOPE, rule_id=made.stream_id,
                changes={"mode": "act"}, reason="test",
            ),
        )  # fmt: skip
        handle_enable_rule(
            uow, EnableRule(actor="user:boss", source="test", scope=SCOPE, rule_id=made.stream_id)
        )
    return made.stream_id


def fired_events(harness: Harness) -> set[str]:
    with harness.backend(True) as uow:
        rows = uow.conn().execute(text("SELECT event_id FROM rule_firing WHERE outcome = 'fired'"))
        return {str(r[0]) for r in rows}


@pytest.mark.parametrize(
    ("access", "fires_on"),
    [("user", {"open"}), ("controller", {"open", "restricted"})],
)
def test_a_rule_acts_only_on_what_its_service_actor_may_read(
    harness: Harness, world: Seed, access: str, fires_on: set[str]
) -> None:
    from tl_api.commands import command_runner
    from tl_core.integration.rules.engine import RulesWorker

    rule_of(harness, access)
    events = {
        kind: synthetic_event(harness, world.ids[kind], f"{access}-{kind}")
        for kind in ("open", "restricted", "privileged", "bogus")
    }
    stats = RulesWorker(harness.backend, command_runner()).run_until_idle()
    done = fired_events(harness)
    for kind, event_id in events.items():
        assert (event_id in done) is (kind in fires_on), (access, kind)
    assert stats.hidden == 4 - len(fires_on)
    feed = json.dumps(harness.client_for(None).get("/feed", params={"scope": SCOPE}).json())
    for kind in ("restricted", "privileged", "bogus"):
        if kind not in fires_on:
            assert world.ids[kind] not in feed


def test_a_rules_dry_run_leaves_out_what_the_rule_could_not_read(
    harness: Harness, world: Seed
) -> None:
    from tl_api.commands import command_runner
    from tl_core.integration.rules.dryrun import dry_run_rule
    from tl_core.integration.rules.engine import load_rule

    rule_id = rule_of(harness, "user")
    events = {
        kind: synthetic_event(harness, world.ids[kind], f"dry-{kind}")
        for kind in ("open", "restricted", "privileged")
    }
    with harness.backend(True) as uow:
        stored = load_rule(uow.conn(), rule_id)
    assert stored is not None
    report = dry_run_rule(harness.backend, command_runner(), stored)
    assert {f.event_id for f in report.firings} == {events["open"]}


def test_an_enricher_reads_and_proposes_only_for_records_its_actor_may_read(
    harness: Harness, world: Seed
) -> None:
    from tl_core.integration.contract import EnrichmentResult, EnrichmentSubject, ProposedValue
    from tl_core.integration.enrichers.dispatcher import EnrichmentDispatcher
    from tl_core.integration.enrichers.registry import use_enrichers
    from tl_core.integration.enrichers.service import (
        RegisterEnricher,
        SetEnricherEnabled,
        handle_register_enricher,
        handle_set_enricher_enabled,
    )

    class Probe:
        name = "probe"
        version = "1"
        model_ref: str | None = None

        def accepts(self, subject: EnrichmentSubject) -> bool:
            return True

        def enrich(self, subject: EnrichmentSubject) -> EnrichmentResult:
            return EnrichmentResult(
                enricher=self.name,
                enricher_version=self.version,
                status="ok",
                values=[ProposedValue(property="label", value="alpha", confidence=0.95)],
                notes=["ADR-0008: no model"],
            )

    with harness.backend(False) as uow, use_enrichers({"probe": Probe}):
        made = handle_register_enricher(
            uow,
            RegisterEnricher(
                actor="user:boss", source="test", scope=SCOPE, name="probe",
                when={"event_types": ["Probe.Happened"]},
                properties=[{"name": "label", "kind": "string", "policy": "propose"}],
            ),
        )  # fmt: skip
        handle_set_enricher_enabled(
            uow,
            SetEnricherEnabled(
                actor="user:boss",
                source="test",
                scope=SCOPE,
                enricher_id=made.stream_id,
                enabled=True,
            ),
        )
    for kind in ("open", "restricted", "privileged"):
        synthetic_event(harness, world.ids[kind], f"enr-{kind}")
    with use_enrichers({"probe": Probe}):
        stats = EnrichmentDispatcher(harness.backend).run_until_idle()
    with harness.backend(True) as uow, confidentiality.system_view():
        targets = {
            str(r[0])
            for r in uow.conn().execute(text("SELECT target_id FROM cur_enrichment_value"))
        }
    assert targets == {world.ids["open"]}
    assert stats.hidden == 2


# --- record threads ---------------------------------------------------------------------------


@pytest.mark.parametrize("reader", READERS)
def test_a_thread_is_as_readable_as_its_record(harness: Harness, world: Seed, reader: str) -> None:
    client = as_(harness, world, reader)
    absent = "01J000000000000000000000"
    for kind in KINDS:
        rid = world.ids[kind]
        answers = (
            client.get(f"/records/{rid}/thread"),
            client.post(f"/records/{rid}/thread/preview", json={"text": "/notify @bob"}),
            client.post(
                "/commands/PostThreadMessage",
                json={"scope": SCOPE, "record_id": rid, "body": "TOKEN-THREAD"},
            ),
        )
        if readable(reader, kind):
            if reader != "bot":  # an agent has no thread reads over the API (it uses MCP)
                assert all(a.status_code != 404 for a in answers), (reader, kind)
            continue
        # a record the reader cannot read answers as a record that is not there: same status, same
        # words (the id in the message is the one the caller sent)
        for hidden, missing in zip(
            answers,
            (
                client.get(f"/records/{absent}/thread"),
                client.post(f"/records/{absent}/thread/preview", json={"text": "/notify @bob"}),
                client.post(
                    "/commands/PostThreadMessage",
                    json={"scope": SCOPE, "record_id": absent, "body": "TOKEN-THREAD"},
                ),
            ),
            strict=True,
        ):
            assert hidden.status_code == missing.status_code, (reader, kind)
            assert hidden.text.replace(rid, absent) == missing.text, (reader, kind)


@pytest.mark.parametrize("reader", READERS)
def test_thread_events_follow_their_record_in_the_event_log_and_the_streams(
    harness: Harness, world: Seed, reader: str
) -> None:
    with harness.backend(False) as uow, confidentiality.system_view():
        for kind in KINDS:
            record = readable_record(uow, world.ids[kind], actor="user:ctl")
            post_message(
                uow, record=record, actor="user:ctl", source="test",
                body=f"BODY-{kind}", check_enabled=False,
            )  # fmt: skip
    client = as_(harness, world, reader)
    events = client.get("/events", params={"type": "Thread.*"}).json()["events"]
    bodies = {str(e["payload"]["body"]) for e in events}
    for kind in KINDS:
        assert (f"BODY-{kind}" in bodies) is readable(reader, kind), (reader, kind)
    with harness.backend(True) as uow:
        for kind in KINDS:
            streams = [(f"thread:{world.ids[kind]}", "core.Thread")]
            who = Viewer(actor="user:bob", level=0, account="user:bob")
            hidden = hidden_event_streams(uow.conn(), streams, who)
            assert bool(hidden) is (kind != "open"), kind


def test_a_key_in_a_command_line_is_not_an_oracle_for_a_record_the_caller_cannot_read(
    harness: Harness, world: Seed
) -> None:
    threads_on(harness)
    bob = as_(harness, world, "bob")
    ctl = as_(harness, world, "ctl")
    rid = world.ids["open"]

    def problem(client: TestClient, key: str) -> dict[str, Any]:
        found = client.post(f"/records/{rid}/thread/preview", json={"text": f"/link {key}"})
        assert found.status_code == 200, found.text
        preview = found.json()["preview"]
        return preview["problems"][0] if preview["problems"] else {}

    missing = problem(bob, "NOSUCH-0001")
    assert missing["code"] == "unknown_key"
    for kind in ("restricted", "privileged", "bogus"):
        shown = problem(bob, world.numbers[kind])
        assert shown["code"] == missing["code"], kind
        assert (
            shown["message"].replace(world.numbers[kind][:80], "NOSUCH-0001") == missing["message"]
        )
    # the reader who may read the record gets it resolved
    assert problem(ctl, world.numbers["restricted"]) == {}


def test_a_mention_does_not_carry_a_thread_to_someone_who_cannot_read_its_record(
    harness: Harness, world: Seed
) -> None:
    threads_on(harness)
    ctl = as_(harness, world, "ctl")
    rid = world.ids["privileged"]  # ctl and amy read it, bob does not

    def problems(who: str) -> list[dict[str, Any]]:
        found = ctl.post(f"/records/{rid}/thread/preview", json={"text": f"/notify @{who}"})
        assert found.status_code == 200, found.text
        return found.json()["preview"]["problems"]

    assert problems("amy") == []
    assert problems("bob")[0]["code"] == "unknown_mention"
    assert problems("nobody-at-all")[0]["code"] == "unknown_mention"
    assert problems("bob")[0]["message"].replace("bob", "x") == problems("nobody-at-all")[0][
        "message"
    ].replace("nobody-at-all", "x")


def test_a_dispatch_proposal_is_listed_only_to_those_who_can_read_its_record(
    harness: Harness, world: Seed
) -> None:
    from tl_core.services import proposals as props

    with harness.backend(False) as uow, confidentiality.system_view():
        for kind in ("open", "restricted"):
            record = readable_record(uow, world.ids[kind], actor="user:ctl")
            props.propose(
                uow,
                tool="propose_dispatch",
                agent="agent:bot",
                command=DispatchFromThread(
                    actor="agent:bot", source="mcp:bot", scope=SCOPE, record_id=record.id,
                    text="/notify @amy", token="a" * 64,
                ),
                summary=f"Dispatch on {kind}",
            )  # fmt: skip
    # a plain reader lists the one on the open record and not the one on the restricted record
    with harness.backend(True) as uow, use_viewer(Viewer(actor="user:bob", level=0)):
        listed = props.list_proposals(uow.conn(), SCOPE, status=None)
    carried = json.dumps([p.command for p in listed])
    assert world.ids["open"] in carried and world.ids["restricted"] not in carried


def test_the_thread_record_helper_is_the_confidentiality_filter(
    harness: Harness, world: Seed
) -> None:
    with harness.backend(True) as uow:
        for name, actor in (("bob", "user:bob"), ("ctl", "user:ctl"), ("amy", "user:amy")):
            for kind in KINDS:
                try:
                    found: ThreadRecord | None = readable_record(uow, world.ids[kind], actor=actor)
                except Exception:
                    found = None
                assert (found is not None) is readable(name, kind), (name, kind)
