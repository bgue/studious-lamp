# Forms — store and forward (Phase 3 design, moved out of the forms evaluation)

This note is §4 of `forms-eval.md`, moved here unchanged when the plan check of 2026-11-15 deferred store and
forward to Phase 3. Section numbers are kept, so "§4.x" in `forms-eval.md`, ADR-0031 and ADR-0032 means this file.
Decision record: ADR-0031 (decisions 9, 10, 14 to 17). Plan: `forms-eval.md` §8.3 (slice P2-FORMS-SF).

## 4. Store and forward

**Deferred to Phase 3 by the plan check (cost cut).** The design below stands for that round, with one cut for its
first version: the receipt time is the only time used; `captured_at` is recorded and shown, never applied (§4.5).
Owner decisions 4, 5 and 6 land with it.

### 4.1 What it is, and what it is not

Store and forward is a **client outbox of commands**. Nothing is written to any ledger while offline. When the
client can reach the server it delivers each queued command once, and the authority runs it then, under the rules
of that moment. It is not the Phase 3 replica sync (`offline-classes.md` §6): no local segment, no merge, no second
node kind, and `TL_NODE_KIND` stays `authority`. An outbox item has the shape Phase 3 calls `PendingCommand`, so the
replica work later reuses it rather than replaces it.

The client is the web client installed as a page with a service worker, scope `/web/forms/` in the first slice. It
keeps: the app shell, the vendored renderer, the Published templates it was sent, the bindings fetched while online
("my work today": inspections scheduled for me, the general forms of my project), an outbox and file blobs, all in
browser storage keyed by account. A native app (Phase 5) or a terminal outbox would use the same routes; neither is
in these slices.

### 4.2 What may be queued

One rule, already written: `tl_core.offline.capture_allowed(record_type, command, node="device")`. The delivery
route refuses everything else, and `GET /record-types` already tells a client which commands those are.

| Command | Class of its type | Queued? |
|---|---|---|
| `SubmitForm`, `SaveFormDraft` (general form) | `forms.Submission`: `draft_only`, drafting commands | Yes |
| `RecordInspectionResult` | `quality.Inspection`: `draft_only`, drafting command (`inspections.md` §3) | Yes |
| `RaisePunchItem`, `RaiseRequisition` (exist) | `draft_only` | Yes, once each has a form source |
| `PlanInspection`, `ScheduleInspection` | `draft_only`, not drafting | No |
| `SuspendPermit`; `RecordGasTest` whose reading fails | `none`, with a closed list of tightening commands (owner decision 4) | Yes, under §4.4 "Permits" |
| Every other permit, isolation and gas-test command | `none` (`permits.md` §4) | **No** |
| Any controller command (verify, approve, issue, publish, void) | any | **Never** (`central_act`) |

### 4.3 Delivery and idempotency

- The client mints one `Idempotency-Key` per outbox item when the person presses Submit, and reuses it on every
  retry. The delivery route passes it to the same idempotency service as the command door, scoped to the actor, so
  a retry through either door replays the first answer and writes nothing new (P2-X1).
- Attachments are uploaded first through the existing upload routes (content-addressed, so a re-upload is harmless),
  then the command is delivered with the file ids. A command whose files are not complete is not sent.
- Each delivery carries `captured_at` (the device clock when Submit was pressed) and `device_now`. On success the
  route writes one event of its own in the same unit of work, `forms.Delivery.Received`
  `{command, target_id, captured_at, received_at, clock_skew_s, queued_s}`, caused by the command's event. No
  existing event or envelope changes. A refusal writes nothing, as in X1; the item stays on the device.
- A key must not outlive the idempotency window. `forms.late_accept_hours` (default 72, must be below
  `idempotency.retention_days`) bounds how old a queued item may be; an older one is refused as `too_late` and the
  person re-submits it by hand. The X1 purge job is deferred today, so this bound is what makes that job safe later.
- The session lasts 12 hours. A device offline for longer signs in again before anything is sent. An outbox belongs
  to one account; another account on the same device cannot read or send it; sign-out asks, then wipes.

### 4.4 When the world moved while the device was offline

Principle: **a fact is accepted late with its own time; an act is refused if its target moved; nothing is merged.**

