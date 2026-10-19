"""A screen command cannot name a field the server sets (second security review, finding 7)."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_embedded_integration import SCOPE, make
from tl_core.services.errors import ReservedIdentifierError


@pytest.mark.parametrize(
    "field", ["actor", "source", "correlation_id", "causation_id", "by_module"]
)
def test_a_server_set_field_is_refused_not_passed_through(tmp_path: Path, field: str) -> None:
    boss = make(tmp_path, "user:boss")
    rule_id = boss.list_integration("rules")[0]["rule_id"]
    with pytest.raises(ReservedIdentifierError):
        boss.integration_command("EnableRule", SCOPE, rule_id=rule_id, **{field: "derive:x"})
    assert not bool(boss.list_integration("rules")[0]["enabled"])
