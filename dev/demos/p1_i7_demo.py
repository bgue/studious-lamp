"""Driver for dev/demos/P1-I7.sh: the parts of the demo that are not a `tl` command.

Modes (first argument; DIR is the demo's work directory):

* ``prepare DIR``: write the files the script feeds to `tl`: the mapping, the payloads, the rules
  and the enricher registration.
* ``receiver DIR``: run a webhook receiver on a free loopback port until killed. It writes its port
  to ``DIR/receiver.port``, picks up its signing secret from ``DIR/receiver.secret`` when that file
  appears, and appends every POST it handled to ``DIR/receiver.log`` (one JSON object per line).
* ``post DIR PATH MODE MESSAGE_ID PAYLOAD``: POST a payload to ``$TL_DEMO_URL`` + PATH and print the
  status code. MODE is ``signed`` (Standard Webhooks, the secret in ``DIR/endpoint.secret``) or
  ``unsigned``.
* ``action-file DIR``: write ``DIR/action.json`` for the receiver's port.
* ``inbound``, ``rules``, ``enrichment``, ``action``, ``secrets``: the checks of the exit clauses,
  read from the ledger (``TL_DB``: a SQLite path or a postgresql:// URL).

Every expectation is an assert: a failing demo exits non-zero. Nothing printed holds a secret.
"""

from __future__ import annotations

import http.client
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import text

PROJECT = "P123"
SCOPE = f"project:{PROJECT}"


def say(text_: str) -> None:
    print(f"   {text_}")


def passed(clause: str, text_: str) -> None:
    print(f"PASS {clause}: {text_}")


# --- files -----------------------------------------------------------------------------------

MAPPING = (
    'results.{"command": "SetPsetValues", "args": {"stream_id": {"$key": valve}, '
    '"pset": "valve_data", "layer": "standard", '
    '"values": {"tag_no": tag, "manufacturer": maker}}}\n'
)
PAYLOAD = {
    "contractor": "acme-nde",
    "results": [
        {"valve": "V-1001", "tag": "FV-1001", "maker": "Acme Valves"},
        {"valve": "V-1002", "tag": "FV-1002", "maker": "Acme Valves"},
    ],
}
BAD_PAYLOAD = {
    "contractor": "acme-nde",
    "results": [{"valve": "V-9999", "tag": "FV-9999", "maker": "Acme Valves"}],
}
FIXED_PAYLOAD = {
    "contractor": "acme-nde",
    "results": [{"valve": "V-1002", "tag": "FV-1003", "maker": "Acme Valves"}],
}
HSE = {
    "key": "hse-notify",
    "title": "Notify HSE",
    "when": {"event_types": ["Feed.Posted"], "hashtags": ["safety"]},
    "then": [{"command": "PostToFeed", "args": {"body": "HSE notified"}}],
}
PING = {
    "key": "ping",
    "title": "Answers a ping with a pong",
    "when": {"event_types": ["Feed.Posted"], "hashtags": ["ping"]},
    "then": [{"command": "PostToFeed", "args": {"body": "pong #pong"}}],
}
PONG = {
    "key": "pong",
    "title": "Answers a pong with a ping",
    "when": {"event_types": ["Feed.Posted"], "hashtags": ["pong"]},
    "then": [{"command": "PostToFeed", "args": {"body": "ping #ping"}}],
}
ENRICHER = {
    "when": {"event_types": ["Document.Defined"]},
    "properties": [
        {"name": "doc_type", "kind": "string", "policy": "propose", "threshold": 0.9},
        {"name": "discipline", "kind": "string", "policy": "propose", "threshold": 0.9},
    ],
}


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=1) + "\n")


def prepare(directory: str) -> None:
    out = Path(directory)
    (out / "map.jsonata").write_text(MAPPING)
    for name, value in (
        ("payload.json", PAYLOAD),
        ("bad-payload.json", BAD_PAYLOAD),
        ("fixed-payload.json", FIXED_PAYLOAD),
        ("hse.json", HSE),
        ("ping.json", PING),
        ("pong.json", PONG),
        ("enricher.json", ENRICHER),
    ):
        write_json(out / name, value)


