# Runbook — QR labels at the workface: print, rotate, revoke, scan, and what the refusals mean

Purpose: print a QR label for a record (an IWP, an inspection, a permit), replace a lost label, revoke a label, let a
crew scan it, and read what each refusal means. Module: [qr](../../packages/tl-modules/qr/README.md). Reference: [qr](../reference/qr.md).
ADR: [0030](../adr/0030-qr-workface-status.md). Spec: [qr-workface](../build-spec/specs/qr-workface.md).

## When to use
- A label is needed for an IWP, an inspection or a permit at the work face.
- A printed label is lost, damaged or photographed, and must stop working.
- A label must die (revoke) without touching the record.
- You need the list of labels a record has (state, who issued, when, expiry).

## Before you start
- Sign in (`tl login <name>`). Commands take the ledger from `--db` or `TL_DB` and the project from `--project`.
- Words (`schema/settings/access-words.yaml`): `ls`, `export` and `resolve` need `qr.view`; `label` and `rotate` need
  `qr.issue`; `revoke` needs `qr.revoke` (controller). Printing also needs the read word of the record's type.
- The public address must be set (step 1). Until it is, nothing is printed.
- The web client must be on (`TL_WEB`). `tl qr label` warns on stderr when it is not; the label still prints, and
  scans need the web client.
- The QR image needs the optional extra `labels` of `tl-mod-qr` (`segno`). Without it the label file says
  `The QR library is not installed: install the labels extra. No label was drawn.` Install it before printing.

## Steps

### 1. Set the base address
1. The setting is `api.public_base_url` (`https://host[:port]`, or `http://localhost` / `http://127.0.0.1` for a trial). No path,
   no trailing slash.
2. It is a platform-only setting. `tl config set` refuses it at every layer, so it is not changed from the terminal.
3. Until it is set, `tl qr label` prints `error: set api.public_base_url first` and writes no file.
4. How a deployment sets its value is not documented yet (open question 1 in the report). The demo gives the label
   calls a scratch copy of the platform file through `TL_SETTINGS_PLATFORM_FILE`; the shipped file is not changed.
5. Changing the address later orphans every printed label. Keep the old host redirecting to the new one, or reprint.

### 2. Print a label for an IWP
1. `uv run tl qr label <IWP key> --project P123 --label "Level 3 deck" -o ./labels/iwp-l3.html`
   prints `label <id>  file ./labels/iwp-l3.html`.
2. The file is one HTML page with the QR as inline SVG. Open it in a browser and print it. The code is in the file only.
3. `--label` is the text under the code (at most 40 characters). Without `--label` the record's title is the text.
   The text and the key are printed only for a record at the lowest confidentiality class; above it the label carries
   the QR and the typed code only.
4. `--size tag` is the only size built (50 × 80 mm). `--expires YYYY-MM-DD` makes the code stop scanning after that day.
5. A label file is never replaced by accident. `--force` replaces it.

### 3. Find the codes of a record
1. `uv run tl qr ls <IWP key> --project P123` prints `scan codes: <n>`, then one line per code. The first column is the
   register id you use for `rotate` and `revoke`. No code is printed.
2. `uv run tl qr export <IWP key> --project P123 --format csv` (or `jsonl`) writes the same rows, with `revoked_at` and
   `replaced_by_id`. Never a code or a hash.

### 4. Rotate a lost or damaged label
1. Find the register id with step 3.
2. `uv run tl qr rotate <code id> --project P123 --reason "label lost" -o ./labels/iwp-l3-new.html`
   prints `rotated <new id>  file ./labels/iwp-l3-new.html`.
3. The old code now answers `no such code`. The new code is the one on the new file. The same record, text, size and
   expiry are kept.
4. Print the new file and put it up. Do not print the old file again.

### 5. Revoke a label
1. `uv run tl qr revoke <code id> --project P123 --reason "printed in error"` prints `revoked <id>`.
2. The code then answers `no such code`. Revoking does not change the record. A record that closes does not revoke its
   codes: a scan of a closed permit shows `CLOSED`. Revoke when the label must die.

### 6. Scan a label (the crew)
1. Point the phone camera at the QR. The phone opens `<base>/web/q/<code>`.
2. A phone that is not signed in goes to the sign-in page first. After sign-in the browser returns to the same
   address. The session cookie persists, so later scans open at once.
