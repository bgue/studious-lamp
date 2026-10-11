"""The TUI grid's own step: load, filter and paint rows from the seeded database, headless.

``RecordGrid`` runs in a minimal Textual app under the headless pilot, over the embedded client on
the dataset. The numbers are wall-clock time on the UI thread, which is what a user waits for:

* ``load page``: ``grid.load()``, one page fetched and put on screen;
* ``apply filter``: ``grid.apply_filter(text)`` (count, then page), blocking the UI thread as the
  filter bar's handler does;
* ``filter to painted``: the same call plus the pilot waiting for the app to settle;
* ``paint visible rows``: ``render_line`` for every line of the viewport, no I/O.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Iterator
from typing import Any

import pytest
from bench_data import Dataset
from bench_env import ROUNDS, SAMPLES, SCOPE, embedded_client
from bench_stats import Recorder, series_from_flat
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from tl_tui.embedded import EmbeddedClient
from tl_tui.widgets.grid import RecordGrid

FILTERS = (
    "status=Approved",
    "psets.valve_data.body_material=SS316L",
    "psets.valve_data.size_in>=12",
)
VIEWPORT = (120, 45)


class GridApp(App[None]):
    def __init__(self, client: EmbeddedClient) -> None:
        super().__init__()
        self._client = client

    def compose(self) -> ComposeResult:
        yield RecordGrid(self._client, SCOPE, id="grid")


@pytest.fixture(scope="module")
def client(dataset: Dataset) -> Iterator[EmbeddedClient]:
    with embedded_client(dataset) as c:
        yield c


def test_grid_load_filter_and_paint(
    client: EmbeddedClient, dataset: Dataset, recorder: Recorder
) -> None:
    app = GridApp(client)
    samples: dict[str, list[float]] = {
        "load page": [],
        "apply filter": [],
        "filter to painted": [],
        "pilot settle alone": [],
        "paint visible rows": [],
    }
    loads: list[float] = []
    per_round = max(6, SAMPLES // 2)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = app.query_one("#grid", RecordGrid)
        assert len(grid.rows) == grid.page_size
        for warm in range(3):
            grid.apply_filter(FILTERS[warm % len(FILTERS)])
            grid.apply_filter("")
        for _ in range(ROUNDS):
            loads.append(round(os.getloadavg()[0], 2))
            for i in range(per_round):
                started = time.perf_counter()
                grid.load()
                samples["load page"].append((time.perf_counter() - started) * 1000.0)

                text = FILTERS[i % len(FILTERS)]
                started = time.perf_counter()
                result = grid.apply_filter(text)
                samples["apply filter"].append((time.perf_counter() - started) * 1000.0)
                assert result.ok and result.count is not None
                await pilot.pause()
                samples["filter to painted"].append((time.perf_counter() - started) * 1000.0)
                started = time.perf_counter()
                await pilot.pause()
                samples["pilot settle alone"].append((time.perf_counter() - started) * 1000.0)

                started = time.perf_counter()
                for y in range(VIEWPORT[1]):
                    grid.render_line(y)
                samples["paint visible rows"].append((time.perf_counter() - started) * 1000.0)
                grid.apply_filter("")

    async def main() -> None:
        async with app.run_test(size=VIEWPORT) as pilot:
            await scenario(pilot)

    asyncio.run(main())
    for name, values in samples.items():
        recorder.add(
            series_from_flat(
                values,
                rounds=ROUNDS,
                target="grid_render",
                scenario=name,
                dialect=dataset.dialect,
                records=dataset.records,
                loads=loads,
                note="headless pilot, 120x45"
                + (
                    "; includes the pilot's own settle time (see 'pilot settle alone')"
                    if name == "filter to painted"
                    else ""
                ),
                informational=name in ("filter to painted", "pilot settle alone"),
            )
        )
