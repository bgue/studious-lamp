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


def test_shadow_enrichment_values_are_the_admins_to_read(tmp_path: Path) -> None:
    from sqlalchemy import text

    boss = make(tmp_path, "user:boss")
    with boss._uow(False) as uow:  # pyright: ignore[reportPrivateUsage]
        for n, state in enumerate(("shadow", "proposed"), 1):
            uow.conn().execute(
                text(
                    "INSERT INTO cur_enrichment_value (value_id, scope, target_json, target_id, "
                    "property_path, value_json, enricher, enricher_version, confidence, "
                    "inputs_json, produced_at, acceptance_state, seq, version, last_seq) VALUES "
                    "(:v, :s, '{}', 'r1', 'enrich.e.p', '\"x\"', 'e', '1', 0.5, '[]', "
                    "'2026-10-19T00:00:00Z', :a, :n, 1, :n)"
                ),
                {"v": f"V{n}", "s": SCOPE, "a": state, "n": n},
            )
    from tl_tui.embedded import EmbeddedClient

    bob = EmbeddedClient.for_sqlite(tmp_path / "tl.db", actor="user:bob")
    assert sorted(r["acceptance_state"] for r in boss.list_integration("enrichments")) == [
        "proposed",
        "shadow",
    ]
    assert [r["acceptance_state"] for r in bob.list_integration("enrichments")] == ["proposed"]
    assert bob.list_integration("enrichments", state="shadow") == []
