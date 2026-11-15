# Spec: QR codes at the workface — scan to get the live status of a record

This spec says what a printed QR code holds, what a scan shows, who may see it, and how labels are printed, rotated
and revoked. Status: draft v0.1, 2026-11-15, owner request of the same day. Decision record: ADR-0030 (proposed).
Build plan: `docs/tickets/P2-QR/README.md`. Brief §7.5 (deep links resolve from printed QR codes), §19.1, §22.9 (deferred mobile notes: record
lookup by QR). Binding rules: `12-extension-plan.md` §0.

## 1. What exists after this is built

- A person who can see a record prints a label or a board sheet for it from the terminal, the CLI or the web.
- A phone camera reads the label and opens a small web page with the record's status as of now: an inspection, a
  permit, a scaffold tag, an IWP.
- A lost or copied label can be killed (revoke) or replaced (rotate) without touching the record.
- A scan never tells anyone more than the same person would get by opening the record.

First four targets: `quality.Inspection`, `permits.Permit`, `scaffold.Scaffold`, `awp.IWP`. Another record type joins
by shipping one small "status card" function; nothing in the QR code or the scan page changes.

## 2. What a QR encodes

Exactly one URL: `<api.public_base_url>/q/<code>`.

- `<code>` is 16 characters from a 32-letter alphabet without look-alikes (80 random bits from the system's secure
  generator). It is printed under the QR in four groups (`7KQ2-M9XA-4TTC-P0HV`) so it can be typed at `/q` when a
  camera fails.
- The code is opaque. It holds no company, project, record type, key, id, date or checksum of any of them. Nothing
  about the record can be learned from the label's QR, and two codes for one record look unrelated.
- The server keeps only the SHA-256 of the code, never the code. The code is shown once, when the label is made.
  A reprint is a new code. (The ledger is permanent; a code written into an event could never be taken back.)
- The human-readable text beside the QR is chosen at print time: by default the record's key and a short label the
  printer types (≤ 40 characters). For a record above the lowest confidentiality class the label carries the QR and
  the typed code only, no key and no text.
- A label never prints the state ("Active", "green"). Paper cannot change when the record does.

## 3. What a scan shows

A phone-width, server-rendered page (no script needed, under 30 KB) built from a **status card**:

| Part | Content |
|---|---|
| Banner | The state in one or two words with a tone: go (green), caution (amber), stop (red), neutral. Colour is never the only signal; the word is always there |
| Identity | Key and title |
| As of | The server time of this answer, and "valid until" when the record has one |
| Lines | At most 8 `label: value` lines chosen by the owning module |
| Link | "Open record", to the web record page when one exists for the type |

| Target | Banner examples | Lines |
|---|---|---|
| Permit | `ACTIVE until 18:00` go · `LAPSED — revalidate` stop · `SUSPENDED` stop · `APPROVED — not issued` caution · `CLOSED` neutral | Type, area, holder, last gas test and result, isolations verified n/m, revalidated |
| Scaffold | `GREEN TAG` go · `RED TAG — do not use` stop · `YELLOW TAG` caution · `INSPECTION OVERDUE` stop | Location, last inspected, next due, load class |
| Inspection | `SCHEDULED 18 Nov` neutral · `ACCEPTED` go · `REJECTED` stop · `HOLD POINT — not released` stop | Point, checklist, inspector, open punch items, for IWP |
| IWP | `ISSUED` go · `ON HOLD` stop · `READY 6/7` caution | Foreman, window, readiness counts, open constraints, drawings stale n |

The page is read-only in this increment. Acting from the phone (suspend a permit, run a checklist) is later work.

**Contract.** `tl_core/qr/types.py` (frozen once merged) defines `ScanCard` (the fields above, with bounds) and
`ScanCardProvider`: `record_type`, `view_word`, and `card(conn, record_id, viewer, now) -> ScanCard | None`. A module
registers its provider under the entry-point group `throughline.scan_cards`, the same pattern as readiness checks.
A provider is a pure read under the viewer's filter and answers `None` for a record the viewer cannot see. Each
provider ships with a contract test (no write, bounds, `None` for hidden).

## 4. Sign-in: required

A scan needs a signed-in person. Reasons:

1. "Hidden looks exactly like missing" is defined per viewer. Without a viewer there is nothing to filter by, and the
   lowest clearance in this system is still a signed-in person with a `read` word.
