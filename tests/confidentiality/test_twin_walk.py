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

import json
import os
import time
import warnings
from pathlib import Path
from typing import Any

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
    mask,
    mask_chain_columns,
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


def _worlds(group: str, new_db: object, tmp_path: Path) -> tuple[World, World, Any, Twinning]:
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
            Path(f"{dump}.{group}").write_text(json.dumps([vars(f) for f in failures], indent=0))
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
    if kind == "webhook":
        return webhook_calls(world, reader, webhook_bodies(world))
    url = {
        "feed-card-group": "/feed",
        "link-total": "/links/search",
        "transmittal-line": f"/projects/P123/transmittals/{world.hidden.numbers['transmittal']}",
    }[kind]
    client = world.h.client_for(None)
    headers = {"Authorization": f"Bearer {world.tokens[reader]}"}
    started = time.perf_counter()
    params = {"scope": "project:P123"}
    if kind == "feed-card-group":
        params |= {"item_type": "card", "limit": "200"}
    response = client.get(ask(url), params=params, headers=headers)
    return [
        Call(
            "api",
            f"GET {url}",
            reader,
            f"{response.status_code}\n{response.text}",
            time.perf_counter() - started,
        )
    ]


#: Leaks that were fixed: each is an ordinary case, not an xfail. (Its ``twin_channels.LEAKS`` entry
#: and mask stay until that module's owner removes them; the case reads the bodies itself, so the
#: mask cannot hide a regression, and the other leaks of the webhook channel do not matter here.)
FIXED = {"webhook-target"}


def _constraint_bodies(bodies: list[str]) -> list[str]:
    return [b for b in bodies if json.loads(b)["type"].startswith("tl.core.Constraint.Raised")]


@pytest.mark.parametrize("name", sorted(FIXED))
def test_a_fixed_leak_shows_no_difference(name: str, new_db: object, tmp_path: Path) -> None:
    """P2-WHR-S1: a constraint raised on a hidden target (a ``PAYLOAD_REFS`` field) reads the same
    in every webhook mode whether the target is hidden (world A) or never existed (B): the
    target fields are null in both, and the id of the target is not in the body."""
    a, b, _, _ = _worlds(LEAKS[name].group, new_db, tmp_path)
    try:
        hooks = {"A": webhook_bodies(a), "B": webhook_bodies(b)}
        secret = a.hidden.ids["restricted"]
        for who in GROUPS[LEAKS[name].group]:
            for mode in ("delta", "full"):
                left = _constraint_bodies(hooks["A"][(who, mode)])
                right = _constraint_bodies(hooks["B"][(who, mode)])
                assert left, (who, mode)
                assert secret not in "".join(left), (who, mode)
                details = [json.loads(x)["data"]["detail"] for x in left]
                assert all(d["target_id"] is None and d["target_kind"] is None for d in details)
                twin = [json.loads(x)["data"]["detail"] for x in right]
                assert [sorted(d) for d in details] == [sorted(d) for d in twin], (who, mode)
                assert all(d["target_id"] is None for d in twin), (who, mode)
    finally:
        a.close()
        b.close()


@pytest.mark.parametrize(
    "name",
    [
        pytest.param(n, marks=pytest.mark.xfail(strict=True, reason=v.reason))
        for n, v in LEAKS.items()
        if n not in FIXED
    ],
)
def test_known_leak(name: str, new_db: object, tmp_path: Path) -> None:
    a, b, _, tw = _worlds(LEAKS[name].group, new_db, tmp_path)
    try:
        kind = {"dedup-flag": "lake", "webhook-target": "webhook"}.get(name, name)
        who = GROUPS[LEAKS[name].group][0]
        failures, _ = diff(_probe(a, None, who, kind), _probe(b, tw, who, kind), tw)
        assert not failures, "\n".join(map(str, failures))
    finally:
        a.close()
        b.close()


# --- the allow-list is as narrow as its reasons ---

_EVENT = '{"event_type":"Transmittal.Defined","seq":7}'


def _failure(channel: str, route: str, a: str, b: str) -> Failure:
    return Failure(channel, route, "bob", a, b)


def test_a_leak_explains_only_its_own_unit_on_its_own_calls() -> None:
    route = "GET /events {'scope': 'project:P123'}"
    base = '200 {}\n{"rows":[{"seq":6}%s],"total":1}'
    a, b = base % "", base % ("," + _EVENT)
    assert explained_by(_failure("api", route, a, b)) == {"transmittal-line"}
    # another difference on the same call is not the leak's
    assert not explained_by(_failure("api", route, a, b.replace('"total":1', '"total":2')))
    assert not explained_by(_failure("api", route, a.replace('"seq":6', '"seq":5'), b))
    # the same marker on a call the leak does not name
    assert not explained_by(_failure("api", "GET /records/x/tags {}", a, b))
    assert not explained_by(_failure("mcp", route, a, b))


def test_a_mask_applies_only_to_the_calls_that_name_it() -> None:
    a, b = '{"link_total":3}', '{"link_total":2}'
    assert explained_by(_failure("api", "GET /links/search {}", a, b)) == {"link-total"}
    assert not explained_by(_failure("api", "GET /records {}", a, b))
    a, b = '{"deduplicated":true}', '{"deduplicated":false}'
    assert not explained_by(_failure("api", "GET /records/x {}", a, b))
    assert explained_by(_failure("api", "GET /events {}", a, b)) == {"dedup-flag"}


def test_a_numbering_counter_is_all_the_counter_mask_zeroes() -> None:
    allocated = '{"key":"K-1","pattern":"p","prefix":"K-","record_type":"t","sequence":%d}'
    assert mask("api", allocated % 5) == mask("api", allocated % 9)
    other = '{"code":"x","sequence":%d}'
    assert mask("api", other % 1) != mask("api", other % 2)


def test_the_lake_masks_the_chain_hashes_and_not_a_content_hash() -> None:
    h = "a" * 64
    cols = ["seq", "event_type", "scope", "prev_hash", "hash", "sha256"]
    data = {"columns": cols, "rows": [[1, "Internal.Redacted", "company", h, h, h]]}
    mask_chain_columns(data)
    assert data["rows"] == [[1, "Internal.Redacted", "SCOPE", "HASH", "HASH", h]]
    data = {"columns": cols, "rows": [[1, "Record.Created", "company", h, h, h]]}
    mask_chain_columns(data)
    assert data["rows"][0][2] == "company"


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