| Situation at delivery | Outcome |
|---|---|
| General form, template version still Published | Accepted |
| General form, template superseded or retired since capture | Accepted late against the **pinned** version if it was Published at `captured_at` and the item is inside the late window; marked `template_superseded`. Otherwise refused `template_retired` |
| Inspection result, inspection still Scheduled, `expected_version` matches | Accepted; answers validated against the version pinned at scheduling |
| Inspection rescheduled or re-pinned meanwhile (`expected_version` differs) | Refused `stale_version`. Never auto-applied: the answers may belong to another checklist version |
| Inspection already Done by someone else, or Cancelled | Refused by the state guard. The answers stay on the device, exportable, for the QA lead to judge |
| The target is now hidden from the actor (class raised, access removed) | Refused as a missing record; the device learns nothing more |
| The actor lost the command's word, or the account is disabled | Refused; nothing is written on a past permission |
| A queued permit command that is not on the tightening list | Refused `online_only`; never dropped silently |
| An inspection whose subject is a permit that was suspended meanwhile | Accepted: it records what was seen at `captured_at`. The record view shows capture and receipt times beside the suspension |

A refused item is never deleted by the client. It moves to "Needs attention" with the fixed reason word; the person
may open it against the current record, carry the answers over by field id, and submit with a **new** key (X1).

**Permits (owner decision 4: yes, for facts that only tighten).** Two things may be queued and nothing else: a
"suspend" (anyone may suspend) and a gas reading. The list is closed in code (`TIGHTENING_COMMANDS` beside
`capture_allowed`); adding to it is a new owner decision. Rules at delivery:
- A suspend takes effect at the receipt time; `captured_at` is shown beside it. If the permit is already Suspended,
  Handed back or Closed the state guard refuses it and the device shows that state.
- A gas reading is computed by the server as always. If it **fails**, it is recorded and suspends the permit. If it
  computes as a pass it is refused `online_only` and stays on the device: a late pass could make work more permitted.
- Resume, issue, revalidate, approve, every isolation command and every passing reading stay online only.
- Until the server answers, the device says "Not sent. The permit is NOT suspended for anyone else. Use the radio."
  A queued stop never replaces the radio and the paper.
`permits.md` §4 and `specs/offline-classes.md` need one line each for this exception (a PTW spec change, not made
here).

### 4.5 Clocks and valid time

- The authority's `recorded_at` is the only trusted time and is set as always. `captured_at` is a claim.
- First version: typed valid-time fields (`done_at`, later `taken_at`) take the receipt time. The delivery record
  keeps `captured_at` and the measured skew as information. Using the claim for valid time within a skew bound
  (`forms.clock_skew_max_seconds`) is a later, separate decision.
- No guard that makes work *more* permitted may rest on a device time. "A passing gas test newer than 240 minutes"
  is always counted from the receipt time. A device time may only make things stricter or be shown as information.

### 4.6 QR scan at the workface while offline

| Works offline | Does not, by design |
|---|---|
| Opening the forms page the person installed, and filling any form fetched while online | Any live status. Whether a permit, an isolation or a gas test is live, suspended or lapsed is never cached, not even "as of" |
| A last-known status for a non-permit record in "my work today" (owner decision 5), always under the line "As of <time>. Not live." and never styled as current | A status older than `forms.offline_status_max_hours` (default 24): nothing is shown |
| After the second slice: a scan of a label whose record is in "my work today" opens that record's **form**, with a banner "Offline: status unknown. The paper on site rules." The server sends the SHA-256 of each such code with the binding, so the device matches a scan without storing a code | A scan of any other label: the phone's own error page, as today |
| Typing or scanning in the trailer on a replica: `tl qr resolve` with "as of last sync" (ADR-0030 decision 10) | Signing in, or renewing an expired session |

The last-known status is not a cached scan page. The scan card stays `no-store` (ADR-0030 decision 9, unchanged);
the status lines travel with the "my work today" payload, for lowest-class subjects only, in the account's storage,
wiped at sign-out. The second slice widens the service worker's scope to `/web/q/` for the offline shell only;
online, the scan page stays script-free. That change to the web client is in ADR-0031's gate list.
