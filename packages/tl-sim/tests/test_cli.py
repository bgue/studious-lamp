"""``tl sim``: options, output lines, exit codes. The five operations are replaced by fakes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx2
import pytest
from tl_api.client.base import ApiUnavailableError
from tl_sim import api, cli
from tl_sim.state import RunError
from typer.testing import CliRunner

RUNNER = CliRunner()


class Calls:
    """Records what the CLI asked for, answers with canned data."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.log: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.assert_ok = True
        self.fail_with: Exception | None = None
        for name in ("sim_create", "sim_advance", "sim_inject", "sim_status", "sim_assert"):
            monkeypatch.setattr(api, name, self._make(name))

    def _make(self, name: str) -> Any:
        def call(*args: Any, **kwargs: Any) -> dict[str, Any]:
            self.log.append((name, args, kwargs))
            if self.fail_with is not None:
                raise self.fail_with
            return getattr(self, "_" + name)(*args, **kwargs)

        return call

    @staticmethod
    def _sim_create(env: api.SimEnv, scenario: str, run_id: str | None = None) -> dict[str, Any]:
        return {
            "run_id": run_id or "r1a2b3c",
            "scope": "project:sim-r1a2b3c",
            "ground_truth": {"record.created": 9, "link.added": 6},
        }

    @staticmethod
    def _sim_advance(
        env: api.SimEnv, run_id: str | None = None, *, days: int = 1
    ) -> dict[str, Any]:
        return {
            "run_id": run_id or "r1a2b3c",
            "dates": [f"2026-11-0{2 + n}" for n in range(days)],
            "ground_truth_written": 20 * days,
            "ground_truth": {"record.created": 9 + 5 * days, "post.created": days},
        }

    @staticmethod
    def _sim_inject(
        env: api.SimEnv, run_id: str | None, event: str, args: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {"run_id": "r1a2b3c", "queued": {"day": 1, "event": event, "args": args or {}}}

    @staticmethod
    def _sim_status(env: api.SimEnv, run_id: str | None = None) -> dict[str, Any]:
        return {
            "run_id": "r1a2b3c",
            "scope": "project:sim-r1a2b3c",
            "scenario": "north-unit-small",
            "seed": 4711,
            "day": 2,
            "next_date": "2026-11-04",
            "last_date": "2026-11-03",
            "digest": "ab" * 32,
            "ground_truth": {"record.created": 19, "post.created": 2},
            "pending": [{"event": "post"}],
            "interrupted": False,
        }

    def _sim_assert(self, env: api.SimEnv, run_id: str | None = None) -> dict[str, Any]:
        failures = (
            []
            if self.assert_ok
            else [
                {
                    "check": "record.created",
                    "ref": "K-1",
                    "field": "title",
                    "expected": "A",
                    "actual": "B",
                },
                {
                    "check": "unexpected_record",
                    "ref": "K-9",
                    "field": "key",
                    "expected": None,
                    "actual": "Stray",
                },
            ]
        )
        return {
            "run_id": "r1a2b3c",
            "ok": self.assert_ok,
            "checked": 40,
            "counts": {},
            "failures": failures,
        }

    def names(self) -> list[str]:
        return [name for name, _, _ in self.log]


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> Calls:
    for var in ("TL_SIM_DIR", "TL_API_URL", "TL_TOKENS"):
        monkeypatch.delenv(var, raising=False)
    return Calls(monkeypatch)


def invoke(*args: str, env: dict[str, str] | None = None) -> Any:
    result = RUNNER.invoke(cli.app, list(args), env=env)
    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    return result


def test_the_group_options_become_the_environment_of_every_call(calls: Calls) -> None:
    invoke("--sim-dir", "/x/sim", "--api-url", "http://h:1", "--tokens", "/x/t.json", "status")
    env = calls.log[0][1][0]
    assert env == api.SimEnv(Path("/x/sim"), "http://h:1", Path("/x/t.json"))


def test_the_defaults_and_the_environment_variables(calls: Calls) -> None:
    invoke("status")
    assert calls.log[0][1][0] == api.SimEnv()
    invoke("status", env={"TL_SIM_DIR": "/e/sim", "TL_API_URL": "http://e:2", "TL_TOKENS": "/e/t"})
    assert calls.log[1][1][0] == api.SimEnv(Path("/e/sim"), "http://e:2", Path("/e/t"))


def test_create_prints_the_run_the_scope_and_the_seed_count(calls: Calls) -> None:
    result = invoke("create", "north-unit-small")
    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        "run r1a2b3c",
        "scope project:sim-r1a2b3c",
        "seeded 9 records",
    ]
    assert calls.log[0][1][1] == "north-unit-small"
    invoke("create", "x.yaml", "--run-id", "rmine")
    assert calls.log[1][2] == {"run_id": "rmine"}


