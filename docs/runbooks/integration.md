# Runbook — the integration layer (actions, rules, inbound endpoints, enrichers)

Purpose: run, switch off and recover the things that act on the ledger on their own: inbound endpoints, rules, actions and enrichers. Brief: §18.5, §18.7 to §18.9, §18.13. Design: [ADR-0017](../adr/0017-integration-layer.md).

## When to use
- Trigger: an endpoint, rule, action or enricher misbehaves; an inbound delivery failed; someone must stop automation now; a new integration is being set up.

## Before you start
- Access needed: the admin role for everything that authors or switches (`tl login <admin>`). A person with the user role may read the registry and decide enrichment values. The inbound error queue and the payloads are the admin's.
- Safe to run during business hours: yes. Every switch below takes effect at the next event or request; nothing restarts.
- The workers are one process: `tl integration serve` (the rules worker, the enrichment dispatcher and the runners of action jobs and inbound deliveries). The API (`tl serve`) only accepts `POST /in/<app>/<endpoint>` and queues it; nothing is mapped or applied until `tl integration serve` runs. `tl integration status` shows the cursors, the queues and the kill switch.

## Steps

### 1. Stop everything (the kill switch)
```
tl config set integration.kill_switch true --company --reason "<why>" --accept-risk
tl integration status
```
Expected: `kill_switch on`. Inbound answers the same fixed 404 as an unknown endpoint, the rules worker and the enrichment dispatcher pass over events (they are not replayed later), action jobs fail with `killed` and are not retried. Turn it off with `false`; events passed over while it was on are gone, not queued.

### 2. Stop one thing
| What | Command |
|---|---|
| everything of one app | `tl integration app disable <app> --project P` |
| one endpoint | `tl endpoint disable <app>/<name> --project P` |
| one endpoint's effect, keeping it listening | `tl endpoint mode <app>/<name> dry-run --reason "<why>" --project P` (deliveries already queued are also only planned) |
| one rule | `tl rule disable <key> --project P` |
| one enricher | `tl enricher disable <name> --project P` |
| one action | `tl action retire <name> --project P` |

### 3. Set up an inbound endpoint
```
tl integration app add acme-nde --label "Acme NDE" --project P
tl endpoint create acme-nde/results --project P --mapping-file mapping.jsonata --allow SetPsetValues
tl delivery dry-run acme-nde/results --project P --sample payload.json
tl endpoint mode acme-nde/results live --reason "dry run looked right" --project P
tl endpoint enable acme-nde/results --project P
```
`create` prints the signing secret once; give it to the sender and keep it nowhere else. The endpoint starts disabled and in dry-run. The sender signs with Standard Webhooks (HMAC) or sends an HS256 token bound to the path. Rotate with `tl endpoint rotate-secret <path>`: the old secret still verifies for `--overlap-hours` (default 24).

### 4. Work the error queue
```
tl delivery ls --state failed
tl delivery show <delivery id>
tl delivery retry <delivery id> [--file corrected.json]
```
`show` never prints the payload. A corrected payload is stored beside the original; the original is kept. Fix a mapping with a revision of the endpoint, then retry.

Putting an endpoint back to dry-run is also the emergency stop for deliveries that are already queued: they are applied as dry-run and end in state `dry_run`. A `dry_run` delivery is final; `tl delivery retry` re-runs only failed ones, so after the cause is fixed ask the sender to send the payloads again.

### 5. Set up a rule
```
tl rule create --file rule.json --project P
tl rule dry-run <key> --project P
tl rule mode <key> act --reason "<why>" --project P
tl rule enable <key> --project P
```
A rule starts disabled and in `propose` mode (its commands wait as proposals). Dry-run it over recent events first. At most three causation levels deep, five steps and twenty commands per event; a rule that loops stops at depth 3 and the firing says `depth_limit`.

### 6. Set up an enricher
```
tl enricher register doc_classifier --file when-and-properties.json --project P
tl enricher enable doc_classifier --project P
tl enrich ls --project P
tl enrich accept <value id> --project P
```
Each property has a policy: `auto` (above its threshold), `propose` (a person accepts in the review queue, `Ctrl+R` in the TUI) or `shadow` (kept for the admin, never shown to a person or written). Nothing writes outside `enrich.<enricher>.*`; a client cannot write that layer or `src.*`.

### 7. Define and run an action
```
tl action define --file action.json --project P
tl action invoke send_to_nde --target <record key> --param method=RT --project P
tl action invocations --project P
```
A webhook action calls only hosts on `webhooks.egress.allowlist` (a dangerous setting: it asks for a reason and an accepted risk) or public https hosts; private, loopback and metadata addresses are refused before any connection. The signing secret is printed once, by `define` and `rotate-secret`.

## Verify
- `tl integration status` shows the cursors close to `last_seq` and no `jobs ... failed`.
- The registry screen (`Ctrl+E`, admin) lists every kind with its state and the kill switch in the title.
- Every write made by automation has a source: `rule:<key>`, `inbound:<app>/<endpoint>`, `enricher:<name>@<version>` or `action:<name>`; `tl events tail` shows the source of each event.

## Roll back
- A rule or endpoint: disable it (step 2). Its past writes stay in the ledger; undo them with the ordinary commands (void, compensate), as a person.
- An enrichment value accepted by mistake cannot be rejected afterwards. A later accepted value of the same property replaces it in the record's layer; the earlier one stays in the history.

### 8. Restricted and privileged records
Automation reads as its service actor, with the clearance its declared access earns: a rule, an enricher or an endpoint whose access is `controller` or `admin` reads restricted records; none reads privileged ones. A rule or an enricher does not see, and does not act on, a record it cannot read: the event is passed over (the engines count it as `hidden`; the CLI does not print it), not retried. If a rule seems to ignore a restricted record, that is why; raise its access with `tl rule` only if the rule is meant to act on such records. A mapped key that names a record the endpoint cannot read is a `key_not_found` in the error queue. A workflow transition by a rule, a mapping or a thread dispatch carries no workflow role (service actors hold none): a transition that needs a role fails with `workflow_guard_failed`; let the rule propose it and a person with the role accept.

## Known limits (accepted, 2026-10-19)
- The per-source and per-endpoint rate counters run before the signature is checked, so an attacker who knows an endpoint path can use up its request budget (the answer is 429 for everyone until the minute turns). Rotate nothing for this; lower the endpoint's `rate_per_minute` or disable it.
- The source of a request is the connection's address. Behind a proxy every caller looks alike: one noisy caller can lock out the rest. Put per-sender limits on the proxy.
- A request that reaches the transport deadline may be reported as a timeout when it was about to finish (the watchdog closes the connection at the boundary); the action is retried like any network error.
- The body is read with the size cap but without a read deadline of its own beyond the server's; a slow sender holds one connection. Put a body timeout on the proxy.
- Account names of the form `svc:inbound-<app>-<name>` (joined with `-`) were replaced by `svc:inbound-<app>.<name>` before any release; there is nothing to migrate.

## Related
- [ADR-0017](../adr/0017-integration-layer.md), [ADR-0014](../adr/0014-derivation-pipeline.md) section 8 (the sandbox the mapping runs in), [settings](settings.md) (`integration.kill_switch`, `webhooks.egress.allowlist`)
- [rebuild-projections](rebuild-projections.md) if the registry reads disagree with the events
