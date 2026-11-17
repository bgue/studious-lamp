# Reference: QR codes at the workface

Purpose: the verbs, routes, settings, status-card contract and words of the QR work face, as built (P2-QR,
ADR-0030). Operator steps are in [`docs/runbooks/qr-labels.md`](../runbooks/qr-labels.md); the module is described in
[`docs/modules/qr/README.md`](../modules/qr/README.md). Access words: [`access-words.md`](access-words.md).

## Words

| Word | Table word | Gives |
|---|---|---|
| `qr.view` | `read` | list, export and resolve codes (the viewer also needs the target type's view word, for example `awp.view`) |
| `qr.issue` | `user` | `label`, `rotate` |
| `qr.revoke` | `controller` | `revoke` |

`qr.read` is the route guard of the API routes. It is not an access word and no agent list names it.

## CLI: `tl qr`

All verbs take `--project P` (the project of the record). `--actor` defaults to the signed-in user.

| Verb | Arguments and options | Output |
|---|---|---|
| `label` | `KEY` (record key), `-o FILE` (required), `--label TEXT` (at most 40 characters), `--size tag`, `--expires YYYY-MM-DD`, `--force` | `label <id>  file <path>`. Issues one code; the code appears only in the file. |
| `rotate` | `CODE_ID` (register id from `ls`), `--reason TEXT` (required), `-o FILE` (required), `--force` | `rotated <new id>  file <path>` |
| `revoke` | `CODE_ID`, `--reason TEXT` (required) | `revoked <id>` |
| `ls` | `KEY` | `scan codes: <n>`, then one line per code (id, label, size, state, issued by and at, expires). Never a code. |
| `export` | `KEY`, `--format csv\|jsonl` (required) | The rows `ls` shows; it also carries `revoked_at` and `replaced_by_id`. Never a code or a hash. |
| `resolve` | code on standard input | The banner, key, title, lines and `as of <time>`; or `no such code` and exit 1 |

There is no `tl qr issue` verb. A new code is issued by `label`; a replacement by `rotate`.

Size: only `tag` (50 × 80 mm) is built. `card` and `sheet` are refused with the text
`label size card is not available yet` (or `sheet`).

## API routes

| Method and path | Access | Answer |
|---|---|---|
| `GET /qr/codes?project=&record=` | `qr.read` guard, `qr.view` | JSON list of codes of one record, newest first, at most 100 |
| `GET /qr/codes/export?project=&record=&format=csv\|jsonl` | as above | `text/csv` or `application/x-ndjson` |
| `GET /qr/resolve/{code}` | `qr.read` guard | the card as JSON, or 404 `no such code` |

A record the viewer may not see answers the same 404 as a missing one; no count is given. Agent tokens are refused
(403 on `/qr/codes` and `/qr/resolve`).

## Scan page (`tl-web`)

| Method and path | Behaviour |
|---|---|
| `GET /web/q` | Form for a typed code. |
| `POST /web/q` | Form field `code`; needs its own origin; 303 to `/web/q/<normalised code>`; a malformed code is a miss. |
| `GET /web/q/{code}` | The status card, or the one miss page. |

- Signed out: `/web/q/<anything>` answers the sign-in page (303 to `/web/sign-in`, with `next=` carrying the scan
  address). The return address is accepted only when it matches `^/web/q/[A-Z0-9]{16}$`.
- One miss page for a malformed, unknown, revoked, expired, hidden, no-view-word or no-provider code: status 404, the
  same bytes and headers for every reader.
- Limits: 10 misses per session and 30 per address in 600 seconds. Once either limit is reached, every
  lookup from that session or address, hits too, gets 429 with `Retry-After` and the text
  `Too many lookups. Wait a few minutes and try again.`. A hit adds nothing to the counts.
- Headers on code pages: `Cache-Control: no-store` and `Referrer-Policy: no-referrer`. The form page and the sign-in
  page with `next=` use `strict-origin`, so the origin check of the form works.
- Access log: the code is replaced by `<redacted>` in `/web/q/` paths (`tl_api.main.redact_code_paths`, installed by
  `install_access_log_filter`).

## Settings

| Key | Type, default | Scope | Meaning |
|---|---|---|---|
| `api.public_base_url` | string, `""` | platform only | The public address of the web client: `https://host[:port]`, or `http://localhost` / `http://127.0.0.1` for a trial. No path, no trailing slash. Printing is refused while it is empty. Changing it orphans printed labels. |
| `qr.codes_per_record_max` | int, `20` (1 to 100) | platform, company, project; lockable | Live codes one record may have. Issuing above it is refused: revoke one first. |

`api.public_base_url` is not settable with `tl config set` at any layer. How a deployment supplies its value is an
open question (see the runbook).

Environment for the client address behind a proxy: `TL_TRUSTED_PROXY_HEADER` (see the runbook).

## Status-card contract

`tl_core.qr.types` (frozen once merged). A provider is a pure read under the viewer's filter.

`ScanCard` fields (extra fields refused):

| Field | Type | Bound |
|---|---|---|
| `record_type` | string | the provider's record type |
| `key` | string | the record key |
| `title` | string | at most 120 characters |
| `banner` | string | at most 40 characters |
| `tone` | `go`, `caution`, `stop` or `neutral` | fixed set |
| `as_of` | timezone-aware datetime | required |
| `valid_until` | datetime or none | optional |
| `lines` | list of `label` (at most 24) and `value` (at most 80) | at most 8 lines |
| `open_path` | string or none | starts with `/web/`; no `//`, no `..` |

`ScanCardProvider` (protocol): `record_type`, `view_word`, and
`card(conn, record_id, viewer, now) -> ScanCard | None`. It answers `None` for a record the viewer cannot see, never
writes, never raises for a bad record, and never opens the network.

### Built cards

| Entry point name | Provider | Record type | View word |
|---|---|---|---|
| `awp_iwp` | `tl_mod_awp.scan_card:provider` | `awp.IWP` | `awp.view` |
| `quality_inspection` | `tl_mod_quality.scan_card:provider` | `quality.Inspection` | `quality.view` |
| `permits_permit` | `tl_mod_permits.scan_card:provider` | `permits.Permit` | `permits.view` |

The scaffold card is not built (it waits for the scaffold module on trunk).

### How a module adds a card

1. Write a provider class with `record_type`, `view_word` and `card(...)` that follows the rules above.
2. Expose a zero-argument callable (`provider()`) that returns it, in `scan_card.py` of the module.
3. Name it in the module's `pyproject.toml` under the entry-point group `throughline.scan_cards`, for example:

```toml
[project.entry-points."throughline.scan_cards"]
awp_iwp = "tl_mod_awp.scan_card:provider"
```

4. Add a contract test that checks: no write, the bounds, `None` for a hidden record, and `None` for a missing record.
   The qr module never imports the module that ships a provider.

The registry holds at most 32 providers (`MAX_PROVIDERS`). A duplicate provider is refused, and so is a load failure.
