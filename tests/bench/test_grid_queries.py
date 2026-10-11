"""Grid scroll, sort and filter on the query path the TUI grid uses (brief §15: 150 ms, 100k rows).

The TUI grid pages with ``list_records`` (no filter) or ``query_records`` plus ``count_records``
(filter bar), 200 rows per page, and ``End`` loads up to ``END_CAP`` rows. Each scenario calls the
same ``EmbeddedClient`` methods, so the number includes the unit of work, the SQL, the row
conversion and the envelope build. Deeper paging than ``END_CAP`` is reported but is not part of
the verdict: the grid does not offer it (it asks the user to narrow the list).
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterator
from typing import Literal

import pytest
from bench_data import Dataset
from bench_env import ROUNDS, SAMPLES, SCOPE, embedded_client
from bench_stats import Recorder, measure, series_from_flat
from tl_tui.embedded import EmbeddedClient
from tl_tui.widgets.grid import END_CAP

PAGE = 200


@pytest.fixture(scope="module")
def client(dataset: Dataset) -> Iterator[EmbeddedClient]:
    with embedded_client(dataset) as c:
        yield c


def test_scroll_pages(client: EmbeddedClient, dataset: Dataset, recorder: Recorder) -> None:
    n = dataset.records
    cases: list[tuple[str, Callable[[int], object], bool]] = [
        (
            "first_page",
            lambda i: client.list_records(SCOPE, record_type="core.Record", limit=PAGE),
            False,
        ),
        (
            "scroll_within_cap",
            lambda i: client.list_records(
                SCOPE,
                record_type="core.Record",
                limit=PAGE,
                offset=(abs(i) * 1200) % (END_CAP - PAGE),
            ),
            False,
        ),
        (
            "page_beyond_cap",
            lambda i: client.list_records(
                SCOPE,
                record_type="core.Record",
                limit=PAGE,
                offset=END_CAP + (abs(i) * 7919) % max(1, n - END_CAP - PAGE),
            ),
            True,
        ),
        (
            "reload_5000_rows",
            lambda i: client.list_records(SCOPE, record_type="core.Record", limit=END_CAP),
            True,
        ),
    ]
    for name, call, informational in cases:
        recorder.add(
            measure(
                call,
                target="grid_scroll",
                scenario=name,
                dialect=dataset.dialect,
                records=n,
                rounds=ROUNDS,
                samples=SAMPLES if name != "reload_5000_rows" else 8,
                informational=informational,
            )
        )
    rows = client.list_records(SCOPE, record_type="core.Record", limit=PAGE)
    assert len(rows) == PAGE


SORTS: list[tuple[str, Literal["asc", "desc"]]] = [
    ("key", "asc"),
    ("key", "desc"),
    ("title", "asc"),
    ("status", "asc"),
    ("type", "asc"),
    ("created_at", "desc"),
    ("updated_at", "desc"),
    ("version", "desc"),
]


def test_sort(client: EmbeddedClient, dataset: Dataset, recorder: Recorder) -> None:
    n = dataset.records
    for column, direction in SORTS:
        order: list[tuple[str, Literal["asc", "desc"]]] = [(column, direction)]

        def call(i: int, order: list[tuple[str, Literal["asc", "desc"]]] = order) -> object:
            return client.list_records(
                SCOPE,
                record_type="core.Record",
                limit=PAGE,
                offset=(abs(i) % 4) * PAGE,
                order_by=order,
            )

        recorder.add(
            measure(
                call,
                target="grid_sort",
                scenario=f"sort {column} {direction}",
                dialect=dataset.dialect,
                records=n,
                rounds=ROUNDS,
                samples=max(6, SAMPLES // 2),
            )
        )

    def pset_sort(i: int) -> object:
        return client.query_records(
            SCOPE, "", limit=PAGE, order_by=[("psets.valve_data.size_in", "asc")]
        )

    recorder.add(
        measure(
            pset_sort,
            target="grid_sort",
            scenario="sort psets.valve_data.size_in asc",
            dialect=dataset.dialect,
            records=n,
            rounds=ROUNDS,
            samples=max(6, SAMPLES // 2),
        )
    )


def _filters(n: int) -> list[tuple[str, Callable[[int], str]]]:
    def tag(i: int) -> str:
        return f"V-{(abs(i) * 7919 + 13) % n:06d}"

    return [
        ("status = Approved", lambda i: "status=Approved"),
        ("status != Approved", lambda i: "status!=Approved"),
        ("type = core.Record", lambda i: "type=core.Record"),
        ("text search (key, title)", lambda i: f"V-{(abs(i) % 90) + 10:02d}"),
        ("pset text = (20% match)", lambda i: "psets.valve_data.body_material=SS316L"),
        ("pset text = (one record)", lambda i: f"psets.valve_data.tag_no={tag(i)}"),
        ("pset number >=", lambda i: "psets.valve_data.size_in>=12"),
        (
            "pset + pset + status",
            lambda i: (
                "psets.valve_data.body_material=SS316L psets.valve_data.size_in>=12 status=Approved"
            ),
        ),
        ("linked(references)", lambda i: "linked(references)"),
        ("count(linked) >= 3", lambda i: "count(linked)>=3"),
        ("missing(link)", lambda i: "missing(link)"),
        ("created_at >= date", lambda i: "created_at>=2026-01-01"),
    ]


def test_filters(client: EmbeddedClient, dataset: Dataset, recorder: Recorder) -> None:
    """What the filter bar does: ``count_records`` to check the text, then the first page."""
    n = dataset.records
    for name, text_of in _filters(n):
        counts: list[float] = []
        pages: list[float] = []
        totals: list[float] = []
        loads: list[float] = []
        found = 0

        def run(
            i: int,
            text_of: Callable[[int], str] = text_of,
            counts: list[float] = counts,
            pages: list[float] = pages,
            totals: list[float] = totals,
        ) -> int:
            text = text_of(i)
            started = time.perf_counter()
            count = client.count_records(SCOPE, text)
            middle = time.perf_counter()
            client.query_records(SCOPE, text, limit=PAGE)
            finished = time.perf_counter()
            if i >= 0:
                counts.append((middle - started) * 1000.0)
                pages.append((finished - middle) * 1000.0)
                totals.append((finished - started) * 1000.0)
            return count

        for i in range(3):
            run(-1 - i)
        for _ in range(ROUNDS):
            loads.append(round(os.getloadavg()[0], 2))
            for _ in range(max(6, SAMPLES // 2)):
                found = run(len(totals))
        for part, values in (("apply (count + page)", totals), ("count", counts), ("page", pages)):
            recorder.add(
                series_from_flat(
                    values,
                    rounds=ROUNDS,
                    target="grid_filter",
                    scenario=f"filter {name}: {part}",
                    dialect=dataset.dialect,
                    records=n,
                    loads=loads,
                    note=f"{found} matches" if part.startswith("apply") else "",
                    informational=not part.startswith("apply"),
                )
            )
