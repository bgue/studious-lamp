# Module spec: qr

Status: as built for P2-QR (S1 to S3, T02, T03, T04, T06, T07 and the T11 demo; T05 not built). Written by: P2-QR-T12 implementer.
Decisions: ADR-0030 (accepted, 2026-11-15). Spec: `docs/build-spec/specs/qr-workface.md`. Brief sections: §7.5, §19.1,
§22.9, §9 M3. Builds on ADR-0009 (accounts and sessions), ADR-0010 (module records), ADR-0016 (confidentiality).

## Purpose
A person who can see a record prints a label for it. A phone camera reads the label and opens a short, read-only status
page for the record as of now. A lost or copied label is revoked or rotated without touching the record. A scan tells
no one more than the same person would get by opening the record. The page is in the web client under `/web/q`.

## Record types
| Type | Table | Purpose | Workflow |
|---|---|---|---|
| `qr.ScanCode` | `cur_qr_scan_code` (view `v_qr_scan_code`) | One issued code: the hash of the code, the record it opens, its label text, size, expiry, state | none (state from events `ScanCode.Issued`, `ScanCode.Revoked`) |

The table is generated (`schema/modules/qr/`). It holds the SHA-256 of the code, never the code. Offline class `none`.

## Commands
| Command | Access word | Effect |
|---|---|---|
| `IssueScanCode` (`tl qr label`) | `qr.issue` | Issues one code; the code is shown once, in the label file |
| `RotateScanCode` (`tl qr rotate`) | `qr.issue` | Revokes one code and issues its replacement in one step |
| `RevokeScanCode` (`tl qr revoke`) | `qr.revoke` | Revokes; the code answers as missing from then on |

Reads (`tl qr ls`, `tl qr export`, `tl qr resolve`, and the three API routes) need `qr.view` and the target type's view word.
Scans are reads and are not ledgered.

## Targets built
| Record type | Card provider (entry point) | View word |
|---|---|---|
| `awp.IWP` | `awp_iwp` | `awp.view` |
| `quality.Inspection` | `quality_inspection` | `quality.view` |
| `permits.Permit` | `permits_permit` | `permits.view` |

The scaffold card waits for the scaffold module on trunk (T05, not built).

## Rules
- A QR holds `<api.public_base_url>/web/q/<code>` and nothing else. The code is 16 characters of a 32-symbol alphabet
  (capital letters without I and O, and the digits 2-9;
  80 random bits). It is opaque: it holds no record data and no id.
- A scan needs a signed-in person. Agent tokens are refused.
- One answer for every miss: unknown, malformed, revoked, expired, hidden record, missing view word and missing provider
  all return the same 404 page, byte for byte. A missing view word is never a 403 on this route.
- Labels never print state. A label prints the key and text only for a record at the lowest class.
- Codes are revocable and rotatable and may expire. A record reaching a final state does not revoke its codes.
- `qr.codes_per_record_max` (default 20) caps the live codes of one record.
- Issuing is refused while `api.public_base_url` is empty (see the runbook).

## Settings
`api.public_base_url` (platform only) and `qr.codes_per_record_max` (platform, company, project; lockable). Keys and
bounds: [`docs/reference/qr.md`](../../reference/qr.md#settings).

## Pages and routes
Routes, verbs and the scan page's behaviour: [`docs/reference/qr.md`](../../reference/qr.md). Operator steps and the
refusal table: [`docs/runbooks/qr-labels.md`](../../runbooks/qr-labels.md). Words: [`docs/reference/access-words.md`](../../reference/access-words.md).

## Not built
Listed once. The reasons are in the spec and ADR-0030.
- The scaffold card (T05): waits for the scaffold module on trunk.
- Client methods, the terminal print action, the web print form.
- `tl qr sheet` (A4 boards) and PDF labels. Only the `tag` size is built.
- Anonymous scans (a public status mode is an owner question, §12 of the spec).
- Offline resolution at the workface (ADR-0030, decision 10).

The follow-up slice is not yet listed in `docs/build-spec/DEFERRED.md`.

## Demo
`dev/demos/P2-QR.sh` (demo `P2-QR`): eight clauses on SQLite. Clause 7 on Postgres failed on the build host (see the
runbook, "Known state").
