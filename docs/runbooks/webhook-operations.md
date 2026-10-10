# Runbook — webhook operations (DLQ redrive, replay, secret rotation, disabled subscriptions)

Purpose: operate outbound webhooks: find and redrive dead letters, replay events a receiver missed, rotate a signing secret without dropping deliveries, and recover a disabled subscription. Brief: §18.4, §24.6. Plan and decisions: `docs/tickets/P0-I5/README-B.md`.

## When to use
- Trigger: a receiver reports missing events, or `tl webhook ls` shows a subscription with `dead` above 0 or status `disabled`.
- Trigger: an auto-disable (`WebhookSubscription.Disabled` with reason `sustained_failure` in the ledger).
- Trigger: a secret may have leaked, or a scheduled rotation.
- Trigger: a new receiver needs the events of the last days (replay).

## Before you start
- Access needed: the ledger (`TL_DB`) and permission to reach the receiver's host from the worker. Commands run as `user:dev` until auth exists (P0-I8).
- The worker must be running for anything to be sent: `uv run tl webhook run` (loop) or `uv run tl webhook run --once` (one drain). Without an allow-listed target, private and loopback addresses are refused; add `--allow-host HOST` or set `TL_WEBHOOK_ALLOWLIST` (comma separated) only for hosts you trust. Public hosts need nothing.
- Safe to run during business hours: yes. Replay and redrive resend events the receiver may already have; receivers dedupe on the event id (`webhook-id` header, CloudEvents `id`).
- Delivery log and counts: `uv run tl webhook ls` prints `subscription_id, status, mode, name, url, delivered, pending, dead` per subscription.

## Steps
1. **Look at the dead-letter queue** (deliveries that ran out of retries over 24 hours, got `410 Gone`, or hit a blocked target):
   ```
   uv run tl webhook dlq ls
   uv run tl webhook dlq ls --subscription <subscription id>
   ```
   Columns: `delivery_id, subscription_id, seq, event_id, attempts, last_status, dead_reason, dead_at`. Reasons: `retries_exhausted`, `gone`, `egress_denied`.
2. **Fix the cause first.** `egress_denied`: the target is private or loopback; allow-list it (`TL_WEBHOOK_ALLOWLIST`) if it is yours, or change the URL. `gone`: the receiver says the endpoint is permanently gone; confirm with its owner. `retries_exhausted`: check the receiver is up. Test it:
   ```
   uv run tl webhook test <subscription id>
   ```
   Expected: `status 200`. The request carries the header `webhook-test: 1`; a disabled or expired subscription is refused.
3. **Redrive** the dead letters once the receiver is healthy:
   ```
   uv run tl webhook dlq redrive <subscription id>
   uv run tl webhook dlq redrive <subscription id> --delivery <delivery id>
   uv run tl webhook run --once
   ```
   Expected: `redriven <n>`, then a summary with `delivered <n>`. Each dead delivery becomes `redriven` (history stays) and a new pending delivery with the same body is created. Order within a record is kept: a redriven event is sent in `seq` order with the record's other pending events.
4. **Replay** a range the receiver missed (it does not need to have failed):
   ```
   uv run tl webhook replay <subscription id> --from-seq 1200 --to-seq 1500
   uv run tl webhook replay <subscription id> --since 2026-10-08T00:00:00 --until 2026-10-09T00:00:00
   uv run tl webhook run --once
   ```
   Expected: `replayed <n>`. Only events that pass the subscription's **current** filter are replayed, rendered in its current payload mode; the same event ids are sent again. Times without an offset are UTC.
5. **Rotate a secret** (planned, or after a leak):
   ```
   uv run tl webhook rotate-secret <subscription id> --project P123 --overlap-hours 24
   ```
   The new secret is printed once (stdout) and cannot be shown again; copy it to the receiver. During the overlap every delivery carries two `v1` signatures, so the receiver can accept either secret; after the overlap the old secret stops signing. After a **leak** use `--overlap-hours 0` and update the receiver at once. A second rotation during an overlap retires the older secret immediately (two secrets at most).
6. **A disabled subscription.** After an auto-disable (5 dead letters since the last success, or 72 hours failing) or `tl webhook disable`:
   ```
   uv run tl webhook ls
   uv run tl webhook enable <subscription id> --project P123
   uv run tl webhook replay <subscription id> --from-seq <seq of the disable> --to-seq <current head>
   uv run tl webhook run --once
   ```
   Enable resumes from now; events committed while it was disabled are **not** sent until you replay them (find the disable's `seq` with `uv run tl events tail --project P123`). Fix the receiver before enabling, or it will be disabled again.
7. **Run the worker** (a service, or in a shell while debugging):
   ```
   uv run tl webhook run --allow-host 127.0.0.1
   ```
   `Ctrl-C` stops it and waits for sends in flight. A worker that dies mid-send leaves a lease that expires after 60 seconds; another worker then takes the delivery (the receiver may see it twice: dedupe on the event id).

## Verify
- `uv run tl webhook ls` shows `dead 0` and status `active` for the subscription.
- The receiver has the events (its log, or for the dev receiver `DevReceiver.messages()`), each with a verifying signature and a repeated `webhook-id` only for replays and redrives.
- `uv run tl webhook dlq ls` is empty for the subscription.
- Each step above is exercised by `just demo P0-I5` (replay, 410 to DLQ, redrive, rotation with two signatures) and by `packages/tl-cli/tests/test_cli_webhook*.py`; disable, enable and the window rules by `tests/webhooks/test_dispatcher.py`.

## Roll back
- Replay and redrive only add deliveries; stop the worker to hold them. A delivery cannot be unsent.
- `uv run tl webhook disable <subscription id> --project P123` stops all further sends at once. A rotated secret cannot be un-rotated: rotate again and give the receiver the new one.

## Related
- ADR-0002 (no outbound internet in the build container: tests use the dev receiver on 127.0.0.1), README-B decisions D4, D6, D9 to D12, D15 (secrets are stored in plaintext in `wh_secret` for Phase 0; envelope-encrypt under a KMS key before any non-dev deployment).
- `docs/runbooks/rebuild-projections.md`: a rebuild re-derives `outbox_events` and `cur_webhook_subscription` and never touches `wh_*` delivery state or secrets, and it sends nothing.
- The event catalog: `packages/tl-schema/src/tl_schema/generated/docs/event-catalog.md`.

## After a restore from the ledger archive
A restored database has its subscriptions (status `active`) but no signing secrets (secrets are never in the ledger) and no delivery state. `uv run tl webhook ls` shows such a subscription as `needs_secret`; the worker sends nothing for it, dead-letters nothing, and logs one warning per subscription per cycle. Its deliveries stay pending. Issue a secret for each, give it to the receiver, then the pending deliveries go out signed:
```
uv run tl webhook rotate-secret <subscription id> --project P123
uv run tl webhook run --once
```
The dispatcher also restarts from seq 0, so events since each subscription was created are queued again and sent once its secret exists; receivers dedupe on the event id. To avoid that, disable the subscription (`uv run tl webhook disable <subscription id> --project P123`) until the receiver is ready, or replay only the range it needs. The restore prints this as `warning:` lines (see `restore-from-archive.md`).

