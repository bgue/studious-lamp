"""The ``job`` executor runs registered pure jobs and never raises (P1-I7-T02a)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from tl_core.integration import contract
from tl_core.integration.action_jobs import EchoJob
from tl_core.integration.contract import (
    ACTION_JOB_ENTRY_POINT,
    ACTION_MAX_RESULT_BYTES,
    ActionJob,
    ActionOutcome,
    ActionRequest,
    JobExecutorConfig,
    RecordRef,
    WebhookExecutorConfig,
)
from tl_core.integration.executors import job as job_module
from tl_core.integration.executors.job import JobExecutor, use_jobs

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tests" / "contract"))

from test_integration_contract import check_executor_contract  # noqa: E402


def request(job: str = "echo", **changes: Any) -> ActionRequest:
    base: dict[str, Any] = {
        "invocation_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PB",
        "action": "export_json",
        "action_version": 1,
        "scope": "project:P123",
        "targets": [RecordRef(id="r1", key="47-1234-W012", record_type="core.Record", version=3)],
        "parameters": {"method": "RT"},
        "invoked_by": "user:jsmith",
        "attempt": 1,
        "config": JobExecutorConfig(job=job),
    }
    return ActionRequest.model_validate({**base, **changes})


class Job:
    """A job that does whatever ``work`` says."""

    version = "1"
    side_effect_class: contract.SideEffectClass = "read"

    def __init__(self, name: str, work: Any) -> None:
        self.name = name
        self._work = work

    def run(self, request: ActionRequest) -> ActionOutcome:
        return self._work(request)


def registered(name: str, work: Any) -> Any:
    return use_jobs({name: lambda: Job(name, work)})


def failure_code(outcome: ActionOutcome) -> str:
    assert outcome.status == "failed" and outcome.problems
    return outcome.problems[0].code


def test_it_passes_the_shared_executor_contract_checks() -> None:
    with use_jobs({"echo": EchoJob}):
        check_executor_contract(
            JobExecutor(),
            [
                request(),
                request(parameters={}, targets=[]),
                request(job="missing"),
                request(config=WebhookExecutorConfig(url="https://x.example/h")),
            ],
        )


def test_the_example_job_is_an_action_job_and_echoes_the_request() -> None:
    assert isinstance(EchoJob(), ActionJob)
    with use_jobs({"echo": EchoJob}):
        outcome = JobExecutor().execute(request())
    assert outcome.status == "completed"
    assert outcome.result == {
        "action": "export_json",
        "attempt": 1,
        "parameters": {"method": "RT"},
        "targets": ["47-1234-W012"],
    }


def test_the_executor_is_the_job_kind() -> None:
    assert JobExecutor().kind == "job"


def test_the_example_job_is_registered_under_the_entry_point_group() -> None:
    """Needs ``uv sync --all-packages`` after the entry point was added to ``tl-core``."""
    outcome = JobExecutor().execute(request())
    assert outcome.status == "completed", outcome.problems


def test_a_job_that_is_not_registered_is_a_failure_not_an_exception() -> None:
    with use_jobs({}):
        assert failure_code(JobExecutor().execute(request(job="nope"))) == "unknown_job"


def test_a_webhook_config_is_not_for_this_executor() -> None:
    config = WebhookExecutorConfig(url="https://x.example/h")
    with use_jobs({"echo": EchoJob}):
        outcome = JobExecutor().execute(request(config=config))
    assert failure_code(outcome) == "wrong_executor"


def test_the_text_of_an_exception_is_never_copied_into_a_message() -> None:
    def boom(_: ActionRequest) -> ActionOutcome:
        raise ValueError("secret value from /home/user/private.txt")

    with registered("boom", boom):
        outcome = JobExecutor().execute(request(job="boom"))
    assert failure_code(outcome) == "job_error"
    message = outcome.problems[0].message
    assert "ValueError" in message
    assert "secret" not in message and "/home" not in message


def test_any_exception_a_job_raises_is_caught() -> None:
    for exc in (RecursionError("deep"), MemoryError("big"), KeyError("k"), OSError("disk")):

        def boom(_: ActionRequest, exc: Exception = exc) -> ActionOutcome:
            raise exc

        with registered("boom", boom):
            assert failure_code(JobExecutor().execute(request(job="boom"))) == "job_error"


def test_a_job_that_does_not_return_an_outcome_is_a_failure() -> None:
    with registered("odd", lambda _: {"status": "completed"}):
        assert failure_code(JobExecutor().execute(request(job="odd"))) == "bad_outcome"


def test_a_result_over_the_limit_is_refused_not_cut() -> None:
    big = ActionOutcome(status="completed", result={"text": "x" * (ACTION_MAX_RESULT_BYTES + 1)})
    with registered("big", lambda _: big):
        assert failure_code(JobExecutor().execute(request(job="big"))) == "result_too_large"
    exact = {"t": "x" * (ACTION_MAX_RESULT_BYTES - 8)}  # `{"t":"..."}` is 8 bytes of framing
    fits = ActionOutcome(status="completed", result=exact)
    with registered("fits", lambda _: fits):
        assert JobExecutor().execute(request(job="fits")).status == "completed"


def test_a_result_that_is_not_json_is_a_failure() -> None:
    odd = ActionOutcome(status="completed", result={"when": object()})
    with registered("odd", lambda _: odd):
        assert failure_code(JobExecutor().execute(request(job="odd"))) == "bad_outcome"
    loop: dict[str, Any] = {}
    loop["self"] = loop
    cyc = ActionOutcome(status="completed", result=loop)
    with registered("cyc", lambda _: cyc):
        assert failure_code(JobExecutor().execute(request(job="cyc"))) == "bad_outcome"


def test_a_failed_outcome_of_the_job_passes_through_with_its_retry_flag() -> None:
    wanted = ActionOutcome(
        status="failed",
        retryable=True,
        problems=[contract.Problem(code="busy", message="Try again.")],
    )
    with registered("busy", lambda _: wanted):
        assert JobExecutor().execute(request(job="busy")) == wanted


def test_the_code_registered_under_a_name_must_be_that_job() -> None:
    with use_jobs({"echo": lambda: Job("other", lambda _: ActionOutcome(status="completed"))}):
        assert failure_code(JobExecutor().execute(request())) == "job_mismatch"
    with use_jobs({"echo": lambda: object()}):
        assert failure_code(JobExecutor().execute(request())) == "job_mismatch"


def test_a_job_that_cannot_be_built_or_loaded_is_a_failure() -> None:
    def build() -> Any:
        raise RuntimeError("no module named /srv/x")

    with use_jobs({"echo": build}):
        outcome = JobExecutor().execute(request())
    assert failure_code(outcome) == "job_unavailable"
    assert "/srv" not in outcome.problems[0].message


def test_an_entry_point_that_does_not_load_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class Broken:
        name = "echo"

        def load(self) -> Any:
            raise RuntimeError("boom /srv/x")

    def fake(group: str) -> list[Broken]:
        assert group == ACTION_JOB_ENTRY_POINT
        return [Broken()]

    monkeypatch.setattr(job_module, "entry_points", fake)
    outcome = JobExecutor().execute(request())
    assert failure_code(outcome) == "job_unavailable"
    assert "/srv" not in outcome.problems[0].message


def test_use_jobs_restores_what_was_there() -> None:
    with use_jobs({"a": EchoJob}):
        with use_jobs({}):
            assert failure_code(JobExecutor().execute(request(job="a"))) == "unknown_job"
        assert JobExecutor().execute(request(job="a")).status in ("completed", "failed")
    assert JobExecutor().execute(request()).status == "completed"  # the entry point again


def test_the_entry_point_with_the_asked_name_is_the_one_loaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Point:
        def __init__(self, name: str, loaded: Any) -> None:
            self.name = name
            self._loaded = loaded

        def load(self) -> Any:
            if self._loaded is None:
                raise AssertionError("an entry point of another name was loaded")
            return self._loaded

    monkeypatch.setattr(
        job_module,
        "entry_points",
        lambda group: [Point("other", None), Point("echo", EchoJob), Point("zzz", None)],
    )
    assert JobExecutor().execute(request()).status == "completed"
    assert failure_code(JobExecutor().execute(request(job="absent"))) == "unknown_job"


def test_a_result_nested_past_the_recursion_limit_is_a_failure() -> None:
    deep: dict[str, Any] = {}
    for _ in range(100_000):
        deep = {"a": deep}
    nested = ActionOutcome(status="completed", result=deep)
    with registered("deep", lambda _: nested):
        assert failure_code(JobExecutor().execute(request(job="deep"))) == "bad_outcome"


def test_the_echo_job_names_a_target_without_a_key_by_its_id() -> None:
    bare = RecordRef(id="r-9", record_type="core.Record")
    with use_jobs({"echo": EchoJob}):
        outcome = JobExecutor().execute(request(targets=[bare]))
    assert outcome.result is not None and outcome.result["targets"] == ["r-9"]
    assert outcome.notes == ["echo"]
