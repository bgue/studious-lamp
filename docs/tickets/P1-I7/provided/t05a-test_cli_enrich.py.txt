"""`tl enricher ls|show|register|enable|disable` and `tl enrich ls|show|accept|reject|run` on a
temporary ledger, with a plugin of the test's own (P1-I7-T05a). Provided; do not edit.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from intcli_support import (
    P,
    fields,
    lines,
    make_record,
    new_env,
    ok,
    plugins,  # noqa: F401  (a fixture)
    refused,
    run,
    sql,
    write_json,
)
from tl_adapters.db import DbTarget
from tl_core.integration.enrichers.dispatcher import EnrichmentDispatcher
from typer.testing import Result as RunResult

FILE = {
    "when": {"event_types": ["Record.Created"]},
    "properties": [{"name": "label", "kind": "string", "policy": "propose", "threshold": 0.9}],
}


@pytest.fixture
def env(new_db: Callable[[], DbTarget], tmp_path: Path, plugins: None) -> dict[str, str]:  # noqa: F811
    return new_env(new_db, tmp_path)


def register(env: dict[str, str], tmp_path: Path, body: object = FILE, *extra: str) -> RunResult:
    path = write_json(tmp_path, "enricher.json", body)
    return run(env, "enricher", "register", "fake", "--project", P, "--file", path, *extra)


def dispatch(env: dict[str, str]) -> None:
    """What the enrichment worker does: follow the ledger and propose."""
    from tl_adapters.db import make_uow_factory

    opened = make_uow_factory(env["TL_DB"])
    try:
        EnrichmentDispatcher(opened).run_until_idle()
    finally:
        opened.dispose()


def waiting(env: dict[str, str], tmp_path: Path, key: str = "ISD-001") -> str:
    ok(register(env, tmp_path))
    ok(run(env, "enricher", "enable", "fake", "--project", P))
    make_record(env, key, "Pump datasheet")
    dispatch(env)
    return sql(env, "SELECT value_id FROM cur_enrichment_value")[0]["value_id"]


# --- tl enricher ---------------------------------------------------------------------------------


def test_register_prints_the_name_and_id_and_the_enricher_starts_off(
    env: dict[str, str], tmp_path: Path
) -> None:
    made = ok(register(env, tmp_path))
    shown = fields(made)
    assert shown["enricher"] == "fake" and len(shown["id"]) == 26
    assert lines(run(env, "enricher", "ls", "--project", P)) == ["fake  off  user  v1  1.0.0"]
    assert ok(run(env, "enricher", "ls", "--project", "OTHER")).stdout == ""
    assert len(lines(run(env, "enricher", "ls"))) == 1


def test_show_prints_the_registration_in_a_fixed_order(env: dict[str, str], tmp_path: Path) -> None:
    ok(register(env, tmp_path))
    shown = lines(run(env, "enricher", "show", "fake", "--project", P))
    assert [s.split(" ")[0] for s in shown] == [
        "enricher", "id", "scope", "version", "code_version", "state", "access", "owner", "actor",
        "when", "property",
    ]  # fmt: skip
    assert shown[0] == "enricher fake" and shown[4] == "code_version 1.0.0"
    assert shown[5] == "state off" and shown[8] == "actor svc:enricher-fake"
    assert shown[9] == 'when {"event_types": ["Record.Created"]}'
    assert shown[10] == "property label string propose 0.9"


def test_enable_and_disable(env: dict[str, str], tmp_path: Path) -> None:
    ok(register(env, tmp_path))
    assert ok(run(env, "enricher", "enable", "fake", "--project", P)).stdout == "enricher fake on\n"
    assert lines(run(env, "enricher", "ls", "--project", P))[0].startswith("fake  on  ")
    refused(run(env, "enricher", "enable", "fake", "--project", P), "already on")
    assert (
        ok(run(env, "enricher", "disable", "fake", "--project", P)).stdout == "enricher fake off\n"
    )
    refused(run(env, "enricher", "show", "nope", "--project", P), "no enricher nope")


@pytest.mark.parametrize(
    ("body", "wanted"),
    [
        ({**FILE, "properties": []}, "propert"),
        ({**FILE, "when": {}}, "when"),
        ({**FILE, "properties": [{"name": "a", "kind": "object"}]}, "kind"),
        ([1], "JSON object"),
    ],
)
def test_a_registration_that_cannot_be_stored_is_an_error(
    env: dict[str, str], tmp_path: Path, body: object, wanted: str
) -> None:
    refused(register(env, tmp_path, body), wanted)
    assert sql(env, "SELECT 1 FROM cur_enricher") == []


def test_only_an_installed_enricher_is_registered_and_never_twice(
    env: dict[str, str], tmp_path: Path
) -> None:
    path = write_json(tmp_path, "e.json", FILE)
    refused(
        run(env, "enricher", "register", "ghost", "--project", P, "--file", path),
        "no enricher plugin",
    )
    ok(register(env, tmp_path))
    refused(register(env, tmp_path), "fake")


# --- tl enrich -----------------------------------------------------------------------------------


def test_a_proposed_value_is_listed_with_its_record_and_confidence(
    env: dict[str, str], tmp_path: Path
) -> None:
    value_id = waiting(env, tmp_path)
    assert lines(run(env, "enrich", "ls", "--project", P)) == [
        f'{value_id}  proposed  enrich.fake.label  ISD-001  "alpha"  0.95'
    ]
    assert ok(run(env, "enrich", "ls", "--project", "OTHER")).stdout == ""
    assert len(lines(run(env, "enrich", "ls", "--state", "all"))) == 1
    assert ok(run(env, "enrich", "ls", "--state", "accepted")).stdout == ""
    refused(run(env, "enrich", "ls", "--state", "bogus"), "--state must be one of")


def test_show_prints_the_value_with_its_provenance(env: dict[str, str], tmp_path: Path) -> None:
    value_id = waiting(env, tmp_path)
    shown = lines(ok(run(env, "enrich", "show", value_id, "--project", P)))
    assert [s.split(" ")[0] for s in shown] == [
        "value", "state", "record", "property", "value", "confidence", "enricher", "produced",
    ]  # fmt: skip
    assert shown[0] == f"value {value_id}" and shown[1] == "state proposed"
    assert shown[2] == "record ISD-001" and shown[3] == "property enrich.fake.label"
    assert shown[4] == 'value "alpha"' and shown[6] == "enricher fake@1.0.0"
    refused(run(env, "enrich", "show", value_id, "--project", "OTHER"), "no value")


def test_accept_writes_the_layer_and_the_value_leaves_the_queue(
    env: dict[str, str], tmp_path: Path
) -> None:
    value_id = waiting(env, tmp_path)
    assert (
        ok(run(env, "enrich", "accept", value_id, "--project", P)).stdout
        == f"accepted {value_id}\n"
    )
    row = sql(env, "SELECT psets_json FROM cur_core_record WHERE key = 'ISD-001'")[0]
    assert json.loads(row["psets_json"])["enrich"]["fake"] == {"label": "alpha"}
    assert ok(run(env, "enrich", "ls", "--project", P)).stdout == ""
    shown = lines(run(env, "enrich", "show", value_id, "--project", P))
    assert "state accepted" in shown and "decided user:dev " in " ".join(shown) + " "
    refused(run(env, "enrich", "accept", value_id, "--project", P), "not waiting")


def test_accept_is_recorded_as_the_actor_given(env: dict[str, str], tmp_path: Path) -> None:
    value_id = waiting(env, tmp_path)
    ok(run(env, "enrich", "accept", value_id, "--project", P, "--actor", "user:mlee"))
    decided = sql(env, "SELECT actor, source FROM events WHERE event_type = 'Enrichment.Accepted'")
    assert [(d["actor"], d["source"]) for d in decided] == [("user:mlee", "cli")]


def test_reject_needs_a_reason_and_the_value_is_not_proposed_again(
    env: dict[str, str], tmp_path: Path
) -> None:
    value_id = waiting(env, tmp_path)
    assert run(env, "enrich", "reject", value_id, "--project", P).exit_code == 2  # no reason
    done = run(env, "enrich", "reject", value_id, "--project", P, "--reason", "wrong type")
    assert ok(done).stdout == f"rejected {value_id}\n"
    assert "reason wrong type" in lines(run(env, "enrich", "show", value_id, "--project", P))
    refused(
        run(env, "enrich", "reject", value_id, "--project", P, "--reason", "again"), "not waiting"
    )
    ok(run(env, "enrich", "run", "fake", "ISD-001", "--project", P))  # the same value: not again
    assert len(sql(env, "SELECT 1 FROM cur_enrichment_value")) == 1


def test_run_proposes_for_one_record(env: dict[str, str], tmp_path: Path) -> None:
    ok(register(env, tmp_path))
    ok(run(env, "enricher", "enable", "fake", "--project", P))
    make_record(env, "ISD-002", "Valve list")
    result = ok(run(env, "enrich", "run", "fake", "ISD-002", "--project", P))
    assert lines(result) == ["proposed 1", "accepted 0"]
    assert (
        len(sql(env, "SELECT 1 FROM cur_enrichment_value WHERE acceptance_state = 'proposed'")) == 1
    )


def test_run_refuses_what_is_off_missing_or_in_another_scope(
    env: dict[str, str], tmp_path: Path
) -> None:
    ok(register(env, tmp_path))
    make_record(env, "ISD-002", "Valve list")
    refused(
        run(env, "enrich", "run", "fake", "ISD-002", "--project", P),
        "no enricher fake is switched on",
    )
    ok(run(env, "enricher", "enable", "fake", "--project", P))
    refused(run(env, "enrich", "run", "fake", "NOPE-1", "--project", P), "no record NOPE-1")
    refused(run(env, "enrich", "run", "fake", "ISD-002", "--project", "OTHER"), "no record ISD-002")
    refused(run(env, "enrich", "run", "ghost", "ISD-002", "--project", P), "ghost")
