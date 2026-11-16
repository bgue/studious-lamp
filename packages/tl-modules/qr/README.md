# tl-mod-qr

Scan codes for the work face (ADR-0030, `docs/build-spec/specs/qr-workface.md`). A printed QR holds one opaque
code and the address `<api.public_base_url>/web/q/<code>`, and nothing else. The server keeps only the SHA-256 hash
of the code, in a ledgered `qr.ScanCode` record (table `cur_qr_scan_code`) that names the record it opens. A scan
shows a status card that the target record's own module supplies through the contract in `tl_core.qr`.

As built. Operator steps: [`docs/runbooks/qr-labels.md`](../../../docs/runbooks/qr-labels.md). Reference (verbs,
routes, settings, card fields): [`docs/reference/qr.md`](../../../docs/reference/qr.md). Module page:
[`docs/modules/qr/README.md`](../../../docs/modules/qr/README.md).

## Access words

| Word | Table word | Used by |
|---|---|---|
| `qr.view` | `read` | `ls`, `export`, `resolve`, and the three API routes. The viewer also needs the view word of the target's type. |
| `qr.issue` | `user` | `label` (issues a code), `rotate` (revoke plus issue) |
| `qr.revoke` | `controller` | `revoke` |

`qr.read` is not an access word. It is the route guard of the API routes (`routes.py`, `READ_ACTION`) and no agent
list names it, so agent tokens are refused the routes. The scan page refuses agents too (401 from the authentication
middleware, before any guard).

## Surfaces

| Surface | Verb or route |
|---|---|
| CLI (`tl qr`, `cli.py`) | `label`, `rotate`, `revoke`, `ls`, `export`, `resolve` |
| API (`routes.py`) | `GET /qr/codes`, `GET /qr/codes/export`, `GET /qr/resolve/{code}` |
| Commands (`commands.py`, `module.py` `COMMANDS`) | `IssueScanCode`, `RevokeScanCode`, `RotateScanCode` |
| Web (`packages/tl-web`, `pages/scan.py`) | `GET /web/q`, `POST /web/q`, `GET /web/q/{code}` |
| MCP (`tools.py`) | none, by design: a code is a bearer path a person prints |

The CLI and the API call the same functions. The command handlers call `service.issue`, `service.revoke` and
`service.rotate`; the generic command handler drops the code that `issue` and `rotate` return.

## Code map

- `service.py`: `issue` and `rotate` return `IssuedCode(code, result)`, so the secret leaves once. `revoke` returns the
  `CommandResult`. Writes are events `ScanCode.Issued` and `ScanCode.Revoked`.
- `resolve.py`: `resolve(conn, code, viewer, now) -> ScanCard | None`. One exit for every miss. Its first statement is
  the hash lookup. It never writes.
- `labels.py`: `label_fields(conn, target_id, viewer)` gives the key and the text a label may print. Above the lowest
  class both are `None`. Also `render_label`, `make_svg`, `LABEL_SIZES` (only `tag` is built), `NO_QR_NOTE`.
- `views.py`: `CodeRow`, `codes_for_record`, `export_rows`. A row never holds a code or its hash.
- `codes.py`: re-exports `tl_core.qr.codes`. This package defines no code function.
- `names.py`, `projectors/`: the record, table and view names; the projector for the two events.

Label rendering needs the optional extra `labels` (`segno`). Without it, a label is written with `NO_QR_NOTE` and no
QR is drawn, and the command says so.

## Tests

- This package: `packages/tl-modules/qr/tests/` (codes, commands, label fields, labels, module spec, projector,
  resolve, views).
- Contract: `packages/tl-core/tests/test_qr_contract.py`.
- Cross-package: `packages/tl-api/tests/test_api_qr.py`, `packages/tl-cli/tests/test_cli_qr.py`,
  `packages/tl-web/tests/test_scan_page.py`, `packages/tl-web/tests/test_scan_limit.py`, and the walks in
  `packages/tl-api/tests/test_confidentiality_walk.py` and `packages/tl-mcp/tests/test_confidentiality_walk.py`.

## Not built

The scaffold card (waits for the scaffold module on trunk), client methods, the terminal print action, the web print
form, `tl qr sheet`, PDF labels, anonymous scans (ADR-0030, decision 2), a TUI view. Each is listed once in the module
page (`docs/modules/qr/README.md`).
