"""Twin worlds for the twin walk (outside review 2026-11-09, section 1, "Harness").

World A is the seed of ``tl_mod_correspondence.confseed`` as it is. World B is the same script
with every step that writes something the reader may not read left out; where a step was left out,
B appends as many filler events on a throwaway ``core.Account`` stream (which every reader skips)
and burns as many ids, so ``seq`` numbers and ids of everything both worlds hold are equal. The
clock is fixed and ids come from a counter, so a record that exists in both worlds is the same
record, byte for byte, and the table that maps ids of A to ids of B is the identity.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from random import Random
from typing import Any

import pytest
from harness import Harness
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow
from tl_core import confidentiality as cf
from tl_core import util
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from tl_core.constraints.commands import RaiseConstraint
from tl_core.constraints.handlers import handle_raise_constraint
from tl_core.ledger import NewEvent
from tl_core.webhooks.delivery import DeliveryEngine
from tl_core.webhooks.dispatch import Dispatcher
from tl_core.webhooks.egress import EgressPolicy
from tl_core.webhooks.retry import RetryPolicy
from tl_core.webhooks.subscriptions import CreateWebhookSubscription, create_subscription
from tl_core.webhooks.testing import FakeClock, ScriptedTransport
from tl_mod_correspondence.confseed import Hidden, seed_hidden_world
from tl_mod_legacy.testing import seed_restricted_run
from ulid import ULID

ROOT = Path(__file__).resolve().parents[2]
FIXED_NOW = datetime(2026, 10, 19, 9, 0, 0, tzinfo=UTC)
PASSWORD = "correct horse battery"
READERS = ("bob", "ctl", "boss", "amy", "bot")
MODES = ("thin", "delta", "full")
SCOPE = "project:P123"


def load_walk() -> Any:
    """The readers and routes of the API walk (a test file, so it is loaded by path)."""
    path = ROOT / "packages" / "tl-api" / "tests" / "test_confidentiality_walk.py"
    spec = importlib.util.spec_from_file_location("tl_api_confidentiality_walk", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --- a fixed clock and a counter for ids ---


class _Frozen(datetime):
    @classmethod
    def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
        return FIXED_NOW if tz is not None else FIXED_NOW.replace(tzinfo=None)


class Ids:
    """``new_ulid`` as a counter; ``reset`` starts every world at the same id."""

    def __init__(self) -> None:
        self.count = 0
        self.muted = 0  # ids taken by filler events come from a range of their own
        self.quiet = False
        self.trace: list[str] = []  # the call site of every id, by number - 1

    def reset(self) -> None:
        self.count = self.muted = 0
        self.quiet = False
        self.trace = []

    def next(self) -> str:
        if self.quiet:
            self.muted += 1
            return str(ULID.from_int((1 << 99) + self.muted))
        self.count += 1
        code = sys._getframe(3).f_code  # next <- __str__ <- new_ulid <- the caller
        self.trace.append(f"{code.co_filename}:{code.co_name}")
        return str(ULID.from_int((1 << 100) + self.count))


IDS = Ids()


class _CounterUlid:
    def __str__(self) -> str:
        return IDS.next()


def freeze(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(util, "datetime", _Frozen)
    monkeypatch.setattr(util, "ULID", _CounterUlid)


# --- the twin hook of the seed ---


def head_seq(target: DbTarget) -> int:
    with open_uow(target, readonly=True) as uow:
        return int(
            uow.conn().execute(text("SELECT COALESCE(MAX(seq), 0) FROM events")).scalar_one()
        )


class Marks:
    """The ``Twin`` of the seed. In A it records (head seq, ids used) at every step; in B it answers
    ``True`` for a step that writes a kind in ``secret`` and, before each step, pads B up to what
    A had at that step."""

    def __init__(self, target: DbTarget, secret: frozenset[str], twin_of: Marks | None) -> None:
        self.target, self.twin_of, self.seen = target, twin_of, 0
        self.replay = None if twin_of is None else twin_of.recorded
        self.last = (0, 0)  # (ids of A, ids of B) at the step before
        self.recorded: list[tuple[int, int]] = []
        # a restricted item takes its file with it
        self.secret = secret | ({"file"} if "restricted" in secret else set())
        self.fillers = 0
        self.a_trace: list[str] = []  # in A: the call site of every id (copied when A is done)
        self.skews: list[tuple[int, int]] = []  # (B id counter at the step, ids B is ahead by)

    def mark(self, kind: str | None) -> bool:
        if self.replay is None:
            self.recorded.append((head_seq(self.target), IDS.count))
            return False
        seq, ids = self.replay[self.seen]
        self.seen += 1
        self._pad(seq, ids)
        return kind in self.secret

    def _pad(self, seq: int, ids: int) -> None:
        missing = seq - head_seq(self.target)
        assert missing >= 0, "B is ahead of A"
        if missing:
            self.fillers += 1
            IDS.quiet = True
            with open_uow(self.target) as uow:
                uow.append(
                    stream_id=f"twin-filler-{self.fillers}",
                    stream_type="core.Account",
                    scope=SCOPE,
                    expected_version=0,
                    events=[NewEvent(event_type="Account.TwinFiller", payload={})] * missing,
                    actor="svc:twin",
                    source="twin",
                    correlation_id="twin",
                )
            IDS.quiet = False
        target = ids + (self.skews[-1][1] if self.skews else 0)  # B's ids sit above A's by the skew
        if target >= IDS.count:
            IDS.trace += ["-"] * (target - len(IDS.trace))  # burnt ids
            IDS.count = target
        else:  # B took ids A did not (a file A deduplicated): later ids of B sit above A's
            self._skew(ids)
        self.last = (ids, IDS.count)

    def _skew(self, ids: int) -> None:
        """Find where B's ids of the step part from A's (one id more in B, here and nowhere else),
        so the ids of B after that point can be written as the ids of A."""
        assert self.twin_of is not None
        a_from, b_from = self.last
        a_steps = self.twin_of.trace_of(a_from, ids)
        b_steps = IDS.trace[b_from : IDS.count]
        extra = len(b_steps) - len(a_steps)
        first = next(
            (i for i, (x, y) in enumerate(zip(a_steps, b_steps, strict=False)) if x != y), None
        )
        assert first is not None or extra > 0, (
            "ids of B differ from A in a way the map cannot cover"
        )
        at = len(a_steps) if first is None else first
        assert a_steps[at:] == b_steps[at + extra :], "B's ids after the split do not follow A's"
        self.skews.append((b_from + at + 1, (self.skews[-1][1] if self.skews else 0) + extra))

    def trace_of(self, start: int, stop: int) -> list[str]:
        return self.a_trace[start:stop]


# --- a world ---


@dataclass
class World:
    name: str
    h: Harness
    hidden: Hidden
    tokens: dict[str, str]  # reader -> session or agent token
    subs: dict[tuple[str, str], str]  # (reader, mode) -> webhook subscription id
    root: Path
    clock: FakeClock
    marks: Marks
    transport: ScriptedTransport = field(default_factory=ScriptedTransport)

    @property
    def target(self) -> DbTarget:
        return self.h.target or self.h.db

    def close(self) -> None:
        self.h.close()


def _person(uow: Any, name: str, roles: list[str]) -> None:
    accounts.create_account(
        uow,
        username=name,
        display_name=name.title(),
        kind="person",
        roles=roles,  # type: ignore[arg-type]
        password=prepare_password(PASSWORD),
        by="svc:test",
    )


def secret_kinds(may_read: set[str]) -> frozenset[str]:
    """What a reader may not read: every kind of the seed they are not given, a class nobody reads
    included."""
    everything = {
        "open",
        "restricted",
        "privileged",
        "bogus",
        "document",
        "file",
        "commercial",
        "secret_rfi",
        "loadrun",
    }
    return frozenset(everything - may_read - {"open"})


def build_world(
    name: str,
    target: DbTarget,
    root: Path,
    walk: Any,
    secret: frozenset[str],
    twin_of: Marks | None,
) -> World:
    """One world; ``twin_of`` is None for A, and A's marks for B."""
    root.mkdir(parents=True)
    IDS.reset()
    h = Harness.build(root, target=target)
    clock = FakeClock(FIXED_NOW)
    marks = Marks(target, secret, twin_of)
    with h.backend(False) as uow:
        _person(uow, "bob", ["user"])
        _person(uow, "ctl", ["document_controller"])
        _person(uow, "boss", ["admin"])
        _person(uow, "amy", ["user"])
        bot = accounts.create_account(
            uow, username="bot", display_name="Bot", kind="agent", roles=["user"], password=None,
            by="svc:test",
        )  # fmt: skip
        _, agent_token = accounts.issue_agent_token(
            uow,
            account_id=bot.account_id,
            label="walk",
            expires_at=FIXED_NOW + timedelta(days=1),
            by="svc:test",
        )
    tokens = {
        who: sessions.sign_in(h.backend, username=who, password=PASSWORD)[1]
        for who in ("bob", "ctl", "boss", "amy")
    }
    tokens["bot"] = agent_token
    subs: dict[tuple[str, str], str] = {}
    for who in READERS:
        for mode in MODES:
            with h.backend() as uow:
                owner = f"agent:{who}" if who == "bot" else f"user:{who}"
                issued = create_subscription(
                    uow,
                    CreateWebhookSubscription(
                        actor=owner,
                        source="test",
                        scope=SCOPE,
                        name=f"hook {who} {mode}",
                        target_url="https://hook.test/in",
                        filter={},
                        payload_mode=mode,  # type: ignore[arg-type]
                    ),
                    clock=clock,
                )
            subs[(who, mode)] = issued.subscription_id
    hidden = seed_hidden_world(target, h.service, root, twin=marks)
    if not marks.mark("loadrun"):
        run_id, run_files = seed_restricted_run(target, h.service)
        hidden.ids["loadrun"] = run_id
        hidden.extra_ids.update({f"loadrun_{slot}_file": fid for slot, fid in run_files.items()})
    _constraint_on_open_item(target, hidden, marks.mark("restricted"))
    marks.mark(None)
    marks.a_trace = list(IDS.trace)
    return World(name, h, hidden, tokens, subs, root, clock, marks)


