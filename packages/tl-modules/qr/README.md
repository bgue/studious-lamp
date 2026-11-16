# tl-mod-qr

Scan codes for the work face (ADR-0030, `docs/build-spec/specs/qr-workface.md`). A printed QR holds an opaque
code; the server keeps only its SHA-256 hash in a ledgered `qr.ScanCode` record (table `cur_qr_scan_code`) that
names the record it opens. A scan shows a status card the target record's own module supplies through the
contract in `tl_core.qr`.

P2-QR S1 holds the schema, the projector and the names. P2-QR S2 adds:

- `commands.py` / `handlers/` / `module.py` (`COMMANDS`): `IssueScanCode`, `RevokeScanCode`, `RotateScanCode`.
- `service.py`: `issue` and `rotate` return `IssuedCode(code, result)`: the secret code leaves here once. The command
  handlers call the same functions and drop the code.
- `resolve.py`: `resolve(conn, code, viewer, now)` gives a card or `None` (one exit for every miss).
- `labels.py`: `label_fields(conn, target_id, viewer)` gives the key and text a label may print.
- `codes.py`: the code functions are those of `tl_core.qr.codes`; `errors.py`; stubs `routes.py`, `tools.py`, `cli.py`
  (hooks), `views.py` (T01 fills it).
Label rendering needs the optional extra `labels` (`segno`).