2. A label is a photograph away from anyone. An anonymous page would make every label a public bearer link to live
   site status (which areas have work at height today, which permits are suspended).
3. It costs the crew one sign-in per phone per shift: the web session cookie persists, so later scans open at once.

Flow: `/q/<anything>` without a session always answers with the sign-in page, whether or not the code exists; after
sign-in the browser returns to the same address. Nothing about a code is revealed before sign-in. Agent tokens are
refused the scan route like any route nobody allowed.

An anonymous "public status" mode (state word only, opt-in per project) is an owner question (§12), default off and
not built.

## 5. Hidden equals missing, for a scan

After sign-in, every one of these answers with **the same page**: status 404, the same bytes, the same headers:

- a code that never existed or is malformed;
- a revoked, rotated-away or expired code;
- a code whose record the viewer cannot see (class filter);
- a code whose record type the viewer lacks the view word for (never a 403: that would confirm the code is real);
- a code whose provider is not installed.

The resolver has one exit for all five (`resolve(...) -> ScanCard | None`), looks the hash up before any other work,
and the route test compares the five responses byte for byte, as five kinds of reader. Listing the codes of a record
(`GET /qr/codes?record=<key>`) first reads the record under the viewer; a hidden record gives the unknown-record
answer and never a count.

## 6. Printing labels and boards

