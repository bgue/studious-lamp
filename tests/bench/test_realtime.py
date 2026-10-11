"""Realtime: a change made by one client is visible to another in under 2 s (brief §15).

Two clients over the real API on loopback, with the seeded database behind it (a private copy):
client A writes, client B holds an open ``GET /stream`` (SSE). The latency is the time from just
before A sends the write until B's reader sees the event.

* ``api write to sse``: A posts ``CreateRecord`` to the API (the event reaches the stream through
  the in-process bus), the path two TUIs in remote mode use;
* ``other process write to sse``: A commits through its own engine, with no bus, so the event
  reaches the stream only through the change-feed poller (interval 0.25 s), the path an embedded
  TUI or a worker sharing the database uses.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from bench_data import Dataset
from bench_env import ROUNDS, SAMPLES, SCOPE
from bench_live import SseReader, copy_of, create_record_command, running_api, write_elsewhere
from bench_stats import Recorder, series_from_flat
from tl_api.client import ApiClient

POLL_INTERVAL_S = 0.25


def test_change_visible_to_another_client(
    dataset: Dataset, recorder: Recorder, tmp_path: Path
) -> None:
    per_round = max(6, SAMPLES // 2)
    api_total: list[float] = []
    api_post: list[float] = []
    other_total: list[float] = []
    loads: list[float] = []
    with copy_of(dataset, tmp_path) as target:
        with running_api(target, tmp_path, poll_interval_s=POLL_INTERVAL_S) as live:
            writer = ApiClient(live.base_url, live.tokens["user:alice"])
            try:
                with SseReader(live, "user:bob") as reader:
                    counter = 0

                    def api_write() -> tuple[float, float]:
                        nonlocal counter
                        counter += 1
                        key = f"RT-API-{counter:05d}"
                        started = time.perf_counter()
                        writer.create_record(create_record_command(key, "user:alice", SCOPE))
                        posted = time.perf_counter()
                        seen = reader.wait_for(key)
                        return (seen - started) * 1000.0, (posted - started) * 1000.0

                    def other_write() -> float:
                        nonlocal counter
                        counter += 1
                        key = f"RT-OTH-{counter:05d}"
                        started = time.perf_counter()
                        write_elsewhere(target, key, SCOPE)
                        seen = reader.wait_for(key)
                        return (seen - started) * 1000.0

                    for _ in range(3):
                        api_write()
                        other_write()
                    for _ in range(ROUNDS):
                        loads.append(round(os.getloadavg()[0], 2))
                        for _ in range(per_round):
                            total, post = api_write()
                            api_total.append(total)
                            api_post.append(post)
                        for _ in range(per_round):
                            other_total.append(other_write())
            finally:
                writer.close()
    common = {"rounds": ROUNDS, "dialect": dataset.dialect, "records": dataset.records}
    recorder.add(
        series_from_flat(
            api_total, target="realtime", scenario="api write to sse", loads=loads, **common
        )
    )
    recorder.add(
        series_from_flat(
            api_post,
            target="realtime",
            scenario="api write (the POST alone)",
            loads=loads,
            informational=True,
            **common,
        )
    )
    recorder.add(
        series_from_flat(
            other_total,
            target="realtime",
            scenario="other process write to sse",
            loads=loads,
            note=f"poll interval {POLL_INTERVAL_S} s",
            **common,
        )
    )
