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


@pytest.mark.parametrize("field", ["actor", "source", "scope"])
def test_a_file_that_names_a_field_the_command_sets_is_a_clean_error(
    new_db: Callable[[], DbTarget], tmp_path: Path, field: str
) -> None:
    env = new_env(new_db, tmp_path)
    path = write_json(tmp_path, "rule.json", {**RULE, field: "user:admin"})
    result = run(env, "rule", "create", "--project", P, "--file", path)
    refused(result, f"the file must not hold {field}")
    assert "Traceback" not in result.output
    assert sql(env, "SELECT key FROM cur_rule") == []
