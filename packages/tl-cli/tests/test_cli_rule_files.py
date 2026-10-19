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


GATED = [
    ("delivery", "ls"),
    ("delivery", "show", "01J9Z6Q4W3X2Y1V0T9S8R7Q6PB"),
    ("delivery", "dry-run", "erp/orders", "--project", P),
    ("rule", "dry-run", "hse-notify", "--project", P),
    ("rule", "mode", "hse-notify", "propose", "--project", P, "--reason", "r"),
    ("endpoint", "enable", "erp/orders", "--project", P),
]


@pytest.mark.parametrize("args", GATED, ids=lambda a: " ".join(a[:2]))
def test_an_admin_command_needs_a_session_outside_a_dev_setup(
    new_db: Callable[[], DbTarget], tmp_path: Path, args: tuple[str, ...]
) -> None:
    """No session and `TL_ENV` not dev, test or ci: the gate fails closed (second review)."""
    env = new_env(new_db, tmp_path)
    result = run({**env, "TL_ENV": "prod"}, *args)
    assert result.exit_code == 1 and "not signed in" in result.stderr, result.stderr
    assert "Traceback" not in result.output


def test_shadow_enrichment_values_are_the_admins_to_read(
    new_db: Callable[[], DbTarget], tmp_path: Path
) -> None:
    from intcli_support import ok
    from sqlalchemy import text
    from tl_adapters.db import open_uow
    from tl_core.auth import accounts
    from tl_core.auth.password import prepare_password

    env = new_env(new_db, tmp_path)
    env["TL_SESSION_FILE"] = str(tmp_path / "session.json")
    with open_uow(env["TL_DB"]) as uow:
        accounts.create_account(
            uow, username="bob", display_name="bob", kind="person", roles=["user"],
            password=prepare_password("correct horse battery"), by="svc:test",
        )  # fmt: skip
        for n, state in enumerate(("shadow", "proposed"), 1):
            uow.conn().execute(
                text(
                    "INSERT INTO cur_enrichment_value (value_id, scope, target_json, target_id, "
                    "property_path, value_json, enricher, enricher_version, confidence, "
                    "inputs_json, produced_at, acceptance_state, seq, version, last_seq) VALUES "
                    "(:v, :s, '{}', 'r1', 'enrich.e.p', '\"x\"', 'e', '1', 0.5, '{}', "
                    "'2026-10-19T00:00:00Z', :a, :n, 1, :n)"
                ),
                {"v": f"V{n}", "s": f"project:{P}", "a": state, "n": n},
            )
    # no session on a dev ledger file: the file's owner sees everything
    seen = run(env, "enrich", "ls", "--state", "all").stdout
    assert "V1" in seen and "V2" in seen
    ok(run(env, "login", "bob", "--password-stdin", input="correct horse battery\n"))
    listed = run(env, "enrich", "ls", "--state", "all").stdout
    assert "V2" in listed and "V1" not in listed
    assert run(env, "enrich", "ls", "--state", "shadow").stdout == ""
    shown = run(env, "enrich", "show", "V1", "--project", P)
    assert shown.exit_code == 1 and "no value V1" in shown.stderr
