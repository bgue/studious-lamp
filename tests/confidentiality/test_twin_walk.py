"""A record a viewer may not read is indistinguishable from one that never existed, through every
channel (outside review 2026-11-09, section 1, "Harness").

Two ledgers are built from one deterministic script (``twin_world``): A holds the secret items of
the reader, B never had them (nor links, posts, proposals, clocks or files that point at them) and
holds filler events on a stream every reader skips, so ``seq`` and ids line up. Each reader who may
not read the secret items then walks both worlds, every API GET route, the event stream, the MCP
read tools, CLI reads, ``lake_query`` and the webhooks of each payload mode, and the answers are
compared byte for byte (ids of B mapped to A, volatile headers dropped). Any difference fails and
names the channel, the route and the reader. A call where A took more than twice as long as B is
flagged in the output (a timing channel), not failed.
"""

from __future__ import annotations

import os
import time
import warnings
from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, open_uow
from twin_channels import (
    LEAKS,
    MASKS,
    Call,
    Failure,
    Twinning,
    api_calls,
    cli_calls,
    diff,
    explained_by,
    lake_calls,
    mcp_calls,
    sse_calls,
    sync_world_lake,
    webhook_calls,
)
from twin_world import (
    World,
    build_world,
    freeze,
    head_seq,
    load_walk,
    secret_kinds,
    webhook_bodies,
)

#: Readers whose secret items are the same share a pair of worlds.
GROUPS = {
    "bob+bot": ("bob", "bot"),
    "ctl": ("ctl",),
    "boss": ("boss",),
    "amy": ("amy",),
}


@pytest.fixture(autouse=True)
def _frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    freeze(monkeypatch)


def _target(new_db: object) -> DbTarget:
    target = new_db()  # type: ignore[operator]
    create_schema(target)
    return target  # type: ignore[no-any-return]


def _ledger_text(world: World) -> str:
    with open_uow(world.target, readonly=True) as uow:
        rows = uow.conn().execute(text("SELECT stream_id, payload FROM events"))
        return " ".join(f"{s} {p}" for s, p in rows)


def _worlds(group: str, new_db: object, tmp_path: Path) -> tuple[World, World, object, Twinning]:
    walk = load_walk()
    secret = secret_kinds(walk.MAY_READ[GROUPS[group][0]])
    a = build_world("A", _target(new_db), tmp_path / "a", walk, frozenset(), None)
    b = build_world("B", _target(new_db), tmp_path / "b", walk, secret, a.marks)
    return a, b, walk, Twinning(a, b)


@pytest.mark.parametrize("group", sorted(GROUPS))
def test_twin_walk(group: str, new_db: object, tmp_path: Path) -> None:
    walk = load_walk()
    readers = GROUPS[group]
    secret = secret_kinds(walk.MAY_READ[readers[0]])
    assert all(secret_kinds(walk.MAY_READ[r]) == secret for r in readers)
    a, b, walk, tw = _worlds(group, new_db, tmp_path)
    try:
        # the twins are what the test says: same length, and B holds none of the secrets
        assert head_seq(a.target) == head_seq(b.target)
        assert a.marks.fillers == 0 and b.marks.fillers > 0
        in_a, in_b = _ledger_text(a), _ledger_text(b)
        for kind in secret - {"file", "loadrun"}:
            assert a.hidden.ids[kind] in in_a, kind
            assert a.hidden.ids[kind] not in in_b, kind
        seed = walk.Seed(a.hidden.ids, a.hidden.numbers, a.hidden.extra_ids, {})
        cands = walk.candidates(seed)
        assert len(walk.get_routes(a.h)) >= walk.MIN_ROUTES
        lakes = {id(w): sync_world_lake(w) for w in (a, b)}
        hooks = {id(a): webhook_bodies(a), id(b): webhook_bodies(b)}
        failures: list[Failure] = []
        slow: list[str] = []
        counts: dict[str, int] = {}
        for reader in readers:
            walked: dict[str, tuple[list[Call], list[Call]]] = {
                "api": (
                    api_calls(a, walk, reader, cands, seed),
                    api_calls(b, walk, reader, cands, seed, tw),
                ),
                "sse": (sse_calls(a, reader), sse_calls(b, reader)),
                "mcp": (mcp_calls(a, reader, a.hidden), mcp_calls(b, reader, a.hidden, tw=tw)),
                "lake": (
                    lake_calls(a, reader, lakes[id(a)]),
                    lake_calls(b, reader, lakes[id(b)]),
                ),
                "cli": (
                    cli_calls(a, reader, a.hidden, tmp_path / f"a-{reader}.json"),
                    cli_calls(b, reader, a.hidden, tmp_path / f"b-{reader}.json", tw),
                ),
                "webhook": (
                    webhook_calls(a, reader, hooks[id(a)]),
                    webhook_calls(b, reader, hooks[id(b)]),
                ),
            }
            for channel, (left, right) in walked.items():
                bad, flags = diff(left, right, tw)
                failures += bad
                slow += flags
                counts[channel] = counts.get(channel, 0) + len(left)
        if slow:  # flagged, not failed: A took more than twice as long as B
            warnings.warn(f"TIMING {len(slow)} calls: " + "; ".join(slow[:5]), stacklevel=1)
        explained: dict[str, int] = {}
        unexplained: list[Failure] = []
        for failure in failures:
            names = explained_by(failure)
            for name in names:
                explained[name] = explained.get(name, 0) + 1
            if not names:
                unexplained.append(failure)
        print(
            "calls per channel:", counts, "| known leaks seen:", explained, "| masks:", list(MASKS)
        )
        if dump := os.environ.get("TWIN_DUMP"):
            Path(f"{dump}.{group}").write_text("\n".join(map(str, failures)))
        assert counts["api"] > 300 * len(readers) and counts["mcp"] > 100 * len(readers)
        assert counts["cli"] >= 50 * len([r for r in readers if r != "bot"])
        assert not unexplained, f"{len(unexplained)} differences:\n" + "\n".join(
            map(str, unexplained[:12])
        )
    finally:
        a.close()
        b.close()


