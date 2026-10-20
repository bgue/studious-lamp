"""`tl delivery ls|show|retry|dry-run` on a temporary ledger (P1-I7-T04d). Provided; do not edit."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from intcli_support import (
    P,
    deliver,
    fields,
    lines,
    make_endpoint,
    new_env,
    ok,
    refused,
    register_app,
    revise_mapping,
    run,
    sql,
    work_inbound,
    write_json,
)
from tl_adapters.db import DbTarget

BROKEN = '{"command": "PostToFeed", "args": {"body": $.text.x.y}}'
GOOD = '{"command": "PostToFeed", "args": {"body": $.text}}'


@pytest.fixture
def env(new_db: Callable[[], DbTarget], tmp_path: Path) -> dict[str, str]:
    values = new_env(new_db, tmp_path)
    register_app(values)
    return values


def endpoint(env: dict[str, str], mapping: str = BROKEN, path: str = "erp/orders") -> str:
    return make_endpoint(env, path, mapping)


def fix_mapping(env: dict[str, str], path: str = "erp/orders") -> None:
    """Replace the endpoint's mapping through the service (there is no CLI for it)."""
    row = sql(
        env, "SELECT endpoint_id FROM cur_inbound_endpoint WHERE name = :n", n=path.split("/")[1]
    )[0]
    revise_mapping(env, row["endpoint_id"], GOOD)


def failed_delivery(env: dict[str, str]) -> str:
    endpoint(env)
    delivery_id = deliver(env, "erp/orders", {"text": "hello"})
    work_inbound(env)
    assert sql(env, "SELECT state FROM int_delivery")[0]["state"] == "failed"
    return delivery_id


def test_ls_shows_deliveries_newest_first_and_the_error_queue_by_state(
    env: dict[str, str], tmp_path: Path
) -> None:
    delivery_id = failed_delivery(env)
    fix_mapping(env)
    second = deliver(env, "erp/orders", {"text": "again"})
    work_inbound(env)
    everything = lines(run(env, "delivery", "ls"))
    assert [row.split("  ")[0] for row in everything] == [second, delivery_id]
    first = everything[1].split("  ")
    assert first[1:3] == ["failed", "erp/orders"] and first[4] != "-"
    assert everything[0].split("  ")[1] == "applied" and everything[0].split("  ")[4] == "-"
    assert lines(run(env, "delivery", "ls", "--state", "failed")) == [everything[1]]
    assert lines(run(env, "delivery", "ls", "--endpoint", "erp/orders", "-n", "1")) == [
        everything[0]
    ]
    assert ok(run(env, "delivery", "ls", "--project", "OTHER")).stdout == ""
    refused(run(env, "delivery", "ls", "--state", "bogus"), "--state must be one of")
    refused(run(env, "delivery", "ls", "--endpoint", "orders"), "<app>/<name>")


def test_show_prints_what_happened_and_never_the_payload(
    env: dict[str, str], tmp_path: Path
) -> None:
    delivery_id = failed_delivery(env)
    shown = run(env, "delivery", "show", delivery_id, "--project", P)
    out = lines(ok(shown))
    assert [s.split(" ")[0] for s in out] == [
        "delivery", "endpoint", "version", "state", "received", "size", "sha256", "attempts",
        "finished", "error",
    ]  # fmt: skip
    assert out[0] == f"delivery {delivery_id}" and out[1] == "endpoint erp/orders"
    assert out[3] == "state failed" and out[7] == "attempts 1"
    assert out[9].startswith("error invalid_command: ")
    assert "hello" not in shown.output
    refused(run(env, "delivery", "show", delivery_id, "--project", "OTHER"), "no delivery")
    refused(
        run(env, "delivery", "show", "01J0000000000000000000000X", "--project", P), "no delivery"
    )


def test_retry_runs_a_failed_delivery_with_the_current_mapping(
    env: dict[str, str], tmp_path: Path
) -> None:
    delivery_id = failed_delivery(env)
    fix_mapping(env)
    assert (
        ok(run(env, "delivery", "retry", delivery_id, "--project", P)).stdout
        == f"queued {delivery_id}\n"
    )
    assert sql(env, "SELECT state FROM int_delivery")[0]["state"] == "queued"
    work_inbound(env)
    assert sql(env, "SELECT state FROM int_delivery")[0]["state"] == "applied"
    assert "corrected yes" not in lines(run(env, "delivery", "show", delivery_id, "--project", P))
    retried = sql(env, "SELECT actor, source FROM events WHERE event_type = 'Inbound.Retried'")
    assert [(r["actor"], r["source"]) for r in retried] == [("user:dev", "cli")]