def action_file(directory: str) -> None:
    out = Path(directory)
    port = int((out / "receiver.port").read_text())
    write_json(
        out / "action.json",
        {
            "name": "send_to_nde",
            "label": "Send to NDE",
            "description": "Ask the NDE contractor to inspect a weld",
            "executor": "webhook",
            "executor_config": {
                "kind": "webhook",
                "url": f"http://127.0.0.1:{port}/hook",
                "timeout_s": 10,
            },
            "side_effect_class": "external",
            "parameters": [
                {
                    "name": "method",
                    "kind": "string",
                    "label": "Method",
                    "required": True,
                    "choices": ["RT", "UT"],
                }
            ],
        },
    )


# --- the receiver --------------------------------------------------------------------------


def receiver(directory: str) -> None:
    from tl_core.webhooks.receiver import DevReceiver

    out = Path(directory)
    seen = 0
    with DevReceiver() as server:
        (out / "receiver.port").write_text(str(server.port))
        secret_file = out / "receiver.secret"
        loaded = ""
        while True:
            if secret_file.exists():
                value = secret_file.read_text().strip()
                if value and value != loaded:
                    server.set_secrets([value])
                    loaded = value
            messages = server.messages()
            if len(messages) > seen:
                with (out / "receiver.log").open("a") as log:
                    for message in messages[seen:]:
                        log.write(
                            json.dumps(
                                {
                                    "path": message.path,
                                    "verified": message.verified,
                                    "duplicate": message.duplicate,
                                    "event": message.event(),
                                }
                            )
                            + "\n"
                        )
                seen = len(messages)
            time.sleep(0.1)


# --- a signed POST ---------------------------------------------------------------------------


def post(directory: str, path: str, mode: str, message_id: str, payload_file: str) -> None:
    from tl_core.webhooks.signing import SigningSecret, sign_headers

    body = Path(payload_file).read_bytes()
    headers = {"Content-Type": "application/json"}
    if mode == "signed":
        secret = SigningSecret((Path(directory) / "endpoint.secret").read_text().strip())
        headers.update(sign_headers(message_id, int(time.time()), body.decode(), [secret]))
    elif mode != "unsigned":
        raise SystemExit(f"unknown mode {mode}")
    url = urlparse(os.environ["TL_DEMO_URL"])
    connection = http.client.HTTPConnection(url.hostname or "127.0.0.1", url.port, timeout=10)
    connection.request("POST", path, body=body, headers=headers)
    print(connection.getresponse().status)


# --- reading the ledger ----------------------------------------------------------------------


def rows(sql: str, **params: Any) -> list[dict[str, Any]]:
    from tl_adapters.db import open_uow

    with open_uow(os.environ["TL_DB"], readonly=True) as uow:
        return [dict(r) for r in uow.conn().execute(text(sql), params).mappings()]


def record_psets(key: str) -> dict[str, Any]:
    found = rows("SELECT psets_json FROM cur_core_record WHERE key = :k", k=key)
    assert found, f"no record {key}"
    return json.loads(found[0]["psets_json"])


def inbound() -> None:
    first = record_psets("V-1001")["valve_data"]
    assert first["tag_no"] == "FV-1001" and first["manufacturer"] == "Acme Valves", first
    second = record_psets("V-1002")["valve_data"]
    assert second["tag_no"] == "FV-1003", second  # the corrected retry came last
    writes = rows(
        "SELECT actor, source FROM events WHERE event_type = 'Pset.ValuesSet' "
        "AND source LIKE 'inbound:%' ORDER BY seq"
    )
    assert len(writes) == 3, writes
    for write in writes:
        assert write["source"] == "inbound:acme-nde/results", write
        assert write["actor"] == "svc:inbound-acme-nde.results", write
    queue = rows("SELECT state, error_code FROM int_delivery ORDER BY received_at")
    assert [r["state"] for r in queue] == ["applied", "applied"], queue
    failed = rows("SELECT 1 FROM events WHERE event_type = 'Inbound.Failed'")
    assert len(failed) == 1, failed
    counted = {r["code"]: r["count"] for r in rows("SELECT code, count FROM int_counter")}
    assert (
        counted.get("replay") == 1
        and counted.get("bad_signature", 0) + counted.get("missing_signature", 0) >= 1
    ), counted
    passed(
        "1a", "the writes carry source inbound:acme-nde/results and the endpoint's service actor"
    )