# --- the leaks the walk found: one strict xfail each, so a fix flips it ---


def _probe(world: World, tw: Twinning | None, reader: str, kind: str) -> list[Call]:
    ask = tw.ask if tw else (lambda t: t)
    if kind == "lake":
        return lake_calls(world, reader, sync_world_lake(world))
    url = {
        "link-total": "/links/search",
        "transmittal-line": f"/projects/P123/transmittals/{world.hidden.numbers['transmittal']}",
    }[kind]
    client = world.h.client_for(None)
    headers = {"Authorization": f"Bearer {world.tokens[reader]}"}
    started = time.perf_counter()
    response = client.get(ask(url), params={"scope": "project:P123"}, headers=headers)
    return [
        Call(
            "api",
            f"GET {url}",
            reader,
            f"{response.status_code}\n{response.text}",
            time.perf_counter() - started,
        )
    ]


@pytest.mark.parametrize(
    "name",
    [
        pytest.param(n, marks=pytest.mark.xfail(strict=True, reason=v.reason))
        for n, v in LEAKS.items()
    ],
)
def test_known_leak(name: str, new_db: object, tmp_path: Path) -> None:
    a, b, _, tw = _worlds(LEAKS[name].group, new_db, tmp_path)
    try:
        kind = "lake" if name == "dedup-flag" else name
        failures, _ = diff(_probe(a, None, "bob", kind), _probe(b, tw, "bob", kind), tw)
        assert not failures, "\n".join(map(str, failures))
    finally:
        a.close()
        b.close()


# --- the one difference the owner knows ---


def test_the_key_oracle_on_create_is_the_known_limit(new_db: object, tmp_path: Path) -> None:
    """Creating a record under the key of a hidden one answers 409 where no such record answers 201:
    known, accepted limit (a key is unique, so the refusal tells). The walk covers GET routes only;
    this keeps the limit named, and fails the day it is closed so the entry can go."""
    a, b, _, tw = _worlds("bob+bot", new_db, tmp_path)
    try:
        statuses: list[int] = []
        for world, key in (
            (a, a.hidden.numbers["restricted"]),
            (b, tw.ask(a.hidden.numbers["restricted"])),
        ):
            client = world.h.client_for(None)
            made = client.post(
                "/commands/CreateRecord",
                json={
                    "scope": "project:P123",
                    "record_type": "core.Record",
                    "title": "x",
                    "key": key,
                },
                headers={"Authorization": f"Bearer {world.tokens['bob']}"},
            )
            statuses.append(made.status_code)
        print("key oracle on create (A, B):", statuses)
        assert statuses[0] == 409 and statuses[1] in (200, 201)
    finally:
        a.close()
        b.close()