def test_advance_prints_each_day_and_the_ground_truth_written(calls: Calls) -> None:
    result = invoke("advance", "--days", "2", "--run", "r1a2b3c")
    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        "played 2026-11-02",
        "played 2026-11-03",
        "ground truth +40 (21 lines)",
    ]
    assert calls.log[0][1][1] == "r1a2b3c" and calls.log[0][2] == {"days": 2}
    assert invoke("advance", "--days", "0").exit_code != 0


def test_inject_parses_arguments_and_keeps_numbers_as_numbers(calls: Calls) -> None:
    result = invoke(
        "inject", "material_late", "--arg", "item=6in flange", "--arg", "days=21", "--run", "r1"
    )
    assert result.exit_code == 0
    assert result.stdout.strip() == "queued material_late for the next day played"
    name, args, _ = calls.log[0]
    assert (name, args[1], args[2], args[3]) == (
        "sim_inject",
        "r1",
        "material_late",
        {"item": "6in flange", "days": 21},
    )


@pytest.mark.parametrize("bad", ["noequals", "=value"])
def test_inject_refuses_an_argument_that_is_not_key_value(calls: Calls, bad: str) -> None:
    result = invoke("inject", "post", "--arg", bad)
    assert result.exit_code == 1
    assert "error: --arg must look like key=value" in result.stderr
    assert calls.log == []


def test_status_prints_key_value_lines_then_the_counts(calls: Calls) -> None:
    result = invoke("status")
    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        "run: r1a2b3c",
        "scope: project:sim-r1a2b3c",
        "scenario: north-unit-small",
        "seed: 4711",
        "day: 2",
        "next_date: 2026-11-04",
        "digest: " + "ab" * 32,
        "  post.created: 2",
        "  record.created: 19",
        "pending: 1",
    ]


def test_assert_that_passes_exits_zero(calls: Calls) -> None:
    result = invoke("assert")
    assert (result.exit_code, result.stdout.strip()) == (0, "ok: 40 checks")


def test_assert_that_fails_lists_every_failure_and_exits_one(calls: Calls) -> None:
    calls.assert_ok = False
    result = invoke("assert")
    assert result.exit_code == 1
    assert result.stdout.splitlines() == [
        "FAILED: 2 of 40 checks",
        "  record.created K-1 title: expected 'A', found 'B'",
        "  unexpected_record K-9 key: expected None, found 'Stray'",
    ]


def test_run_creates_advances_the_scenarios_duration_and_asserts_in_that_order(
    calls: Calls,
) -> None:
    result = invoke("run", "seed-xs")
    assert result.exit_code == 0
    assert calls.names() == ["sim_create", "sim_advance", "sim_assert"]
    assert calls.log[1][2] == {"days": 3} and calls.log[1][1][1] == "r1a2b3c"
    assert result.stdout.splitlines()[0] == "run r1a2b3c"
    assert result.stdout.splitlines()[-1] == "ok: 40 checks"


def test_run_exits_one_when_the_assertion_fails(calls: Calls) -> None:
    calls.assert_ok = False
    result = invoke("run", "seed-xs")
    assert result.exit_code == 1 and "FAILED" in result.stdout


def test_seed_runs_the_bundled_scenario_of_the_scale(calls: Calls) -> None:
    assert invoke("seed", "--scale", "s").exit_code == 0
    assert calls.log[0][1][1] == "seed-s" and calls.log[1][2] == {"days": 10}
    invoke("seed")
    assert calls.log[3][1][1] == "seed-xs"


def test_seed_refuses_an_unknown_scale(calls: Calls) -> None:
    result = invoke("seed", "--scale", "xl")
    assert result.exit_code == 1 and "--scale must be one of xs, s, m" in result.stderr
    assert calls.log == []


@pytest.mark.parametrize(
    "error",
    [
        RunError("no run 'r9' in /x (runs: none)"),
        ApiUnavailableError(httpx2.ConnectError("refused")),
    ],
)
def test_a_known_failure_is_an_error_line_not_a_traceback(calls: Calls, error: Exception) -> None:
    calls.fail_with = error
    for command in (["status"], ["assert"], ["advance"], ["create", "seed-xs"]):
        result = invoke(*command)
        assert result.exit_code == 1
        assert result.stderr.startswith("error: ")
        assert "Traceback" not in result.stderr


def test_an_unknown_scenario_name_is_an_error_line(calls: Calls) -> None:
    result = invoke("run", "no-such-scenario")
    assert result.exit_code == 1 and result.stderr.startswith("error: ")
    assert calls.log == []