| From | How |
|---|---|
| CLI | `tl qr label <record key> [--label TEXT] [--size tag\|card\|sheet] [--expires DATE] -o FILE` issues one code and writes one printable HTML file with the QR as inline SVG. `tl qr sheet <key> <key> … -o FILE` puts up to 24 labels on an A4 sheet (a board for an area's permits or a scaffold run) |
| Terminal | On the record screen of a supported type, action "Print label" asks for the label text and size, issues the code and writes the file to the downloads folder, printing its path |
| Web | On the scan page and the web record page, "Print label" (a form post with the CSRF token) returns the printable page; the browser prints it |

Sizes: `tag` 50 × 80 mm (scaffold tag holder, permit pouch), `card` A6 (area board), `sheet` A4. Output is HTML with
SVG; the QR is drawn by `segno` (BSD, already the optional `pack` extra of the awp module; here the optional extra
`labels` of the qr module). Without the library the command says so and issues nothing. PDF is later.

Printing is the act of issuing a code, so it is a command (`IssueScanCode`), ledgered, and needs the word `qr.issue`.
At most `qr.codes_per_record_max` (20) live codes per record.

## 7. Rotation, revocation, expiry

- **Revoke** (`RevokeScanCode`, `qr.revoke`, with a reason): the code answers as missing from then on.
- **Rotate** (`RotateScanCode`, `qr.issue`): revoke one code and issue a new one for the same record in one step;
  returns the new label. For a damaged or photographed label.
- **Expiry**: optional date at issue. An expired code answers as missing. No job is needed: expiry is checked at scan.
- A code is not revoked when its record closes: scanning the label of a closed permit should say `CLOSED`, which is
  the useful answer. A controller revokes when the label must die.
- The register of codes (`tl qr ls <record key>`, `tl qr export`) shows id, label text, who issued, when, state and
  expiry. It can never show the code.
- Scans are reads and are not ledgered. The web access log records `/q/…` with the code removed.

## 8. Offline at the workface

A QR needs the server. This increment is honest about that rather than half-solving it:

- With no signal the page does not load; the phone shows its own error. The crew falls back to the paper that already
  rules the site: the physical scaffold tag, the signed permit copy in its pouch, the IWP pack.
- The page is small and script-free so it loads on a weak signal. It is sent `no-store`, so a phone never shows an
  old status as if it were current.
- A site trailer with the terminal on a replica (the embedded client) can resolve a typed code locally:
  `tl qr resolve <code>` prints the card with "as of last sync <time>". That is the offline path until Phase 3 sync
  and the Phase 5 mobile work, where a site server on the site network becomes the `api.public_base_url`.
- Labels never print state (§2), so a label is never wrong, only silent.

## 9. `api.public_base_url`

A new platform setting (scope platform only, not lockable below): the public address of this deployment's web
client, `https://host[:port]`, no path, query or credentials; `http://localhost` and `http://127.0.0.1` are accepted
in dev only. It was planned in Phase 2 (risk T-11) and dropped from P2-I5; it is added here.

- Unset: `IssueScanCode` is refused with a fixed message naming the setting, and no label can be printed. Resolving
  existing codes is unaffected. (`09-phase3-plan.md` §0.1: "guest links and QR deep links are refused until set".)
- The web client must be on (`TL_WEB`); `tl qr label` warns when it is not.
- Changing the address orphans every printed label. The runbook says: keep the old host redirecting to the new one,
  or reprint. The setting change is a ledgered event like any other.
- The IWP pack's existing QR codes (the record key as text) are not changed by this increment.

## 10. Where it lives

| Piece | Path |
|---|---|
| Contract (`ScanCard`, `ScanCardProvider`, bounds, entry-point group) | `packages/tl-core/src/tl_core/qr/types.py`, registry `tl_core/qr/registry.py` |
| Module `qr`: record `qr.ScanCode`, events `ScanCode.Issued`, `ScanCode.Revoked`, commands, resolver, views, label renderer, CLI, JSON routes (through the hooks) | `packages/tl-modules/qr/` (`tl_mod_qr`), `schema/modules/qr/` |
| Scan page `/q` and `/q/{code}`, print form | `packages/tl-web/src/tl_web/pages/scan.py`, `templates/scan.html` |
| Cards | In each owning module: `tl_mod_awp/scan_card.py`, `tl_mod_scaffold/scan_card.py`, `tl_mod_quality/scan_card.py`, `tl_mod_permits/scan_card.py` |

`qr.ScanCode` fields: `code_hash` (unique), `target_id`, `target_type`, `label_text`, `size`, `issued_by`,
`issued_at`, `expires_on`, `revoked_at`, `revoked_by`, `revoke_reason`, `replaced_by_id`. No workflow; `Live`,
`Revoked` and `Expired` are derived. Offline class `none`. A scan code is hidden through its target (one part in the
subject rule of `tl_core/confidentiality.py`), so its events and register rows vanish with the record.
Access words: `qr.view` → read, `qr.issue` → user, `qr.revoke` → controller. No agent tool issues, revokes or
resolves; `list_scan_codes` is not built.

## 11. Threat model, in short

| Threat | Answer |
|---|---|
| Guessing codes | 80 random bits; lookups rate-limited per session and per address; every miss looks like every other miss |
| A photographed or stolen label | Useless without a sign-in and without access to the record; revoke or rotate kills it |
| Learning that a hidden record exists | One 404 for unknown, revoked, expired, hidden and no-word (§5); sign-in page before any lookup (§4) |
| Label text leaking a restricted record | No key or text printed above the lowest class (§2) |
| Code leaking through logs, referrers, caches, history | Code removed from access logs; `Referrer-Policy: no-referrer`; `Cache-Control: no-store`; no third-party resources on the page |
| A code stolen from the database or a backup | Only hashes are stored |
| A forged label pointing at another site (phishing for sign-ins) | Labels use only `api.public_base_url`; the sign-in page is the same hardened page as the web client (origin check, rate limit); the runbook tells crews to check the address |
| A swapped label (the permit label moved to another job) | The card shows key, title, area and holder so a mismatch is visible; a label is a pointer, never the authority |
| Stale status mistaken for live | "As of" time on every card; `no-store`; no state on paper |
| Agents harvesting status | The scan route and code register are closed to agent tokens |
| Unbounded card content | `ScanCard` bounds (8 lines, lengths) enforced by the contract; a provider past them fails closed to the 404 |

## 12. Owner questions (the build proceeds on the default)

| # | Question | Default |
|---|---|---|
| 1 | Sign-in required for every scan? | Yes (§4) |
| 2 | Allow an anonymous "public status" (state word only) per project, e.g. for scaffold tags read by crews without accounts? | No, not built; revisit with subcontractor parties in Phase 3 |
| 3 | Print the record key and a short text on labels? | Yes at the lowest class; QR and typed code only above it |
| 4 | Do codes die when the record closes? | No; they show the closed state until someone revokes |
| 5 | Who may print, who may revoke? | Print: any `user` who can see the record. Revoke: a controller |
| 6 | Where does QR live: a core service or a module? | A small module `qr` with the card contract in core (ADR-0030) |
