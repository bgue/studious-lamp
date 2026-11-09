"""The channels the twin walk reads a world through, as one reader: every call is one ``Call``.

A ``Call`` holds what a caller could see (status, the headers that are not volatile, the body) and
the wall time. ``diff`` compares the calls of A and B in order; an allow-listed difference carries a
reason; every other one is a failure that names the channel, the route and the reader.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx2
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import text
from tl_adapters.db import make_engine, open_uow
from tl_cli import session as cli_session
from tl_cli.main import app as cli_app
from tl_lake import read_snapshot, sync_lake
from tl_lake.config import LakeConfig
from tl_mcp.server import build_server
from tl_mod_correspondence.confseed import TOKENS
from twin_world import FIXED_NOW, SCOPE, World
from typer.testing import CliRunner
from ulid import ULID

FAKE_ID = "01J000000000000000000000"
#: Headers that differ between two calls of the same world.
VOLATILE_HEADERS = {"date", "x-request-id", "x-correlation-id", "server-timing"}
ULID_RE = re.compile(r"\b[0-9A-HJKMNP-TV-Z]{26}\b")
#: Differences that are known and kept out of the comparison, each with its reason (see ``MASKS``).
HASH_RE = re.compile(r'("(?:prev_)?hash": ?")[0-9a-f]{64}(")|( v\d+ )[0-9a-f]{64}$', re.MULTILINE)
COUNTER_RE = re.compile(
    r'("stream_id": ?"numbering:[^"]*", ?"stream_type": ?"[^"]*", ?"stream_version": ?)\d+'
    r"|(numbering:\S+ v)\d+"
)
#: A flat JSON object (a payload, possibly written with escaped quotes) that holds a ``sequence``.
FLAT_OBJECT_RE = re.compile(r"\{[^{}]*\\*\"sequence\\*\": ?\d+[^{}]*\}")
SEQUENCE_RE = re.compile(r'(\\*"sequence\\*": ?)\d+')
#: The keys that make a flat object the payload of ``Numbering.Allocated``.
ALLOCATED_KEYS = ("pattern", "key", "prefix", "record_type")
#: Lake columns that hold the chain hashes.
LAKE_HASH_COLUMNS = ("prev_hash", "hash")
REDACTED_SCOPE = "SCOPE"

#: (what is masked, why). Every other difference between A and B fails the walk.
MASKS = {
    "hash chain": (
        "prev_hash and hash of an event: the chain of a scope covers every event of the scope, the "
        "hidden ones too (tamper evidence); it carries no content"
    ),
    "filler events": (
        "B's filler events (Account.TwinFiller on a core.Account stream) are written out of the "
        "event list an admin reads; every other reader skips account streams"
    ),
    "redacted row scope": (
        "the scope column of an Internal.Redacted row of the lake events table (the placeholder of "
        "an event the reader may not read): on Postgres one account event sits a seq later in A "
        "(A's hidden event comes first in its step) than in B (the filler is padded after it), so "
        "the placeholder at that seq differs in scope; nothing else of the row is masked"
    ),
    "numbering counter": (
        "stream_version of a numbering:<scope>:<pattern>:<prefix> stream (and numbering vN in "
        "text) and payload.sequence of Numbering.Allocated, nothing else called sequence: a number "
        "follows its place in the counter, so a gap in the numbers shows that something was "
        "numbered (owner ruling 2026-11-09: a known limit); the keys themselves are mapped A -> B"
    ),
}


FILLER = '{"event_type":"Account.TwinFiller"'


def _object_end(text_: str, start: int) -> int:
    depth, at, quoted = 0, start, False
    while at < len(text_):
        ch = text_[at]
        if quoted:
            if ch == "\\":
                at += 1
            quoted = ch != '"'
        elif ch == '"':
            quoted = True
        elif ch in "{}":
            depth += 1 if ch == "{" else -1
            if depth == 0:
                return at + 1
        at += 1
    raise AssertionError("an unfinished JSON object")


def drop_fillers(body: str) -> str:
    """B's filler events written out of a JSON list: an admin reads account streams, so for an admin
    they are in the list (and in no other reader's); they stand where A has events nobody reads."""
    while (start := body.find(FILLER)) >= 0:
        end = _object_end(body, start)
        if body[end : end + 1] == ",":
            end += 1
        elif body[start - 1 : start] == ",":
            start -= 1
        body = body[:start] + body[end:]
    return body


def canon(body: str) -> str:
    """A JSON body with its object keys in order: the order of a mapping (the feed's ``labels``) is
    the database's, and Postgres hands rows back in the order its pages hold them."""
    head, _, tail = body.partition("\n")
    for text_, prefix in ((tail, head + "\n"), (body, "")):
        try:
            return prefix + json.dumps(json.loads(text_), sort_keys=True, separators=(",", ":"))
        except ValueError:
            continue
    return body


def mask(channel: str, body: str) -> str:
    body = HASH_RE.sub(
        lambda m: f"{m.group(1)}HASH{m.group(2)}" if m.group(1) else f"{m.group(3)}HASH", body
    )
    body = COUNTER_RE.sub(lambda m: f"{m.group(1) or m.group(2)}0", body)
    body = FLAT_OBJECT_RE.sub(_zero_allocated_sequence, body)
    return canon(body)


def _zero_allocated_sequence(m: re.Match[str]) -> str:
    """The sequence of a Numbering.Allocated payload; any other object that has a ``sequence``
    (a tag's, a schedule's) is left as it is."""
    obj = m.group(0)
    if all(re.search(rf'\\*"{key}\\*":', obj) for key in ALLOCATED_KEYS):
        return SEQUENCE_RE.sub(r"\g<1>0", obj)
    return obj


@dataclass
class Call:
    channel: str
    route: str
    reader: str
    body: str
    wall: float


# --- the table that maps A to B ---

BASE = 1 << 100


class Twinning:
    """What is the same record in A and in B, and so what to ask B when A is asked about a record.

    A record in both worlds has the id it has in A, but for the ids B took after a file A
    deduplicated (``Marks.skews``), and a key (a number) that follows its place in the counter, so
    when B never made an item the items after it have lower numbers. Everything A holds and B does
    not (the secret items, what hangs on them, their numbers) is asked of B as an id or a number
    that never existed, and the answer is written back as the id or number A was asked about.
    """

    def __init__(self, a: World, b: World) -> None:
        self.skews = b.marks.skews
        a_ids, a_keys = self._records(a)
        b_ids, b_keys = self._records(b)
        b_in_a = {self.to_a_id(i): i for i in b_ids}  # A's name of an id of B -> B's id
        self.id_to_b: dict[str, str] = {}
        for n, a_id in enumerate(sorted(a_ids)):
            self.id_to_b[a_id] = b_in_a.get(a_id) or str(ULID.from_int(BASE + (1 << 60) + n))
        self.key_to_b: dict[str, str] = {}
        taken = {*a_keys.values(), *b_keys.values()}
        for a_id, key in sorted(a_keys.items()):
            twin = b_keys.get(self.id_to_b[a_id]) if self.id_to_b[a_id] in b_ids else None
            if twin is None:
                twin = self._unused(key, taken)
                taken.add(twin)
            self.key_to_b[key] = twin
        fresh = {v: k for k, v in self.id_to_b.items() if v not in b_ids}
        self.back = {**fresh, **{v: k for k, v in self.key_to_b.items()}}
        words = sorted((*self.id_to_b, *self.key_to_b), key=len, reverse=True)
        self.ask_re = re.compile("|".join(re.escape(w) for w in words)) if words else None
        self.back_re = re.compile(
            "|".join(re.escape(w) for w in sorted(self.back, key=len, reverse=True))
        )

    @staticmethod
    def _unused(key: str, taken: set[str]) -> str:
        """A key of the same shape as ``key`` that no record of either world has."""
        found = list(re.finditer(r"\d+", key))
        assert found, key
        last = found[-1]
        width = len(last.group(0))
        for n in range(10**width - 1, 0, -1):
            fresh = f"{key[: last.start()]}{n:0{width}d}{key[last.end() :]}"
            if fresh not in taken:
                return fresh
        raise AssertionError(f"no unused key like {key}")

    @staticmethod
    def _records(world: World) -> tuple[set[str], dict[str, str]]:
        with open_uow(world.target, readonly=True) as uow:
            conn = uow.conn()
            ids = {
                str(r[0])
                for r in conn.execute(
                    text(
                        "SELECT DISTINCT stream_id FROM events WHERE stream_type <> 'core.Account'"
                    )
                )
            }
            keys = {
                str(r[0]): str(r[1])
                for r in conn.execute(
                    text("SELECT id, key FROM cur_core_record WHERE key IS NOT NULL")
                )
            }
        return ids, keys

    def to_a_id(self, b_id: str) -> str:
        try:
            value = int(ULID.from_str(b_id))
        except ValueError:
            return b_id
        n = value - BASE
        if not 0 < n < (1 << 40):
            return b_id
        shift = 0
        for threshold, skew in self.skews:
            if n > threshold:
                shift = skew
        return str(ULID.from_int(value - shift)) if shift else b_id

    def ask(self, text_: str) -> str:
        """What to say to B for what was said to A."""
        if self.ask_re is None:
            return text_
        mapping = {**self.id_to_b, **self.key_to_b}
        return self.ask_re.sub(lambda m: mapping[m.group(0)], text_)

    def answer(self, text_: str) -> str:
        """What B said, written as A would have said it."""
        text_ = ULID_RE.sub(lambda m: self.to_a_id(m.group(0)), text_)
        return self.back_re.sub(lambda m: self.back.get(m.group(0), m.group(0)), text_)


# --- the API ---


def api_calls(
    world: World,
    walk: Any,
    reader: str,
    cands: dict[str, list[str]],
    seed: Any,
    tw: Twinning | None = None,
) -> list[Call]:
    ask = tw.ask if tw else (lambda t: t)
    client = world.h.client_for(None)
    headers = {"Authorization": f"Bearer {world.tokens[reader]}"}
    out: list[Call] = []
    for path, path_params, query_params in walk.get_routes(world.h):
        if path in walk.NOT_WALKED:
            continue
        for name in path_params:
            assert name in cands, f"{path}: add values for the path parameter {name!r}"
        combos = itertools.islice(itertools.product(*(cands[n] for n in path_params)), 60)
        for combo in combos:
            url = path
            for name, value in zip(path_params, combo, strict=True):
                url = url.replace("{" + name + "}", value)
            for query in walk.query_variants(seed, query_params):
                started = time.perf_counter()
                response = client.get(
                    ask(url), params={k: ask(v) for k, v in query.items()}, headers=headers
                )
                wall = time.perf_counter() - started
                kept = {
                    k: v
                    for k, v in sorted(response.headers.items())
                    if k not in VOLATILE_HEADERS and k != "content-length"
                }
                body = response.content.decode("utf-8", errors="replace")
                text_ = f"{response.status_code} {kept}\n{body}"
                out.append(Call("api", f"GET {url} {query}", reader, text_, wall))
    return out


# --- the event stream ---


def sse_calls(world: World, reader: str) -> list[Call]:
    """The catch-up of ``/stream`` from the start: every line up to the first keepalive."""
    lines: list[str] = []
    started = time.perf_counter()
    with world.h.live("user:alice") as server:
        with httpx2.Client(base_url=server.base_url, timeout=httpx2.Timeout(8)) as client:
            with client.stream(
                "GET",
                "/stream",
                headers={"Authorization": f"Bearer {world.tokens[reader]}"},
                params={"after": 0, "scope": SCOPE},
            ) as response:
                lines.append(f"{response.status_code}")
                deadline = time.monotonic() + 8
                for line in response.iter_lines():
                    if line.startswith(":"):  # a keepalive: the catch-up is over
                        break
                    lines.append(line)
                    if time.monotonic() > deadline:
                        lines.append("TIMEOUT")
                        break
    return [
        Call("sse", "GET /stream?after=0", reader, "\n".join(lines), time.perf_counter() - started)
    ]


# --- MCP ---


def _mcp_values(hidden: Any) -> dict[str, list[Any]]:
    all_ids = [*hidden.ids.values(), *hidden.extra_ids.values()]
    return {
        "project": ["P123"],
        "scope": [SCOPE],
        "number": [*hidden.numbers.values(), "P123-THR-0001", "P123-CWP-CIV-0001"],
        "record": [*all_ids, *hidden.numbers.values()],
        "record_id": all_ids,
        "derived": ["x"],
        "type_ref": ["x"],
        "code_list": ["x"],
        "from_code": ["A"],
        "to_code": ["B"],
        "q": ["", *TOKENS.values()],
        "schedule": ["MAIN", "x"],
        "activity_id": ["x"],
        "code": ["MER", "x", "1.1.1"],
        "lot": ["P123-RCPT-0001@1", "x"],
        "iwp": [*hidden.numbers.values(), "P123-IWP-0001", "x"],
    }


def mcp_actor(reader: str) -> str:
    return f"agent:{reader}" if reader == "bot" else f"user:{reader}"


def _tool_text(server: Any, tool: str, args: dict[str, Any]) -> str:
    try:
        result = asyncio.run(server.call_tool(tool, args))
    except ToolError as exc:
        return f"ERROR {exc}"
    return result.model_dump_json() if hasattr(result, "model_dump_json") else str(result)


def mcp_calls(
    world: World, reader: str, hidden: Any, lake_dir: Path | None = None, tw: Twinning | None = None
) -> list[Call]:
    ask = tw.ask if tw else (lambda t: t)
    server = build_server(
        world.h.backend, actor=mcp_actor(reader), lake_dir=lake_dir or world.root / "lake"
    )
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    reading = {
        name: t
        for name, t in tools.items()
        if t.annotations is not None and t.annotations.read_only_hint and name != "lake_query"
    }
    cands = _mcp_values(hidden)
    out: list[Call] = []
    for name, tool in sorted(reading.items()):
        props = list(tool.input_schema.get("properties", {}))
        for param in tool.input_schema.get("required") or []:
            assert param in cands, f"{name}: add values for the argument {param!r}"
        names = [p for p in props if p in cands]
        for combo in itertools.islice(itertools.product(*(cands[p] for p in names)), 80):
            args = dict(zip(names, combo, strict=True))
            if args.get("q") == "":
                args.pop("q")
            started = time.perf_counter()
            reply = _tool_text(
                server, name, {k: ask(v) if isinstance(v, str) else v for k, v in args.items()}
            )
            out.append(Call("mcp", f"{name} {args}", reader, reply, time.perf_counter() - started))
    return out


# --- the lake ---

LAKE_SQL = (
    "SELECT * FROM events ORDER BY seq",
    "SELECT * FROM cur_core_record ORDER BY id",
    "SELECT * FROM cur_core_link ORDER BY 1",
    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' ORDER BY 1",
)


def sync_world_lake(world: World) -> Path:
    lake = world.root / "lake"
    engine = make_engine(world.target)
    try:
        with read_snapshot(engine) as conn:
            sync_lake(LakeConfig.at(lake), conn, now=lambda: FIXED_NOW)
    finally:
        engine.dispose()
    return lake


def mask_chain_columns(data: dict[str, Any]) -> None:
    """The lake columns the MASKS "hash chain" and "redacted row scope" entries name; a file's
    content hash stays."""
    cols = data.get("columns", [])
    chain = [i for i, c in enumerate(cols) if c in LAKE_HASH_COLUMNS]
    kind, scope = (cols.index(c) if c in cols else -1 for c in ("event_type", "scope"))
    for row in data.get("rows", []):
        for i in chain:
            if isinstance(row[i], str) and re.fullmatch(r"[0-9a-f]{64}", row[i]):
                row[i] = "HASH"
        if kind >= 0 and scope >= 0 and row[kind] == "Internal.Redacted":
            row[scope] = REDACTED_SCOPE


def lake_calls(world: World, reader: str, lake: Path) -> list[Call]:
    server = build_server(world.h.backend, actor=mcp_actor(reader), lake_dir=lake)
    out: list[Call] = []
    for sql in LAKE_SQL:
        started = time.perf_counter()
        reply = _tool_text(server, "lake_query", {"sql": sql, "limit": 1000})
        try:
            data = json.loads(reply)
            data = data.get("structured_content") or data
            for volatile in ("snapshot_id", "as_of", "elapsed_ms", "content"):
                data.pop(volatile, None)
            # the chain hashes, by column (MASKS "hash chain"); a file's content hash stays
            mask_chain_columns(data)
            reply = json.dumps(data, sort_keys=True)
        except (ValueError, AttributeError):
            pass
        out.append(Call("lake", sql, reader, reply, time.perf_counter() - started))
    return out


# --- the CLI ---

CLI_FIXED = (
    ["events", "tail", "--project", "P123", "-n", "500"],
    ["corr", "ls", "--project", "P123"],
    ["rfi", "ls", "--project", "P123"],
    ["comm", "ls", "--project", "P123"],
    ["doc", "ls", "--project", "P123"],
    ["feed", "ls", "--project", "P123"],
    ["constraint", "ls", "--project", "P123"],
)
CLI_PER_KEY = (
    ["record", "show"],
    ["corr", "show"],
    ["link", "list"],
    ["thread", "show"],
    ["evidence"],
)


def cli_calls(
    world: World, reader: str, hidden: Any, session_file: Path, tw: Twinning | None = None
) -> list[Call]:
    """CLI reads through Typer's runner, signed in as the reader (agents have no CLI session)."""
    import os
    from unittest import mock

    ask = tw.ask if tw else (lambda t: t)
    if reader == "bot":
        return []
    target = world.target
    env = {"TL_DB": str(target), "TL_SESSION_FILE": str(session_file), "TL_ENV": "test"}
    keys = [*hidden.numbers.values(), FAKE_ID, "P123-NOPE-0001"]
    runner = CliRunner()
    out: list[Call] = []
    with mock.patch.dict(os.environ, env):
        cli_session.save(
            cli_session.StoredSession(
                target=cli_session.db_target(target),
                username=reader,
                actor=f"user:{reader}",
                expires_at="2099-01-01T00:00:00Z",
                token=world.tokens[reader],
            )
        )
        commands = [*CLI_FIXED]
        for base in CLI_PER_KEY:
            commands += [[*base, key, "--project", "P123"] for key in keys]
        commands += [["file", "ls", "--project", "P123", "--record", key] for key in keys]
        for args in commands:
            started = time.perf_counter()
            result = runner.invoke(cli_app, [ask(a) for a in args], env=env)
            reply = f"{result.exit_code}\n{result.output}"
            out.append(
                Call("cli", "tl " + " ".join(args), reader, reply, time.perf_counter() - started)
            )
    return out


# --- webhooks ---


def webhook_calls(
    world: World, reader: str, bodies: dict[tuple[str, str], list[str]]
) -> list[Call]:
    return [
        Call("webhook", f"delivery {mode}", reader, "\n".join(bodies[(reader, mode)]), 0.0)
        for mode in ("thin", "delta", "full")
    ]


# --- comparison ---


@dataclass
class Failure:
    channel: str
    route: str
    reader: str
    a: str
    b: str

    def __str__(self) -> str:
        at = next(
            (i for i, (x, y) in enumerate(zip(self.a, self.b, strict=False)) if x != y),
            min(len(self.a), len(self.b)),
        )
        return (
            f"{self.channel} | {self.route[:140]} | as {self.reader}\n"
            f"    A: ...{self.a[max(0, at - 40) : at + 100]!r}\n"
            f"    B: ...{self.b[max(0, at - 40) : at + 100]!r}"
        )


def diff(a: list[Call], b: list[Call], tw: Twinning) -> tuple[list[Failure], list[str]]:
    """(differences, slow flags). ``b`` is read through the table of ids first."""
    failures: list[Failure] = []
    slow: list[str] = []
    assert [c.route for c in a] == [c.route for c in b], "the two walks made different calls"
    for left, right in zip(a, b, strict=True):
        mapped = mask(left.channel, drop_fillers(tw.answer(right.body)))
        left_body = mask(left.channel, left.body)
        if left.wall - right.wall > 0.1 and left.wall > 2 * right.wall:
            slow.append(
                f"{left.channel} {left.route} as {left.reader}: "
                f"A {left.wall:.3f}s B {right.wall:.3f}s"
            )
        if left_body != mapped:
            failures.append(Failure(left.channel, left.route, left.reader, left_body, mapped))
    return failures, slow


# --- leaks the walk found ---


def _redacted_row(unit: str) -> str:
    """What the lake shows a reader in the place of an event it may not read: a placeholder row."""
    seq = unit[1 : unit.index(",")]
    return (
        f'[{seq},"redacted-{seq}","internal","internal",1,"Internal.Redacted",1,"{REDACTED_SCOPE}","{{}}",'
        f'"internal","2026-10-19T00:00:00.000000+00:00","2026-10-19T00:00:00.000000+00:00",'
        f'"redacted-{seq}",null,"internal",null,"redacted",null]'
    )


Where = tuple[tuple[str, str], ...]  # (channel, a fragment of the route that is never empty)


@dataclass(frozen=True)
class Leak:
    reason: str  # "LEAK: ..." (the text of the strict xfail)
    group: str  # the readers whose worlds show it
    # what the leak writes into a response, masked where ``mask_where`` says: the twins then agree
    mask: re.Pattern[str] | None = None
    mask_where: Where = ()
    # or: a unit (a JSON object, a row, a line) that is in B's answer and not in A's (a card, an
    # event the reader is not given): it is cut out of B where ``where`` says, and the rest of
    # the answer must then be byte for byte A's
    extra_in_b: str | None = None
    where: Where = ()
    # what A shows in the place of the unit it does not give (None: nothing)
    stands_for: Callable[[str], str] | None = None
    # the answer is a page of fixed size: A shows older units where B shows the cut ones
    page_shift: bool = False

    def __post_init__(self) -> None:
        for scope, used in ((self.mask_where, self.mask), (self.where, self.extra_in_b)):
            assert bool(scope) == bool(used), (
                f"a leak that sets a mask or an extra names its calls: {self}"
            )
            assert all(c and frag for c, frag in scope), f"no empty route fragment: {self}"


LEAKS = {
    "dedup-flag": Leak(
        "LEAK: File.Attached of a visible document says deduplicated=true when a file the reader "
        "may not read has the same bytes (events, history, webhooks delta/full, lake)",
        "bob+bot",
        mask=re.compile(r'(\\*"deduplicated\\*": ?)(true|false)'),
        mask_where=(
            ("api", "GET /events "),
            ("lake", "SELECT * FROM events"),
            ("webhook", "delivery delta"),
            ("webhook", "delivery full"),
        ),
    ),
    "link-total": Leak(
        "LEAK: link_total of /links/search counts links to records the reader may not read "
        "(owner ruling 2026-11-09: it must count only the visible links)",
        "bob+bot",
        mask=re.compile(r'("link_total": ?)\d+'),
        mask_where=(("api", "GET /links/search "),),
    ),
    "transmittal-line": Leak(
        "LEAK: a transmittal that lists a revision the reader may not read keeps its position "
        "(position 2 with no 1), and its Transmittal.Defined event is withheld from the reader",
        "bob+bot",
        mask=re.compile(r'(\\*"position\\*": ?)\d+'),
        mask_where=(("api", "GET /projects/P123/transmittals/"), ("mcp", "get_transmittal ")),
        extra_in_b="Transmittal.Defined",
        stands_for=lambda unit: _redacted_row(unit) if unit.startswith("[") else "",
        where=(
            ("api", "GET /events "),
            ("api", "/activity "),
            ("api", "/history "),
            ("cli", "tl events tail"),
            ("lake", "SELECT * FROM events"),
            ("webhook", "delivery "),
        ),
    ),
    "webhook-target": Leak(
        "LEAK: a delta or full webhook of a constraint whose target is unreadable carries "
        "the target's id and kind (the API and the events show null)",
        "bob+bot",
        mask=re.compile(
            r'(\\*"target_id\\*": ?)(null|\\*"[0-9A-Z]{26}\\*")'
            r'(, ?\\*"target_kind\\*": ?)(null|\\*"record\\*")'
        ),
        mask_where=(("webhook", "delivery delta"), ("webhook", "delivery full")),
    ),
    "feed-card-group": Leak(
        "LEAK: the feed folds consecutive events into one card and withholds the whole card when "
        "one event is hidden, so the card of a visible link is missing next to a hidden one",
        "amy",
        extra_in_b="ctl added a link",
        where=(("api", "GET /feed "), ("cli", "tl feed ls")),
        page_shift=True,
    ),
}


def _in_scope(failure: Failure, where: Where) -> bool:
    return any(failure.channel == c and frag in failure.route for c, frag in where)


def _opener(text_: str, at: int) -> int:
    """The ``{`` or ``[`` that opens the bracket holding ``text_[at]`` on its line; -1 when none."""
    line = text_.rfind("\n", 0, at) + 1
    depth = 0
    for i in range(at - 1, line - 1, -1):
        if text_[i] in "}]":
            depth += 1
        elif text_[i] in "{[":
            if depth == 0:
                return i
            depth -= 1
    return -1


def _unit_at(text_: str, at: int) -> tuple[int, int]:
    """The element of a JSON list that holds ``text_[at]`` (an event, a row, a card); when no list
    holds it on its line, the line."""
    inner = _opener(text_, at)
    while inner >= 0:
        outer = _opener(text_, inner)
        if outer >= 0 and text_[outer] == "[":
            end = _object_end(text_, inner) if text_[inner] == "{" else _list_end(text_, inner)
            return inner, end
        inner = outer
    line = text_.rfind("\n", 0, at) + 1
    end = text_.find("\n", at)
    return line, len(text_) if end < 0 else end + 1


def _list_end(text_: str, start: int) -> int:
    depth, quoted, at = 0, False, start
    while at < len(text_):
        ch = text_[at]
        if quoted:
            if ch == "\\":
                at += 1
            quoted = ch != '"'
        elif ch == '"':
            quoted = True
        elif ch in "[]":
            depth += 1 if ch == "[" else -1
            if depth == 0:
                return at + 1
        at += 1
    raise AssertionError("an unfinished JSON list")


def cut_extra(a: str, b: str, leak: Leak) -> tuple[str, int]:
    """``b`` without the units that hold the leak's marker and that ``a`` does not hold (and the
    comma or the line that went with each), and how many; the rest of ``b`` is not touched. A leak
    that ``stands_for`` its unit puts what A shows there instead."""
    assert leak.extra_in_b
    at, cut = len(b), 0
    while (at := b.rfind(leak.extra_in_b, 0, at)) >= 0:
        start, end = _unit_at(b, at)
        unit = b[start:end].rstrip("\n")
        if unit not in a:
            cut += 1
            instead = leak.stands_for(unit) if leak.stands_for else ""
            if instead:
                b = b[:start] + instead + b[start + len(unit) :]
            else:
                if b[end : end + 1] == ",":
                    end += 1
                elif b[start - 1 : start] == ",":
                    start -= 1
                elif b[start - 1 : start] == "\n" and b[end - 1 : end] == "\n":
                    pass  # a whole line goes, with its own newline
                b = b[:start] + b[end:]
        at = start
    return b, cut


def _page_shift(a: str, b: str, cut: int) -> bool:
    """What the cut units drag along on a page of fixed size: A shows at most ``cut`` older units
    at the end where B had the cut ones; ``next_before`` and the label of a record that only one
    page names may differ (labels that both name must agree). Nothing else may."""
    head_a, _, tail_a = a.partition("\n")
    head_b, _, tail_b = b.partition("\n")
    if head_a != head_b:
        return False
    try:
        da, db = json.loads(tail_a), json.loads(tail_b)
    except ValueError:  # text: B's lines, then at most ``cut`` more
        la, lb = a.splitlines(), b.splitlines()
        return len(lb) < len(la) <= len(lb) + cut and la[: len(lb)] == lb
    ia, ib = da.pop("items", None), db.pop("items", None)
    if ia is None or ib is None or not (0 <= len(ia) - len(ib) <= cut) or ia[: len(ib)] != ib:
        return False
    la, lb = da.pop("labels", {}), db.pop("labels", {})
    da.pop("next_before", None), db.pop("next_before", None)
    return da == db and all(la[k] == lb[k] for k in la.keys() & lb.keys())


def explained_by(failure: Failure) -> set[str]:
    """The leaks that account for a difference; empty when something else is going on.

    A leak counts only on the calls it names (channel and route), only for the one thing it writes
    (a masked field, or one cut-out unit), and the rest of the answer must be A's byte for byte."""
    a, b, names = failure.a, failure.b, set[str]()
    for name, leak in LEAKS.items():
        if leak.mask is None or not _in_scope(failure, leak.mask_where):
            continue
        a2, b2 = leak.mask.sub(r"\1N", a), leak.mask.sub(r"\1N", b)
        if (a2, b2) != (a, b):
            names.add(name)
            a, b = a2, b2
    for name, leak in LEAKS.items():
        if leak.extra_in_b and _in_scope(failure, leak.where):
            b2, cut = cut_extra(a, b, leak)
            if cut:
                names.add(name)
                b = b2
                if leak.page_shift and a != b and _page_shift(a, b, cut):
                    return names
    return names if a == b else set()