def test_retry_with_a_corrected_payload_stores_it_beside_the_received_one(
    env: dict[str, str], tmp_path: Path
) -> None:
    delivery_id = failed_delivery(env)
    fix_mapping(env)
    corrected = write_json(tmp_path, "fixed.json", {"text": "corrected"})
    ok(run(env, "delivery", "retry", delivery_id, "--project", P, "--file", corrected))
    work_inbound(env)
    assert "corrected yes" in lines(run(env, "delivery", "show", delivery_id, "--project", P))
    body = sql(env, "SELECT payload FROM events WHERE event_type = 'Feed.Posted'")
    assert any("corrected" in str(r["payload"]) for r in body)
    event = sql(env, "SELECT payload FROM events WHERE event_type = 'Inbound.Retried'")[0]
    assert "corrected_sha256" in str(event["payload"]) and "None" not in str(event["payload"])[:0]


def test_only_a_failed_delivery_retries_and_a_bad_file_is_an_error(
    env: dict[str, str], tmp_path: Path
) -> None:
    delivery_id = failed_delivery(env)
    refused(
        run(env, "delivery", "retry", delivery_id, "--project", P, "--file", str(tmp_path / "x")),
        "cannot read JSON",
    )
    fix_mapping(env)
    ok(run(env, "delivery", "retry", delivery_id, "--project", P))
    refused(run(env, "delivery", "retry", delivery_id, "--project", P), "queued")  # not failed now
    work_inbound(env)
    refused(run(env, "delivery", "retry", delivery_id, "--project", P), "applied")
    refused(run(env, "delivery", "retry", delivery_id, "--project", "OTHER"), "no delivery")


def test_dry_run_over_a_sample_shows_the_planned_commands_and_writes_nothing(
    env: dict[str, str], tmp_path: Path
) -> None:
    endpoint(env, GOOD)
    sample = write_json(tmp_path, "sample.json", {"text": "hello"})
    before = len(sql(env, "SELECT 1 FROM events"))
    result = ok(run(env, "delivery", "dry-run", "erp/orders", "--project", P, "--sample", sample))
    out = lines(result)
    assert out[:3] == ["status ok", "endpoint erp/orders", "version 2"]
    assert out[3].startswith("PostToFeed  ok  ") and len(out) == 4
    assert (
        len(sql(env, "SELECT 1 FROM events")) == before
        and sql(env, "SELECT 1 FROM int_delivery") == []
    )


def test_dry_run_reports_a_refused_command_and_a_mapping_error(
    env: dict[str, str], tmp_path: Path
) -> None:
    mapping = (
        '[{"command": "PostToFeed", "args": {"body": "x"}}, '
        '{"command": "CreateRecord", "args": {"record_type": "core.Record", "title": "T"}}]'
    )
    endpoint(env, mapping)
    out = lines(
        ok(
            run(
                env,
                "delivery",
                "dry-run",
                "erp/orders",
                "--project",
                P,
                "--sample",
                write_json(tmp_path, "s.json", {}),
            )
        )
    )
    assert out[3].startswith("PostToFeed  ok  ")
    assert out[4].startswith("CreateRecord  refused  ")
    assert out[5].startswith("  problem command_not_allowed: ")
    other = tmp_path / "other"
    other.mkdir()
    endpoint(env, '{"command": "PostToFeed", "args": {"body": $number($.text)}}', "erp/second")
    bad = lines(
        ok(
            run(
                env,
                "delivery",
                "dry-run",
                "erp/second",
                "--project",
                P,
                "--sample",
                write_json(other, "s.json", {"text": "abc"}),
            )
        )
    )
    assert bad[0] == "status error" and bad[-1].startswith("problem mapping_error: ")


def test_dry_run_over_a_stored_delivery_and_its_argument_errors(
    env: dict[str, str], tmp_path: Path
) -> None:
    endpoint(env, GOOD)
    delivery_id = deliver(env, "erp/orders", {"text": "stored"})
    result = ok(
        run(env, "delivery", "dry-run", "erp/orders", "--project", P, "--delivery", delivery_id)
    )
    assert fields(result)["status"] == "ok"
    refused(run(env, "delivery", "dry-run", "erp/orders", "--project", P), "--sample or --delivery")
    sample = write_json(tmp_path, "s.json", {})
    both = ["--sample", sample, "--delivery", delivery_id]
    refused(
        run(env, "delivery", "dry-run", "erp/orders", "--project", P, *both),
        "--sample or --delivery",
    )
    refused(
        run(env, "delivery", "dry-run", "erp/nope", "--project", P, "--sample", sample),
        "no endpoint erp/nope",
    )
    refused(
        run(env, "delivery", "dry-run", "orders", "--project", P, "--sample", sample),
        "<app>/<name>",
    )
