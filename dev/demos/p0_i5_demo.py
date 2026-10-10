"""Demo driver for P0-I5 workstream B: signed, filtered webhook delivery, replay, DLQ, rotation.

Run by `dev/demos/P0-I5.sh` (`just demo P0-I5`). Uses a temporary ledger and a dev receiver on
127.0.0.1 (allow-listed with --allow-host; production egress never reaches loopback). Every `tl`
command runs in a subprocess exactly as a person would type it. Exits 1 when an expectation fails.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from tl_adapters.sqlite.uow import open_uow
from tl_core.ledger import NewEvent
from tl_core.webhooks.receiver import DevReceiver

SCOPE = "project:P123"


def fail(message: str) -> None:
    print(f"DEMO FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def expect(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def step(title: str) -> None:
    print(f"\n== {title}")


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="tl-p0-i5-"))
    env = {**os.environ, "TL_DB": str(work / "tl.db"), "TL_ENV": "dev", "TL_WEBHOOK_ALLOWLIST": ""}
    os.environ.update(TL_DB=env["TL_DB"])

    def tl(*args: str) -> dict[str, str]:
        """Run `tl <args>`, echo its output (secrets hidden) and return its `name value` lines."""
        done = subprocess.run(
            [sys.executable, "-c", "from tl_cli.main import app; app()", *args],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        shown = "\n".join(
            "secret whsec_<hidden>" if line.startswith("secret ") else line
            for line in done.stdout.splitlines()
        )
        print(f"$ tl {' '.join(args)}" + (f"\n{shown}" if shown else ""))
        if done.returncode != 0:
            fail(f"tl {' '.join(args)} exited {done.returncode}: {done.stderr.strip()}")
        found: dict[str, str] = {}
        for line in done.stdout.splitlines():
            name, _, value = line.partition(" ")
            found[name] = value
        return found

    def append(stream: str, event_type: str, payload: dict[str, object]) -> None:
        with open_uow(env["TL_DB"]) as uow:
            version = uow.ledger.stream_version(stream)
            uow.append(
                stream_id=stream,
                stream_type="core.Record",
                scope=SCOPE,
                expected_version=version,
                events=[NewEvent(event_type=event_type, payload=payload)],
                actor="user:jsmith",
                source="demo",
                correlation_id="demo",
            )

    def record_id(key: str) -> str:
        with open_uow(env["TL_DB"], readonly=True) as uow:
            from sqlalchemy import text

            row = uow.conn().execute(
                text("SELECT id FROM cur_core_record WHERE key = :k"), {"k": key}
            )
            return str(row.scalar_one())

    transition = {"workflow": "document", "workflow_version": 1, "transition": "issue"}

    with DevReceiver() as receiver:
        step("a ledger, two records, and a filtered subscription (delta mode, only 'Issued')")
        tl("init")
        tl("record", "create", "--project", "P123", "--key", "DOC-1", "--title", "Piping spec")
        tl("record", "create", "--project", "P123", "--key", "DOC-2", "--title", "Valve list")
        added = tl(
            "webhook", "add", "--project", "P123", "--name", "NDE contractor",
            "--url", receiver.url, "--mode", "delta",
            "--event-type", "Workflow.Transitioned", "--transition", "* -> Issued",
        )  # fmt: skip
        sid, secret = added["subscription"], added["secret"]
        receiver.set_secrets([secret])

        step("events: one matching transition, one that does not match, one unrelated update")
        # DOC-1 and DOC-2 exist before the subscription, so their creations are not delivered.
        doc1, doc2 = record_id("DOC-1"), record_id("DOC-2")
        append(
            doc1,
            "Workflow.Transitioned",
            {**transition, "from_state": "InReview", "to_state": "Issued"},
        )
        append(
            doc2,
            "Workflow.Transitioned",
            {**transition, "from_state": "Draft", "to_state": "InReview"},
        )
        append(doc2, "Record.Updated", {"changes": {"title": ["Valve list", "Valve list rev A"]}})

        step("tl webhook run --once: only the matching event is delivered, signed")
        summary = tl("webhook", "run", "--once", "--allow-host", "127.0.0.1")
        expect(summary["delivered"] == "1", f"expected 1 delivery, got {summary}")
        (message,) = receiver.messages()
        body = message.event()
        expect(message.verified, "the receiver could not verify the signature")
        expect(body["type"] == "tl.core.Workflow.Transitioned.v1", "wrong event type")
        expect(body["data"]["detail"]["to_state"] == "Issued", "wrong transition delivered")
        expect(body["data"]["changes"] == {"status": ["InReview", "Issued"]}, "wrong changes")
        expect(body["subject"] == f"urn:tl:{doc1}", "wrong subject")
        print(f"receiver verified {message.webhook_id} (tlseq {body['tlseq']}, "
              f"origin {body['data']['origin']['key']})")  # fmt: skip

        step("replay the whole seq range: the same event id arrives again, the receiver dedupes")
        replayed = tl("webhook", "replay", sid, "--from-seq", "1", "--to-seq", "999")
        expect(replayed["replayed"] == "1", f"expected 1 replayed, got {replayed}")
        tl("webhook", "run", "--once", "--allow-host", "127.0.0.1")
        expect(len(receiver.messages()) == 2, "the replay was not delivered")
        expect(len(receiver.unique()) == 1, "the replay carried a new event id")
        expect(receiver.messages()[1].duplicate, "the receiver did not flag the duplicate")

        step("a failing endpoint: 410 Gone goes straight to the dead-letter queue, then a redrive")
        events = tl(
            "webhook", "add", "--project", "P123", "--name", "All records",
            "--url", receiver.url, "--event-type", "Record.Updated",
        )  # fmt: skip
        receiver.set_secrets([secret, events["secret"]])
        receiver.fail_next([410])
        append(doc1, "Record.Updated", {"changes": {"title": ["Piping spec", "Piping spec rev A"]}})
        summary = tl("webhook", "run", "--once", "--allow-host", "127.0.0.1")
        expect(summary["dead"] == "1", f"expected 1 dead letter, got {summary}")
        dlq = tl("webhook", "dlq", "ls")
        expect(bool(dlq), "the dead letter is not listed")
        redriven = tl("webhook", "dlq", "redrive", events["subscription"])
        expect(redriven["redriven"] == "1", f"expected 1 redriven, got {redriven}")
        summary = tl("webhook", "run", "--once", "--allow-host", "127.0.0.1")
        expect(summary["delivered"] == "1", f"expected the redrive to deliver, got {summary}")

        step("rotate the secret: during the overlap a test event carries two signatures")
        rotated = tl("webhook", "rotate-secret", sid, "--project", "P123", "--overlap-hours", "2")
        receiver.set_secrets([rotated["secret"]])
        tested = tl("webhook", "test", sid, "--allow-host", "127.0.0.1")
        expect(tested["status"] == "200", f"the test event was refused: {tested}")
        last = receiver.messages()[-1]
        expect(len(last.headers["webhook-signature"].split()) == 2, "expected two signatures")
        expect(last.headers.get("webhook-test") == "1", "the test event is not marked")
        with sqlite3.connect(env["TL_DB"]) as conn:
            ledger_text = json.dumps(conn.execute("SELECT payload FROM events").fetchall())
        expect(
            secret not in ledger_text and rotated["secret"] not in ledger_text, "secret in ledger"
        )

    print("\nP0-I5 demo ok")


if __name__ == "__main__":
    main()
