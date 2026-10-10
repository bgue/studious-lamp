"""Property: a lake built by many incremental syncs equals one built by a single full load.

Hypothesis generates a history of commands in two project scopes (create, edit, void, set and unset
pset values with promoted columns appearing mid-history, add and retract links) with sync points
between them. After the last sync, the incrementally built lake must hold exactly the rows of a
lake rebuilt from scratch, and both must equal the ledger's own tables row for row (not just in
count), with values converted the way the loader converts them.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from builder import OTHER_SCOPE, SCOPE, LedgerBuilder
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from lakecheck import assert_lake_matches_ledger, do_sync
from tl_core.ledger import ConcurrencyError
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services.errors import ServiceError
from tl_lake import LakeConfig

OPS = st.tuples(
    st.sampled_from(["create", "title", "void", "values", "unset", "link", "retract", "sync"]),
    st.integers(min_value=0, max_value=50),
    st.integers(min_value=0, max_value=50),
)


def play(
    ledger: LedgerBuilder, config: LakeConfig, ops: list[tuple[str, int, int]], every: int
) -> None:
    records: list[str] = []
    links: list[str] = []
    for n, (kind, i, j) in enumerate(ops):
        if n and n % every == 0 and ledger.head():
            do_sync(ledger, config)  # a sync point in addition to the generated ones
        try:
            if kind == "create":
                scope = OTHER_SCOPE if j % 3 == 0 else SCOPE
                records.append(ledger.record(f"R-{n}", scope=scope))
            elif kind == "sync":
                do_sync(ledger, config)
            elif not records:
                continue
            elif kind == "title":
                ledger.update(records[i % len(records)], title=f"title {n}")
            elif kind == "void":
                ledger.void(records[i % len(records)])
            elif kind == "values":
                ledger.values(
                    records[i % len(records)],
                    "valve_data",
                    {"size_in": 1 + j % 6, "manufacturer": f"M{j % 3}"},
                )
            elif kind == "unset":
                ledger.values(
                    records[i % len(records)], "valve_data", {"size_in": None, "manufacturer": None}
                )
            elif kind == "link" and len(records) > 1:
                a, b = i % len(records), j % len(records)
                if a != b:
                    links.append(ledger.link(records[a], records[b]))
            elif kind == "retract" and links:
                ledger.retract(links[i % len(links)])
        except (ServiceError, ConcurrencyError):
            continue  # an invalid command for the current state: the history just skips it


@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    database=None,
)
@given(ops=st.lists(OPS, min_size=4, max_size=20), every=st.integers(min_value=1, max_value=4))
def test_incremental_lake_equals_full_rebuild_and_the_ledger(
    ops: list[tuple[str, int, int]], every: int
) -> None:
    fixtures = Path(__file__).resolve().parents[3] / "schema" / "fixtures"
    with tempfile.TemporaryDirectory() as tmp, use_provider(DirectorySchemaProvider(fixtures)):
        root = Path(tmp)
        ledger = LedgerBuilder.create(root / "tl.db")
        incremental = LakeConfig.at(root / "incremental")
        play(ledger, incremental, ops, every)
        if ledger.head() == 0:
            return
        do_sync(ledger, incremental)
        rebuilt = LakeConfig.at(root / "rebuilt")
        do_sync(ledger, rebuilt)

        assert_lake_matches_ledger(ledger, incremental, rebuilt)
