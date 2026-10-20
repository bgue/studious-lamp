"""Two projects whose ids spell the same in a number resolve only their own item (P1-I6).

The numbering drops symbols from a project id, so ``project:sim-a`` and ``project:sima`` both
number their first RFI ``sima-RFI-0001``. Every lookup by number is bound to its scope; this test
holds each of them to it.
"""

from __future__ import annotations

from tl_adapters.db import open_uow
from tl_core.services import queries
from tl_mod_correspondence import registry, registry_domain
from tl_mod_correspondence.testing import CorrWorld, frozen_today

HYPHEN = "project:sim-a"
PLAIN = "project:sima"
NUMBER = "sima-RFI-0001"


def test_equal_spellings_in_two_projects_resolve_only_their_own_item(world: CorrWorld) -> None:
    with frozen_today("2026-10-19"):
        first = world.raise_technical(scope=HYPHEN)
        second = world.raise_technical(scope=PLAIN)
    assert first.key == second.key == NUMBER
    assert first.stream_id != second.stream_id
    with open_uow(world.db, readonly=True) as uow:
        conn = uow.conn()
        for scope, mine in ((HYPHEN, first.stream_id), (PLAIN, second.stream_id)):
            found = registry_domain.find_technical(conn, scope, NUMBER)
            assert found is not None and found.item.id == mine
            item = registry.find_item(conn, scope, NUMBER)
            assert item is not None and item.id == mine
            assert registry.find_item_id_for_control(conn, scope, NUMBER) == mine
            record = queries.get_record(uow, scope, NUMBER)
            assert record is not None and record["id"] == mine
            assert [row.item.id for row in registry_domain.list_technical(conn, scope)] == [mine]
        assert registry_domain.find_technical(conn, "project:P123", NUMBER) is None
        assert queries.get_record(uow, "project:P123", NUMBER) is None
