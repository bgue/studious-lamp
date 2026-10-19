"""`tl rule create` refuses a file that names a field the command sets (P1-I7). Supervisor-built:
a clean error, never a traceback (T03b review note)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from intcli_support import P, new_env, refused, run, sql, write_json
from tl_adapters.db import DbTarget

RULE = {
    "key": "hse-notify",
    "title": "Notify HSE",
    "when": {"event_types": ["Feed.Posted"]},
    "then": [{"command": "PostToFeed", "args": {"body": "HSE notified"}}],
}


@pytest.mark.parametrize(
    "field",
    ["actor", "source", "scope", "correlation_id", "causation_id", "idempotency_key", "by_module"],
)
def test_a_file_that_names_a_field_the_command_sets_is_a_clean_error(
    new_db: Callable[[], DbTarget], tmp_path: Path, field: str
) -> None:
    env = new_env(new_db, tmp_path)
    path = write_json(tmp_path, "rule.json", {**RULE, field: "user:admin"})
    result = run(env, "rule", "create", "--project", P, "--file", path)
    refused(result, f"the file must not hold {field}")
    assert "Traceback" not in result.output
    assert sql(env, "SELECT key FROM cur_rule") == []


@pytest.mark.parametrize("field", ["actor", "source", "scope", "correlation_id"])
def test_action_define_and_enricher_register_refuse_server_set_fields_cleanly(
    new_db: Callable[[], DbTarget], tmp_path: Path, field: str
) -> None:
    env = new_env(new_db, tmp_path)
    action = {
        "name": "send_to_nde", "label": "Send", "executor": "job",
        "executor_config": {"kind": "job", "job": "echo"}, "side_effect_class": "read",
        field: "user:admin",
    }  # fmt: skip
    made = run(
        env, "action", "define", "--project", P, "--file", write_json(tmp_path, "a.json", action)
    )
    refused(made, f"the file must not hold {field}")
    assert "Traceback" not in made.output
    enricher = {"when": {"event_types": ["Document.Defined"]}, "properties": [], field: "x"}
    registered = run(
        env, "enricher", "register", "doc_classifier", "--project", P,
        "--file", write_json(tmp_path, "e.json", enricher),
    )  # fmt: skip
    refused(registered, f"the file must not hold {field}")
    clash = {"when": {"event_types": ["Document.Defined"]}, "properties": [], "name": "other"}
    named = run(
        env, "enricher", "register", "doc_classifier", "--project", P,
        "--file", write_json(tmp_path, "e2.json", clash),
    )  # fmt: skip
    refused(named, "the file must not hold name")
    assert sql(env, "SELECT 1 FROM cur_action_definition") == []
