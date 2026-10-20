"""Session-sensitive CLI checks of the integration layer (second security review). Supervisor-built.

``AUTO_SIGN_IN = False``: on Postgres the conftest would otherwise sign a test admin in for every
command; these tests are about having no session, or a given one.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from intcli_support import P, new_env, ok, refused, run, sql, write_json  # noqa: F401
from tl_adapters.db import DbTarget

AUTO_SIGN_IN = False

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
    env["TL_SESSION_FILE"] = str(tmp_path / "no-session.json")
    result = run({**env, "TL_ENV": "prod"}, *args)
    assert result.exit_code == 1 and "not signed in" in result.stderr, result.stderr
    assert "Traceback" not in result.output


def test_shadow_enrichment_values_are_the_admins_to_read(
    new_db: Callable[[], DbTarget], tmp_path: Path
) -> None:
    from sqlalchemy import text
    from tl_adapters.db import open_uow
    from tl_core.auth import accounts
    from tl_core.auth.password import prepare_password

    env = new_env(new_db, tmp_path)
    env["TL_SESSION_FILE"] = str(tmp_path / "session.json")
    with open_uow(env["TL_DB"]) as uow:
        for name, roles in (("boss", ["admin"]), ("bob", ["user"])):
            accounts.create_account(
                uow, username=name, display_name=name, kind="person", roles=roles,
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
    ok(run(env, "login", "boss", "--password-stdin", input="correct horse battery\n"))
    seen = run(env, "enrich", "ls", "--state", "all").stdout
    assert "V1" in seen and "V2" in seen
    ok(run(env, "login", "bob", "--password-stdin", input="correct horse battery\n"))
    listed = run(env, "enrich", "ls", "--state", "all").stdout
    assert "V2" in listed and "V1" not in listed
    assert run(env, "enrich", "ls", "--state", "shadow").stdout == ""
    shown = run(env, "enrich", "show", "V1", "--project", P)
    assert shown.exit_code == 1 and "no value V1" in shown.stderr