3. The card shows the banner (for example `ISSUED`, `HOLD POINT — not released`, `ACTIVE until 18:00`), the key, the
   title, as-of time, and up to 8 lines. It is read-only.
4. If the camera fails, type the four groups of the code at `/web/q` (the form). A typed code counts as a lookup.
5. A code the viewer cannot read, a revoked code, an expired code, a wrong or unknown code all show the same
   `no such code` page. Do not ask which one it is; check the record with `tl qr ls`.
6. Terminal check of the same card: `printf '%s\n' "<code>" | uv run tl qr resolve --project P123`.

## Proxy note: access log and the real client address
- The application's access log replaces the code in every `/web/q/` path with `<redacted>`. The filter is installed at
  start-up (`install_access_log_filter`).
- A reverse proxy in front of the server writes its own access log. It must strip or mask the `/web/q/` path too, or the
  code is in the proxy log.
- Miss counts are kept per address. The address is the one the trusted proxy header names. Set `TL_TRUSTED_PROXY_HEADER`
  to the header name the proxy sets. The proxy must overwrite that header or append its own entry; a client's own line
  must never pass through behind the proxy's. Without it, the peer address is used, and every phone behind one proxy
  shares one address limit.

## Miss limit
- A miss is a failed lookup (malformed, unknown, revoked, expired, hidden, no view word, no provider) or a typed code
  that does not normalise. A hit adds nothing to the counts.
- Per session: 10 misses in 600 seconds. Per address: 30 misses in 600 seconds.
- Once the session has 10 misses, or the address 30, in the window, every lookup from it (hits too) gets `429` with `Retry-After` and the text
  `Too many lookups. Wait a few minutes and try again.` The counters are held in the web process memory; a restart clears them.

## Refusals and what they mean
Texts are copied from the code and from the QR reports (T02, T06, T07, S2, S3, QRT11). The CLI prints `error: <text>`.
The `<key>` is the key you typed.

| Text | Meaning | What to do |
|---|---|---|
| `error: set api.public_base_url first` | The public address is unset; no file is written | Set it (step 1) |
| `label size card is not available yet` (`sheet` likewise) | Only `tag` is built | Use `--size tag` |
| `error: <action> needs the <word> access word for qr on <scope>` | Your account lacks `qr.issue` (label, rotate) or `qr.revoke` (revoke) | Ask a controller |
| `no record with that id` | The record is unknown, or hidden from you (the same text) | Check the key; check your access to the record |
| `that record has as many live scan codes as it may have; revoke one first` | The record is at `qr.codes_per_record_max` live codes | Revoke an old code (`ls`, then `revoke`) |
| `the expiry is in the past` | `--expires` is before today | Give a later date |
| rotate refused for an expired code | A code past its expiry is not rotated | Revoke it; if a label is still needed, `label` again |
| `that scan code is already revoked` | `revoke` or `rotate` on a revoked code | Use `ls` for the live code |
| `no such code` (CLI `resolve` exit 1; web 404) | Every miss: unknown, malformed, revoked, expired, hidden, no view word, no provider | Check the label is the newest one; check the record with `ls` |
| `no such record` (API 404) | The record is unknown or hidden for `GET /qr/codes` (the same answer) | Check the key and access |
| `Too many lookups. Wait a few minutes and try again.` (429) | The miss limit for the session or the address | Wait for the window (10 minutes) |
| `The QR library is not installed: install the labels extra. No label was drawn.` | The `labels` extra is missing | Install the extra, print again |
| `warning` on stderr about `TL_WEB` | The web client is off, so scans fail | Turn `TL_WEB` on before the crew scans |

## Known state
- The scan page, the miss counter and the log filter are built. The scaffold card is not (waits for the scaffold module).
  Client methods, the terminal print action, the web print form, `tl qr sheet`, PDF labels and anonymous scans are not
  built. See [qr](../../packages/tl-modules/qr/README.md#not-built).
- The demo `dev/demos/P2-QR.sh` passes its eight clauses on SQLite. On Postgres on the build host, clause 7 failed
  with a backend killed for memory during a card lookup (QRT11). Do not rely on the demo as a Postgres acceptance until
  that is resolved.
