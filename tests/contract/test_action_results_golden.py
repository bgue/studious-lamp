"""Golden cases for what an action returns (P1-I7-T08). Provided; do not edit.

``tests/golden/actions/results.json`` lists requests to the two Phase 1 executors with the answer
the world gave (a scripted receiver for ``webhook``, the registered jobs below for ``job``) and the
outcome that must come back. The file is the ticket's work: every category needs at least the
number of cases in ``MINIMUM``, and together the cases must produce every failure code in
``REQUIRED_CODES``. Nothing here touches a network: the transport is scripted and the resolver is
a table.

A webhook case: ``{"name", "category", "url"?, "secret"?: "none", "answer": {"status", "excerpt"?,
"truncated"?}, "expect": {...}}`` (a ``status`` of ``null`` is no answer at all). A job case:
``{"name", "category", "job", "parameters"?, "targets"?, "expect": {...}}``. ``expect`` holds
``status``, ``retryable`` (default false), ``http_status`` (default none) and either ``result``
(exactly) or ``problem_code``. A failed outcome never carries a result.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tl_core.integration.action_jobs import EchoJob
from tl_core.integration.contract import (
    ActionOutcome,
    ActionRequest,
    JobExecutorConfig,
    Problem,
    RecordRef,
    WebhookExecutorConfig,
)
from tl_core.integration.executors.job import JobExecutor, use_jobs
from tl_core.integration.executors.webhook import WebhookExecutor
from tl_core.webhooks.egress import EgressPolicy
from tl_core.webhooks.signing import SigningSecret, generate_secret
from tl_core.webhooks.testing import ScriptedTransport
from tl_core.webhooks.transport import TransportResult

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "actions" / "results.json"
MINIMUM = {
    "webhook_completed": 4,  # an object, another JSON value, plain text, an empty body
    "webhook_retryable": 5,  # 408, 425, 429, 500 and 503 among them
    "webhook_final": 4,  # a 4xx that is not retried
    "webhook_redirect": 2,
    "webhook_no_answer": 1,
    "webhook_too_large": 1,
    "webhook_refused": 5,  # egress and resolution: never connected to
    "webhook_secret": 1,
    "job_completed": 2,
    "job_failed": 6,  # unknown, raises, wrong name, not an outcome, not JSON, too large, ...
}
REQUIRED_CODES = {
    "http_error", "redirect", "network_error", "result_too_large", "egress_denied",
    "unresolvable", "no_secret", "unknown_job", "job_error", "job_mismatch", "bad_outcome",
    "job_unavailable",
}  # fmt: skip
HOSTS = {"nde.example.net": ["93.184.216.34"], "internal.example.net": ["10.1.2.3"]}
DEFAULT_URL = "https://nde.example.net/hooks/request"
SECRET = SigningSecret(generate_secret())


class Raises:
    name = "raises"
    version = "1"
    side_effect_class = "read"

    def run(self, request: ActionRequest) -> ActionOutcome:
        raise RuntimeError("secret detail /home/x/y")


class Mismatch(EchoJob):
    name = "something-else"


class ReturnsText:
    name = "returns-text"
    version = "1"
    side_effect_class = "read"

    def run(self, request: ActionRequest) -> Any:
        return "done"


class Huge:
    name = "huge"
    version = "1"
    side_effect_class = "read"

    def run(self, request: ActionRequest) -> ActionOutcome:
        return ActionOutcome(status="completed", result={"blob": "x" * 70_000})


class NotJson:
    name = "not-json"
    version = "1"
    side_effect_class = "read"

    def run(self, request: ActionRequest) -> ActionOutcome:
        return ActionOutcome(status="completed", result={"when": {1, 2, 3}})


class Refuses:
    name = "refuses"
    version = "1"
    side_effect_class = "read"

    def run(self, request: ActionRequest) -> ActionOutcome:
        return ActionOutcome(
            status="failed", problems=[Problem(code="no_capacity", message="Try later.")]
        )


def broken_factory() -> Any:
    raise ImportError("cannot load /somewhere/else")


JOBS = {
    "echo": EchoJob,
    "raises": Raises,
    "mismatch": Mismatch,
    "returns-text": ReturnsText,
    "huge": Huge,
    "not-json": NotJson,
    "refuses": Refuses,
    "broken": broken_factory,
}


def load() -> dict[str, list[dict[str, Any]]]:
    return json.loads(GOLDEN.read_text("utf-8"))


def request(config: Any, **changes: Any) -> ActionRequest:
    base: dict[str, Any] = {
        "invocation_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PB",
        "action": "send_to_nde",
        "action_version": 2,
        "scope": "project:P123",
        "targets": [RecordRef(id="r1", key="47-1234-W012", record_type="core.Record", version=3)],
        "parameters": {"method": "RT"},
        "invoked_by": "user:jsmith",
        "attempt": 1,
        "config": config,
    }
    return ActionRequest.model_validate({**base, **changes})


def run_webhook(case: dict[str, Any]) -> tuple[ActionOutcome, ScriptedTransport]:
    answer = case["answer"]
    transport = ScriptedTransport(
        default=TransportResult(
            status=answer["status"],
            latency_ms=1,
            excerpt=answer.get("excerpt", ""),
            truncated=answer.get("truncated", False),
        )
    )
    secrets = [] if case.get("secret") == "none" else [SECRET]
    executor = WebhookExecutor(
        policy=EgressPolicy((), lambda host, port: HOSTS.get(host, [])),
        transport=transport,
        secrets=lambda secret_id: secrets,
        clock=lambda: 1_800_000_000.0,
    )
    config = WebhookExecutorConfig(url=case.get("url", DEFAULT_URL), secret_id="S" * 26)
    return executor.execute(request(config)), transport


def run_job(case: dict[str, Any]) -> ActionOutcome:
    targets = [
        RecordRef(id=f"r{n}", key=key, record_type="core.Record")
        for n, key in enumerate(case.get("targets", []), 1)
    ]
    config = JobExecutorConfig(job=case["job"])
    with use_jobs(JOBS):
        return JobExecutor().execute(
            request(config, targets=targets, parameters=case.get("parameters", {}))
        )


def check_expectation(case: dict[str, Any], outcome: ActionOutcome) -> None:
    expect = case["expect"]
    name = case["name"]
    assert outcome.status == expect["status"], (name, outcome.problems)
    assert outcome.retryable is expect.get("retryable", False), name
    assert outcome.http_status == expect.get("http_status"), name
    if outcome.status == "completed":
        assert outcome.result == expect["result"], name
        assert not outcome.problems, name
    else:
        assert outcome.result is None, name
        assert [p.code for p in outcome.problems] == [expect["problem_code"]], name
        for problem in outcome.problems:  # nothing from the world is echoed back
            assert "/home/" not in problem.message and "93.184" not in problem.message, name
            assert "10.1.2.3" not in problem.message and "secret detail" not in problem.message


WEBHOOK_CASES = load()["webhook"]
JOB_CASES = load()["job"]


def test_every_category_has_enough_cases_and_every_failure_code_is_seen() -> None:
    found: dict[str, int] = {}
    for case in [*WEBHOOK_CASES, *JOB_CASES]:
        found[case["category"]] = found.get(case["category"], 0) + 1
    assert set(found) <= set(MINIMUM), f"unknown categories: {set(found) - set(MINIMUM)}"
    for category, least in MINIMUM.items():
        assert found.get(category, 0) >= least, f"{category}: {found.get(category, 0)} of {least}"
    codes = {
        c["expect"]["problem_code"]
        for c in [*WEBHOOK_CASES, *JOB_CASES]
        if c["expect"]["status"] == "failed"
    }
    assert REQUIRED_CODES <= codes, f"no case for {sorted(REQUIRED_CODES - codes)}"
    names = [c["name"] for c in [*WEBHOOK_CASES, *JOB_CASES]]
    assert len(names) == len(set(names)), "a case name is used twice"
    assert {c["job"] for c in JOB_CASES} <= set(JOBS) | {"missing-job"}, "an unknown test job"


@pytest.mark.parametrize("case", WEBHOOK_CASES, ids=lambda c: c["name"])
def test_a_webhook_case_gives_the_recorded_outcome(case: dict[str, Any]) -> None:
    outcome, transport = run_webhook(case)
    check_expectation(case, outcome)
    if case["category"] in ("webhook_refused", "webhook_secret"):
        assert transport.sent == [], "nothing is sent when the call is refused first"
    else:
        assert len(transport.sent) == 1


@pytest.mark.parametrize("case", JOB_CASES, ids=lambda c: c["name"])
def test_a_job_case_gives_the_recorded_outcome(case: dict[str, Any]) -> None:
    check_expectation(case, run_job(case))