def _constraint_on_open_item(target: DbTarget, hidden: Hidden, no_target: bool) -> None:
    """A constraint on the open item whose target is the restricted item (``Constraint.Raised`` is
    the payload reference of ``intent.PAYLOAD_REFS``); where the restricted item never existed the
    constraint has no target. It is the last step: the link to the hidden target is the last event
    of the step, and B's filler takes its place. (A clear that names the hidden record as its
    resolver puts its link between visible events, where a filler cannot stand.)"""
    gone = None if no_target else hidden.ids["restricted"]
    cmd = {"actor": "user:ctl", "source": "test", "scope": SCOPE}
    with cf.system_view(), open_uow(target) as uow:
        raised = handle_raise_constraint(
            uow,
            RaiseConstraint(
                **cmd,
                subject=hidden.ids["open"],
                phase="execution",
                severity="advisory",
                category="other",
                owner="user:amy",
                description="Waiting on the hidden item",
                target=gone,
            ),
        )
    hidden.ids["constraint"] = raised.stream_id
    hidden.numbers["constraint"] = raised.key or ""


def webhook_bodies(world: World) -> dict[tuple[str, str], list[str]]:
    """What each subscription was sent: the dispatcher and the delivery engine run to idle."""
    Dispatcher(world.h.backend, clock=world.clock).run_until_idle()
    engine = DeliveryEngine(
        world.h.backend,
        world.transport,
        egress=EgressPolicy((), lambda host, port: ["93.184.216.34"]),
        retry=RetryPolicy(base_s=10, jitter=0),
        clock=world.clock,
        rng=Random(1),
        worker_id="twin",
    )
    while engine.run_cycle(limit=50).claimed:
        pass
    by_sub = {sid: key for key, sid in world.subs.items()}
    out: dict[tuple[str, str], list[str]] = {key: [] for key in world.subs}
    with open_uow(world.target, readonly=True) as uow:
        rows = uow.conn().execute(
            text("SELECT subscription_id, body FROM wh_delivery ORDER BY seq, subscription_id")
        )
        for sid, body in rows:
            out[by_sub[str(sid)]].append(str(body))
    return out