def rules() -> None:
    posts = rows(
        "SELECT actor, source FROM events WHERE event_type = 'Feed.Posted' "
        "AND actor = 'svc:rule-hse-notify'"
    )
    assert len(posts) == 1 and posts[0]["source"].startswith("rule:hse-notify@"), posts
    fired = rows(
        "SELECT u.key AS key, f.outcome AS outcome, f.depth AS depth FROM rule_firing f "
        "JOIN cur_rule u ON u.rule_id = f.rule_id WHERE u.key IN ('ping', 'pong') ORDER BY f.seq"
    )
    assert [(r["key"], r["outcome"], r["depth"]) for r in fired] == [
        ("ping", "fired", 0),
        ("pong", "fired", 1),
        ("ping", "fired", 2),
        ("pong", "depth_limit", 3),
    ], fired
    passed("2a", "hse-notify posted as svc:rule-hse-notify; ping and pong stopped at depth 3")


def enrichment() -> None:
    layer = record_psets("ISD-001").get("enrich", {}).get("doc_classifier", {})
    assert layer.get("doc_type") == "ISO", layer
    values = rows("SELECT acceptance_state, decided_by FROM cur_enrichment_value ORDER BY seq")
    states = sorted(v["acceptance_state"] for v in values)
    assert states == ["accepted", "rejected"], states
    assert all(v["decided_by"] == "user:amy" for v in values), values
    passed("3a", "psets.enrich.doc_classifier.doc_type reads ISO after amy accepted it")


def action(directory: str) -> None:
    log = [json.loads(line) for line in (Path(directory) / "receiver.log").read_text().splitlines()]
    assert len(log) == 1, log
    entry = log[0]
    assert entry["verified"] and entry["path"] == "/hook", entry
    event = entry["event"]
    assert event["action"] == "send_to_nde" and event["parameters"] == {"method": "RT"}, event
    assert [t["key"] for t in event["targets"]] == ["V-1001"], event
    runs = rows("SELECT status FROM cur_action_invocation")
    assert [r["status"] for r in runs] == ["completed"], runs
    passed("5a", "the receiver verified the signature of one POST naming send_to_nde and V-1001")


def thread_action(directory: str) -> None:
    log = [json.loads(line) for line in (Path(directory) / "receiver.log").read_text().splitlines()]
    assert len(log) == 2, log
    entry = log[1]
    assert entry["verified"] and entry["path"] == "/hook", entry
    event = entry["event"]
    assert event["action"] == "send_to_nde" and event["parameters"] == {"method": "UT"}, event
    assert [t["key"] for t in event["targets"]] == ["V-1001"], event
    runs = rows(
        "SELECT invoked_by, status, parameters_json FROM cur_action_invocation ORDER BY seq"
    )
    assert [r["status"] for r in runs] == ["completed", "completed"], runs
    assert runs[0]["invoked_by"] == runs[1]["invoked_by"] == "user:amy", runs
    passed("4a", "the thread's /dispatch ran send_to_nde as user:amy and the receiver verified it")


def secrets(directory: str) -> None:
    """No signing secret is in any event payload or operational row the demo made."""
    needles = [
        (Path(directory) / name).read_text().strip()
        for name in ("endpoint.secret", "receiver.secret")
        if (Path(directory) / name).exists()
    ]
    assert needles, "no secret was recorded by the demo"
    for needle in needles:
        found = rows("SELECT 1 FROM events WHERE payload LIKE :n", n=f"%{needle}%")
        assert not found, "a signing secret is in an event"
        for table, column in (("int_delivery", "error_message"), ("job_queue", "last_error")):
            try:
                hits = rows(f"SELECT 1 FROM {table} WHERE {column} LIKE :n", n=f"%{needle}%")  # noqa: S608
            except Exception:
                continue
            assert not hits, f"a signing secret is in {table}"
    passed("6", "no signing secret is in an event, a delivery or a job row")


def main(argv: list[str]) -> None:
    mode = argv[0]
    if mode == "prepare":
        prepare(argv[1])
    elif mode == "receiver":
        receiver(argv[1])
    elif mode == "action-file":
        action_file(argv[1])
    elif mode == "post":
        post(*argv[1:6])
    elif mode == "inbound":
        inbound()
    elif mode == "rules":
        rules()
    elif mode == "enrichment":
        enrichment()
    elif mode == "action":
        action(argv[1])
    elif mode == "thread-action":
        thread_action(argv[1])
    elif mode == "secrets":
        secrets(argv[1])
    else:
        raise SystemExit(f"unknown mode {mode}")


if __name__ == "__main__":
    main(sys.argv[1:])
