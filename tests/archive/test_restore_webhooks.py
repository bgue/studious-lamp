"""A restored database has webhook subscriptions but no signing secrets (L-P0-I7-A9).

Secrets are never in the ledger. The delivery engine must send nothing unsigned, dead-letter
nothing, keep the deliveries pending, say so (a log line per subscription, `needs_secret` in
listings, a restore warning), and send them with a valid signature once the secret is rotated.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from tl_adapters.db import (
    DbTarget,
    create_schema,
    make_engine,
    make_uow_factory,
    read_tx,
)
from tl_adapters.restore import restore_from_archive
from tl_core.archive import generate_signer, seal_segment
from tl_core.webhooks import queries
from tl_core.webhooks.signing import SigningSecret, verify
from tl_core.webhooks.subscriptions import RotateWebhookSecret, rotate_secret
from tl_core.webhooks.testing import FakeClock, ScriptedTransport

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "webhooks"))

from world import SCOPE, World  # noqa: E402


@pytest.fixture
def restored_world(
    new_db: Callable[[], DbTarget], memory_store: Callable[..., Any]
) -> Iterator[tuple[World, str, list[str]]]:
    """A restored copy of a ledger with one subscription and three records after it."""
    original = new_db()
    create_schema(original)
    factory = make_uow_factory(original)
    world = World(original, factory, FakeClock(), ScriptedTransport())
    subscription = world.subscribe()
    for key in ("A-1", "A-2", "A-3"):
        world.record(key)
    factory.dispose()

    signer = generate_signer()
    store = memory_store()
    engine = make_engine(original)
    try:
        with read_tx(engine) as conn:
            assert seal_segment(conn, store, signer) is not None
    finally:
        engine.dispose()

    target = new_db()
    result = restore_from_archive(store, target, public_key=signer.public_key)
    new_factory = make_uow_factory(target)
    fresh = World(target, new_factory, FakeClock(), ScriptedTransport())
    yield fresh, subscription.subscription_id, list(result.warnings)
    new_factory.dispose()


def test_restore_warns_for_each_subscription_that_needs_a_secret(
    restored_world: tuple[World, str, list[str]],
) -> None:
    _, subscription_id, warnings = restored_world
    [per_subscription, dispatcher] = warnings
    assert per_subscription == (
        f"webhook subscription {subscription_id} (scope {SCOPE}) has no signing secret after the "
        f"restore and sends nothing until you run: tl webhook rotate-secret {subscription_id} "
        "--project P1"
    )
    assert dispatcher == (
        "the webhook dispatcher starts at the restored head (seq 4): events up to it are not "
        "queued again. A receiver may have missed events between its last delivery and the "
        "restore point; replay them with: tl webhook replay <subscription id> --from-seq N "
        "--to-seq 4"
    )


def test_the_dispatcher_starts_at_the_restored_head_so_no_history_is_queued(
    restored_world: tuple[World, str, list[str]],
) -> None:
    world, _, _ = restored_world
    assert world.query("SELECT last_seq FROM wh_cursor WHERE name = 'outbox'") == [{"last_seq": 4}]
    assert world.dispatcher().run_until_idle().created == 0
    assert world.query("SELECT COUNT(*) AS n FROM wh_delivery")[0]["n"] == 0
    assert world.engine().claim(10) == []
    assert world.transport.sent == []


def test_a_new_event_for_a_restored_subscription_waits_for_its_secret(
    restored_world: tuple[World, str, list[str]], caplog: pytest.LogCaptureFixture
) -> None:
    world, subscription_id, _ = restored_world
    world.record("A-4")
    world.dispatcher().run_until_idle()
    engine = world.engine()
    with caplog.at_level(logging.WARNING, logger="tl_core.webhooks.delivery"):
        assert engine.claim(10) == []
        assert engine.claim(10) == []  # a second cycle logs again, once per cycle
    assert world.transport.sent == []  # nothing, signed or unsigned, left the process

    rows = world.query("SELECT status, attempts FROM wh_delivery ORDER BY seq")
    assert [(r["status"], r["attempts"]) for r in rows] == [("pending", 0)]  # not dead, not tried
    assert world.query("SELECT COUNT(*) AS n FROM wh_attempt")[0]["n"] == 0

    warned = [r for r in caplog.records if subscription_id in r.getMessage()]
    assert len(warned) == 2 and engine.needs_secret == [subscription_id]
    assert "secret_id" not in " ".join(r.getMessage() for r in caplog.records)

    with world.factory(readonly=True) as uow:
        [row] = queries.list_subscriptions(uow)
    assert row["status"] == "active" and row["status_label"] == "needs_secret"
    assert row["needs_secret"] is True and row["pending"] == 1 and row["dead"] == 0


def rotate(world: World, subscription_id: str) -> Any:
    with world.factory() as uow:
        return rotate_secret(
            uow,
            RotateWebhookSecret(
                actor="user:alice", source="test", scope=SCOPE, subscription_id=subscription_id
            ),
            clock=world.clock,
        )


def drain(world: World, engine: Any) -> int:
    delivered = 0
    for _ in range(10):
        claims = engine.claim(10)
        if not claims:
            break
        for claim in claims:
            assert engine.deliver(claim).state == "delivered"
            delivered += 1
    return delivered


def test_after_rotate_secret_no_history_goes_out_and_a_new_event_does_signed(
    restored_world: tuple[World, str, list[str]],
) -> None:
    world, subscription_id, _ = restored_world
    issued = rotate(world, subscription_id)  # appends one event itself: seq 5, a new event
    engine = world.engine()

    world.dispatcher().run_until_idle()  # one worker cycle on the restored database
    assert drain(world, engine) == 1  # only that rotation event, none of seq 2 to 4
    assert [r["seq"] for r in world.query("SELECT seq FROM wh_delivery")] == [5]

    world.record("A-4")  # seq 6
    world.dispatcher().run_until_idle()
    assert drain(world, engine) == 1
    delivered = world.query("SELECT seq FROM wh_delivery WHERE status = 'delivered' ORDER BY seq")
    assert [r["seq"] for r in delivered] == [5, 6]
    assert len(world.transport.sent) == 2
    for request in world.transport.sent:
        verify(
            request.headers,
            request.body,
            [SigningSecret(issued.secret)],
            now=world.clock().timestamp(),
        )  # raises SignatureError if the signature is wrong
    last = json.loads(world.transport.sent[-1].body)
    assert (
        last["id"] == world.query("SELECT event_id FROM outbox_events WHERE seq = 6")[0]["event_id"]
    )
    with world.factory(readonly=True) as uow:
        [row] = queries.list_subscriptions(uow)
    assert row["status_label"] == "active" and row["pending"] == 0


def test_replay_covers_a_range_a_receiver_may_have_missed(
    restored_world: tuple[World, str, list[str]],
) -> None:
    world, subscription_id, _ = restored_world
    issued = rotate(world, subscription_id)
    engine = world.engine()
    assert (
        world.dispatcher().replay(subscription_id, 1, 4) == 4
    )  # the creation event and the three records
    assert drain(world, engine) == 4 and len(world.transport.sent) == 4
    for request in world.transport.sent:
        verify(
            request.headers,
            request.body,
            [SigningSecret(issued.secret)],
            now=world.clock().timestamp(),
        )


def test_the_cli_shows_needs_secret_after_a_restore_and_active_after_rotating(
    tmp_path: Path,
) -> None:
    from tl_cli.main import app
    from typer.testing import CliRunner

    runner = CliRunner()
    env = {"TL_DB": str(tmp_path / "tl.db"), "TL_ENV": "dev"}
    archive = f"--archive={tmp_path / 'archive'}"
    key = f"--key={tmp_path / 'k' / 'a.key'}"

    def run(*args: str, **kw: str) -> Any:
        result = runner.invoke(app, list(args), env={**env, **kw})
        assert result.exit_code == 0 and result.exception is None, result.output
        return result

    run("init")
    run("record", "create", "--project", "P1", "--title", "One", "--key", "K-1")
    added = run("webhook", "add", "--project", "P1", "--name", "n", "--url", "https://hook.test/x")
    subscription = added.stdout.splitlines()[0].split()[1]
    run("archive", "keygen", key)
    run("archive", "seal", archive, key)

    restored = str(tmp_path / "restored.db")
    result = run(
        "restore",
        "--from-archive",
        str(tmp_path / "archive"),
        "--db",
        restored,
        "--public-key",
        str(tmp_path / "k" / "a.pub"),
    )
    assert f"warning: webhook subscription {subscription} (scope project:P1) has no signing" in (
        result.stderr
    )
    listing = runner.invoke(app, ["--db", restored, "webhook", "ls"], env=env)
    assert listing.exit_code == 0, listing.output
    assert listing.stdout.split("\t")[:2] == [subscription, "needs_secret"]

    rotated = runner.invoke(
        app,
        ["--db", restored, "webhook", "rotate-secret", subscription, "--project", "P1"],
        env=env,
    )
    assert rotated.exit_code == 0 and rotated.exception is None, rotated.output
    listing = runner.invoke(app, ["--db", restored, "webhook", "ls"], env=env)
    assert listing.stdout.split("\t")[:2] == [subscription, "active"]


def test_send_test_refuses_a_subscription_without_a_secret_before_any_egress_check(
    restored_world: tuple[World, str, list[str]],
) -> None:
    from tl_core.webhooks.subscriptions import SubscriptionNotActiveError

    world, subscription_id, _ = restored_world
    engine = world.engine()
    with pytest.raises(
        SubscriptionNotActiveError,
        match=f"no active signing secret; run `tl webhook rotate-secret {subscription_id}`",
    ):
        engine.send_test(subscription_id)
    assert world.resolver_calls == [] and world.transport.sent == []  # no DNS, no request

    rotate(world, subscription_id)
    assert engine.send_test(subscription_id).ok
    assert len(world.transport.sent) == 1
