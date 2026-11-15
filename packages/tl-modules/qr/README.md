# tl-mod-qr

Scan codes for the work face (ADR-0030, `docs/build-spec/specs/qr-workface.md`). A printed QR holds an opaque
code; the server keeps only its SHA-256 hash in a ledgered `qr.ScanCode` record (table `cur_qr_scan_code`) that
names the record it opens. A scan shows a status card the target record's own module supplies through the
contract in `tl_core.qr`.

This piece (P2-QR S1) holds the schema, the projector and the names. Issue and revoke commands come later.
Label rendering needs the optional extra `labels` (`segno`).
